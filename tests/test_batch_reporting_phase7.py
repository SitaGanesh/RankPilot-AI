import json
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from audits.batch import retry_batch
from audits.batch_agents import REQUIRED_BATCH_AGENTS
from audits.models import Audit, AuditBatch, AuditReport, BatchAgentRun, BatchTarget


class BatchReportingPhase7Tests(TestCase):
    def setUp(self):
        self.client = APIClient()
        now = timezone.now()
        self.batch = AuditBatch.objects.create(
            idempotency_key="reporting-test-batch",
            status=AuditBatch.Status.COMPLETED,
        )

        # Target 1: Singapore (Successful, score 80)
        self.target_sg = BatchTarget.objects.create(
            batch=self.batch,
            position=0,
            submitted_url="https://tutors.tychr.com/ib-tutor/cities/singapore",
            normalized_url="https://tutors.tychr.com/ib-tutor/cities/singapore",
            final_url="https://tutors.tychr.com/ib-tutor/cities/singapore",
            status=BatchTarget.Status.COMPLETED,
            analysis_status=BatchTarget.AnalysisStatus.COMPLETED,
            response_status=200,
        )
        # Create agent runs for Target 1
        BatchAgentRun.objects.create(
            target=self.target_sg,
            agent_id="onpage",
            status=BatchAgentRun.Status.COMPLETED,
            started_at=now,
            result_json={
                "score": 85,
                "findings": [
                    {
                        "check_id": "title-missing",
                        "title": "Title tag is missing or short",
                        "severity": "critical",
                        "status": "fail",
                        "recommendation": "Add a descriptive title",
                        "why_it_matters": "Search engines use title tags for indexing.",
                    }
                ],
            },
        )
        BatchAgentRun.objects.create(
            target=self.target_sg,
            agent_id="technical",
            status=BatchAgentRun.Status.COMPLETED,
            started_at=now,
            result_json={"score": 90, "findings": []},
        )
        BatchAgentRun.objects.create(
            target=self.target_sg,
            agent_id="visibility",
            status=BatchAgentRun.Status.COMPLETED,
            started_at=now,
            result_json={"score": 75, "findings": []},
        )
        BatchAgentRun.objects.create(
            target=self.target_sg,
            agent_id="ib_conversion",
            status=BatchAgentRun.Status.COMPLETED,
            started_at=now,
            result_json={
                "score": 70,
                "findings": [
                    {
                        "check_id": "cta-missing",
                        "title": "Clear Call to Action is missing",
                        "severity": "high",
                        "status": "warning",
                        "recommendation": "Add a consultation button",
                        "why_it_matters": "Increases student conversion.",
                    }
                ],
            },
        )

        # Target 2: Toronto (Successful, score 65)
        self.target_to = BatchTarget.objects.create(
            batch=self.batch,
            position=1,
            submitted_url="https://tutors.tychr.com/ib-tutor/cities/toronto",
            normalized_url="https://tutors.tychr.com/ib-tutor/cities/toronto",
            final_url="https://tutors.tychr.com/ib-tutor/cities/toronto",
            status=BatchTarget.Status.COMPLETED,
            analysis_status=BatchTarget.AnalysisStatus.COMPLETED,
            response_status=200,
        )
        BatchAgentRun.objects.create(
            target=self.target_to,
            agent_id="onpage",
            status=BatchAgentRun.Status.COMPLETED,
            started_at=now,
            result_json={
                "score": 60,
                "findings": [
                    {
                        "check_id": "title-missing",
                        "title": "Title tag is missing or short",
                        "severity": "critical",
                        "status": "fail",
                        "recommendation": "Add a descriptive title",
                        "why_it_matters": "Search engines use title tags for indexing.",
                    }
                ],
            },
        )
        BatchAgentRun.objects.create(
            target=self.target_to,
            agent_id="technical",
            status=BatchAgentRun.Status.COMPLETED,
            started_at=now,
            result_json={"score": 70, "findings": []},
        )
        BatchAgentRun.objects.create(
            target=self.target_to,
            agent_id="visibility",
            status=BatchAgentRun.Status.COMPLETED,
            started_at=now,
            result_json={"score": 65, "findings": []},
        )
        BatchAgentRun.objects.create(
            target=self.target_to,
            agent_id="ib_conversion",
            status=BatchAgentRun.Status.COMPLETED,
            started_at=now,
            result_json={"score": 65, "findings": []},
        )

        # Target 3: Failed Target
        self.target_failed = BatchTarget.objects.create(
            batch=self.batch,
            position=2,
            submitted_url="https://tutors.tychr.com/ib-tutor/cities/broken",
            normalized_url="https://tutors.tychr.com/ib-tutor/cities/broken",
            status=BatchTarget.Status.FAILED,
            analysis_status=BatchTarget.AnalysisStatus.FAILED,
            response_status=500,
            error="Server error 500",
        )

    def test_batch_collection_view_lists_recent_batches(self):
        response = self.client.get("/api/batches/")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertGreaterEqual(len(data), 1)
        batch_ids = [b["id"] for b in data]
        self.assertIn(str(self.batch.id), batch_ids)

    def test_batch_report_aggregates_summary_and_deduplicates_top_issues(self):
        response = self.client.get(f"/api/batches/{self.batch.id}/report/")
        self.assertEqual(response.status_code, 200)
        data = response.json()

        self.assertIn("summary", data)
        summary = data["summary"]
        self.assertEqual(summary["total_targets"], 3)
        self.assertEqual(summary["crawled_count"], 2)
        self.assertEqual(summary["failed_count"], 1)

        # Check overall score and agent averages
        self.assertIsNotNone(summary["overall_score"])
        self.assertEqual(summary["agent_averages"]["onpage"], 72.5)  # (85 + 60) / 2
        self.assertEqual(summary["agent_averages"]["technical"], 80.0)  # (90 + 70) / 2

        # Check top issues deduplication: "title-missing" should have affected_count = 2
        top_issues = summary["top_issues"]
        title_issue = next((issue for issue in top_issues if issue["check_id"] == "title-missing"), None)
        self.assertIsNotNone(title_issue)
        self.assertEqual(title_issue["affected_count"], 2)
        self.assertEqual(len(title_issue["affected_urls"]), 2)
        self.assertIn(self.target_sg.submitted_url, title_issue["affected_urls"])
        self.assertIn(self.target_to.submitted_url, title_issue["affected_urls"])

    def test_batch_report_filtering_by_query_and_status(self):
        # Search query matching "singapore"
        res_search = self.client.get(f"/api/batches/{self.batch.id}/report/?q=singapore")
        self.assertEqual(res_search.status_code, 200)
        targets = res_search.json()["targets"]
        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0]["submitted_url"], self.target_sg.submitted_url)

        # Status filter for failed
        res_failed = self.client.get(f"/api/batches/{self.batch.id}/report/?status=failed")
        self.assertEqual(res_failed.status_code, 200)
        targets_failed = res_failed.json()["targets"]
        self.assertEqual(len(targets_failed), 1)
        self.assertEqual(targets_failed[0]["submitted_url"], self.target_failed.submitted_url)

        # Finding filter for severity=critical
        res_crit = self.client.get(f"/api/batches/{self.batch.id}/report/?severity=critical")
        self.assertEqual(res_crit.status_code, 200)
        findings = res_crit.json()["findings"]
        self.assertTrue(all(f["severity"] == "critical" for f in findings))
        self.assertEqual(len(findings), 2)  # title-missing on both targets

    def test_batch_report_sorting(self):
        res_asc = self.client.get(f"/api/batches/{self.batch.id}/report/?sort=position")
        self.assertEqual(res_asc.status_code, 200)
        positions = [t["position"] for t in res_asc.json()["targets"]]
        self.assertEqual(positions, [0, 1, 2])

        res_desc = self.client.get(f"/api/batches/{self.batch.id}/report/?sort=-position")
        self.assertEqual(res_desc.status_code, 200)
        positions_desc = [t["position"] for t in res_desc.json()["targets"]]
        self.assertEqual(positions_desc, [2, 1, 0])

    def test_batch_report_csv_export(self):
        # Targets CSV (default)
        res_csv = self.client.get(f"/api/batches/{self.batch.id}/report/?format=csv")
        self.assertEqual(res_csv.status_code, 200)
        self.assertIn("text/csv", res_csv["Content-Type"])
        self.assertIn("attachment; filename=", res_csv["Content-Disposition"])
        content = res_csv.content.decode("utf-8")
        self.assertIn("Submitted URL", content)
        self.assertIn("singapore", content)

        # Findings CSV
        res_findings_csv = self.client.get(f"/api/batches/{self.batch.id}/report/?format=csv&type=findings")
        self.assertEqual(res_findings_csv.status_code, 200)
        findings_content = res_findings_csv.content.decode("utf-8")
        self.assertIn("Check ID", findings_content)
        self.assertIn("title-missing", findings_content)

    def test_batch_export_endpoint_targets_and_findings(self):
        # Targets CSV
        res_targets = self.client.get(f"/api/batches/{self.batch.id}/export/?type=targets&format=csv")
        self.assertEqual(res_targets.status_code, 200)
        self.assertIn("text/csv", res_targets["Content-Type"])
        content = res_targets.content.decode("utf-8")
        self.assertIn("Position", content)
        self.assertIn("singapore", content)

        # Findings JSON
        res_findings_json = self.client.get(f"/api/batches/{self.batch.id}/export/?type=findings&format=json")
        self.assertEqual(res_findings_json.status_code, 200)
        self.assertEqual(res_findings_json["Content-Type"], "application/json")
        data = res_findings_json.json()
        self.assertIn("findings", data)
        self.assertIsInstance(data["findings"], list)
        self.assertGreaterEqual(len(data["findings"]), 2)

    def test_single_audit_report_csv_export(self):
        audit = Audit.objects.create(
            url="https://tutors.tychr.com",
            status=Audit.Status.COMPLETED,
        )
        AuditReport.objects.create(
            audit=audit,
            agent_id="onpage",
            normalized_url="https://tutors.tychr.com",
            report_json={
                "agents": [
                    {
                        "agent_id": "onpage",
                        "findings": [
                            {
                                "check_id": "title-missing",
                                "title": "Title missing",
                                "severity": "critical",
                                "status": "fail",
                                "recommendation": "Add a title tag",
                                "why_it_matters": "Search engines use title tags.",
                            }
                        ],
                    }
                ]
            },
        )
        res = self.client.get(f"/api/audits/{audit.id}/report/?agent_id=onpage&format=csv")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res["Content-Type"], "text/csv; charset=utf-8")
        content = res.content.decode("utf-8")
        self.assertIn("Check ID", content)
        self.assertIn("title-missing", content)

    @patch("audits.views.threading.Thread")
    def test_batch_retry_recovers_failed_and_partial_agent_runs(self, mock_thread):
        # Create a target that crawled successfully but whose analysis is PARTIAL
        batch = AuditBatch.objects.create(
            idempotency_key="retry-test-batch",
            status=AuditBatch.Status.PARTIAL,
        )
        target = BatchTarget.objects.create(
            batch=batch,
            position=0,
            submitted_url="https://tutors.tychr.com/ib-tutor/cities/seattle",
            normalized_url="https://tutors.tychr.com/ib-tutor/cities/seattle",
            status=BatchTarget.Status.COMPLETED,
            analysis_status=BatchTarget.AnalysisStatus.PARTIAL,
        )

        res = self.client.post(f"/api/batches/{batch.id}/retry/")
        self.assertEqual(res.status_code, 202)
        mock_thread.assert_called_once()

        # Verify retry_batch resets target to RETRYABLE and analysis_status to PENDING
        with patch("audits.batch.run_batch") as mock_run_batch:
            retry_batch(batch.id)
            mock_run_batch.assert_called_once_with(batch.id)

        target.refresh_from_db()
        self.assertEqual(target.status, BatchTarget.Status.RETRYABLE)
        self.assertEqual(target.analysis_status, BatchTarget.AnalysisStatus.PENDING)
