"""
Pydantic models for documents: extracted data and verification results.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    PRESCRIPTION = "PRESCRIPTION"
    HOSPITAL_BILL = "HOSPITAL_BILL"
    LAB_REPORT = "LAB_REPORT"
    PHARMACY_BILL = "PHARMACY_BILL"
    DIAGNOSTIC_REPORT = "DIAGNOSTIC_REPORT"
    DISCHARGE_SUMMARY = "DISCHARGE_SUMMARY"
    DENTAL_REPORT = "DENTAL_REPORT"
    UNKNOWN = "UNKNOWN"


class DocumentQuality(str, Enum):
    GOOD = "GOOD"
    FAIR = "FAIR"
    POOR = "POOR"
    UNREADABLE = "UNREADABLE"


class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    WRONG_TYPE = "WRONG_TYPE"
    UNREADABLE = "UNREADABLE"
    PATIENT_MISMATCH = "PATIENT_MISMATCH"
    MISSING_REQUIRED = "MISSING_REQUIRED"


class ExtractedLineItem(BaseModel):
    description: str
    amount: float
    quantity: int = 1
    rate: Optional[float] = None


class ExtractedDocument(BaseModel):
    """Structured data extracted from a medical document by the parsing agent."""
    file_id: str
    detected_type: DocumentType
    quality: DocumentQuality = DocumentQuality.GOOD
    confidence: float = 1.0

    # Common fields
    patient_name: Optional[str] = None
    date: Optional[str] = None
    hospital_name: Optional[str] = None

    # Prescription fields
    doctor_name: Optional[str] = None
    doctor_registration: Optional[str] = None
    doctor_specialization: Optional[str] = None
    diagnosis: Optional[str] = None
    medicines: list[str] = Field(default_factory=list)
    tests_ordered: list[str] = Field(default_factory=list)

    # Bill fields
    line_items: list[ExtractedLineItem] = Field(default_factory=list)
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    total: Optional[float] = None
    bill_number: Optional[str] = None

    # Lab report fields
    test_results: list[dict[str, Any]] = Field(default_factory=list)
    lab_name: Optional[str] = None
    pathologist_name: Optional[str] = None
    remarks: Optional[str] = None

    # Pharmacy fields
    pharmacy_name: Optional[str] = None
    drug_license: Optional[str] = None
    discount: Optional[float] = None

    # Raw extraction (for audit)
    raw_extraction: Optional[dict[str, Any]] = None
    extraction_warnings: list[str] = Field(default_factory=list)


class DocumentVerificationResult(BaseModel):
    """Result of document verification for a claim."""
    is_valid: bool
    status: VerificationStatus
    message: str
    details: list[str] = Field(default_factory=list)
    documents_found: list[dict[str, str]] = Field(default_factory=list)
    documents_required: list[str] = Field(default_factory=list)
    documents_missing: list[str] = Field(default_factory=list)
