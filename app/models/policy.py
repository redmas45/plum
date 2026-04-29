"""
Pydantic models for policy terms, members, and coverage data.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class CategoryCoverage(BaseModel):
    sub_limit: float
    copay_percent: float = 0
    network_discount_percent: float = 0
    requires_prescription: bool = False
    requires_pre_auth: bool = False
    pre_auth_threshold: Optional[float] = None
    high_value_tests_requiring_pre_auth: list[str] = Field(default_factory=list)
    covered: bool = True
    covered_procedures: list[str] = Field(default_factory=list)
    excluded_procedures: list[str] = Field(default_factory=list)
    covered_items: list[str] = Field(default_factory=list)
    excluded_items: list[str] = Field(default_factory=list)
    branded_drug_copay_percent: Optional[float] = None
    generic_mandatory: Optional[bool] = None
    requires_dental_report: Optional[bool] = None
    requires_registered_practitioner: Optional[bool] = None
    max_sessions_per_year: Optional[int] = None
    covered_systems: list[str] = Field(default_factory=list)


class WaitingPeriods(BaseModel):
    initial_waiting_period_days: int = 30
    pre_existing_conditions_days: int = 365
    specific_conditions: dict[str, int] = Field(default_factory=dict)


class FraudThresholds(BaseModel):
    same_day_claims_limit: int = 2
    monthly_claims_limit: int = 6
    high_value_claim_threshold: float = 25000
    auto_manual_review_above: float = 25000
    fraud_score_manual_review_threshold: float = 0.80


class Member(BaseModel):
    member_id: str
    name: str
    date_of_birth: str
    gender: str
    relationship: str
    join_date: Optional[str] = None
    dependents: list[str] = Field(default_factory=list)
    primary_member_id: Optional[str] = None


class Coverage(BaseModel):
    sum_insured_per_employee: float
    annual_opd_limit: float
    per_claim_limit: float
    family_floater: dict[str, Any] = Field(default_factory=dict)


class SubmissionRules(BaseModel):
    deadline_days_from_treatment: int = 30
    minimum_claim_amount: float = 500
    currency: str = "INR"


class PolicyTerms(BaseModel):
    """Complete policy configuration loaded from policy_terms.json."""
    policy_id: str
    policy_name: str
    insurer: str
    policy_holder: dict[str, Any]
    coverage: Coverage
    opd_categories: dict[str, CategoryCoverage]
    waiting_periods: WaitingPeriods
    exclusions: dict[str, list[str]]
    pre_authorization: dict[str, Any]
    network_hospitals: list[str]
    submission_rules: SubmissionRules
    document_requirements: dict[str, dict[str, list[str]]]
    fraud_thresholds: FraudThresholds
    members: list[Member]

    def get_member(self, member_id: str) -> Optional[Member]:
        """Look up a member by ID."""
        for m in self.members:
            return_member = None
            if m.member_id == member_id:
                return_member = m
            if return_member:
                return return_member
        return None

    def get_category_coverage(self, category: str) -> Optional[CategoryCoverage]:
        """Get coverage config for a claim category."""
        cat_key = category.lower()
        return self.opd_categories.get(cat_key)

    def get_document_requirements(self, category: str) -> dict[str, list[str]]:
        """Get required / optional document types for a claim category."""
        return self.document_requirements.get(category, {"required": [], "optional": []})

    def is_network_hospital(self, hospital_name: str) -> bool:
        """Check if a hospital is in the network."""
        if not hospital_name:
            return False
        name_lower = hospital_name.lower()
        return any(h.lower() in name_lower or name_lower in h.lower()
                    for h in self.network_hospitals)
