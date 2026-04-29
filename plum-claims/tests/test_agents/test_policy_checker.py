import pytest
from app.models.claim import ClaimCategory
from app.models.policy import PolicyTerms
from app.agents.policy_checker import PolicyChecker

# Mock LLM Client
class MockLLMClient:
    pass

@pytest.fixture
def mock_policy_data():
    return {
        "policy_id": "TEST_POLICY",
        "policy_name": "Test Policy",
        "insurer": "Test Insurer",
        "policy_holder": {"company_name": "Test Co"},
        "coverage": {
            "sum_insured_per_employee": 500000,
            "annual_opd_limit": 50000,
            "per_claim_limit": 5000,
            "family_floater": {}
        },
        "opd_categories": {
            "consultation": {
                "sub_limit": 2000,
                "copay_percent": 10,
                "network_discount_percent": 20,
                "covered": True
            }
        },
        "waiting_periods": {
            "initial_waiting_period_days": 30,
            "pre_existing_conditions_days": 365,
            "specific_conditions": {"diabetes": 90}
        },
        "exclusions": {"conditions": []},
        "pre_authorization": {},
        "network_hospitals": ["Test Hospital"],
        "submission_rules": {},
        "document_requirements": {},
        "fraud_thresholds": {
            "same_day_claims_limit": 2,
            "monthly_claims_limit": 6,
            "high_value_claim_threshold": 25000,
            "auto_manual_review_above": 25000,
            "fraud_score_manual_review_threshold": 0.8
        },
        "members": [
            {
                "member_id": "EMP1",
                "name": "John Doe",
                "date_of_birth": "1990-01-01",
                "gender": "M",
                "relationship": "SELF",
                "join_date": "2024-01-01"
            }
        ]
    }

@pytest.mark.asyncio
async def test_policy_checker_per_claim_limit(mock_policy_data):
    policy = PolicyTerms(**mock_policy_data)
    checker = PolicyChecker(MockLLMClient(), policy)
    from app.utils.confidence import start
    confidence = start()
    
    # Claim above the 5000 per claim limit
    result, step = await checker.check(
        member_id="EMP1",
        claim_category=ClaimCategory.CONSULTATION,
        treatment_date="2024-06-01",
        claimed_amount=6000,
        hospital_name="Test Hospital",
        extracted_docs=[],
        ytd_claims_amount=0,
        confidence=confidence
    )
    
    assert not result.eligible
    assert "PER_CLAIM_EXCEEDED" in result.rejection_codes
