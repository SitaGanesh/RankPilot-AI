"""Pipeline stage names and progress event emission."""

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Stage(StrEnum):
    API = "api"
    COORDINATOR = "coordinator"
    COLLECTOR = "collector"
    EVIDENCE = "evidence"
    SPECIALIZED_AGENT = "specialized_agent"
    AGENTIC_INVESTIGATION = "agentic_investigation"
    FINDING_VALIDATOR = "finding_validator"
    SCORING = "scoring"
    AGGREGATOR = "aggregator"
    COMPARISON = "comparison"
    FINAL_AUDIT_LLM = "final_audit_llm"
    OUTPUT_VALIDATOR = "output_validator"
    REPORT_BUILDER = "report_builder"
    RESPONSE = "response"
    FRONTEND = "frontend"


class StageStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass(frozen=True)
class StageEvent:
    stage: Stage
    status: StageStatus
    message: str


class EventEmitter:
    """Emit ordered progress events to an optional persistence callback."""

    def __init__(self, callback: Callable[[StageEvent], Any] | None = None):
        self.callback = callback
        self.events: list[StageEvent] = []

    def emit(self, stage: Stage, status: StageStatus, message: str) -> StageEvent:
        event = StageEvent(stage=stage, status=status, message=message)
        self.events.append(event)
        if self.callback:
            self.callback(event)
        return event
