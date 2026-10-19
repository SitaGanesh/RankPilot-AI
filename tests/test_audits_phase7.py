from datetime import datetime, timezone
from unittest.mock import Mock, patch

from django.test import TestCase
from rest_framework.test import APIClient

from audits.models import AgentRun, Audit, AuditReport, EvidenceSnapshot, StageEvent
from collector.evidence import PageEvidence
from core.errors import FetchError
from pipeline.final_audit import deterministic_fallback
from pipeline.coordinator import run_agent, run_collection


class AuditApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_html_routes_load_expected_frontend_hooks(self):
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertContains(home, 'id="audit-form"')
        self.assertContains(home, "audits/app.js")
        self.assertContains(home, "audits/app.css")

        audit = Audit.objects.create(
            url="https://example.com/",
            normalized_url="https://example.com/",
        )
        detail = self.client.get(f"/audits/{audit.id}/")
        self.assertEqual(detail.status_code, 200)
        self.assertContains(detail, f'data-audit-id="{audit.id}"')
        self.assertContains(detail, 'id="stepper"')
        self.assertContains(detail, 'id="download-report"')

    def test_registered_agents_endpoint(self):
        response = self.client.get("/api/agents/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual({agent["id"] for agent in response.json()}, {"onpage", "technical"})

    def test_invalid_url_is_rejected_before_background_collection(self):
        response = self.client.post("/api/audits/", {"url": "ftp://example.com/"}, format="json")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Audit.objects.count(), 0)

    @patch("audits.views.threading.Thread")
    def test_unsafe_urls_are_rejected_without_starting_collection(self, thread_class):
        for url in (
            "not-a-url",
            "http://user:password@example.com/",
            "http://localhost/",
            "http://127.0.0.1/",
            "http://169.254.169.254/latest/meta-data/",
        ):
            with self.subTest(url=url):
                response = self.client.post("/api/audits/", {"url": url}, format="json")
                self.assertEqual(response.status_code, 400)
                self.assertIn("error", response.json())

        thread_class.assert_not_called()
        self.assertEqual(Audit.objects.count(), 0)

    @patch("audits.views.threading.Thread")
    def test_valid_url_is_validated_before_collection_thread_starts(self, thread_class):
        thread_class.return_value.start = Mock()

        response = self.client.post("/api/audits/", {"url": "https://example.com/"}, format="json")

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], Audit.Status.PENDING)
        self.assertEqual(Audit.objects.count(), 1)
        thread_class.assert_called_once()
        self.assertIs(thread_class.call_args.kwargs["daemon"], True)

    def test_missing_audit_returns_json_not_found(self):
        response = self.client.get("/api/audits/00000000-0000-0000-0000-000000000000/")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "Audit not found."})

    def test_malformed_audit_id_returns_json_not_found(self):
        response = self.client.get("/api/audits/not-a-uuid/")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "Audit ID must be a valid UUID."})

    def test_status_endpoint_returns_ordered_stage_events(self):
        audit = Audit.objects.create(url="https://example.com/", normalized_url="https://example.com/")
        StageEvent.objects.create(audit=audit, stage="collector", status="running", message="Fetching page")
        StageEvent.objects.create(audit=audit, stage="collector", status="done", message="Page collected")

        response = self.client.get(f"/api/audits/{audit.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([event["status"] for event in response.json()["stage_events"]], ["running", "done"])

    def test_evidence_and_agent_run_persist_json_and_restore_in_order(self):
        audit = Audit.objects.create(
            url="https://example.com/",
            normalized_url="https://example.com/",
        )
        first = EvidenceSnapshot.objects.create(
            audit=audit,
            json={"requested_url": audit.url, "status": 200},
        )
        second = EvidenceSnapshot.objects.create(
            audit=audit,
            json={"requested_url": audit.url, "status": 404},
        )
        now = datetime.now(timezone.utc)
        run = AgentRun.objects.create(
            audit=audit,
            agent_id="onpage",
            rule_version="onpage-1.0.0",
            status="completed",
            result_json={"findings": []},
            score_percent=75.5,
            started_at=now,
            finished_at=now,
        )

        self.assertEqual(audit.evidence_snapshots.first().pk, second.pk)
        self.assertEqual(audit.evidence_snapshots.first().json["status"], 404)
        self.assertEqual(audit.agent_runs.first().pk, run.pk)
        self.assertEqual(audit.agent_runs.first().result_json, {"findings": []})
        self.assertEqual(audit.agent_runs.first().score_percent, 75.5)
        self.assertEqual(first.audit_id, audit.id)

    def test_agent_run_requires_evidence_snapshot(self):
        audit = Audit.objects.create(
            url="https://example.com/",
            normalized_url="https://example.com/",
            status=Audit.Status.COLLECTED,
        )

        response = self.client.post(f"/api/audits/{audit.id}/agents/onpage/run/")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"error": "Collected evidence is not available."})

    def test_agent_run_rejects_unknown_agent(self):
        audit = Audit.objects.create(
            url="https://example.com/",
            normalized_url="https://example.com/",
            status=Audit.Status.COLLECTED,
        )
        EvidenceSnapshot.objects.create(audit=audit, json={"url": "https://example.com/"})

        response = self.client.post(f"/api/audits/{audit.id}/agents/unknown/run/")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "Unknown agent."})

    @patch("audits.views.threading.Thread")
    def test_agent_run_marks_audit_running_and_rejects_duplicate_start(self, thread_class):
        thread_class.return_value.start = Mock()
        audit = Audit.objects.create(
            url="https://example.com/",
            normalized_url="https://example.com/",
            status=Audit.Status.COLLECTED,
        )
        EvidenceSnapshot.objects.create(audit=audit, json={"url": "https://example.com/"})

        first = self.client.post(f"/api/audits/{audit.id}/agents/onpage/run/")
        second = self.client.post(f"/api/audits/{audit.id}/agents/onpage/run/")

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json(), {"error": "Collection is not complete."})
        audit.refresh_from_db()
        self.assertEqual(audit.status, Audit.Status.RUNNING)

    def test_report_requires_agent_id_and_returns_only_matching_audit_report(self):
        audit = Audit.objects.create(url="https://example.com/", normalized_url="https://example.com/")
        other = Audit.objects.create(url="https://other.example/", normalized_url="https://other.example/")
        AuditReport.objects.create(
            audit=other,
            agent_id="onpage",
            normalized_url=other.normalized_url,
            report_json={"audit_id": str(other.id)},
        )

        missing_agent = self.client.get(f"/api/audits/{audit.id}/report/")
        unrelated = self.client.get(f"/api/audits/{audit.id}/report/?agent_id=onpage")

        self.assertEqual(missing_agent.status_code, 400)
        self.assertEqual(missing_agent.json(), {"error": "agent_id is required."})
        self.assertEqual(unrelated.status_code, 404)
        self.assertEqual(unrelated.json(), {"error": "Report is not ready."})

    def test_report_returns_persisted_report_for_matching_audit_and_agent(self):
        audit = Audit.objects.create(
            url="https://example.com/",
            normalized_url="https://example.com/",
            status=Audit.Status.COMPLETED,
        )
        report_json = {"audit_id": str(audit.id), "score": {"percent": 100}}
        AuditReport.objects.create(
            audit=audit,
            agent_id="onpage",
            normalized_url=audit.normalized_url,
            report_json=report_json,
        )

        response = self.client.get(f"/api/audits/{audit.id}/report/?agent_id=onpage")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), report_json)

    def test_report_is_not_returned_for_unfinished_audit(self):
        audit = Audit.objects.create(
            url="https://example.com/",
            normalized_url="https://example.com/",
            status=Audit.Status.RUNNING,
        )
        AuditReport.objects.create(
            audit=audit,
            agent_id="onpage",
            normalized_url=audit.normalized_url,
            report_json={"audit_id": str(audit.id)},
        )

        response = self.client.get(f"/api/audits/{audit.id}/report/?agent_id=onpage")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json(), {"error": "Report is not ready."})

    @patch("pipeline.coordinator.SEOCoordinator")
    def test_collection_background_failure_marks_audit_failed(self, coordinator_class):
        coordinator_class.return_value.collect.side_effect = RuntimeError("collection failed")
        audit = Audit.objects.create(url="https://example.com/", normalized_url="https://example.com/")

        run_collection(audit.id)

        audit.refresh_from_db()
        self.assertEqual(audit.status, Audit.Status.FAILED)
        self.assertEqual(audit.stage_events.get().status, "failed")

    @patch("pipeline.coordinator.generate_final_audit")
    @patch("pipeline.coordinator.collect_evidence")
    def test_coordinator_success_persists_evidence_run_report_and_ordered_events(
        self,
        collect_evidence,
        generate_final_audit,
    ):
        audit = Audit.objects.create(
            url="https://example.com/",
            normalized_url="https://example.com/",
        )
        evidence = PageEvidence(
            requested_url=audit.url,
            normalized_url=audit.normalized_url,
            final_url=audit.url,
            status=200,
            parsed_title="A sufficiently descriptive title for this page",
            meta_tags={"description": ["A sufficiently long description that provides useful context for this page and exceeds seventy characters."]},
            canonical=audit.url,
            headings=[{"level": 1, "text": "Main heading"}],
            lang="en",
            viewport="width=device-width",
            visible_text_word_count=350,
        )
        collect_evidence.return_value = evidence

        def fallback(findings, score, comparison):
            return deterministic_fallback(findings, score), True

        generate_final_audit.side_effect = fallback

        run_collection(audit.id)
        audit.refresh_from_db()
        self.assertEqual(audit.status, Audit.Status.COLLECTED)
        self.assertEqual(EvidenceSnapshot.objects.filter(audit=audit).count(), 1)

        run_agent(audit.id, "onpage")

        audit.refresh_from_db()
        self.assertEqual(audit.status, Audit.Status.COMPLETED)
        self.assertEqual(AgentRun.objects.filter(audit=audit, agent_id="onpage").count(), 1)
        self.assertEqual(AuditReport.objects.filter(audit=audit, agent_id="onpage").count(), 1)
        stages = list(audit.stage_events.values_list("stage", "status"))
        self.assertEqual(stages[0], ("coordinator", "running"))
        self.assertEqual(stages[1], ("collector", "running"))
        self.assertEqual(stages[2], ("collector", "done"))
        self.assertEqual(stages[-1], ("report_builder", "done"))
        self.assertEqual(audit.current_stage, "report_builder")

    @patch("pipeline.coordinator.generate_final_audit")
    def test_technical_agent_produces_retrievable_report_after_collection(
        self,
        generate_final_audit,
    ):
        audit = Audit.objects.create(
            url="https://example.com/",
            normalized_url="https://example.com/",
            status=Audit.Status.COLLECTED,
        )
        evidence = PageEvidence(
            requested_url=audit.url,
            normalized_url=audit.normalized_url,
            final_url=audit.url,
            status=200,
            canonical=audit.url,
        )
        EvidenceSnapshot.objects.create(
            audit=audit,
            json=evidence.model_dump(mode="json"),
        )
        generate_final_audit.side_effect = lambda findings, score, comparison: (
            deterministic_fallback(findings, score),
            True,
        )

        run_agent(audit.id, "technical")

        response = self.client.get(f"/api/audits/{audit.id}/report/?agent_id=technical")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["agents"][0]["agent_id"], "technical")
        self.assertEqual(response.json()["agents"][0]["rule_version"], "technical-1.0.0")
        self.assertEqual(AgentRun.objects.filter(audit=audit, agent_id="technical").count(), 1)
        self.assertEqual(AuditReport.objects.filter(audit=audit, agent_id="technical").count(), 1)

        run_agent(audit.id, "onpage")
        onpage_response = self.client.get(f"/api/audits/{audit.id}/report/?agent_id=onpage")
        self.assertEqual(onpage_response.status_code, 200)
        self.assertEqual(onpage_response.json()["agents"][0]["agent_id"], "onpage")

    @patch("pipeline.coordinator.collect_evidence", side_effect=FetchError("blocked"))
    def test_collection_failure_persists_safe_failure_event(self, collect_evidence):
        audit = Audit.objects.create(
            url="https://example.com/",
            normalized_url="https://example.com/",
        )

        run_collection(audit.id)

        audit.refresh_from_db()
        self.assertEqual(audit.status, Audit.Status.FAILED)
        event = audit.stage_events.filter(status="failed").get()
        self.assertEqual(event.stage, "collector")
        self.assertEqual(event.status, "failed")
        self.assertEqual(event.message, "Website collection could not be completed")

    @patch("pipeline.coordinator.get_agent")
    def test_agent_failure_marks_audit_failed_without_report(self, get_agent):
        get_agent.return_value.run.side_effect = RuntimeError("agent detail")
        audit = Audit.objects.create(
            url="https://example.com/",
            normalized_url="https://example.com/",
            status=Audit.Status.COLLECTED,
        )
        EvidenceSnapshot.objects.create(
            audit=audit,
            json=PageEvidence(requested_url=audit.url).model_dump(mode="json"),
        )

        run_agent(audit.id, "onpage")

        audit.refresh_from_db()
        self.assertEqual(audit.status, Audit.Status.FAILED)
        self.assertFalse(AuditReport.objects.filter(audit=audit).exists())

    @patch("pipeline.coordinator.get_agent")
    def test_invalid_agent_result_fails_before_persisting_run(self, get_agent):
        get_agent.return_value.run.return_value = {"not": "an AgentResult"}
        audit = Audit.objects.create(
            url="https://example.com/",
            normalized_url="https://example.com/",
            status=Audit.Status.COLLECTED,
        )
        EvidenceSnapshot.objects.create(
            audit=audit,
            json=PageEvidence(requested_url=audit.url).model_dump(mode="json"),
        )

        run_agent(audit.id, "onpage")

        audit.refresh_from_db()
        self.assertEqual(audit.status, Audit.Status.FAILED)
        self.assertFalse(AgentRun.objects.filter(audit=audit).exists())

    @patch("pipeline.coordinator.SEOCoordinator")
    def test_agent_background_failure_marks_audit_failed_and_emits_event(self, coordinator_class):
        coordinator_class.return_value.run_agent.side_effect = RuntimeError("agent failed")
        audit = Audit.objects.create(
            url="https://example.com/",
            normalized_url="https://example.com/",
            status=Audit.Status.RUNNING,
        )

        run_agent(audit.id, "onpage")

        audit.refresh_from_db()
        self.assertEqual(audit.status, Audit.Status.FAILED)
        event = audit.stage_events.get()
        self.assertEqual(event.status, "failed")