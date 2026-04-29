"""
Orchestrator — Master pipeline coordinator.
Runs all 5 agents in sequence, handles failures gracefully,
and produces the final ClaimDecision with full ClaimTrace.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Optional

from app.agents.decision_maker import DecisionMaker
from app.agents.doc_parser import DocParser
from app.agents.doc_verifier import DocVerifier
from app.agents.fraud_detector import FraudDetector
from app.agents.policy_checker import PolicyChecker
from app.models.claim import (
    ClaimCategory,
    ClaimDecision,
    ClaimDecisionType,
    ClaimRecord,
    ClaimStatus,
    DocumentMeta,
)
from app.models.document import DocumentVerificationResult, VerificationStatus
from app.models.policy import PolicyTerms
from app.models.trace import AgentName, AgentStep, ClaimTrace, FailureRecord, StepStatus
from app.config import settings
from app.services.llm_client import LLMClient
from app.utils.confidence import ConfidenceTracker

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Master pipeline coordinator.
    Runs: DocVerifier → DocParser → PolicyChecker → FraudDetector → DecisionMaker
    """

    def __init__(self, llm_client: LLMClient, policy: PolicyTerms):
        self.llm = llm_client
        self.policy = policy
        self.doc_verifier = DocVerifier(llm_client, policy)
        self.doc_parser = DocParser(llm_client)
        self.policy_checker = PolicyChecker(llm_client, policy)
        self.fraud_detector = FraudDetector(llm_client, policy)
        self.decision_maker = DecisionMaker(llm_client)

    async def process_claim(self, record: ClaimRecord) -> tuple[ClaimDecision, ClaimTrace]:
        """
        Run the full 5-agent pipeline for a claim.
        Returns (decision, trace) with full observability.
        """
        start_time = time.time()
        claim_id = record.claim_id
        logger.info(f"[{claim_id}] Starting pipeline for {record.member_id}")

        # Initialize trace and confidence
        trace = ClaimTrace(claim_id=claim_id)
        confidence = ConfidenceTracker(initial=settings.initial_confidence)

        # Look up member
        member = self.policy.get_member(record.member_id)
        member_name = member.name if member else record.member_id

        # ═══════════════════════════════════════════════════
        # AGENT 1: Document Verification
        # ═══════════════════════════════════════════════════
        logger.info(f"[{claim_id}] Agent 1: Document Verification")

        if record.simulate_component_failure:
            # Simulate failure for TC011
            step = AgentStep(
                agent=AgentName.DOC_VERIFIER,
                status=StepStatus.FAILED,
                confidence_before=confidence.score,
                input_summary="Simulated component failure",
                output_summary="FAILED: Simulated component failure for testing",
            )
            step.failure = FailureRecord(
                agent=AgentName.DOC_VERIFIER,
                error_type="SimulatedFailure",
                error_message="Component failure simulated for testing graceful degradation",
                recoverable=True,
            )
            confidence.deduct(settings.confidence_deduct_component_failure, "Component failure (simulated) -- doc verification skipped")
            step.confidence_after = confidence.score
            step.completed_at = datetime.utcnow().isoformat()
            trace.add_step(step)
            trace.degradation_notes.append("Document verification was skipped due to component failure")

            # Create a permissive verification result
            verification_result = DocumentVerificationResult(
                is_valid=True,
                status=VerificationStatus.VERIFIED,
                message="Verification skipped due to component failure — proceeding with reduced confidence",
                details=["Component failure simulated"],
                documents_found=[],
                documents_required=[],
            )
        else:
            verification_result, ver_step = await self.doc_verifier.verify(
                documents=record.documents,
                claim_category=record.claim_category,
                member_name=member_name,
                confidence=confidence,
            )
            trace.add_step(ver_step)

        # If verification failed, stop pipeline early
        if not verification_result.is_valid:
            logger.info(f"[{claim_id}] Document verification failed — stopping pipeline")
            decision = ClaimDecision(
                claim_id=claim_id,
                member_id=record.member_id,
                decision=ClaimDecisionType.REJECTED,
                claimed_amount=record.claimed_amount,
                approved_amount=0,
                confidence_score=confidence.score,
                reasons=[verification_result.message],
                notes=f"Claim stopped at document verification. {' | '.join(verification_result.details)}",
                processing_time_ms=(time.time() - start_time) * 1000,
            )
            trace.completed_at = datetime.utcnow().isoformat()
            trace.total_duration_ms = (time.time() - start_time) * 1000
            return decision, trace

        # ═══════════════════════════════════════════════════
        # AGENT 2: Document Parsing
        # ═══════════════════════════════════════════════════
        logger.info(f"[{claim_id}] Agent 2: Document Parsing")
        extracted_docs, parse_step = await self.doc_parser.parse(
            documents=record.documents,
            claim_category=record.claim_category,
            confidence=confidence,
        )
        trace.add_step(parse_step)

        # ═══════════════════════════════════════════════════
        # AGENT 3: Policy Checking
        # ═══════════════════════════════════════════════════
        logger.info(f"[{claim_id}] Agent 3: Policy Checking")
        policy_result, policy_step = await self.policy_checker.check(
            member_id=record.member_id,
            claim_category=record.claim_category,
            treatment_date=record.treatment_date,
            claimed_amount=record.claimed_amount,
            hospital_name=record.hospital_name,
            extracted_docs=extracted_docs,
            ytd_claims_amount=record.ytd_claims_amount,
            confidence=confidence,
        )
        trace.add_step(policy_step)

        # ═══════════════════════════════════════════════════
        # AGENT 4: Fraud Detection
        # ═══════════════════════════════════════════════════
        logger.info(f"[{claim_id}] Agent 4: Fraud Detection")
        fraud_result, fraud_step = await self.fraud_detector.detect(
            member_id=record.member_id,
            claim_category=record.claim_category,
            treatment_date=record.treatment_date,
            claimed_amount=record.claimed_amount,
            hospital_name=record.hospital_name,
            extracted_docs=extracted_docs,
            claims_history=record.claims_history,
            confidence=confidence,
        )
        trace.add_step(fraud_step)

        # ═══════════════════════════════════════════════════
        # AGENT 5: Final Decision
        # ═══════════════════════════════════════════════════
        logger.info(f"[{claim_id}] Agent 5: Decision Maker")
        decision, decision_step = await self.decision_maker.decide(
            claim_id=claim_id,
            member_id=record.member_id,
            member_name=member_name,
            claim_category=record.claim_category,
            treatment_date=record.treatment_date,
            claimed_amount=record.claimed_amount,
            verification_result=verification_result,
            extracted_docs=extracted_docs,
            policy_result=policy_result,
            fraud_result=fraud_result,
            trace=trace,
            confidence=confidence,
        )
        trace.add_step(decision_step)

        # Finalize
        decision.processing_time_ms = (time.time() - start_time) * 1000
        trace.completed_at = datetime.utcnow().isoformat()
        trace.total_duration_ms = decision.processing_time_ms

        logger.info(
            f"[{claim_id}] Pipeline complete: {decision.decision.value} "
            f"₹{decision.approved_amount:,.0f} "
            f"(confidence: {decision.confidence_score:.2f}, "
            f"time: {decision.processing_time_ms:.0f}ms)"
        )

        return decision, trace
