"""Registered Technical SEO agent."""

from datetime import datetime, timezone

from collector.evidence import PageEvidence
from core.base_agent import BaseAgent
from core.contracts import AgentResult, AgentStatus, Finding, FindingSource
from core.registry import register_agent
from core.scoring import calculate_score

from .checklist import CHECK_WEIGHTS, RULE_VERSION, total_weight
from .checks import ALL_CHECKS


@register_agent
class TechnicalAgent(BaseAgent):
    agent_id = "technical"
    name = "Technical SEO & AI-Readability Agent"
    version = "1.0.0"
    scope = "HTTP status, redirects, canonicals, robots directives, sitemaps, structured data, machine comprehension, and AI search engine readability"
    checklist = ALL_CHECKS
    check_weights = CHECK_WEIGHTS
    supported_tasks = ("technical_audit", "indexability_review", "redirect_review", "ai_readability_review", "machine_comprehension")
    evidence_requirements = ("fetched_html_evidence", "robots_txt_observation", "sitemap_observations", "layout_summary")

    def run(self, evidence: PageEvidence) -> AgentResult:
        """Run authentic AI-driven Technical SEO evaluation grounded in PageEvidence."""
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

    @classmethod
    def investigate(cls, audit_id: str, objective: str = "Perform comprehensive technical SEO investigation"):
        """Run the full agentic technical SEO investigation using tools and iterative supervisor."""
        from agentic.supervisor import create_investigation, run_investigation
        from audits.models import Audit
        audit = Audit.objects.get(pk=audit_id)
        investigation = audit.investigations.order_by("-created_at").first()
        if investigation is None:
            investigation = create_investigation(audit, objective)
        return run_investigation(investigation.id)

    @staticmethod
    def diagnose_probable_root_cause(finding_check_id: str, evidence: PageEvidence) -> str:
        """Heuristically deduce root cause for technical SEO findings when evidence allows."""
        if "redirect" in finding_check_id:
            hops = len(evidence.redirect_chain)
            return f"Server or router redirect rule misconfiguration causing {hops} redirect hops."
        if "canonical" in finding_check_id:
            return "Template canonical tag divergence from requested/final URL or cross-domain specification."
        if "indexability" in finding_check_id:
            return "Conflicting indexing directives between meta tags and server HTTP headers."
        if "robots" in finding_check_id:
            return "Robots.txt Disallow rule or gateway block preventing crawler discovery."
        if "sitemap" in finding_check_id:
            return "Sitemap generation pipeline omitted indexable URLs or included non-200 destinations."
        if "structured_data" in finding_check_id:
            return "CMS or template JSON-LD generator emitting malformed or invalid syntax."
        return "Unknown template or server-side configuration defect."

