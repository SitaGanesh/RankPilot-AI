"""Remediation planning, approval and post-fix verification.

No website is modified by this module unless an operator configures a real
write integration (``SEO_REMEDIATION_EXECUTOR``).  Approval alone never marks a
finding resolved; only re-measured evidence can do that.
"""

from __future__ import annotations

import importlib
import logging
from datetime import datetime, timezone
from typing import Any

from django.conf import settings
from django.utils import timezone as django_timezone

from audits.models import (
    Audit,
    Investigation,
    InvestigationFinding,
    RemediationProposal,
    VerificationResult,
)
from audits.state_machine import transition_audit, transition_investigation
from core.errors import ContractValidationError

from .signals import capture_signals

logger = logging.getLogger(__name__)

TARGET_SIGNALS: list[tuple[str, str]] = [
    ("indexability.canonical", "canonical"),
    ("canonical.target_status", "status"),
    ("indexability.robots", "meta_robots"),
    ("robots.blocked", "robots_txt_allows"),
    ("indexability.robots_txt_block", "robots_txt_allows"),
    ("https.mixed_content", "insecure_resource_count"),
    ("https.", "scheme"),
    ("http.status", "status"),
    ("sitemaps.", "sitemap_listed"),
    ("javascript.empty_html_shell", "word_count"),
    ("page.missing_title", "title"),
    ("page.missing_h1", "h1_count"),
    ("structured_data.", "json_ld_blocks"),
    ("ai_crawlers.", "robots_txt_allows"),
]
SIGNAL_KEYS = (
    "status",
    "final_url",
    "scheme",
    "canonical",
    "meta_robots",
    "x_robots_tag",
    "robots_txt_allows",
    "title",
    "h1_count",
    "word_count",
    "json_ld_blocks",
    "insecure_resource_count",
)


def target_signal_for(check_id: str) -> str | None:
    for prefix, signal in TARGET_SIGNALS:
        if check_id.startswith(prefix):
            return signal
    return None


def _first_url(finding: InvestigationFinding, investigation: Investigation) -> str:
    if finding.affected_urls:
        return finding.affected_urls[0]
    return investigation.audit.normalized_url or investigation.audit.url


def create_proposal(
    *,
    investigation: Investigation,
    finding: InvestigationFinding,
    decision: Any,
) -> RemediationProposal:
    """Create a structured, evidence-linked remediation proposal."""

    if not decision.change or not decision.verification_method:
        raise ContractValidationError(
            "A remediation proposal requires a concrete change and a verification method."
        )
    url = _first_url(finding, investigation)
    signals = capture_signals(url)
    proposal = RemediationProposal.objects.create(
        investigation=investigation,
        finding_ref=finding.finding_ref,
        status=RemediationProposal.Status.AWAITING_APPROVAL,
        change=decision.change,
        scope=decision.scope or url,
        expected_outcome=decision.expected_outcome or "",
        risk=decision.risk or "",
        verification_method=decision.verification_method,
        rollback=decision.rollback or "",
        baseline={
            "url": url,
            "check_id": finding.check_id,
            "target_signal": target_signal_for(finding.check_id),
            "signals": signals,
        },
        evidence_refs=finding.evidence_refs,
    )
    return proposal


def _load_executor():
    path = getattr(settings, "SEO_REMEDIATION_EXECUTOR", "").strip()
    if not path:
        return None
    module_path, _, class_name = path.rpartition(".")
    if not module_path or not class_name:
        raise ContractValidationError("SEO_REMEDIATION_EXECUTOR must be a dotted class path")
    module = importlib.import_module(module_path)
    return getattr(module, class_name)()


