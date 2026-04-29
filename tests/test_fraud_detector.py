"""
Tests for Fraud Detector Agent (Agent 4).
Validates same-day claim limits, high-value thresholds, and document consistency checks.
"""

import pytest
import json
from unittest.mock import AsyncMock

from app.agents.fraud_detector import FraudDetector, FraudCheckResult
from app.models.claim import ClaimCategory
from app.models.document import ExtractedDocument, DocumentType
from app.models.policy import PolicyTerms
from app.utils.confidence import ConfidenceTracker


@pytest.fixture
def policy() -> PolicyTerms:
    with open("data/policy_terms.json", "r") as f:
        data = json.load(f)
    return PolicyTerms(**data)


@pytest.fixture
def detector(policy) -> FraudDetector:
    mock_llm = AsyncMock()
    mock_llm.call_text_model = AsyncMock(return_value={
        "recommend_manual_review": False,
        "recommendation_reason": "",
    })
    return FraudDetector(mock_llm, policy)


class TestSameDayClaims:
    """Tests for same-day claims fraud detection."""

    @pytest.mark.asyncio
    async def test_no_history_no_fraud(self, detector):
        """No claims history -> no fraud signals."""
        confidence = ConfidenceTracker()
        result, step = await detector.detect(
            member_id="EMP001", claim_category=ClaimCategory.CONSULTATION,
            treatment_date="2024-11-01", claimed_amount=1500,
            hospital_name=None, extracted_docs=[], claims_history=None,
            confidence=confidence,
        )
        assert result.same_day_exceeded is False
        assert result.risk_level == "LOW"

    @pytest.mark.asyncio
    async def test_same_day_limit_exceeded(self, detector):
        """2+ claims on same day should trigger fraud signal (limit is 2)."""
        history = [
            {"date": "2024-11-01", "amount": 1000, "category": "CONSULTATION"},
            {"date": "2024-11-01", "amount": 2000, "category": "PHARMACY"},
        ]
        confidence = ConfidenceTracker()
        result, step = await detector.detect(
            member_id="EMP001", claim_category=ClaimCategory.CONSULTATION,
            treatment_date="2024-11-01", claimed_amount=1500,
            hospital_name=None, extracted_docs=[], claims_history=history,
            confidence=confidence,
        )
        assert result.same_day_exceeded is True
        assert result.recommend_manual_review is True
        assert confidence.score < 1.0  # Deduction applied

    @pytest.mark.asyncio
    async def test_different_day_no_flag(self, detector):
        """Claims on different days should not trigger same-day fraud."""
        history = [
            {"date": "2024-10-30", "amount": 1000, "category": "CONSULTATION"},
            {"date": "2024-10-31", "amount": 2000, "category": "PHARMACY"},
        ]
        confidence = ConfidenceTracker()
        result, step = await detector.detect(
            member_id="EMP001", claim_category=ClaimCategory.CONSULTATION,
            treatment_date="2024-11-01", claimed_amount=1500,
            hospital_name=None, extracted_docs=[], claims_history=history,
            confidence=confidence,
        )
        assert result.same_day_exceeded is False


class TestHighValueClaims:
    """Tests for high-value claim detection."""

    @pytest.mark.asyncio
    async def test_below_threshold_not_flagged(self, detector):
        confidence = ConfidenceTracker()
        result, step = await detector.detect(
            member_id="EMP001", claim_category=ClaimCategory.CONSULTATION,
            treatment_date="2024-11-01", claimed_amount=5000,
            hospital_name=None, extracted_docs=[], claims_history=None,
            confidence=confidence,
        )
        assert result.high_value is False

    @pytest.mark.asyncio
    async def test_above_threshold_flagged(self, detector):
        """Rs 25,000+ should trigger high-value flag."""
        confidence = ConfidenceTracker()
        result, step = await detector.detect(
            member_id="EMP001", claim_category=ClaimCategory.DIAGNOSTIC,
            treatment_date="2024-11-01", claimed_amount=30000,
            hospital_name=None, extracted_docs=[], claims_history=None,
            confidence=confidence,
        )
        assert result.high_value is True
        assert result.recommend_manual_review is True


class TestDocumentConsistency:
    """Tests for cross-document consistency checks."""

    def test_matching_patient_names_no_flag(self, detector):
        docs = [
            ExtractedDocument(file_id="F1", detected_type=DocumentType.PRESCRIPTION, patient_name="Rajesh Kumar"),
            ExtractedDocument(file_id="F2", detected_type=DocumentType.HOSPITAL_BILL, patient_name="Rajesh Kumar"),
        ]
        observations = FraudDetector._check_document_consistency(docs)
        name_flags = [o for o in observations if "patient name" in o["signal"].lower()]
        assert len(name_flags) == 0

    def test_mismatched_patient_names_flagged(self, detector):
        docs = [
            ExtractedDocument(file_id="F1", detected_type=DocumentType.PRESCRIPTION, patient_name="Rajesh Kumar"),
            ExtractedDocument(file_id="F2", detected_type=DocumentType.HOSPITAL_BILL, patient_name="Vikram Joshi"),
        ]
        observations = FraudDetector._check_document_consistency(docs)
        name_flags = [o for o in observations if "patient name" in o["signal"].lower()]
        assert len(name_flags) == 1
        assert name_flags[0]["severity"] == "HIGH"

    def test_mismatched_dates_flagged(self, detector):
        docs = [
            ExtractedDocument(file_id="F1", detected_type=DocumentType.PRESCRIPTION, date="2024-11-01"),
            ExtractedDocument(file_id="F2", detected_type=DocumentType.HOSPITAL_BILL, date="2024-10-15"),
        ]
        observations = FraudDetector._check_document_consistency(docs)
        date_flags = [o for o in observations if "date" in o["signal"].lower()]
        assert len(date_flags) == 1
        assert date_flags[0]["severity"] == "MEDIUM"


class TestFraudCheckResult:
    """Tests for FraudCheckResult data model."""

    def test_default_values(self):
        result = FraudCheckResult()
        assert result.fraud_score == 0.0
        assert result.risk_level == "LOW"
        assert result.signals == []
        assert result.recommend_manual_review is False

    def test_to_dict(self):
        result = FraudCheckResult()
        result.fraud_score = 0.85
        result.risk_level = "CRITICAL"
        d = result.to_dict()
        assert d["fraud_score"] == 0.85
        assert d["risk_level"] == "CRITICAL"
