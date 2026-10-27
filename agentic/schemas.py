"""Validated schemas for the agentic SEO supervisor.

The LLM may only return one of a small set of actions.  Free-form tool names,
arbitrary code, shell commands, SQL and unregistered URLs are rejected by the
supervisor before anything executes.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ActionType(StrEnum):
    CALL_TOOL = "call_tool"
    REQUEST_ACCESS = "request_access"
    PROPOSE_FIX = "propose_fix"
    REPORT = "report"
    STOP = "stop"


class HypothesisUpdate(BaseModel):
    """A hypothesis formulated, tested, or updated by the agent."""

    statement: str
    status: Literal["open", "supported", "refuted", "confirmed", "unresolved"] = "open"
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    supporting_evidence: list[str] = Field(default_factory=list)
    contradicting_evidence: list[str] = Field(default_factory=list)
    notes: str = ""


class SupervisorDecision(BaseModel):
    """One structured decision returned by the supervisor model."""

    model_config = ConfigDict(extra="forbid")

    action: ActionType
    rationale: str = ""

    # call_tool
    tool_name: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)

    # request_access
    missing_capability: str | None = None
    access_reason: str | None = None

    # propose_fix
    finding_refs: list[str] = Field(default_factory=list)
    change: str | None = None
    scope: str | None = None
    expected_outcome: str | None = None
    risk: str | None = None
    verification_method: str | None = None
    rollback: str | None = None

    # iterative reasoning, hypotheses and root cause diagnosis
    hypotheses: list[HypothesisUpdate] = Field(default_factory=list)
    diagnosed_root_causes: dict[str, str] = Field(default_factory=dict)
    finding_priorities: dict[str, str] = Field(default_factory=dict)

    # report / stop
    summary: str | None = None
    referenced_finding_refs: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    stop_reason: str | None = None

    @field_validator("tool_name", "change", "scope", "summary", "stop_reason")
    @classmethod
    def _strip_optional(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class FindingDraft(BaseModel):
    """A measured or suspected issue produced by a tool.

    ``confirmed`` is set only by deterministic checks or direct measurements
    (for example an HTTP 404).  The LLM never sets this flag.
    """

    model_config = ConfigDict(extra="forbid")

    finding_ref: str
    check_id: str
    title: str
    severity: Literal["critical", "high", "medium", "low", "info"] = "medium"
    confidence: float = Field(default=0.6, ge=0, le=1)
    observed: str
    expected: str = ""
    root_cause: str = ""
    recommendation: str = ""
    affected_urls: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    source_tool: str = ""
    confirmed: bool = False


class ToolResult(BaseModel):
    """Structured result of one tool invocation."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    ok: bool
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    findings: list[FindingDraft] = Field(default_factory=list)
    source_url: str | None = None
    external_request: bool = False
    started_at: datetime
    finished_at: datetime
    duration_ms: float = 0.0


class DecisionValidationError(ValueError):
    """A supervisor decision violated the action contract or safety policy."""


class BudgetExceeded(RuntimeError):
    """An investigation budget was exhausted."""

    def __init__(self, budget: str):
        super().__init__(f"Investigation budget exhausted: {budget}")
        self.budget = budget


class ToolScopeError(ValueError):
    """A tool was asked to inspect a URL outside the investigation scope."""


class LLMUnavailable(RuntimeError):
    """The supervisor model could not produce a usable structured decision."""
