"""
Agent 2 — Document Parser
Uses Llama 4 Scout (VISION) to extract structured data from medical documents.
Handles prescriptions, hospital bills, lab reports, and pharmacy bills.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.models.claim import ClaimCategory, DocumentMeta
from app.models.document import (
    DocumentQuality,
    DocumentType,
    ExtractedDocument,
    ExtractedLineItem,
)
from app.models.trace import AgentName, AgentStep, FailureRecord, StepStatus
from app.services.file_handler import file_to_base64
from app.services.llm_client import LLMClient
from app.utils.confidence import ConfidenceTracker
from app.utils.prompts import (
    DOC_PARSER_SYSTEM,
    DOC_PARSER_PRESCRIPTION,
    DOC_PARSER_BILL,
    DOC_PARSER_LAB_REPORT,
    DOC_PARSER_PHARMACY_BILL,
)

logger = logging.getLogger(__name__)


class DocParser:
    """Agent 2: Extracts structured information from medical documents."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def parse(
        self,
        documents: list[DocumentMeta],
        claim_category: ClaimCategory,
        confidence: ConfidenceTracker,
    ) -> tuple[list[ExtractedDocument], AgentStep]:
        """
        Parse all documents and extract structured data.

        Returns:
            (list_of_extracted_documents, agent_step) for tracing
        """
        start_time = time.time()
        step = AgentStep(
            agent=AgentName.DOC_PARSER,
            status=StepStatus.SUCCESS,
            confidence_before=confidence.score,
            input_summary=f"Parsing {len(documents)} docs for {claim_category.value}",
        )

        extracted: list[ExtractedDocument] = []
        total_llm_calls = 0
        total_tokens = 0

        try:
            for doc in documents:
                try:
                    ext_doc = await self._parse_single_document(doc)
                    extracted.append(ext_doc)
                    total_llm_calls += 1

                    # Deduct confidence for low-quality extractions
                    if ext_doc.confidence < 0.5:
                        confidence.deduct(
                            0.1,
                            f"Low extraction confidence ({ext_doc.confidence:.2f}) for {doc.file_name}",
                        )
                except Exception as e:
                    logger.warning(f"Failed to parse document {doc.file_name}: {e}")
                    # Create a minimal extraction from metadata
                    ext_doc = self._fallback_extraction(doc)
                    extracted.append(ext_doc)
                    confidence.deduct(0.15, f"Document parsing failed for {doc.file_name}: {e}")

            step.llm_calls = total_llm_calls
            step.tokens_used = total_tokens
            step.output_summary = f"Parsed {len(extracted)} documents"
            step.output_data = {
                "documents": [d.model_dump() for d in extracted],
                "total_line_items": sum(len(d.line_items) for d in extracted),
            }
            step.confidence_after = confidence.score
            return extracted, self._finalize_step(step, start_time)

        except Exception as e:
            logger.error(f"Document parsing pipeline failed: {e}")
            step.status = StepStatus.FAILED
            step.failure = FailureRecord(
                agent=AgentName.DOC_PARSER,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            confidence.deduct(0.25, f"Doc parser agent failed: {e}")
            step.confidence_after = confidence.score
            step.output_summary = f"FAILED: {e}"

            # Return whatever we extracted so far
            return extracted, self._finalize_step(step, start_time)

    async def _parse_single_document(self, doc: DocumentMeta) -> ExtractedDocument:
        """Parse a single document using vision model or pre-provided content."""
        # If content is already provided (test case), use it directly
        if doc.content:
            return self._build_from_content(doc)

        # Use vision model for real files
        if doc.file_path:
            image_b64 = file_to_base64(doc.file_path)
            if image_b64:
                prompt = self._get_parser_prompt(doc.actual_type or "UNKNOWN")
                result = await self.llm.call_vision_model(
                    system_prompt=DOC_PARSER_SYSTEM,
                    user_prompt=prompt,
                    image_base64=image_b64,
                )
                return self._build_from_llm_result(doc, result)

        # Fallback
        return self._fallback_extraction(doc)

    def _build_from_content(self, doc: DocumentMeta) -> ExtractedDocument:
        """Build ExtractedDocument from pre-provided test case content."""
        content = doc.content or {}
        doc_type = DocumentType(doc.actual_type) if doc.actual_type and doc.actual_type in DocumentType.__members__ else DocumentType.UNKNOWN
        quality = DocumentQuality(doc.quality) if doc.quality and doc.quality in DocumentQuality.__members__ else DocumentQuality.GOOD

        line_items = []
        for item in content.get("line_items", []):
            line_items.append(ExtractedLineItem(
                description=item.get("description", ""),
                amount=item.get("amount", 0),
                quantity=item.get("quantity", 1),
                rate=item.get("rate"),
            ))

        return ExtractedDocument(
            file_id=doc.file_id,
            detected_type=doc_type,
            quality=quality,
            confidence=0.95 if quality == DocumentQuality.GOOD else 0.5,
            patient_name=content.get("patient_name", doc.patient_name_on_doc),
            date=content.get("date"),
            hospital_name=content.get("hospital_name"),
            doctor_name=content.get("doctor_name"),
            doctor_registration=content.get("doctor_registration"),
            doctor_specialization=content.get("doctor_specialization"),
            diagnosis=content.get("diagnosis"),
            medicines=content.get("medicines", []),
            tests_ordered=content.get("tests_ordered", []),
            line_items=line_items,
            total=content.get("total"),
            bill_number=content.get("bill_number"),
            lab_name=content.get("lab_name"),
            test_results=content.get("test_results", []),
            pharmacy_name=content.get("pharmacy_name"),
            raw_extraction=content,
        )

    def _build_from_llm_result(self, doc: DocumentMeta, result: dict) -> ExtractedDocument:
        """Build ExtractedDocument from LLM vision model output."""
        doc_type = DocumentType(doc.actual_type) if doc.actual_type and doc.actual_type in DocumentType.__members__ else DocumentType.UNKNOWN

        line_items = []
        for item in result.get("line_items", []):
            line_items.append(ExtractedLineItem(
                description=item.get("description", ""),
                amount=float(item.get("amount", 0)),
                quantity=int(item.get("quantity", 1)),
                rate=float(item.get("rate")) if item.get("rate") else None,
            ))

        medicines_raw = result.get("medicines", [])
        medicines = []
        if isinstance(medicines_raw, list):
            for m in medicines_raw:
                if isinstance(m, dict):
                    medicines.append(m.get("name", str(m)))
                else:
                    medicines.append(str(m))

        return ExtractedDocument(
            file_id=doc.file_id,
            detected_type=doc_type,
            quality=DocumentQuality.GOOD,
            confidence=result.get("extraction_confidence", 0.7),
            patient_name=result.get("patient_name"),
            date=result.get("date") or result.get("report_date"),
            hospital_name=result.get("hospital_name"),
            doctor_name=result.get("doctor_name") or result.get("referring_doctor"),
            doctor_registration=result.get("doctor_registration") or result.get("pathologist_registration"),
            doctor_specialization=result.get("doctor_specialization"),
            diagnosis=result.get("diagnosis"),
            medicines=medicines,
            tests_ordered=result.get("tests_ordered", []),
            line_items=line_items,
            subtotal=result.get("subtotal"),
            tax=result.get("tax"),
            total=result.get("total") or result.get("net_amount"),
            bill_number=result.get("bill_number"),
            lab_name=result.get("lab_name"),
            pathologist_name=result.get("pathologist_name"),
            test_results=result.get("test_results", []),
            remarks=result.get("remarks"),
            pharmacy_name=result.get("pharmacy_name"),
            drug_license=result.get("drug_license"),
            discount=result.get("discount"),
            raw_extraction=result,
            extraction_warnings=result.get("warnings", []),
        )

    @staticmethod
    def _fallback_extraction(doc: DocumentMeta) -> ExtractedDocument:
        """Create minimal extraction when parsing fails."""
        doc_type = DocumentType(doc.actual_type) if doc.actual_type and doc.actual_type in DocumentType.__members__ else DocumentType.UNKNOWN
        return ExtractedDocument(
            file_id=doc.file_id,
            detected_type=doc_type,
            quality=DocumentQuality.POOR,
            confidence=0.2,
            patient_name=doc.patient_name_on_doc,
            extraction_warnings=["Extraction failed — using fallback with minimal data"],
        )

    @staticmethod
    def _get_parser_prompt(doc_type: str) -> str:
        """Get the right parser prompt for the document type."""
        prompts = {
            "PRESCRIPTION": DOC_PARSER_PRESCRIPTION,
            "HOSPITAL_BILL": DOC_PARSER_BILL,
            "LAB_REPORT": DOC_PARSER_LAB_REPORT,
            "DIAGNOSTIC_REPORT": DOC_PARSER_LAB_REPORT,
            "PHARMACY_BILL": DOC_PARSER_PHARMACY_BILL,
        }
        return prompts.get(doc_type, DOC_PARSER_BILL)

    @staticmethod
    def _finalize_step(step: AgentStep, start_time: float) -> AgentStep:
        from datetime import datetime
        step.completed_at = datetime.utcnow().isoformat()
        step.duration_ms = (time.time() - start_time) * 1000
        return step
