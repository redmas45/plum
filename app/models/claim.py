"""
Pydantic models for claim submission, decision, and records.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class ClaimCategory(str, Enum):
    CONSULTATION = "CONSULTATION"
    DIAGNOSTIC = "DIAGNOSTIC"
    PHARMACY = "PHARMACY"
    DENTAL = "DENTAL"
    VISION = "VISION"
    ALTERNATIVE_MEDICINE = "ALTERNATIVE_MEDICINE"


class ClaimDecisionType(str, Enum):
    APPROVED = "APPROVED"
    PARTIAL = "PARTIAL"
    REJECTED = "REJECTED"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class ClaimStatus(str, Enum):
    SUBMITTED = "SUBMITTED"
    PROCESSING = "PROCESSING"
    DECIDED = "DECIDED"
    FAILED = "FAILED"


# ── Request models ─────────────────────────────────────


class ClaimSubmission(BaseModel):
    """What the API receives when a claim is submitted."""
    member_id: str
    policy_id: str = "PLUM_GHI_2024"
    claim_category: ClaimCategory
    treatment_date: str
    claimed_amount: float
    hospital_name: Optional[str] = None
    ytd_claims_amount: Optional[float] = 0.0
    claims_history: Optional[list[dict[str, Any]]] = None
    simulate_component_failure: Optional[bool] = False
    # documents come as uploaded files — metadata tracked separately


class DocumentMeta(BaseModel):
    """Metadata for an uploaded document file."""
    file_id: str = Field(default_factory=lambda: f"F{uuid.uuid4().hex[:6].upper()}")
    file_name: str
    file_path: str = ""
    content_type: str = ""
    actual_type: Optional[str] = None
    # For test-case driven submissions (pre-parsed content)
    content: Optional[dict[str, Any]] = None
    quality: Optional[str] = "GOOD"
    patient_name_on_doc: Optional[str] = None


# ── Response / Decision models ─────────────────────────


class LineItemDecision(BaseModel):
    description: str
    amount: float
    approved: bool
    reason: str = ""


class ClaimDecision(BaseModel):
    """The final output of the claims processing pipeline."""
    claim_id: str
    member_id: str
    decision: ClaimDecisionType
    claimed_amount: float
    approved_amount: float = 0.0
    confidence_score: float = 0.0
    reasons: list[str] = Field(default_factory=list)
    line_item_decisions: list[LineItemDecision] = Field(default_factory=list)
    rejection_codes: list[str] = Field(default_factory=list)
    notes: str = ""
    processing_time_ms: float = 0.0


class ClaimRecord(BaseModel):
    """Full claim record stored in the database."""
    claim_id: str = Field(default_factory=lambda: f"CLM_{uuid.uuid4().hex[:8].upper()}")
    member_id: str
    policy_id: str
    claim_category: ClaimCategory
    treatment_date: str
    claimed_amount: float
    hospital_name: Optional[str] = None
    status: ClaimStatus = ClaimStatus.SUBMITTED
    decision: Optional[ClaimDecision] = None
    trace: Optional[dict[str, Any]] = None
    documents: list[DocumentMeta] = Field(default_factory=list)
    submitted_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    decided_at: Optional[str] = None
    ytd_claims_amount: float = 0.0
    claims_history: Optional[list[dict[str, Any]]] = None
    simulate_component_failure: bool = False
