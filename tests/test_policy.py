"""
Tests for Policy Terms loading, member lookup, and coverage rules.
Validates all deterministic policy logic without LLM calls.
"""

import json
import pytest
from app.models.policy import PolicyTerms, CategoryCoverage, Member


@pytest.fixture
def policy() -> PolicyTerms:
    """Load the actual policy_terms.json as the fixture."""
    with open("data/policy_terms.json", "r") as f:
        data = json.load(f)
    return PolicyTerms(**data)


class TestMemberLookup:
    """Tests for member roster lookups."""

    def test_find_existing_member(self, policy):
        member = policy.get_member("EMP001")
        assert member is not None
        assert member.name == "Rajesh Kumar"

    def test_find_dependent(self, policy):
        member = policy.get_member("DEP001")
        assert member is not None
        assert member.relationship == "SPOUSE"

    def test_missing_member_returns_none(self, policy):
        member = policy.get_member("EMP999")
        assert member is None

    def test_all_12_members_exist(self, policy):
        """All 12 members from the policy roster must be loadable."""
        member_ids = [f"EMP{i:03d}" for i in range(1, 11)] + ["DEP001", "DEP002"]
        for mid in member_ids:
            assert policy.get_member(mid) is not None, f"Member {mid} not found"


class TestCategoryCoverage:
    """Tests for category coverage lookups."""

    def test_consultation_coverage(self, policy):
        cov = policy.get_category_coverage("CONSULTATION")
        assert cov is not None
        assert cov.sub_limit == 2000
        assert cov.copay_percent == 10
        assert cov.network_discount_percent == 20

    def test_diagnostic_coverage(self, policy):
        cov = policy.get_category_coverage("DIAGNOSTIC")
        assert cov is not None
        assert cov.sub_limit == 10000
        assert cov.copay_percent == 0
        assert cov.network_discount_percent == 10

    def test_pharmacy_coverage(self, policy):
        cov = policy.get_category_coverage("PHARMACY")
        assert cov is not None
        assert cov.sub_limit == 15000

    def test_dental_coverage_has_excluded_procedures(self, policy):
        cov = policy.get_category_coverage("DENTAL")
        assert cov is not None
        assert "Teeth Whitening" in cov.excluded_procedures
        assert "Root Canal Treatment" in cov.covered_procedures

    def test_vision_coverage(self, policy):
        cov = policy.get_category_coverage("VISION")
        assert cov is not None
        assert cov.sub_limit == 5000

    def test_alternative_medicine_coverage(self, policy):
        cov = policy.get_category_coverage("ALTERNATIVE_MEDICINE")
        assert cov is not None
        assert cov.sub_limit == 8000

    def test_invalid_category_returns_none(self, policy):
        cov = policy.get_category_coverage("NONEXISTENT")
        assert cov is None


class TestDocumentRequirements:
    """Tests for document requirement lookups per category."""

    def test_consultation_requires_prescription_and_bill(self, policy):
        reqs = policy.get_document_requirements("CONSULTATION")
        assert "PRESCRIPTION" in reqs["required"]
        assert "HOSPITAL_BILL" in reqs["required"]

    def test_diagnostic_requires_three_docs(self, policy):
        reqs = policy.get_document_requirements("DIAGNOSTIC")
        assert "PRESCRIPTION" in reqs["required"]
        assert "LAB_REPORT" in reqs["required"]
        assert "HOSPITAL_BILL" in reqs["required"]

    def test_dental_only_requires_bill(self, policy):
        reqs = policy.get_document_requirements("DENTAL")
        assert "HOSPITAL_BILL" in reqs["required"]
        assert "PRESCRIPTION" not in reqs["required"]

    def test_pharmacy_requires_prescription_and_pharmacy_bill(self, policy):
        reqs = policy.get_document_requirements("PHARMACY")
        assert "PRESCRIPTION" in reqs["required"]
        assert "PHARMACY_BILL" in reqs["required"]


class TestNetworkHospitals:
    """Tests for network hospital matching."""

    def test_apollo_is_network(self, policy):
        assert policy.is_network_hospital("Apollo Hospitals") is True

    def test_partial_match_works(self, policy):
        assert policy.is_network_hospital("Apollo") is True

    def test_case_insensitive(self, policy):
        assert policy.is_network_hospital("FORTIS HEALTHCARE") is True

    def test_unknown_hospital_not_network(self, policy):
        assert policy.is_network_hospital("City Medical Centre") is False

    def test_empty_string_not_network(self, policy):
        assert policy.is_network_hospital("") is False


class TestCoverageLimits:
    """Tests for global coverage limits."""

    def test_per_claim_limit(self, policy):
        assert policy.coverage.per_claim_limit == 5000

    def test_sum_insured(self, policy):
        assert policy.coverage.sum_insured_per_employee == 500000

    def test_annual_opd_limit(self, policy):
        assert policy.coverage.annual_opd_limit == 50000


class TestWaitingPeriods:
    """Tests for waiting period configurations."""

    def test_initial_waiting_period(self, policy):
        assert policy.waiting_periods.initial_waiting_period_days == 30

    def test_diabetes_waiting_period(self, policy):
        assert policy.waiting_periods.specific_conditions.get("diabetes") == 90

    def test_maternity_waiting_period(self, policy):
        assert policy.waiting_periods.specific_conditions.get("maternity") == 270

    def test_joint_replacement_longest(self, policy):
        assert policy.waiting_periods.specific_conditions.get("joint_replacement") == 730


class TestFraudThresholds:
    """Tests for fraud detection thresholds."""

    def test_same_day_limit(self, policy):
        assert policy.fraud_thresholds.same_day_claims_limit == 2

    def test_monthly_limit(self, policy):
        assert policy.fraud_thresholds.monthly_claims_limit == 6

    def test_high_value_threshold(self, policy):
        assert policy.fraud_thresholds.high_value_claim_threshold == 25000

    def test_auto_manual_review(self, policy):
        assert policy.fraud_thresholds.auto_manual_review_above == 25000


class TestSubmissionRules:
    """Tests for claim submission rules."""

    def test_deadline_30_days(self, policy):
        assert policy.submission_rules.deadline_days_from_treatment == 30

    def test_minimum_claim_amount(self, policy):
        assert policy.submission_rules.minimum_claim_amount == 500

    def test_currency_is_inr(self, policy):
        assert policy.submission_rules.currency == "INR"
