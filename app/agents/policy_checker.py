"""
Agent 3 — Policy Checker
Uses Llama 3.3 70B (text) to evaluate claims against policy rules.
Handles coverage limits, waiting periods, exclusions, pre-auth, and financial calculations.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Optional

from app.models.claim import ClaimCategory, LineItemDecision
from app.models.document import ExtractedDocument
from app.models.policy import PolicyTerms
from app.models.trace import AgentName, AgentStep, FailureRecord, StepStatus
from app.services.llm_client import LLMClient
from app.utils.confidence import ConfidenceTracker
from app.utils.prompts import POLICY_CHECKER_SYSTEM, POLICY_CHECKER_USER
from app.config import settings

logger = logging.getLogger(__name__)


class PolicyCheckResult:
    """Structured result from policy checking."""

    def __init__(self):
        self.eligible: bool = True
        self.rejection_reasons: list[str] = []
        self.rejection_codes: list[str] = []
        self.line_item_decisions: list[LineItemDecision] = []
        self.approved_amount: float = 0.0
        self.network_discount_amount: float = 0.0
        self.copay_amount: float = 0.0
        self.calculation_breakdown: str = ""
        self.notes: str = ""
        self.waiting_period_details: str = ""
        self.exclusion_details: str = ""
        self.pre_auth_missing: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "eligible": self.eligible,
            "rejection_reasons": self.rejection_reasons,
            "rejection_codes": self.rejection_codes,
            "line_item_decisions": [lid.model_dump() for lid in self.line_item_decisions],
            "approved_amount": self.approved_amount,
            "network_discount_amount": self.network_discount_amount,
            "copay_amount": self.copay_amount,
            "calculation_breakdown": self.calculation_breakdown,
            "notes": self.notes,
            "waiting_period_details": self.waiting_period_details,
            "exclusion_details": self.exclusion_details,
            "pre_auth_missing": self.pre_auth_missing,
        }


class PolicyChecker:
    """Agent 3: Evaluates claim against policy terms."""

    def __init__(self, llm_client: LLMClient, policy: PolicyTerms):
        self.llm = llm_client
        self.policy = policy

    async def check(
        self,
        member_id: str,
        claim_category: ClaimCategory,
        treatment_date: str,
        claimed_amount: float,
        hospital_name: Optional[str],
        extracted_docs: list[ExtractedDocument],
        ytd_claims_amount: float,
        confidence: ConfidenceTracker,
    ) -> tuple[PolicyCheckResult, AgentStep]:
        """
        Check claim against all policy rules.
        Uses deterministic rule checks first, then LLM for complex reasoning.
        """
        start_time = time.time()
        step = AgentStep(
            agent=AgentName.POLICY_CHECKER,
            status=StepStatus.SUCCESS,
            confidence_before=confidence.score,
            input_summary=f"Checking {claim_category.value} claim for ₹{claimed_amount}",
        )

        result = PolicyCheckResult()

        try:
            member = self.policy.get_member(member_id)
            if not member:
                result.eligible = False
                result.rejection_reasons.append(f"Member '{member_id}' not found in policy roster")
                result.rejection_codes.append("MEMBER_NOT_FOUND")
                confidence.deduct(settings.confidence_deduct_policy_violation, "Member not found")
                step.output_summary = "REJECTED: Member not found"
                step.output_data = result.to_dict()
                step.confidence_after = confidence.score
                return result, self._finalize_step(step, start_time)

            category_coverage = self.policy.get_category_coverage(claim_category.value)
            if not category_coverage:
                result.eligible = False
                result.rejection_reasons.append(f"Category '{claim_category.value}' not found in policy")
                result.rejection_codes.append("CATEGORY_NOT_COVERED")
                confidence.deduct(settings.confidence_deduct_policy_violation, "Category not covered")
                step.output_summary = "REJECTED: Category not covered"
                step.output_data = result.to_dict()
                step.confidence_after = confidence.score
                return result, self._finalize_step(step, start_time)

            # ── 1. Per-claim limit check ─────────────────────
            per_claim_limit = self.policy.coverage.per_claim_limit
            if claimed_amount > per_claim_limit:
                result.eligible = False
                result.rejection_reasons.append(
                    f"Claimed amount ₹{claimed_amount:,.0f} exceeds the per-claim limit of ₹{per_claim_limit:,.0f}"
                )
                result.rejection_codes.append("PER_CLAIM_EXCEEDED")
                confidence.deduct(0.0, "Per-claim limit exceeded (deterministic)")
                step.output_summary = f"REJECTED: Per-claim limit exceeded (₹{claimed_amount} > ₹{per_claim_limit})"
                step.output_data = result.to_dict()
                step.confidence_after = confidence.score
                return result, self._finalize_step(step, start_time)

            # ── 2. Waiting period check ──────────────────────
            waiting_result = self._check_waiting_period(
                member, treatment_date, extracted_docs
            )
            if waiting_result:
                result.eligible = False
                result.rejection_reasons.append(waiting_result["reason"])
                result.rejection_codes.append("WAITING_PERIOD")
                result.waiting_period_details = waiting_result["details"]
                confidence.deduct(0.0, "Waiting period violation (deterministic)")
                step.output_summary = f"REJECTED: Waiting period"
                step.output_data = result.to_dict()
                step.confidence_after = confidence.score
                return result, self._finalize_step(step, start_time)

            # ── 3. Exclusion check ───────────────────────────
            exclusion_result = self._check_exclusions(
                claim_category, extracted_docs
            )
            if exclusion_result:
                result.eligible = False
                result.rejection_reasons.append(exclusion_result["reason"])
                result.rejection_codes.append("EXCLUDED_CONDITION")
                result.exclusion_details = exclusion_result["details"]
                confidence.deduct(0.0, "Excluded treatment (deterministic)")
                step.output_summary = f"REJECTED: Excluded condition"
                step.output_data = result.to_dict()
                step.confidence_after = confidence.score
                return result, self._finalize_step(step, start_time)

            # ── 4. Pre-authorization check ───────────────────
            preauth_result = self._check_pre_auth(
                claim_category, claimed_amount, extracted_docs
            )
            if preauth_result:
                result.eligible = False
                result.rejection_reasons.append(preauth_result["reason"])
                result.rejection_codes.append("PRE_AUTH_MISSING")
                result.pre_auth_missing = True
                confidence.deduct(0.0, "Pre-auth required but missing (deterministic)")
                step.output_summary = "REJECTED: Pre-auth missing"
                step.output_data = result.to_dict()
                step.confidence_after = confidence.score
                return result, self._finalize_step(step, start_time)

            # ── 5. Line item evaluation + financial calculation ──
            is_network = self.policy.is_network_hospital(hospital_name or "")

            # Check for partial approvals (excluded procedures in line items)
            line_items = self._get_all_line_items(extracted_docs)
            line_item_decisions, approved_total = self._evaluate_line_items(
                line_items, claim_category, category_coverage
            )
            result.line_item_decisions = line_item_decisions

            # Use claimed amount if no line items
            base_amount = approved_total if approved_total > 0 else claimed_amount

            # Apply sub-limit cap
            sub_limit = category_coverage.sub_limit
            if base_amount > sub_limit:
                base_amount = sub_limit
                result.notes += f"Amount capped at category sub-limit of ₹{sub_limit:,.0f}. "

            # ── Financial calculation ────────────────────────
            # Network discount applied FIRST, then co-pay
            network_discount_pct = category_coverage.network_discount_percent if is_network else 0
            copay_pct = category_coverage.copay_percent

            amount_after_discount = base_amount
            network_discount_amount = 0.0
            if network_discount_pct > 0:
                network_discount_amount = base_amount * (network_discount_pct / 100)
                amount_after_discount = base_amount - network_discount_amount

            copay_amount = amount_after_discount * (copay_pct / 100)
            final_amount = amount_after_discount - copay_amount

            result.approved_amount = round(final_amount, 2)
            result.network_discount_amount = round(network_discount_amount, 2)
            result.copay_amount = round(copay_amount, 2)

            # Build calculation breakdown
            breakdown_parts = [f"Base amount: ₹{base_amount:,.0f}"]
            if network_discount_pct > 0:
                breakdown_parts.append(
                    f"Network discount ({network_discount_pct}%): -₹{network_discount_amount:,.0f} → ₹{amount_after_discount:,.0f}"
                )
            if copay_pct > 0:
                breakdown_parts.append(
                    f"Co-pay ({copay_pct}%): -₹{copay_amount:,.0f}"
                )
            breakdown_parts.append(f"Final approved: ₹{final_amount:,.0f}")
            result.calculation_breakdown = " | ".join(breakdown_parts)

            # Check if any line items were rejected (partial approval)
            rejected_items = [lid for lid in line_item_decisions if not lid.approved]
            if rejected_items and line_item_decisions:
                # This is a partial approval
                result.notes += f"{len(rejected_items)} line item(s) excluded. "

            # Use LLM for additional reasoning if needed
            try:
                llm_result = await self._llm_policy_check(
                    member, claim_category, treatment_date, claimed_amount,
                    hospital_name, extracted_docs, ytd_claims_amount,
                    category_coverage, is_network
                )
                step.llm_calls = 1
                if llm_result.get("notes"):
                    result.notes += llm_result["notes"]
            except Exception as e:
                logger.warning(f"LLM policy check failed, using deterministic only: {e}")
                confidence.deduct(settings.confidence_deduct_llm_fallback, "LLM reasoning unavailable, using rules only")

            step.output_summary = f"Eligible: approved ₹{result.approved_amount:,.0f}"
            step.output_data = result.to_dict()
            step.confidence_after = confidence.score
            return result, self._finalize_step(step, start_time)

        except Exception as e:
            logger.error(f"Policy check failed: {e}")
            step.status = StepStatus.FAILED
            step.failure = FailureRecord(
                agent=AgentName.POLICY_CHECKER,
                error_type=type(e).__name__,
                error_message=str(e),
            )
            confidence.deduct(settings.confidence_deduct_policy_agent_error, f"Policy checker failed: {e}")
            step.confidence_after = confidence.score
            step.output_summary = f"FAILED: {e}"
            return result, self._finalize_step(step, start_time)

    def _check_waiting_period(
        self, member, treatment_date: str, docs: list[ExtractedDocument]
    ) -> Optional[dict]:
        """Check waiting period violations."""
        join_date = member.join_date
        if not join_date:
            return None

        try:
            join_dt = datetime.strptime(join_date, "%Y-%m-%d")
            treat_dt = datetime.strptime(treatment_date, "%Y-%m-%d")
        except ValueError:
            return None

        days_since_join = (treat_dt - join_dt).days

        # Initial waiting period
        initial_days = self.policy.waiting_periods.initial_waiting_period_days
        if days_since_join < initial_days:
            eligible_date = (join_dt + timedelta(days=initial_days)).strftime("%Y-%m-%d")
            return {
                "reason": f"Treatment date is within the {initial_days}-day initial waiting period. "
                          f"Member joined on {join_date} and the treatment was on {treatment_date} "
                          f"({days_since_join} days after joining).",
                "details": f"Eligible for claims from {eligible_date} onwards.",
            }

        # Condition-specific waiting periods
        diagnosis = self._get_diagnosis(docs)
        if diagnosis:
            diag_lower = diagnosis.lower()
            for condition, wait_days in self.policy.waiting_periods.specific_conditions.items():
                if condition.lower() in diag_lower or self._match_condition(condition, diag_lower):
                    if days_since_join < wait_days:
                        eligible_date = (join_dt + timedelta(days=wait_days)).strftime("%Y-%m-%d")
                        return {
                            "reason": f"The diagnosis '{diagnosis}' falls under '{condition}' "
                                      f"which has a {wait_days}-day waiting period. "
                                      f"Member joined on {join_date} ({days_since_join} days ago), "
                                      f"but {wait_days} days must pass before claims for this condition are eligible.",
                            "details": f"Member will be eligible for {condition}-related claims from {eligible_date} onwards.",
                        }

        return None

    @staticmethod
    def _match_condition(condition: str, diagnosis: str) -> bool:
        """Fuzzy match between policy condition names and diagnosis text."""
        mappings = {
            "diabetes": ["diabetes", "t2dm", "type 2 diabetes", "diabetic", "dm", "mellitus"],
            "hypertension": ["hypertension", "htn", "high blood pressure", "bp"],
            "thyroid_disorders": ["thyroid", "hypothyroid", "hyperthyroid", "tsh"],
            "maternity": ["maternity", "pregnancy", "prenatal", "antenatal"],
            "mental_health": ["mental", "depression", "anxiety", "psychiatric"],
            "obesity_treatment": ["obesity", "obese", "bariatric", "weight loss", "bmi"],
            "hernia": ["hernia"],
            "cataract": ["cataract"],
        }
        keywords = mappings.get(condition.lower(), [condition.lower()])
        return any(kw in diagnosis for kw in keywords)

    def _check_exclusions(
        self, category: ClaimCategory, docs: list[ExtractedDocument]
    ) -> Optional[dict]:
        """Check if the treatment is excluded under the policy."""
        diagnosis = self._get_diagnosis(docs)
        treatment = self._get_treatment(docs)
        combined = f"{diagnosis or ''} {treatment or ''}".lower()

        # Check general exclusions
        for exclusion in self.policy.exclusions.get("conditions", []):
            excl_lower = exclusion.lower()
            # Check key terms from the exclusion
            excl_terms = [t.strip() for t in excl_lower.split("and")]
            for term in excl_terms:
                core_words = [w for w in term.split() if len(w) > 3]
                if core_words and all(w in combined for w in core_words):
                    return {
                        "reason": f"The treatment/diagnosis '{diagnosis or treatment}' falls under "
                                  f"the policy exclusion: '{exclusion}'.",
                        "details": f"Policy exclusion matched: {exclusion}",
                    }

        # Check category-specific exclusions
        cat_key = category.value.lower()
        dental_exclusions = self.policy.exclusions.get("dental_exclusions", [])
        vision_exclusions = self.policy.exclusions.get("vision_exclusions", [])

        if cat_key == "dental":
            for excl in dental_exclusions:
                if excl.lower() in combined:
                    return {
                        "reason": f"'{excl}' is excluded under dental coverage.",
                        "details": f"Dental exclusion: {excl}",
                    }
        elif cat_key == "vision":
            for excl in vision_exclusions:
                if excl.lower() in combined:
                    return {
                        "reason": f"'{excl}' is excluded under vision coverage.",
                        "details": f"Vision exclusion: {excl}",
                    }

        return None

    def _check_pre_auth(
        self, category: ClaimCategory, amount: float, docs: list[ExtractedDocument]
    ) -> Optional[dict]:
        """Check if pre-authorization is required but missing."""
        if category.value != "DIAGNOSTIC":
            return None

        category_coverage = self.policy.get_category_coverage(category.value)
        if not category_coverage:
            return None

        # Check for high-value tests
        tests = []
        for doc in docs:
            tests.extend(doc.tests_ordered)
            for item in doc.line_items:
                tests.append(item.description)

        high_value_tests = category_coverage.high_value_tests_requiring_pre_auth
        threshold = category_coverage.pre_auth_threshold or 10000

        for test in tests:
            test_lower = test.lower()
            for hvt in high_value_tests:
                if hvt.lower() in test_lower:
                    if amount > threshold:
                        return {
                            "reason": f"Pre-authorization is required for '{hvt}' when the amount exceeds "
                                      f"₹{threshold:,.0f} (claimed: ₹{amount:,.0f}). "
                                      f"No pre-authorization was provided with this claim. "
                                      f"Please obtain pre-authorization from the insurer before the procedure, "
                                      f"then resubmit the claim with the pre-authorization reference number.",
                            "details": f"Test: {hvt}, Amount: ₹{amount:,.0f}, Threshold: ₹{threshold:,.0f}",
                        }

        return None

    def _evaluate_line_items(
        self,
        line_items: list[dict],
        category: ClaimCategory,
        coverage,
    ) -> tuple[list[LineItemDecision], float]:
        """Evaluate each line item for coverage. Returns decisions and approved total."""
        if not line_items:
            return [], 0.0

        decisions = []
        approved_total = 0.0

        excluded_procedures = coverage.excluded_procedures
        covered_procedures = coverage.covered_procedures

        for item in line_items:
            desc = item.get("description", "")
            amount = item.get("amount", 0)
            desc_lower = desc.lower()

            # Check against excluded procedures
            is_excluded = False
            exclusion_reason = ""
            for excl in excluded_procedures:
                if excl.lower() in desc_lower or desc_lower in excl.lower():
                    is_excluded = True
                    exclusion_reason = f"'{desc}' is an excluded procedure under {category.value} coverage"
                    break

            # Check general exclusions
            if not is_excluded:
                for excl in self.policy.exclusions.get("conditions", []):
                    excl_words = [w.lower() for w in excl.split() if len(w) > 3]
                    if excl_words and all(w in desc_lower for w in excl_words):
                        is_excluded = True
                        exclusion_reason = f"'{desc}' falls under policy exclusion: '{excl}'"
                        break

            if is_excluded:
                decisions.append(LineItemDecision(
                    description=desc,
                    amount=amount,
                    approved=False,
                    reason=exclusion_reason,
                ))
            else:
                decisions.append(LineItemDecision(
                    description=desc,
                    amount=amount,
                    approved=True,
                    reason="Covered under policy",
                ))
                approved_total += amount

        return decisions, approved_total

    @staticmethod
    def _get_all_line_items(docs: list[ExtractedDocument]) -> list[dict]:
        """Aggregate line items from all extracted documents."""
        items = []
        for doc in docs:
            for item in doc.line_items:
                items.append(item.model_dump())
        return items

    @staticmethod
    def _get_diagnosis(docs: list[ExtractedDocument]) -> Optional[str]:
        """Get diagnosis from extracted documents."""
        for doc in docs:
            if doc.diagnosis:
                return doc.diagnosis
        return None

    @staticmethod
    def _get_treatment(docs: list[ExtractedDocument]) -> Optional[str]:
        """Get treatment description from extracted documents."""
        for doc in docs:
            if doc.raw_extraction and doc.raw_extraction.get("treatment"):
                return doc.raw_extraction["treatment"]
        return None

    async def _llm_policy_check(
        self, member, category, treatment_date, claimed_amount,
        hospital_name, docs, ytd_claims_amount, coverage, is_network,
    ) -> dict:
        """Use LLM for additional policy reasoning."""
        diagnosis = self._get_diagnosis(docs) or "Not specified"
        line_items = json.dumps(self._get_all_line_items(docs), indent=2)

        prompt = POLICY_CHECKER_USER.format(
            member_id=member.member_id,
            member_name=member.name,
            join_date=member.join_date or "N/A",
            claim_category=category.value,
            treatment_date=treatment_date,
            claimed_amount=claimed_amount,
            hospital_name=hospital_name or "Not specified",
            ytd_claims_amount=ytd_claims_amount,
            diagnosis=diagnosis,
            line_items=line_items,
            per_claim_limit=self.policy.coverage.per_claim_limit,
            sub_limit=coverage.sub_limit,
            copay_percent=coverage.copay_percent,
            network_discount_percent=coverage.network_discount_percent,
            is_network=is_network,
            initial_waiting_days=self.policy.waiting_periods.initial_waiting_period_days,
            specific_waiting_periods=json.dumps(self.policy.waiting_periods.specific_conditions),
            exclusions=json.dumps(self.policy.exclusions.get("conditions", [])),
            pre_auth_required=json.dumps(self.policy.pre_authorization.get("required_for", [])),
            covered_procedures=json.dumps(coverage.covered_procedures),
            excluded_procedures=json.dumps(coverage.excluded_procedures),
        )

        return await self.llm.call_text_model(
            system_prompt=POLICY_CHECKER_SYSTEM,
            user_prompt=prompt,
        )

    @staticmethod
    def _finalize_step(step: AgentStep, start_time: float) -> AgentStep:
        from datetime import datetime as dt
        step.completed_at = dt.utcnow().isoformat()
        step.duration_ms = (time.time() - start_time) * 1000
        return step