def approve_proposal(
    proposal: RemediationProposal, *, approved_by=None, note: str = ""
) -> dict[str, Any]:
    """Record approval, then execute only through a configured integration."""

    if proposal.status in {
        RemediationProposal.Status.VERIFIED,
        RemediationProposal.Status.REJECTED,
    }:
        return {
            "proposal_id": str(proposal.pk),
            "status": proposal.status,
            "message": "Proposal can no longer be approved in its current state.",
        }
    proposal.status = RemediationProposal.Status.APPROVED
    proposal.approved_by = approved_by
    proposal.approved_at = django_timezone.now()
    proposal.approval_note = note
    proposal.save(update_fields=["status", "approved_by", "approved_at", "approval_note", "updated_at"])

    try:
        executor = _load_executor()
    except Exception as exc:  # noqa: BLE001
        proposal.status = RemediationProposal.Status.EXECUTION_UNAVAILABLE
        proposal.execution_status = "executor_configuration_error"
        proposal.execution_result = {"ok": False, "detail": str(exc)}
        proposal.save(update_fields=["status", "execution_status", "execution_result", "updated_at"])
        return {
            "proposal_id": str(proposal.pk),
            "status": proposal.status,
            "message": "No usable remediation executor is configured; nothing was changed.",
        }

    if executor is None:
        proposal.status = RemediationProposal.Status.EXECUTION_UNAVAILABLE
        proposal.execution_status = "executor_not_configured"
        proposal.execution_result = {
            "ok": False,
            "detail": (
                "This deployment has read-only access. The proposal is approved but no site "
                "change was executed. Configure SEO_REMEDIATION_EXECUTOR to enable an "
                "authorized write integration."
            ),
        }
        proposal.save(update_fields=["status", "execution_status", "execution_result", "updated_at"])
        return {
            "proposal_id": str(proposal.pk),
            "status": proposal.status,
            "message": proposal.execution_result["detail"],
        }

    try:
        result = executor.execute(proposal)
        if not isinstance(result, dict):
            raise ContractValidationError("Executor must return a result dictionary")
        ok = bool(result.get("ok"))
        proposal.execution_result = result
        proposal.execution_status = "executed" if ok else "execution_failed"
        proposal.status = (
            RemediationProposal.Status.IMPLEMENTED
            if ok
            else RemediationProposal.Status.EXECUTION_UNAVAILABLE
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Remediation executor failed for proposal %s", proposal.pk)
        proposal.execution_result = {"ok": False, "detail": str(exc)[:1000]}
        proposal.execution_status = "execution_error"
        proposal.status = RemediationProposal.Status.EXECUTION_UNAVAILABLE
    proposal.save(update_fields=["status", "execution_status", "execution_result", "updated_at"])
    return {
        "proposal_id": str(proposal.pk),
        "status": proposal.status,
        "message": "Reviewed by the configured executor. Verification is still required.",
    }


def reject_proposal(proposal: RemediationProposal, *, note: str = "") -> None:
    proposal.status = RemediationProposal.Status.REJECTED
    proposal.approval_note = note
    proposal.save(update_fields=["status", "approval_note", "updated_at"])


def verify_proposal(proposal: RemediationProposal) -> dict[str, Any]:
    """Re-measure the proposal URL and only resolve the finding on matching evidence."""

    baseline = proposal.baseline or {}
    url = baseline.get("url")
    before = baseline.get("signals") or {}
    target_signal = baseline.get("target_signal")
    if not url:
        raise ContractValidationError("Proposal has no baseline URL to verify")
    after = capture_signals(url)
    changes = {
        key: {"before": before.get(key), "after": after.get(key)}
        for key in SIGNAL_KEYS
        if before.get(key) != after.get(key)
    }
    notes = []
    if not after.get("available"):
        outcome = VerificationResult.Outcome.INCONCLUSIVE
        notes.append(f"Re-measurement failed: {after.get('error')}")
    elif before.get("status") and 200 <= int(before["status"]) < 300 and (
        after.get("status") and int(after["status"]) >= 400
    ):
        outcome = VerificationResult.Outcome.FAILED
        notes.append("The page status regressed to an error after the change.")
    elif target_signal == "sitemap_listed":
        outcome = VerificationResult.Outcome.INCONCLUSIVE
        notes.append("Sitemap membership was not re-measured by this verification tool.")
    elif target_signal and target_signal in changes:
        outcome = VerificationResult.Outcome.VERIFIED
        notes.append(f"Target signal '{target_signal}' changed after the correction.")
    elif target_signal:
        outcome = VerificationResult.Outcome.FAILED
        notes.append(f"Target signal '{target_signal}' did not change.")
    elif changes:
        outcome = VerificationResult.Outcome.INCONCLUSIVE
        notes.append(
            "A change was observed, but this check has no mapped target signal; the specific "
            "issue cannot be confirmed resolved."
        )
    else:
        outcome = VerificationResult.Outcome.FAILED
        notes.append("No measured signal changed.")

    verification = VerificationResult.objects.create(
        proposal=proposal,
        outcome=outcome,
        before=before,
        after=after,
        notes=" ".join(notes),
    )
    proposal.verification = {
        "outcome": outcome,
        "target_signal": target_signal,
        "changes": changes,
        "before": before,
        "after": after,
        "notes": " ".join(notes),
        "verification_id": verification.pk,
    }
    proposal.verified_at = datetime.now(timezone.utc)
    proposal.status = (
        RemediationProposal.Status.VERIFIED
        if outcome == VerificationResult.Outcome.VERIFIED
        else RemediationProposal.Status.VERIFICATION_FAILED
    )
    proposal.save(
        update_fields=["status", "verification", "verified_at", "updated_at"]
    )

    if outcome == VerificationResult.Outcome.VERIFIED:
        finding = InvestigationFinding.objects.filter(
            investigation_id=proposal.investigation_id, finding_ref=proposal.finding_ref
        ).first()
        if finding is not None:
            finding.status = InvestigationFinding.Status.RESOLVED
            finding.verification_status = f"verified: {target_signal} changed"
            finding.save(update_fields=["status", "verification_status", "updated_at"])
    elif outcome == VerificationResult.Outcome.FAILED:
        finding = InvestigationFinding.objects.filter(
            investigation_id=proposal.investigation_id, finding_ref=proposal.finding_ref
        ).first()
        if finding is not None and finding.status != InvestigationFinding.Status.RESOLVED:
            finding.verification_status = "verification_failed"
            finding.save(update_fields=["verification_status", "updated_at"])

    investigation = proposal.investigation
    all_proposals = list(investigation.proposals.all())
    all_verified = all(
        item.status == RemediationProposal.Status.VERIFIED for item in all_proposals
    )
    final_status = (
        Investigation.Status.COMPLETED if all_verified else Investigation.Status.COMPLETED_WITH_LIMITATIONS
    )
    transition_investigation(investigation, final_status)
    transition_audit(investigation.audit, Audit.Status.COMPLETED_WITH_LIMITATIONS)
    return {
        "proposal_id": str(proposal.pk),
        "status": proposal.status,
        "outcome": outcome,
        "changes": changes,
        "notes": " ".join(notes),
    }
