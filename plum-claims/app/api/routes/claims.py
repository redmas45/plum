"""
Claims API routes:
  POST /claims/submit     — Submit a new claim (with file uploads or JSON test data)
  GET  /claims/{id}       — Get claim by ID with decision and trace
  GET  /claims/list       — List all claims
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.agents.orchestrator import Orchestrator
from app.api.dependencies import get_llm_client, get_policy
from app.models.claim import (
    ClaimCategory,
    ClaimDecision,
    ClaimRecord,
    ClaimStatus,
    DocumentMeta,
)
from app.services import claim_store
from app.services.file_handler import validate_and_store_file
from app.services.llm_client import LLMClient
from app.models.policy import PolicyTerms
from app.utils.exceptions import ClaimException

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/claims", tags=["Claims"])


@router.post("/submit")
async def submit_claim(
    member_id: str = Form(...),
    claim_category: str = Form(...),
    treatment_date: str = Form(...),
    claimed_amount: float = Form(...),
    policy_id: str = Form("PLUM_GHI_2024"),
    hospital_name: Optional[str] = Form(None),
    ytd_claims_amount: float = Form(0.0),
    claims_history: Optional[str] = Form(None),
    simulate_component_failure: bool = Form(False),
    documents: list[UploadFile] = File(default=[]),
    # For JSON-based test case submission
    documents_json: Optional[str] = Form(None),
):
    """
    Submit a claim for processing.

    Accepts either:
    - File uploads (real documents)
    - JSON document metadata (for test cases)
    """
    try:
        policy = get_policy()
        llm = get_llm_client()

        # Parse claim category
        try:
            category = ClaimCategory(claim_category.upper())
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid claim category: {claim_category}. "
                       f"Valid categories: {[c.value for c in ClaimCategory]}",
            )

        # Build document list
        doc_metas: list[DocumentMeta] = []

        if documents_json:
            # Test case mode: documents provided as JSON
            try:
                docs_data = json.loads(documents_json)
                for d in docs_data:
                    doc_metas.append(DocumentMeta(**d))
            except (json.JSONDecodeError, Exception) as e:
                raise HTTPException(status_code=400, detail=f"Invalid documents_json: {e}")
        elif documents:
            # Real file upload mode
            for upload_file in documents:
                content = await upload_file.read()
                meta = await validate_and_store_file(
                    filename=upload_file.filename or "unknown",
                    content=content,
                    content_type=upload_file.content_type or "",
                )
                doc_metas.append(meta)

        # Parse claims history
        history = None
        if claims_history:
            try:
                history = json.loads(claims_history)
            except json.JSONDecodeError:
                pass

        # Create claim record
        record = ClaimRecord(
            member_id=member_id,
            policy_id=policy_id,
            claim_category=category,
            treatment_date=treatment_date,
            claimed_amount=claimed_amount,
            hospital_name=hospital_name,
            documents=doc_metas,
            ytd_claims_amount=ytd_claims_amount,
            claims_history=history,
            simulate_component_failure=simulate_component_failure,
        )

        # Save initial record
        record.status = ClaimStatus.PROCESSING
        await claim_store.save_claim(record)

        # Run the pipeline
        orchestrator = Orchestrator(llm, policy)
        decision, trace = await orchestrator.process_claim(record)

        # Update record with decision
        record.status = ClaimStatus.DECIDED
        record.decision = decision
        record.trace = trace.model_dump()
        record.decided_at = datetime.utcnow().isoformat()
        await claim_store.save_claim(record)

        logger.info(f"Claim {record.claim_id} processed: {decision.decision.value}")

        return {
            "claim_id": record.claim_id,
            "status": record.status.value,
            "decision": decision.model_dump(),
            "trace": trace.model_dump(),
        }

    except HTTPException:
        raise
    except ClaimException as e:
        logger.error(f"Claim error: {e}")
        raise HTTPException(status_code=400, detail={"error": e.code, "message": e.message, "details": e.details})
    except Exception as e:
        logger.error(f"Unexpected error processing claim: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")


@router.get("/list")
async def list_claims_endpoint(
    member_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """List claims with optional filters."""
    try:
        claims = await claim_store.list_claims(
            member_id=member_id,
            status=status,
            limit=limit,
            offset=offset,
        )
        total = await claim_store.count_claims(member_id=member_id)

        return {
            "claims": [
                {
                    "claim_id": c.claim_id,
                    "member_id": c.member_id,
                    "claim_category": c.claim_category.value,
                    "treatment_date": c.treatment_date,
                    "claimed_amount": c.claimed_amount,
                    "status": c.status.value,
                    "decision": c.decision.model_dump() if c.decision else None,
                    "submitted_at": c.submitted_at,
                    "decided_at": c.decided_at,
                }
                for c in claims
            ],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    except Exception as e:
        logger.error(f"Error listing claims: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{claim_id}")
async def get_claim_endpoint(claim_id: str):
    """Get a claim by ID with full decision and trace."""
    claim = await claim_store.get_claim(claim_id)
    if not claim:
        raise HTTPException(status_code=404, detail=f"Claim '{claim_id}' not found")

    return {
        "claim_id": claim.claim_id,
        "member_id": claim.member_id,
        "policy_id": claim.policy_id,
        "claim_category": claim.claim_category.value,
        "treatment_date": claim.treatment_date,
        "claimed_amount": claim.claimed_amount,
        "hospital_name": claim.hospital_name,
        "status": claim.status.value,
        "decision": claim.decision.model_dump() if claim.decision else None,
        "trace": claim.trace,
        "documents": [d.model_dump() for d in claim.documents],
        "submitted_at": claim.submitted_at,
        "decided_at": claim.decided_at,
    }
