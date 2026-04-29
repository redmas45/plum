"""
Agent 1 — Document Verifier
Uses Llama 4 Scout (VISION) to verify uploaded documents match requirements.
Catches wrong document types, unreadable documents, and patient name mismatches early.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

from app.models.claim import ClaimCategory, DocumentMeta
from app.models.document import (
    DocumentQuality,
    DocumentType,
    DocumentVerificationResult,
    VerificationStatus,
)
from app.models.policy import PolicyTerms
from app.models.trace import AgentName, AgentStep, FailureRecord, StepStatus
from app.services.file_handler import file_to_base64
from app.services.llm_client import LLMClient
from app.utils.confidence import ConfidenceTracker
from app.utils.exceptions import DocumentVerificationError
from app.utils.prompts import DOC_VERIFICATION_SYSTEM, DOC_VERIFICATION_USER
from app.config import settings

logger = logging.getLogger(__name__)


class DocVerifier:
    """Agent 1: Verifies documents are correct type, readable, and consistent."""

    def __init__(self, llm_client: LLMClient, policy: PolicyTerms):
        self.llm = llm_client
        self.policy = policy

    async def verify(
        self,
        documents: list[DocumentMeta],
        claim_category: ClaimCategory,
        member_name: str,
        confidence: ConfidenceTracker,
    ) -> tuple[DocumentVerificationResult, AgentStep]:
        """
        Verify all documents for a claim.

        Returns:
            (verification_result, agent_step) for tracing
        """
        start_time = time.time()
        step = AgentStep(
            agent=AgentName.DOC_VERIFIER,
            status=StepStatus.SUCCESS,
            confidence_before=confidence.score,
            input_summary=f"Verifying {len(documents)} docs for {claim_category.value} claim",
        )

        try:
            # Get document requirements
            requirements = self.policy.get_document_requirements(claim_category.value)
            required_types = requirements.get("required", [])
            optional_types = requirements.get("optional", [])

            # Classify each document
            classified_docs: list[dict[str, Any]] = []
            llm_calls = 0
            tokens = 0

            for doc in documents:
                doc_info = await self._classify_document(doc)
                classified_docs.append(doc_info)
                llm_calls += doc_info.get("llm_calls", 0)
                tokens += doc_info.get("tokens", 0)

            step.llm_calls = llm_calls
            step.tokens_used = tokens

            # Check for unreadable documents
            unreadable = [d for d in classified_docs if d["quality"] == "UNREADABLE"]
            if unreadable:
                result = DocumentVerificationResult(
                    is_valid=False,
                    status=VerificationStatus.UNREADABLE,
                    message=self._build_unreadable_message(unreadable),
                    details=[f"Document '{d['file_name']}' is unreadable — please re-upload a clear photo or scan." for d in unreadable],
                    documents_found=[{"file_name": d["file_name"], "type": d["detected_type"]} for d in classified_docs],
                    documents_required=required_types,
                )
                confidence.deduct(settings.confidence_deduct_unreadable_doc, "Unreadable document(s) detected")
                step.status = StepStatus.SUCCESS  # Agent succeeded, doc is bad
                step.output_summary = f"UNREADABLE: {len(unreadable)} document(s) cannot be read"
                step.output_data = result.model_dump()
                step.confidence_after = confidence.score
                return result, self._finalize_step(step, start_time)

            # Check if required document types are present
            found_types = [d["detected_type"] for d in classified_docs]
            missing_types = [rt for rt in required_types if rt not in found_types]

            if missing_types:
                # Build specific error message about what was uploaded vs what's needed
                result = DocumentVerificationResult(
                    is_valid=False,
                    status=VerificationStatus.WRONG_TYPE,
                    message=self._build_wrong_type_message(
                        classified_docs, required_types, missing_types, claim_category
                    ),
                    details=[
                        f"Uploaded: {d['file_name']} → detected as {d['detected_type']}"
                        for d in classified_docs
                    ],
                    documents_found=[
                        {"file_name": d["file_name"], "type": d["detected_type"]}
                        for d in classified_docs
                    ],
                    documents_required=required_types,
                    documents_missing=missing_types,
                )
                confidence.deduct(settings.confidence_deduct_missing_doc, f"Missing required documents: {missing_types}")
                step.output_summary = f"WRONG_TYPE: Missing {missing_types}"
                step.output_data = result.model_dump()
                step.confidence_after = confidence.score
                return result, self._finalize_step(step, start_time)

            # Check patient name consistency across documents
            patient_names = [
                d["patient_name"]
                for d in classified_docs
                if d.get("patient_name")
            ]
            if len(set(n.lower().strip() for n in patient_names if n)) > 1:
                unique_names = list(set(patient_names))
                result = DocumentVerificationResult(
                    is_valid=False,
                    status=VerificationStatus.PATIENT_MISMATCH,
                    message=self._build_mismatch_message(classified_docs, unique_names),
                    details=[
                        f"Document '{d['file_name']}' ({d['detected_type']}) shows patient name: '{d.get('patient_name', 'unknown')}'"
                        for d in classified_docs
                    ],
                    documents_found=[
                        {"file_name": d["file_name"], "type": d["detected_type"]}
                        for d in classified_docs
                    ],
                    documents_required=required_types,
                )
                confidence.deduct(settings.confidence_deduct_patient_mismatch, f"Patient name mismatch: {unique_names}")
                step.output_summary = f"PATIENT_MISMATCH: Names found: {unique_names}"
                step.output_data = result.model_dump()
                step.confidence_after = confidence.score
                return result, self._finalize_step(step, start_time)

            # All checks passed
            result = DocumentVerificationResult(
                is_valid=True,
                status=VerificationStatus.VERIFIED,
                message="All documents verified successfully.",
                details=[
                    f"✓ {d['file_name']} → {d['detected_type']} (quality: {d['quality']})"
                    for d in classified_docs
                ],
                documents_found=[
                    {"file_name": d["file_name"], "type": d["detected_type"]}
                    for d in classified_docs
                ],
                documents_required=required_types,
            )

            # Small deduction for POOR quality docs
            poor_docs = [d for d in classified_docs if d["quality"] == "POOR"]
            if poor_docs:
                confidence.deduct(
                    settings.confidence_deduct_poor_quality * len(poor_docs),
                    f"{len(poor_docs)} document(s) with poor quality",
                )

            step.output_summary = f"VERIFIED: {len(classified_docs)} documents OK"
            step.output_data = result.model_dump()
            step.confidence_after = confidence.score
            return result, self._finalize_step(step, start_time)

        except Exception as e:
            logger.error(f"Document verification failed: {e}")
            step.status = StepStatus.FAILED
            step.failure = FailureRecord(
                agent=AgentName.DOC_VERIFIER,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            confidence.deduct(settings.confidence_deduct_doc_agent_error, f"Doc verification agent failed: {e}")
            step.confidence_after = confidence.score
            step.output_summary = f"FAILED: {e}"

            # Return a degraded result rather than crashing
            result = DocumentVerificationResult(
                is_valid=True,  # Allow pipeline to continue
                status=VerificationStatus.VERIFIED,
                message="Document verification encountered an error but pipeline continues with reduced confidence.",
                details=[f"Error: {e}"],
                documents_found=[],
                documents_required=[],
            )
            return result, self._finalize_step(step, start_time)

    async def _classify_document(self, doc: DocumentMeta) -> dict[str, Any]:
        """Classify a single document using vision model or metadata."""
        # If test-case metadata provides the type directly, use it
        if doc.actual_type:
            quality = doc.quality or "GOOD"
            patient_name = doc.patient_name_on_doc

            # If content is provided (test case), extract patient name from it
            if doc.content and not patient_name:
                patient_name = doc.content.get("patient_name")

            return {
                "file_id": doc.file_id,
                "file_name": doc.file_name,
                "detected_type": doc.actual_type,
                "quality": quality,
                "patient_name": patient_name,
                "confidence": 0.95,
                "llm_calls": 0,
                "tokens": 0,
            }

        # Use vision model for real uploaded files
        if doc.file_path:
            image_b64 = file_to_base64(doc.file_path)
            if image_b64:
                try:
                    result = await self.llm.call_vision_model(
                        system_prompt=DOC_VERIFICATION_SYSTEM,
                        user_prompt=DOC_VERIFICATION_USER,
                        image_base64=image_b64,
                    )
                    return {
                        "file_id": doc.file_id,
                        "file_name": doc.file_name,
                        "detected_type": result.get("detected_type", "UNKNOWN"),
                        "quality": result.get("quality", "GOOD"),
                        "patient_name": result.get("patient_name"),
                        "confidence": result.get("confidence", 0.5),
                        "llm_calls": 1,
                        "tokens": 0,
                    }
                except Exception as e:
                    logger.warning(f"Vision model failed for {doc.file_name}: {e}")

        # Fallback: classify by filename heuristics
        return {
            "file_id": doc.file_id,
            "file_name": doc.file_name,
            "detected_type": self._guess_type_from_filename(doc.file_name),
            "quality": "GOOD",
            "patient_name": None,
            "confidence": 0.3,
            "llm_calls": 0,
            "tokens": 0,
        }

    @staticmethod
    def _guess_type_from_filename(filename: str) -> str:
        """Heuristic fallback for document type classification."""
        name = filename.lower()
        if "prescription" in name or "rx" in name:
            return "PRESCRIPTION"
        if "bill" in name or "invoice" in name or "receipt" in name:
            return "HOSPITAL_BILL"
        if "lab" in name or "report" in name or "diagnostic" in name:
            return "LAB_REPORT"
        if "pharmacy" in name:
            return "PHARMACY_BILL"
        return "UNKNOWN"

    @staticmethod
    def _build_wrong_type_message(
        classified: list[dict],
        required: list[str],
        missing: list[str],
        category: ClaimCategory,
    ) -> str:
        uploaded_desc = ", ".join(
            f"'{d['file_name']}' (detected as {d['detected_type']})" for d in classified
        )
        missing_desc = ", ".join(missing)
        return (
            f"Document verification failed for your {category.value} claim. "
            f"You uploaded: {uploaded_desc}. "
            f"However, a {category.value} claim requires: {', '.join(required)}. "
            f"Missing document type(s): {missing_desc}. "
            f"Please upload the correct documents and resubmit."
        )

    @staticmethod
    def _build_unreadable_message(unreadable: list[dict]) -> str:
        names = ", ".join(f"'{d['file_name']}'" for d in unreadable)
        return (
            f"The following document(s) cannot be read: {names}. "
            f"Please re-upload a clear, well-lit photo or scan of each document. "
            f"Ensure the entire document is visible and text is legible."
        )

    @staticmethod
    def _build_mismatch_message(classified: list[dict], unique_names: list[str]) -> str:
        doc_details = "; ".join(
            f"'{d['file_name']}' ({d['detected_type']}) shows patient name '{d.get('patient_name', 'unknown')}'"
            for d in classified
        )
        return (
            f"Patient name mismatch detected across your documents. "
            f"The documents show different patient names: {', '.join(unique_names)}. "
            f"Details: {doc_details}. "
            f"All documents for a claim must belong to the same patient. "
            f"Please verify and resubmit with matching documents."
        )

    @staticmethod
    def _finalize_step(step: AgentStep, start_time: float) -> AgentStep:
        from datetime import datetime
        step.completed_at = datetime.utcnow().isoformat()
        step.duration_ms = (time.time() - start_time) * 1000
        return step
