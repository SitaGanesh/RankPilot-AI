from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from audits.batch import run_batch
from audits.batch_agents import (
    REQUIRED_BATCH_AGENTS,
    make_finding_key,
    run_agents_for_page,
)
from audits.models import AuditBatch, BatchAgentRun, BatchTarget
from collector.evidence import PageEvidence
from core.errors import NonHTMLResponseError


SEED_URLS = [
    "https://tutors.tychr.com/ib-tutor/cities/singapore",
    "https://tutors.tychr.com/ib-tutor/cities/toronto",
    "https://tutors.tychr.com/ib-tutor/cities/seattle",
    "https://tutors.tychr.com/ib-tutor/cities/san-diego",
    "https://tutors.tychr.com/ib-tutor/cities/vancouver",
    "https://tutors.tychr.com/ib-tutor/cities/london",
    "https://tutors.tychr.com/ib-tutor/cities/zurich",
    "https://tutors.tychr.com/ib-tutor/countries/basel",
    "https://tutors.tychr.com/ib-tutor/cities/lausanne",
    "https://tutors.tychr.com/ib-tutor/cities/geneva",
    "https://tutors.tychr.com/ib-tutor/cities/ontario",
    "https://tutors.tychr.com/ib-tutor/cities/boston",
    "https://tutors.tychr.com/ib-tutor/cities/kowloon",
    "https://tutors.tychr.com/ib-tutor/cities/hong-kong",
    "https://tutors.tychr.com/ib-tutor/cities/san-francisco",
    "https://tutors.tychr.com/ib-tutor/cities/dallas",
    "https://tutors.tychr.com/ib-tutor/cities/houston",
    "https://tutors.tychr.com/ib-tutor/cities/chicago",
    "https://tutors.tychr.com/ib-tutor/cities/new-york-city",
    "https://tutors.tychr.com/ib-tutor/cities/brooklyn",
    "https://tutors.tychr.com/ib-tutor/cities/washington",
    "https://tutors.tychr.com/ib-tutor/cities/berkshire",
    "https://tutors.tychr.com/ib-tutor/cities/sussex",
    "https://tutors.tychr.com/ib-tutor/cities/melbourne",
    "https://tutors.tychr.com/ib-tutor/cities/western-australia",
]


def evidence(url, error=None):
    return PageEvidence(
        requested_url=url,
        normalized_url=url,
        final_url=url if error is None else None,
        status=200 if error is None else None,
        parsed_title="IB tutoring",
        visible_text_preview="IB tutoring in the city for students and parents.",
        raw_html_size=100 if error is None else 0,
        collection_errors=[error] if error else [],
        links=[
            {"href": f"{url}/contact", "text": "Contact", "internal": True},
            {"href": "https://outside.example/x", "text": "External", "internal": False},
        ],
        images=[{"src": f"{url}/hero.jpg", "alt": "Hero"}],
    )


