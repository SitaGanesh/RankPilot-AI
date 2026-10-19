"""Registered On-Page SEO agent."""

from datetime import datetime, timezone

from collector.evidence import PageEvidence
from core.base_agent import BaseAgent
from core.contracts import AgentResult, AgentStatus, Finding, FindingSource
from core.registry import register_agent
from core.scoring import calculate_score

from .checks import ALL_CHECKS
from .checklist import CHECK_WEIGHTS, RULE_VERSION, total_weight


@register_agent
class OnPageAgent(BaseAgent):
    agent_id = "onpage"
    name = "On-Page SEO Agent"
    version = "1.0.0"
    scope = "On-page HTML, metadata, indexability, links, and content signals"
    checklist = ALL_CHECKS
    check_weights = CHECK_WEIGHTS

    def run(self, evidence: PageEvidence) -> AgentResult:
        """Run every deterministic On-Page check against shared evidence."""

        started_at = datetime.now(timezone.utc)
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
        status = AgentStatus.PARTIAL if evidence.collection_errors or unknown else AgentStatus.COMPLETED
        return AgentResult(
            agent_id=self.agent_id,
            agent_version=self.version,
            rule_version=RULE_VERSION,
            scope=self.scope,
            status=status,
            score=score,
            findings=findings,
            checks_completed=completed,
            checks_unknown=unknown,
            checks_not_applicable=not_applicable,
            errors=evidence.collection_errors,
            started_at=started_at,
            finished_at=finished_at,
        )
