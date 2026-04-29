"""
Tests for Policy Checker Agent (Agent 3).
Validates per-claim limits, waiting periods, exclusions, pre-auth, and financial calculations.
All deterministic — no LLM calls.
"""

import pytest
import json
from unittest.mock import AsyncMock

from app.agents.policy_checker import PolicyChecker
from app.models.claim import ClaimCategory
from app.models.document import ExtractedDocument, DocumentType, ExtractedLineItem
from app.models.policy import PolicyTerms
from app.utils.confidence import ConfidenceTracker


@pytest.fixture
def policy() -> PolicyTerms:
    with open("data/policy_terms.json", "r") as f:
        data = json.load(f)
    return PolicyTerms(**data)


@pytest.fixture
def checker(policy) -> PolicyChecker:
    mock_llm = AsyncMock()
    # Mock the LLM to return empty notes
    mock_llm.call_text_model = AsyncMock(return_value={"notes": ""})
    return PolicyChecker(mock_llm, policy)


def make_doc(diagnosis=None, line_items=None, date="2024-11-01"):
    """Helper to create an ExtractedDocument for tests."""
    items = []
    if line_items:
        for desc, amt in line_items:
            items.append(ExtractedLineItem(description=desc, amount=amt))
    return ExtractedDocument(
        file_id="F001",
        detected_type=DocumentType.HOSPITAL_BILL,
        patient_name="Test Patient",
        date=date,
        diagnosis=diagnosis,
        line_items=items,
    )


class TestPerClaimLimit:
    """Tests for the global per-claim limit of Rs 5,000."""

    @pytest.mark.asyncio
    async def test_under_limit_passes(self, checker):
        docs = [make_doc()]
        confidence = ConfidenceTracker()
        result, step = await checker.check(
            member_id="EMP001", claim_category=ClaimCategory.CONSULTATION,
            treatment_date="2024-11-01", claimed_amount=1500,
            hospital_name=None, extracted_docs=docs, ytd_claims_amount=0,
            confidence=confidence,
        )
        assert result.eligible is True

    @pytest.mark.asyncio
    async def test_over_limit_rejected(self, checker):
        """Rs 7,500 > Rs 5,000 per-claim limit -> reject."""
        docs = [make_doc()]
        confidence = ConfidenceTracker()
        result, step = await checker.check(
            member_id="EMP001", claim_category=ClaimCategory.CONSULTATION,
            treatment_date="2024-11-01", claimed_amount=7500,
            hospital_name=None, extracted_docs=docs, ytd_claims_amount=0,
            confidence=confidence,
        )
        assert result.eligible is False
        assert "PER_CLAIM_EXCEEDED" in result.rejection_codes

    @pytest.mark.asyncio
    async def test_exact_limit_passes(self, checker):
        """Rs 5,000 exactly at limit -> should pass."""
        docs = [make_doc()]
        confidence = ConfidenceTracker()
        result, step = await checker.check(
            member_id="EMP001", claim_category=ClaimCategory.DENTAL,
            treatment_date="2024-11-01", claimed_amount=5000,
            hospital_name=None, extracted_docs=docs, ytd_claims_amount=0,
            confidence=confidence,
        )
        assert result.eligible is True


class TestWaitingPeriod:
    """Tests for waiting period violations."""

    @pytest.mark.asyncio
    async def test_within_initial_waiting_period_rejected(self, checker):
        """EMP005 joined 2024-09-01, treatment on 2024-09-15 = only 14 days -> reject."""
        docs = [make_doc()]
        confidence = ConfidenceTracker()
        result, step = await checker.check(
            member_id="EMP005", claim_category=ClaimCategory.CONSULTATION,
            treatment_date="2024-09-15", claimed_amount=1500,
            hospital_name=None, extracted_docs=docs, ytd_claims_amount=0,
            confidence=confidence,
        )
        assert result.eligible is False
        assert "WAITING_PERIOD" in result.rejection_codes

    @pytest.mark.asyncio
    async def test_past_initial_waiting_period_passes(self, checker):
        """EMP005 joined 2024-09-01, treatment on 2024-11-01 = 61 days -> pass."""
        docs = [make_doc()]
        confidence = ConfidenceTracker()
        result, step = await checker.check(
            member_id="EMP005", claim_category=ClaimCategory.CONSULTATION,
            treatment_date="2024-11-01", claimed_amount=1500,
            hospital_name=None, extracted_docs=docs, ytd_claims_amount=0,
            confidence=confidence,
        )
        assert result.eligible is True

    @pytest.mark.asyncio
    async def test_diabetes_within_90_day_waiting_rejected(self, checker):
        """Diabetes has 90-day waiting. EMP001 joined 2024-04-01, diagnosed 2024-06-01 = 61 days."""
        docs = [make_doc(diagnosis="Type 2 Diabetes Mellitus")]
        confidence = ConfidenceTracker()
        result, step = await checker.check(
            member_id="EMP001", claim_category=ClaimCategory.CONSULTATION,
            treatment_date="2024-06-01", claimed_amount=1500,
            hospital_name=None, extracted_docs=docs, ytd_claims_amount=0,
            confidence=confidence,
        )
        assert result.eligible is False
        assert "WAITING_PERIOD" in result.rejection_codes