class BatchPhase4Tests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_finding_key_is_stable_and_subject_is_normalized(self):
        first = make_finding_key(
            batch_url_id="42", agent_id="onpage", rule_id="title", subject="  Title  "
        )
        second = make_finding_key(
            batch_url_id="42", agent_id="onpage", rule_id="title", subject="title"
        )
        self.assertEqual(first, second)
        self.assertNotEqual(
            first,
            make_finding_key(
                batch_url_id="43", agent_id="onpage", rule_id="title", subject="title"
            ),
        )

    def test_all_required_agents_run_independently_and_persist_results(self):
        batch = AuditBatch.objects.create(idempotency_key="agent-runs")
        target = BatchTarget.objects.create(
            batch=batch,
            position=0,
            submitted_url=SEED_URLS[0],
            normalized_url=SEED_URLS[0],
        )

        results = run_agents_for_page(target, evidence(SEED_URLS[0]))

        self.assertEqual(set(results), set(REQUIRED_BATCH_AGENTS))
        self.assertEqual(
            set(target.agent_runs.values_list("agent_id", flat=True)),
            set(REQUIRED_BATCH_AGENTS),
        )
        self.assertEqual(target.analysis_status, BatchTarget.AnalysisStatus.PARTIAL)
        self.assertFalse(
            target.agent_runs.filter(status=BatchAgentRun.Status.FAILED).exists()
        )
        self.assertTrue(
            BatchAgentRun.objects.filter(
                target=target, finding_keys__isnull=False
            ).exists()
        )

    @patch("audits.views.threading.Thread")
    def test_creates_exactly_25_targets_and_is_idempotent(self, thread):
        response = self.client.post(
            "/api/batches/",
            {"urls": SEED_URLS, "idempotency_key": "phase4-seeds"},
            format="json",
        )
        self.assertEqual(response.status_code, 202)
        batch_id = response.json()["id"]
        self.assertEqual(AuditBatch.objects.get(pk=batch_id).targets.count(), 25)
        repeat = self.client.post(
            "/api/batches/",
            {"urls": list(reversed(SEED_URLS)), "idempotency_key": "phase4-seeds"},
            format="json",
        )
        self.assertEqual(repeat.status_code, 200)
        self.assertEqual(repeat.json()["id"], batch_id)
        thread.assert_called_once()

    def test_rejects_duplicate_normalized_urls_and_ssrf(self):
        duplicate = self.client.post(
            "/api/batches/",
            {"urls": [SEED_URLS[0], SEED_URLS[0] + "/"], "idempotency_key": "duplicate"},
            format="json",
        )
        self.assertEqual(duplicate.status_code, 400)
        unsafe = self.client.post(
            "/api/batches/",
            {"urls": ["http://127.0.0.1/"], "idempotency_key": "unsafe"},
            format="json",
        )
        self.assertEqual(unsafe.status_code, 400)

    @patch("audits.batch.collect_evidence")
    def test_run_persists_success_failure_media_evidence_and_counts(self, collect):
        batch = AuditBatch.objects.create(idempotency_key="run")
        BatchTarget.objects.create(batch=batch, position=0, submitted_url=SEED_URLS[0], normalized_url=SEED_URLS[0])
        BatchTarget.objects.create(batch=batch, position=1, submitted_url=SEED_URLS[1], normalized_url=SEED_URLS[1])
        collect.side_effect = [evidence(SEED_URLS[0]), evidence(SEED_URLS[1], "Timed out")]

        run_batch(batch.id)

        batch.refresh_from_db()
        self.assertEqual(batch.status, AuditBatch.Status.PARTIAL)
        self.assertEqual(batch.completed_count, 1)
        self.assertEqual(batch.failed_count, 1)
        first = batch.targets.get(position=0)
        self.assertEqual(first.image_count, 1)
        self.assertEqual(first.internal_link_count, 1)
        self.assertEqual(first.external_link_count, 1)

    @patch("audits.batch.collect_evidence")
    def test_optional_internal_discovery_is_bounded(self, collect):
        batch = AuditBatch.objects.create(idempotency_key="discover", allow_internal_discovery=True)
        BatchTarget.objects.create(batch=batch, position=0, submitted_url=SEED_URLS[0], normalized_url=SEED_URLS[0])
        collect.side_effect = lambda url: evidence(url)

        run_batch(batch.id)

        self.assertTrue(batch.targets.filter(normalized_url=f"{SEED_URLS[0]}/contact").exists())
        self.assertFalse(batch.targets.filter(normalized_url__contains="outside.example").exists())

    @patch("audits.batch.collect_evidence")
    def test_resume_recovers_interrupted_running_target(self, collect):
        batch = AuditBatch.objects.create(idempotency_key="resume")
        target = BatchTarget.objects.create(
            batch=batch, position=0, submitted_url=SEED_URLS[0], normalized_url=SEED_URLS[0],
            status=BatchTarget.Status.RUNNING,
        )
        collect.return_value = evidence(SEED_URLS[0])

        from audits.batch import resume_batch
        resume_batch(batch.id)

        target.refresh_from_db()
        self.assertEqual(target.status, BatchTarget.Status.COMPLETED)
        self.assertEqual(target.attempts, 1)

    @patch("audits.batch.collect_evidence")
    def test_retry_only_reprocesses_failed_targets(self, collect):
        batch = AuditBatch.objects.create(idempotency_key="retry")
        BatchTarget.objects.create(
            batch=batch, position=0, submitted_url=SEED_URLS[0], normalized_url=SEED_URLS[0],
            status=BatchTarget.Status.FAILED, error="timeout",
        )
        collect.return_value = evidence(SEED_URLS[0])

        from audits.batch import retry_batch
        retry_batch(batch.id)

        target = batch.targets.get()
        self.assertEqual(target.status, BatchTarget.Status.COMPLETED)
        self.assertEqual(target.attempts, 1)

    @patch("collector.evidence.fetch_page")
    def test_non_html_evidence_preserves_final_url_and_content_type(self, fetch):
        fetch.side_effect = NonHTMLResponseError(
            "Response Content-Type is not HTML",
            200,
            "https://example.com/image.jpg",
            "image/jpeg",
        )
        from collector.evidence import collect_evidence

        with patch("collector.evidence.validate_url", return_value="https://example.com/image.jpg"):
            result = collect_evidence("https://example.com/image.jpg")

        self.assertEqual(result.final_url, "https://example.com/image.jpg")
        self.assertEqual(result.status, 200)
        self.assertEqual(result.headers["content-type"], "image/jpeg")

    def test_cancel_marks_pending_targets_skipped(self):
        batch = AuditBatch.objects.create(idempotency_key="cancel")
        BatchTarget.objects.create(
            batch=batch, position=0, submitted_url=SEED_URLS[0], normalized_url=SEED_URLS[0]
        )

        response = self.client.post(f"/api/batches/{batch.id}/cancel/")

        self.assertEqual(response.status_code, 200)
        batch.refresh_from_db()
        self.assertEqual(batch.status, AuditBatch.Status.CANCELLED)
        self.assertEqual(batch.targets.get().status, BatchTarget.Status.SKIPPED)
