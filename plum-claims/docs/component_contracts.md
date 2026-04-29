# Component Contracts

This document defines the interfaces for the 5 agents in the pipeline. These contracts ensure that any single component can be swapped out or reimplemented without affecting the rest of the system.

---

## 1. Document Verifier (Agent 1)

**Purpose:** Validates that the uploaded documents are readable and match the required types for the claim category.

**Input:**
- `documents`: List of uploaded document metadata (names, paths, content types).
- `claim_category`: Enum (CONSULTATION, PHARMACY, etc.).
- `member_name`: String (for patient name matching).
- `confidence`: ConfidenceTracker instance.

**Output:** `DocumentVerificationResult`
```json
{
  "is_valid": boolean,
  "status": "VERIFIED|WRONG_TYPE|UNREADABLE|PATIENT_MISMATCH|MISSING_REQUIRED",
  "message": "User-friendly explanation of what went wrong",
  "details": ["Detailed technical reasons"],
  "documents_found": [{"file_name": "x.jpg", "type": "PRESCRIPTION"}],
  "documents_required": ["PRESCRIPTION", "HOSPITAL_BILL"]
}
```

**Errors Raised:** None directly. Catches internal errors, logs them, applies a confidence deduction, and returns a degraded valid state to prevent pipeline crashing.

---

## 2. Document Parser (Agent 2)

**Purpose:** Extracts structured data (JSON) from medical document images.

**Input:**
- `documents`: List of validated document metadata.
- `claim_category`: Enum.
- `confidence`: ConfidenceTracker instance.

**Output:** `List[ExtractedDocument]`
```json
[
  {
    "file_id": "string",
    "detected_type": "HOSPITAL_BILL",
    "quality": "GOOD",
    "confidence": 0.95,
    "patient_name": "string",
    "date": "YYYY-MM-DD",
    "hospital_name": "string",
    "line_items": [
      {"description": "Consultation", "amount": 1000, "quantity": 1}
    ],
    "total": 1000,
    "extraction_warnings": []
  }
]
```

**Errors Raised:** Catches LLM parsing errors. If a document fails entirely, returns a fallback extraction with low confidence.

---

## 3. Policy Checker (Agent 3)

**Purpose:** Evaluates extracted data against policy rules (limits, exclusions, waiting periods).

**Input:**
- `member_id`: String.
- `claim_category`: Enum.
- `treatment_date`: String.
- `claimed_amount`: Float.
- `hospital_name`: String.
- `extracted_docs`: List[ExtractedDocument].
- `ytd_claims_amount`: Float.
- `confidence`: ConfidenceTracker instance.

**Output:** `PolicyCheckResult`
```json
{
  "eligible": boolean,
  "rejection_reasons": ["string"],
  "rejection_codes": ["WAITING_PERIOD", "EXCLUDED_CONDITION"],
  "line_item_decisions": [
    {"description": "Item", "amount": 1000, "approved": true, "reason": "Covered"}
  ],
  "approved_amount": 900.0,
  "network_discount_amount": 0.0,
  "copay_amount": 100.0,
  "calculation_breakdown": "string",
  "notes": "string"
}
```

**Errors Raised:** None directly. Logs failures and falls back to deterministic rule sets if LLM augmentation fails.

---

## 4. Fraud Detector (Agent 4)

**Purpose:** Identifies suspicious patterns or document inconsistencies.

**Input:**
- `member_id`: String.
- `claim_category`: Enum.
- `treatment_date`: String.
- `claimed_amount`: Float.
- `hospital_name`: String.
- `extracted_docs`: List[ExtractedDocument].
- `claims_history`: List[Dict].
- `confidence`: ConfidenceTracker instance.

**Output:** `FraudCheckResult`
```json
{
  "fraud_score": 0.0 to 1.0,
  "risk_level": "LOW|MEDIUM|HIGH|CRITICAL",
  "signals": [
    {"signal": "string", "severity": "HIGH", "evidence": "string"}
  ],
  "recommend_manual_review": boolean,
  "recommendation_reason": "string"
}
```

**Errors Raised:** Handles its own errors. If it fails, applies confidence deduction and returns a neutral score.

---

## 5. Decision Maker (Agent 5)

**Purpose:** Synthesizes all previous outputs into a final actionable decision.

**Input:**
- All outputs from Agents 1-4.
- `trace`: Current ClaimTrace.
- `confidence`: Final ConfidenceTracker instance.

**Output:** `ClaimDecision`
```json
{
  "claim_id": "string",
  "member_id": "string",
  "decision": "APPROVED|PARTIAL|REJECTED|MANUAL_REVIEW",
  "claimed_amount": 1000.0,
  "approved_amount": 900.0,
  "confidence_score": 0.92,
  "reasons": ["string"],
  "rejection_codes": ["string"],
  "line_item_decisions": [],
  "notes": "Explainable summary of the entire decision process"
}
```

**Errors Raised:** If this component fails catastrophically, the Orchestrator catches it and forces a `MANUAL_REVIEW` decision to fail safely.
