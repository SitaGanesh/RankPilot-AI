"""Registered Website Functionality agent."""

from datetime import datetime, timezone

from collector.evidence import PageEvidence
from core.base_agent import BaseAgent
from core.contracts import AgentResult, AgentStatus, Finding, FindingSource
from core.registry import register_agent
from core.scoring import calculate_score

from .checklist import CHECK_WEIGHTS, RULE_VERSION, total_weight
from .checks import ALL_CHECKS


@register_agent
class FunctionalityAgent(BaseAgent):
    agent_id = "functionality"
    name = "Website Functionality Agent"
    version = "1.0.0"
    scope = "Navigation menus, forms & client validation, interactive controls, subresource failures, JS console errors, client hydration shells, and mobile responsive layout"
    checklist = ALL_CHECKS
    check_weights = CHECK_WEIGHTS
    supported_tasks = ("functionality_audit", "form_usability_review", "browser_runtime_review", "responsive_layout_review")
    evidence_requirements = ("fetched_html_evidence", "browser_observation", "forms_summary", "navigation_summary")

    def run(self, evidence: PageEvidence) -> AgentResult:
        """Run authentic AI-driven Website Functionality evaluation grounded in PageEvidence."""
        from core.agent_llm_evaluator import run_agent_with_ai
        from .checklist import CHECK_DEFINITIONS

        started_at = datetime.now(timezone.utc)

        def _fallback() -> AgentResult:
            results = [check(evidence) for check in self.checklist]
            findings = [
                Finding(
                    id=f"{result.check_id}:{index}",
                    check_id=result.check_id,
                    title=result.title,
                    status=result.status,
                    severity=result.severity,
                    weight=result.weight,
                    points_earned=result.points_earned,
                    evidence=result.evidence,
                    why_it_matters=result.why_it_matters,
                    recommendation=result.recommendation,
                    confidence=result.confidence,
                    source=FindingSource.DETERMINISTIC,
                )
                for index, result in enumerate(results, start=1)
            ]
            score = calculate_score(findings, total_weight=total_weight())
            finished_at = datetime.now(timezone.utc)
            unknown = [result.check_id for result in results if result.status.value == "unknown"]
            not_applicable = [result.check_id for result in results if result.status.value == "not_applicable"]
            completed = [result.check_id for result in results if result.status.value in {"pass", "warn", "fail"}]
            return AgentResult(
                agent_id=self.agent_id,
                agent_version=self.version,
                rule_version=RULE_VERSION,
                scope=self.scope,
                status=AgentStatus.PARTIAL if unknown else AgentStatus.COMPLETED,
                score=score,
                findings=findings,
                checks_completed=completed,
                checks_unknown=unknown,
                checks_not_applicable=not_applicable,
                errors=list(evidence.collection_errors),
                started_at=started_at,
                finished_at=finished_at,
            )

        return run_agent_with_ai(
            agent_id=self.agent_id,
            agent_name=self.name,
            agent_version=self.version,
            rule_version=RULE_VERSION,
            scope=self.scope,
            evidence=evidence,
            reference_rules=CHECK_DEFINITIONS,
            total_reference_weight=total_weight(),
            fallback_fn=_fallback,
        )
