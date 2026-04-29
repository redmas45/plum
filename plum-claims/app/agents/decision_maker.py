"""
Agent 5 — Decision Maker
Uses Llama 3.3 70B (text) to synthesize all agent outputs into a final claim decision.
Produces APPROVED, PARTIAL, REJECTED, or MANUAL_REVIEW decisions.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from app.agents.fraud_detector import FraudCheckResult
from app.agents.policy_checker import PolicyCheckResult
from app.models.claim import ClaimCategory, ClaimDecision, ClaimDecisionType, LineItemDecision
from app.models.document import DocumentVerificationResult, ExtractedDocument
from app.models.trace import AgentName, AgentStep, ClaimTrace, FailureRecord, StepStatus
from app.services.llm_client import LLMClient
from app.utils.confidence import ConfidenceTracker
from app.utils.prompts import DECISION_MAKER_SYSTEM, DECISION_MAKER_USER

logger = logging.getLogger(__name__)


class DecisionMaker:
    """Agent 5: Makes the final claim decision."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def decide(
        self,
        claim_id: str,
        member_id: str,
        member_name: str,
        claim_category: ClaimCategory,
        treatment_date: str,
        claimed_amount: float,
        verification_result: DocumentVerificationResult,
        extracted_docs: list[ExtractedDocument],
        policy_result: PolicyCheckResult,
        fraud_result: FraudCheckResult,
        trace: ClaimTrace,
        confidence: ConfidenceTracker,
    ) -> tuple[ClaimDecision, AgentStep]:
        """
        Make the final decision by synthesizing all agent outputs.
        """
        start_time = time.time()
        step = AgentStep(
            agent=AgentName.DECISION_MAKER,
            status=StepStatus.SUCCESS,
            confidence_before=confidence.score,
            input_summary=f"Final decision for {claim_id}",
        )

        try:
            # ── Determine decision based on agent outputs ──

            # If documents failed verification, stop early
            if not verification_result.is_valid:
                decision = ClaimDecision(
                    claim_id=claim_id,
                    member_id=member_id,
                    decision=ClaimDecisionType.REJECTED,
                    claimed_amount=claimed_amount,
                    approved_amount=0,
                    confidence_score=confidence.score,
                    reasons=[verification_result.message],
                    notes=f"Claim stopped at document verification: {verification_result.message}",
                )
                step.output_summary = f"REJECTED (doc verification): {verification_result.status.value}"
                step.output_data = decision.model_dump()
                step.confidence_after = confidence.score
                return decision, self._finalize_step(step, start_time)

            # If policy check rejected
            if not policy_result.eligible:
                decision = ClaimDecision(
                    claim_id=claim_id,
                    member_id=member_id,
                    decision=ClaimDecisionType.REJECTED,
                    claimed_amount=claimed_amount,
                    approved_amount=0,
                    confidence_score=confidence.score,
                    reasons=policy_result.rejection_reasons,
                    rejection_codes=policy_result.rejection_codes,
                    notes=f"{policy_result.waiting_period_details} {policy_result.exclusion_details}".strip(),
                )
                step.output_summary = f"REJECTED (policy): {policy_result.rejection_codes}"
                step.output_data = decision.model_dump()
                step.confidence_after = confidence.score
                return decision, self._finalize_step(step, start_time)

            # If fraud detector recommends manual review
            if fraud_result.recommend_manual_review:
                decision = ClaimDecision(
                    claim_id=claim_id,
                    member_id=member_id,
                    decision=ClaimDecisionType.MANUAL_REVIEW,
                    claimed_amount=claimed_amount,
                    approved_amount=0,
                    confidence_score=confidence.score,
                    reasons=[fraud_result.recommendation_reason],
                    notes=f"Fraud signals detected: {len(fraud_result.signals)} signal(s). "
                          f"Risk level: {fraud_result.risk_level}. "
                          f"Routing to manual review. "
                          + "; ".join(s["signal"] for s in fraud_result.signals),
                )
                step.output_summary = f"MANUAL_REVIEW: fraud score {fraud_result.fraud_score:.2f}"
                step.output_data = decision.model_dump()
                step.confidence_after = confidence.score
                return decision, self._finalize_step(step, start_time)

            # ── Normal approval path ───────────────────────

            # Check for partial approval (some line items rejected)
            rejected_items = [
                lid for lid in policy_result.line_item_decisions
                if not lid.approved
            ]
            has_approved_items = any(
                lid.approved for lid in policy_result.line_item_decisions
            )

            if rejected_items and has_approved_items:
                decision_type = ClaimDecisionType.PARTIAL
                reasons = [
                    f"Partial approval: {len(rejected_items)} line item(s) excluded"
                ]
                for lid in rejected_items:
                    reasons.append(f"Excluded: '{lid.description}' (₹{lid.amount:,.0f}) — {lid.reason}")
            elif rejected_items and not has_approved_items:
                decision_type = ClaimDecisionType.REJECTED
                reasons = [f"All line items excluded"]
            else:
                decision_type = ClaimDecisionType.APPROVED
                reasons = ["Claim meets all policy requirements"]

            # If pipeline was degraded, note it
            if trace.pipeline_degraded:
                confidence.cap(0.7, "Pipeline degraded — some components failed")
                reasons.append(
                    "Note: Some processing components encountered errors. "
                    "Manual review is recommended for verification."
                )

            # Build final notes with calculation breakdown
            notes_parts = []
            if policy_result.calculation_breakdown:
                notes_parts.append(f"Calculation: {policy_result.calculation_breakdown}")
            if policy_result.notes:
                notes_parts.append(policy_result.notes)
            if trace.pipeline_degraded:
                notes_parts.append(
                    f"Pipeline degraded: {', '.join(trace.degradation_notes) if trace.degradation_notes else 'Component failure detected'}. "
                    f"Manual review recommended."
                )

            # Use LLM for final reasoning
            try:
                llm_decision = await self._llm_decision(
                    claim_id, member_id, member_name, claim_category,
                    treatment_date, claimed_amount,
                    verification_result, extracted_docs,
                    policy_result, fraud_result, trace, confidence,
                )
                step.llm_calls = 1

                # Use LLM notes if available
                if llm_decision.get("notes"):
                    notes_parts.append(f"AI analysis: {llm_decision['notes']}")
            except Exception as e:
                logger.warning(f"LLM decision reasoning failed: {e}")
                confidence.deduct(0.05, "LLM decision reasoning unavailable")

            decision = ClaimDecision(
                claim_id=claim_id,
                member_id=member_id,
                decision=decision_type,
                claimed_amount=claimed_amount,
                approved_amount=policy_result.approved_amount,
                confidence_score=round(confidence.score, 4),
                reasons=reasons,
                line_item_decisions=policy_result.line_item_decisions,
                rejection_codes=policy_result.rejection_codes,
                notes=" | ".join(notes_parts),
            )

            step.output_summary = (
                f"{decision_type.value}: ₹{policy_result.approved_amount:,.0f} "
                f"(confidence: {confidence.score:.2f})"
            )
            step.output_data = decision.model_dump()
            step.confidence_after = confidence.score
            return decision, self._finalize_step(step, start_time)

        except Exception as e:
            logger.error(f"Decision maker failed: {e}")
            step.status = StepStatus.FAILED
            step.failure = FailureRecord(
                agent=AgentName.DECISION_MAKER,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            confidence.deduct(0.3, f"Decision maker failed: {e}")
            step.confidence_after = confidence.score
            step.output_summary = f"FAILED: {e}"

            # Return a MANUAL_REVIEW decision on failure
            decision = ClaimDecision(
                claim_id=claim_id,
                member_id=member_id,
                decision=ClaimDecisionType.MANUAL_REVIEW,
                claimed_amount=claimed_amount,
                approved_amount=0,
                confidence_score=confidence.score,
                reasons=[f"Decision maker encountered an error: {e}. Routing to manual review."],
                notes="Automatic routing to manual review due to system error.",
            )
            return decision, self._finalize_step(step, start_time)

    async def _llm_decision(
        self, claim_id, member_id, member_name, category,
        treatment_date, claimed_amount,
        verification, docs, policy, fraud, trace, confidence,
    ) -> dict:
        """Use LLM for final decision reasoning."""
        # Build summaries
        doc_ver_summary = f"Status: {verification.status.value}. {verification.message}"
        doc_parse_summary = ", ".join(
            f"{d.detected_type.value} (confidence: {d.confidence:.2f})"
            for d in docs
        ) or "No documents parsed"

        policy_summary = (
            f"Eligible: {policy.eligible}. "
            f"Approved amount: ₹{policy.approved_amount:,.0f}. "
            f"Reasons: {policy.rejection_reasons}. "
            f"Breakdown: {policy.calculation_breakdown}"
        )

        fraud_summary = (
            f"Fraud score: {fraud.fraud_score:.2f}. "
            f"Risk: {fraud.risk_level}. "
            f"Signals: {len(fraud.signals)}. "
            f"Manual review: {fraud.recommend_manual_review}"
        )

        failed_components = [
            s.agent.value for s in trace.steps if s.status == StepStatus.FAILED
        ]

        prompt = DECISION_MAKER_USER.format(
            claim_id=claim_id,
            member_name=member_name,
            member_id=member_id,
            claim_category=category.value,
            claimed_amount=claimed_amount,
            treatment_date=treatment_date,
            doc_verification_summary=doc_ver_summary,
            doc_parsing_summary=doc_parse_summary,
            policy_check_summary=policy_summary,
            fraud_detection_summary=fraud_summary,
            failed_components=", ".join(failed_components) if failed_components else "None",
            pipeline_degraded=trace.pipeline_degraded,
            current_confidence=confidence.score,
        )

        return await self.llm.call_text_model(
            system_prompt=DECISION_MAKER_SYSTEM,
            user_prompt=prompt,
        )

    @staticmethod
    def _finalize_step(step: AgentStep, start_time: float) -> AgentStep:
        from datetime import datetime
        step.completed_at = datetime.utcnow().isoformat()
        step.duration_ms = (time.time() - start_time) * 1000
        return step
