"""
Agent 4 — Fraud Detector
Uses Llama 3.3 70B (text) to detect potential fraud signals.
Analyzes claim patterns, document consistency, and claim history.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

from app.models.claim import ClaimCategory
from app.models.document import ExtractedDocument
from app.models.policy import PolicyTerms
from app.models.trace import AgentName, AgentStep, FailureRecord, StepStatus
from app.services.llm_client import LLMClient
from app.utils.confidence import ConfidenceTracker
from app.utils.prompts import FRAUD_DETECTOR_SYSTEM, FRAUD_DETECTOR_USER
from app.config import settings

logger = logging.getLogger(__name__)


class FraudCheckResult:
    """Structured result from fraud detection."""

    def __init__(self):
        self.fraud_score: float = 0.0
        self.risk_level: str = "LOW"
        self.signals: list[dict[str, str]] = []
        self.recommend_manual_review: bool = False
        self.recommendation_reason: str = ""
        self.same_day_exceeded: bool = False
        self.monthly_exceeded: bool = False
        self.high_value: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "fraud_score": self.fraud_score,
            "risk_level": self.risk_level,
            "signals": self.signals,
            "recommend_manual_review": self.recommend_manual_review,
            "recommendation_reason": self.recommendation_reason,
            "same_day_exceeded": self.same_day_exceeded,
            "monthly_exceeded": self.monthly_exceeded,
            "high_value": self.high_value,
        }


class FraudDetector:
    """Agent 4: Detects potential fraud signals in claims."""

    def __init__(self, llm_client: LLMClient, policy: PolicyTerms):
        self.llm = llm_client
        self.policy = policy

    async def detect(
        self,
        member_id: str,
        claim_category: ClaimCategory,
        treatment_date: str,
        claimed_amount: float,
        hospital_name: Optional[str],
        extracted_docs: list[ExtractedDocument],
        claims_history: Optional[list[dict[str, Any]]],
        confidence: ConfidenceTracker,
    ) -> tuple[FraudCheckResult, AgentStep]:
        """
        Analyze a claim for fraud signals.
        Uses deterministic checks + LLM reasoning.
        """
        start_time = time.time()
        step = AgentStep(
            agent=AgentName.FRAUD_DETECTOR,
            status=StepStatus.SUCCESS,
            confidence_before=confidence.score,
            input_summary=f"Fraud check for {member_id}, ₹{claimed_amount}",
        )

        result = FraudCheckResult()

        try:
            thresholds = self.policy.fraud_thresholds

            # ── 1. Same-day claims check ─────────────────
            same_day_count = 0
            if claims_history:
                same_day_count = sum(
                    1 for c in claims_history
                    if c.get("date") == treatment_date
                )

            if same_day_count >= thresholds.same_day_claims_limit:
                result.same_day_exceeded = True
                result.signals.append({
                    "signal": f"Member has {same_day_count + 1} claims on the same day ({treatment_date}), "
                              f"exceeding the limit of {thresholds.same_day_claims_limit}",
                    "severity": "HIGH",
                    "evidence": f"Previous same-day claims: {json.dumps(claims_history)}",
                })
                result.fraud_score = max(result.fraud_score, 0.85)
                result.recommend_manual_review = True
                result.recommendation_reason = (
                    f"Unusual same-day claim pattern detected: {same_day_count + 1} claims "
                    f"on {treatment_date}, exceeding the limit of {thresholds.same_day_claims_limit}. "
                    f"Previous claims were at different providers, which is suspicious."
                )
                confidence.deduct(settings.confidence_deduct_fraud_same_day, f"Same-day claims exceeded ({same_day_count + 1} claims)")

            # ── 2. High-value claim check ────────────────
            if claimed_amount >= thresholds.high_value_claim_threshold:
                result.high_value = True
                result.signals.append({
                    "signal": f"High-value claim: ₹{claimed_amount:,.0f} (threshold: ₹{thresholds.high_value_claim_threshold:,.0f})",
                    "severity": "MEDIUM",
                    "evidence": f"Claimed amount exceeds high-value threshold",
                })
                result.fraud_score = max(result.fraud_score, 0.5)
                if claimed_amount >= thresholds.auto_manual_review_above:
                    result.recommend_manual_review = True
                    if not result.recommendation_reason:
                        result.recommendation_reason = (
                            f"Claim amount ₹{claimed_amount:,.0f} exceeds auto-review threshold "
                            f"of ₹{thresholds.auto_manual_review_above:,.0f}"
                        )

            # ── 3. Document consistency check ────────────
            doc_observations = self._check_document_consistency(extracted_docs)
            if doc_observations:
                for obs in doc_observations:
                    result.signals.append(obs)
                    if obs["severity"] == "HIGH":
                        result.fraud_score = max(result.fraud_score, 0.7)
                        confidence.deduct(settings.confidence_deduct_doc_inconsistency, f"Document inconsistency: {obs['signal']}")

            # ── 4. Set risk level ────────────────────────
            if result.fraud_score >= 0.8:
                result.risk_level = "CRITICAL"
            elif result.fraud_score >= 0.6:
                result.risk_level = "HIGH"
            elif result.fraud_score >= 0.3:
                result.risk_level = "MEDIUM"
            else:
                result.risk_level = "LOW"

            # ── 5. LLM-based reasoning (optional) ───────
            if result.signals:
                try:
                    diagnosis = None
                    for doc in extracted_docs:
                        if doc.diagnosis:
                            diagnosis = doc.diagnosis
                            break

                    llm_result = await self._llm_fraud_check(
                        member_id, claim_category, treatment_date,
                        claimed_amount, hospital_name, diagnosis,
                        claims_history, doc_observations, thresholds,
                    )
                    step.llm_calls = 1

                    # Merge LLM insights
                    if llm_result.get("recommend_manual_review"):
                        result.recommend_manual_review = True
                    if llm_result.get("recommendation_reason") and not result.recommendation_reason:
                        result.recommendation_reason = llm_result["recommendation_reason"]

                except Exception as e:
                    logger.warning(f"LLM fraud check failed: {e}")
                    confidence.deduct(settings.confidence_deduct_llm_fallback, "LLM fraud reasoning unavailable")

            step.output_summary = (
                f"Fraud score: {result.fraud_score:.2f}, "
                f"Risk: {result.risk_level}, "
                f"Signals: {len(result.signals)}, "
                f"Manual review: {result.recommend_manual_review}"
            )
            step.output_data = result.to_dict()
            step.confidence_after = confidence.score
            return result, self._finalize_step(step, start_time)

        except Exception as e:
            logger.error(f"Fraud detection failed: {e}")
            step.status = StepStatus.FAILED
            step.failure = FailureRecord(
                agent=AgentName.FRAUD_DETECTOR,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            confidence.deduct(settings.confidence_deduct_fraud_agent_error, f"Fraud detector failed: {e}")
            step.confidence_after = confidence.score
            step.output_summary = f"FAILED: {e}"
            return result, self._finalize_step(step, start_time)

    @staticmethod
    def _check_document_consistency(docs: list[ExtractedDocument]) -> list[dict]:
        """Check for document consistency issues."""
        observations = []

        # Check patient name consistency
        names = [d.patient_name for d in docs if d.patient_name]
        if len(set(n.lower().strip() for n in names)) > 1:
            observations.append({
                "signal": f"Different patient names across documents: {list(set(names))}",
                "severity": "HIGH",
                "evidence": "Patient name mismatch",
            })

        # Check date consistency
        dates = [d.date for d in docs if d.date]
        if len(set(dates)) > 1:
            observations.append({
                "signal": f"Different dates across documents: {list(set(dates))}",
                "severity": "MEDIUM",
                "evidence": "Date mismatch across documents",
            })

        # Check for extraction warnings
        for doc in docs:
            if doc.extraction_warnings:
                observations.append({
                    "signal": f"Extraction warnings on {doc.file_id}: {doc.extraction_warnings}",
                    "severity": "LOW",
                    "evidence": "Document quality issues",
                })

        return observations

    async def _llm_fraud_check(
        self, member_id, category, treatment_date, amount,
        hospital_name, diagnosis, claims_history, doc_observations,
        thresholds,
    ) -> dict:
        """Use LLM for deeper fraud reasoning."""
        prompt = FRAUD_DETECTOR_USER.format(
            member_id=member_id,
            claim_category=category.value,
            treatment_date=treatment_date,
            claimed_amount=amount,
            hospital_name=hospital_name or "Not specified",
            diagnosis=diagnosis or "Not specified",
            claims_history=json.dumps(claims_history or [], indent=2),
            same_day_limit=thresholds.same_day_claims_limit,
            monthly_limit=thresholds.monthly_claims_limit,
            high_value_threshold=thresholds.high_value_claim_threshold,
            auto_review_above=thresholds.auto_manual_review_above,
            document_observations=json.dumps(doc_observations, indent=2),
        )

        return await self.llm.call_text_model(
            system_prompt=FRAUD_DETECTOR_SYSTEM,
            user_prompt=prompt,
        )

    @staticmethod
    def _finalize_step(step: AgentStep, start_time: float) -> AgentStep:
        from datetime import datetime
        step.completed_at = datetime.utcnow().isoformat()
        step.duration_ms = (time.time() - start_time) * 1000
        return step
