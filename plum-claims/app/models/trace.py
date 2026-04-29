"""
Pydantic models for the observability / tracing system.
Every claim decision has a full trace showing what each agent did.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class AgentName(str, Enum):
    DOC_VERIFIER = "doc_verifier"
    DOC_PARSER = "doc_parser"
    POLICY_CHECKER = "policy_checker"
    FRAUD_DETECTOR = "fraud_detector"
    DECISION_MAKER = "decision_maker"
    ORCHESTRATOR = "orchestrator"


class StepStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    DEGRADED = "DEGRADED"


class FailureRecord(BaseModel):
    """Records an individual failure during processing."""
    agent: AgentName
    error_type: str
    error_message: str
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    recoverable: bool = True


class AgentStep(BaseModel):
    """One step in the processing trace — output of a single agent."""
    agent: AgentName
    status: StepStatus
    started_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: Optional[str] = None
    duration_ms: float = 0.0
    input_summary: str = ""
    output_summary: str = ""
    output_data: Optional[dict[str, Any]] = None
    confidence_before: float = 1.0
    confidence_after: float = 1.0
    deductions: list[str] = Field(default_factory=list)
    failure: Optional[FailureRecord] = None
    llm_calls: int = 0
    tokens_used: int = 0


class ClaimTrace(BaseModel):
    """Full processing trace for a claim — makes every decision explainable."""
    claim_id: str
    steps: list[AgentStep] = Field(default_factory=list)
    failures: list[FailureRecord] = Field(default_factory=list)
    overall_confidence: float = 1.0
    started_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: Optional[str] = None
    total_duration_ms: float = 0.0
    total_llm_calls: int = 0
    total_tokens: int = 0
    pipeline_degraded: bool = False
    degradation_notes: list[str] = Field(default_factory=list)

    def add_step(self, step: AgentStep) -> None:
        self.steps.append(step)
        self.total_llm_calls += step.llm_calls
        self.total_tokens += step.tokens_used
        self.overall_confidence = step.confidence_after
        if step.failure:
            self.failures.append(step.failure)
            self.pipeline_degraded = True
