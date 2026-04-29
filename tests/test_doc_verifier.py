"""
Tests for Document Verification Agent (Agent 1).
Validates document type checking, patient name matching, and quality assessment.
No LLM calls — tests use pre-classified document metadata.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock
import json

from app.agents.doc_verifier import DocVerifier
from app.models.claim import ClaimCategory, DocumentMeta
from app.models.document import VerificationStatus
from app.models.policy import PolicyTerms
from app.utils.confidence import ConfidenceTracker


@pytest.fixture
def policy() -> PolicyTerms:
    with open("data/policy_terms.json", "r") as f:
        data = json.load(f)
    return PolicyTerms(**data)


@pytest.fixture
def verifier(policy) -> DocVerifier:
    mock_llm = AsyncMock()
    return DocVerifier(mock_llm, policy)


class TestDocumentTypeChecking:
    """Tests for verifying correct document types are uploaded per category."""

    @pytest.mark.asyncio
    async def test_consultation_with_correct_docs_passes(self, verifier):
        """CONSULTATION with prescription + hospital bill should pass."""
        docs = [
            DocumentMeta(file_name="rx.png", actual_type="PRESCRIPTION", patient_name_on_doc="Rajesh Kumar"),
            DocumentMeta(file_name="bill.png", actual_type="HOSPITAL_BILL", patient_name_on_doc="Rajesh Kumar"),
        ]
        confidence = ConfidenceTracker()
        result, step = await verifier.verify(docs, ClaimCategory.CONSULTATION, "Rajesh Kumar", confidence)
        assert result.is_valid is True
        assert result.status == VerificationStatus.VERIFIED

    @pytest.mark.asyncio
    async def test_consultation_missing_bill_fails(self, verifier):
        """CONSULTATION with only prescription (no bill) should fail."""
        docs = [
            DocumentMeta(file_name="rx.png", actual_type="PRESCRIPTION", patient_name_on_doc="Rajesh Kumar"),
        ]
        confidence = ConfidenceTracker()
        result, step = await verifier.verify(docs, ClaimCategory.CONSULTATION, "Rajesh Kumar", confidence)
        assert result.is_valid is False
        assert result.status == VerificationStatus.WRONG_TYPE
        assert "HOSPITAL_BILL" in result.documents_missing

    @pytest.mark.asyncio
    async def test_diagnostic_requires_three_docs(self, verifier):
        """DIAGNOSTIC with only prescription + bill (no lab report) should fail."""
        docs = [
            DocumentMeta(file_name="rx.png", actual_type="PRESCRIPTION", patient_name_on_doc="Test"),
            DocumentMeta(file_name="bill.png", actual_type="HOSPITAL_BILL", patient_name_on_doc="Test"),
        ]
        confidence = ConfidenceTracker()
        result, step = await verifier.verify(docs, ClaimCategory.DIAGNOSTIC, "Test", confidence)
        assert result.is_valid is False
        assert "LAB_REPORT" in result.documents_missing

    @pytest.mark.asyncio
    async def test_dental_only_needs_bill(self, verifier):
        """DENTAL with just a hospital bill should pass."""
        docs = [
            DocumentMeta(file_name="dental_bill.png", actual_type="HOSPITAL_BILL", patient_name_on_doc="Amit Verma"),
        ]
        confidence = ConfidenceTracker()
        result, step = await verifier.verify(docs, ClaimCategory.DENTAL, "Amit Verma", confidence)
        assert result.is_valid is True


class TestPatientNameMatching:
    """Tests for patient name consistency across documents."""

    @pytest.mark.asyncio
    async def test_matching_names_pass(self, verifier):
        """Same patient name across all docs should pass."""
        docs = [
            DocumentMeta(file_name="rx.png", actual_type="PRESCRIPTION", patient_name_on_doc="Priya Singh"),
            DocumentMeta(file_name="bill.png", actual_type="HOSPITAL_BILL", patient_name_on_doc="Priya Singh"),
        ]
        confidence = ConfidenceTracker()
        result, step = await verifier.verify(docs, ClaimCategory.CONSULTATION, "Priya Singh", confidence)
        assert result.is_valid is True

    @pytest.mark.asyncio
    async def test_mismatched_names_fail(self, verifier):
        """Different patient names across docs should reject."""
        docs = [
            DocumentMeta(file_name="rx.png", actual_type="PRESCRIPTION", patient_name_on_doc="Rajesh Kumar"),
            DocumentMeta(file_name="bill.png", actual_type="HOSPITAL_BILL", patient_name_on_doc="Arjun Mehta"),
        ]
        confidence = ConfidenceTracker()
        result, step = await verifier.verify(docs, ClaimCategory.CONSULTATION, "Rajesh Kumar", confidence)
        assert result.is_valid is False
        assert result.status == VerificationStatus.PATIENT_MISMATCH


class TestDocumentQuality:
    """Tests for document quality assessment."""

    @pytest.mark.asyncio
    async def test_unreadable_document_fails(self, verifier):
        """UNREADABLE quality docs should cause rejection."""
        docs = [
            DocumentMeta(file_name="blurry.png", actual_type="PRESCRIPTION", quality="UNREADABLE", patient_name_on_doc="Test"),
            DocumentMeta(file_name="bill.png", actual_type="HOSPITAL_BILL", patient_name_on_doc="Test"),
        ]
        confidence = ConfidenceTracker()
        result, step = await verifier.verify(docs, ClaimCategory.CONSULTATION, "Test", confidence)
        assert result.is_valid is False
        assert result.status == VerificationStatus.UNREADABLE

    @pytest.mark.asyncio
    async def test_poor_quality_deducts_confidence(self, verifier):
        """POOR quality docs should pass but deduct confidence."""
        docs = [
            DocumentMeta(file_name="rx.png", actual_type="PRESCRIPTION", quality="POOR", patient_name_on_doc="Test"),
            DocumentMeta(file_name="bill.png", actual_type="HOSPITAL_BILL", quality="POOR", patient_name_on_doc="Test"),
        ]
        confidence = ConfidenceTracker()
        result, step = await verifier.verify(docs, ClaimCategory.CONSULTATION, "Test", confidence)
        assert result.is_valid is True
        assert confidence.score < 1.0  # Confidence should be reduced


class TestConfidenceDeductions:
    """Tests that confidence deductions are applied correctly per scenario."""

    @pytest.mark.asyncio
    async def test_unreadable_deducts_configured_amount(self, verifier):
        docs = [
            DocumentMeta(file_name="blurry.png", actual_type="PRESCRIPTION", quality="UNREADABLE"),
        ]
        confidence = ConfidenceTracker(initial=1.0)
        await verifier.verify(docs, ClaimCategory.CONSULTATION, "Test", confidence)
        # UNREADABLE deduction is applied (default 0.5)
        assert len(confidence.deductions) >= 1
        assert confidence.score < 1.0

    @pytest.mark.asyncio
    async def test_missing_doc_deducts_full(self, verifier):
        docs = [
            DocumentMeta(file_name="rx.png", actual_type="PRESCRIPTION", patient_name_on_doc="Test"),
        ]
        confidence = ConfidenceTracker(initial=1.0)
        await verifier.verify(docs, ClaimCategory.CONSULTATION, "Test", confidence)
        # Missing doc deduction = 1.0 (default)
        assert confidence.score == 0.0


class TestFilenameHeuristics:
    """Tests for the filename-based document type guessing fallback."""

    def test_prescription_keyword(self):
        result = DocVerifier._guess_type_from_filename("my_prescription_2024.pdf")
        assert result == "PRESCRIPTION"

    def test_bill_keyword(self):
        result = DocVerifier._guess_type_from_filename("hospital_bill.png")
        assert result == "HOSPITAL_BILL"

    def test_lab_keyword(self):
        result = DocVerifier._guess_type_from_filename("blood_lab_report.pdf")
        assert result == "LAB_REPORT"

    def test_unknown_filename(self):
        result = DocVerifier._guess_type_from_filename("IMG_20240301_142356.jpg")
        assert result == "UNKNOWN"
