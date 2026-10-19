"""Shared contracts used by every SEO agent and pipeline stage."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CheckStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class AgentStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class FindingSource(StrEnum):
    DETERMINISTIC = "deterministic"
    LLM = "llm"


class Evidence(BaseModel):
    """A concrete observation supporting a check or finding."""

    model_config = ConfigDict(extra="forbid")

    selector: str | None = None
    observed: str
    expected: str
    snippet: str | None = None


class Finding(BaseModel):
    """A validated, score-bearing or advisory audit finding."""

    model_config = ConfigDict(extra="forbid")

    id: str
    check_id: str
    title: str
    status: CheckStatus
    severity: Severity
    weight: float = Field(ge=0)
    points_earned: float = Field(ge=0)
    evidence: Evidence
    why_it_matters: str
    recommendation: str
    confidence: float = Field(ge=0, le=1)
    source: FindingSource


class CheckResult(BaseModel):
    """Output of one deterministic or advisory check."""

    model_config = ConfigDict(extra="forbid")

    check_id: str
    category: str
    title: str
    status: CheckStatus
    severity: Severity
    weight: float = Field(ge=0)
    points_earned: float = Field(ge=0)
    evidence: Evidence | None = None
    why_it_matters: str
    recommendation: str
    confidence: float = Field(ge=0, le=1)
    source: FindingSource = FindingSource.DETERMINISTIC


class ScoreSummary(BaseModel):
    """Deterministic score and coverage for a set of findings."""

    model_config = ConfigDict(extra="forbid")

    earned: float = Field(ge=0)
    applicable_weight: float = Field(ge=0)
    total_weight: float = Field(ge=0)
    percent: float = Field(ge=0, le=100)
    coverage_percent: float = Field(ge=0, le=100)
    per_category: dict[str, dict[str, float]] = Field(default_factory=dict)


class AgentResult(BaseModel):
    """The stable result contract returned by every registered agent."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str
    agent_version: str
    rule_version: str
    scope: str
    status: AgentStatus
    score: ScoreSummary
    findings: list[Finding] = Field(default_factory=list)
    checks_completed: list[str] = Field(default_factory=list)
    checks_unknown: list[str] = Field(default_factory=list)
    checks_not_applicable: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    started_at: datetime
    finished_at: datetime


def export_json_schema() -> dict[str, Any]:
    """Return the JSON Schema for the shared agent result contract."""

    return AgentResult.model_json_schema()