class TestExclusions:
    """Tests for excluded treatments."""

    @pytest.mark.asyncio
    async def test_cosmetic_procedure_excluded(self, checker):
        """Cosmetic procedures are in the general exclusions list."""
        docs = [make_doc(diagnosis="Cosmetic rhinoplasty for aesthetic procedures")]
        confidence = ConfidenceTracker()
        result, step = await checker.check(
            member_id="EMP001", claim_category=ClaimCategory.CONSULTATION,
            treatment_date="2024-11-01", claimed_amount=3000,
            hospital_name=None, extracted_docs=docs, ytd_claims_amount=0,
            confidence=confidence,
        )
        assert result.eligible is False
        assert "EXCLUDED_CONDITION" in result.rejection_codes

    @pytest.mark.asyncio
    async def test_dental_whitening_excluded(self, checker):
        """Teeth whitening is in dental excluded_procedures."""
        docs = [make_doc(
            diagnosis="Professional Teeth Whitening procedure",
            line_items=[("Teeth Whitening", 5000)],
        )]
        confidence = ConfidenceTracker()
        result, step = await checker.check(
            member_id="EMP001", claim_category=ClaimCategory.DENTAL,
            treatment_date="2024-11-01", claimed_amount=5000,
            hospital_name=None, extracted_docs=docs, ytd_claims_amount=0,
            confidence=confidence,
        )
        # Either rejected outright or all line items excluded (approved_amount = 0)
        has_excluded_items = any(not lid.approved for lid in result.line_item_decisions)
        assert not result.eligible or has_excluded_items or result.approved_amount == 0


class TestFinancialCalculation:
    """Tests for co-pay, network discount, and sub-limit calculations."""

    @pytest.mark.asyncio
    async def test_consultation_copay_10_percent(self, checker):
        """Consultation: 10% co-pay, no network discount (non-network hospital)."""
        docs = [make_doc(line_items=[("OPD Consultation", 1000)])]
        confidence = ConfidenceTracker()
        result, step = await checker.check(
            member_id="EMP001", claim_category=ClaimCategory.CONSULTATION,
            treatment_date="2024-11-01", claimed_amount=1000,
            hospital_name="City Clinic", extracted_docs=docs, ytd_claims_amount=0,
            confidence=confidence,
        )
        assert result.eligible is True
        # Rs 1000 - 10% copay = Rs 900
        assert result.approved_amount == pytest.approx(900.0)

    @pytest.mark.asyncio
    async def test_consultation_network_discount(self, checker):
        """Consultation at network hospital: 20% discount, then 10% co-pay."""
        docs = [make_doc(line_items=[("OPD Consultation", 2000)])]
        confidence = ConfidenceTracker()
        result, step = await checker.check(
            member_id="EMP001", claim_category=ClaimCategory.CONSULTATION,
            treatment_date="2024-11-01", claimed_amount=2000,
            hospital_name="Apollo Hospitals", extracted_docs=docs, ytd_claims_amount=0,
            confidence=confidence,
        )
        assert result.eligible is True
        # Rs 2000 (sub-limit cap) - 20% network = 1600 - 10% copay = Rs 1440
        assert result.approved_amount == pytest.approx(1440.0)

    @pytest.mark.asyncio
    async def test_sub_limit_caps_amount(self, checker):
        """Consultation sub-limit is Rs 2000. Claiming 4500 -> capped at 2000."""
        docs = [make_doc(line_items=[("Treatment", 4500)])]
        confidence = ConfidenceTracker()
        result, step = await checker.check(
            member_id="EMP001", claim_category=ClaimCategory.CONSULTATION,
            treatment_date="2024-11-01", claimed_amount=4500,
            hospital_name=None, extracted_docs=docs, ytd_claims_amount=0,
            confidence=confidence,
        )
        assert result.eligible is True
        # Capped at 2000, 10% copay = 1800
        assert result.approved_amount == pytest.approx(1800.0)


class TestMemberValidation:
    """Tests for member existence checks."""

    @pytest.mark.asyncio
    async def test_unknown_member_rejected(self, checker):
        docs = [make_doc()]
        confidence = ConfidenceTracker()
        result, step = await checker.check(
            member_id="UNKNOWN_123", claim_category=ClaimCategory.CONSULTATION,
            treatment_date="2024-11-01", claimed_amount=1000,
            hospital_name=None, extracted_docs=docs, ytd_claims_amount=0,
            confidence=confidence,
        )
        assert result.eligible is False
        assert "MEMBER_NOT_FOUND" in result.rejection_codes
