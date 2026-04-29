"""
Tests for the Confidence Tracker utility.
Validates the scoring engine used across all pipeline agents.
"""

import pytest
from app.utils.confidence import ConfidenceTracker, start


class TestConfidenceTracker:
    """Tests for ConfidenceTracker core functionality."""

    def test_initial_score_default(self):
        """Default confidence starts at 1.0."""
        tracker = ConfidenceTracker()
        assert tracker.score == 1.0

    def test_initial_score_custom(self):
        """Custom initial score is respected."""
        tracker = ConfidenceTracker(initial=0.85)
        assert tracker.score == 0.85

    def test_deduct_reduces_score(self):
        """Deduction reduces the score by the given amount."""
        tracker = ConfidenceTracker(initial=1.0)
        result = tracker.deduct(0.3, "Test deduction")
        assert result == pytest.approx(0.7)
        assert tracker.score == pytest.approx(0.7)

    def test_deduct_records_reason(self):
        """Every deduction is logged with its reason."""
        tracker = ConfidenceTracker()
        tracker.deduct(0.2, "Missing document")
        tracker.deduct(0.1, "Poor quality scan")
        assert len(tracker.deductions) == 2
        assert "-0.20: Missing document" in tracker.deductions[0]
        assert "-0.10: Poor quality scan" in tracker.deductions[1]

    def test_deductions_are_immutable_copy(self):
        """deductions property returns a copy, not internal state."""
        tracker = ConfidenceTracker()
        tracker.deduct(0.1, "test")
        d = tracker.deductions
        d.append("hacked")
        assert len(tracker.deductions) == 1  # Original untouched

    def test_multiple_deductions_cumulative(self):
        """Multiple deductions are cumulative."""
        tracker = ConfidenceTracker(initial=1.0)
        tracker.deduct(0.15, "Fraud signal")
        tracker.deduct(0.10, "Doc inconsistency")
        tracker.deduct(0.05, "LLM fallback")
        assert tracker.score == pytest.approx(0.70)

    def test_score_does_not_go_below_floor(self):
        """Score respects the floor value."""
        tracker = ConfidenceTracker(initial=0.5)
        tracker.floor(0.1)
        tracker.deduct(0.6, "Massive deduction")
        assert tracker.score == 0.1  # Floor prevents going below

    def test_score_can_go_negative_without_floor(self):
        """Without a floor, score can go below zero internally but returns 0.0."""
        tracker = ConfidenceTracker(initial=0.3)
        tracker.deduct(0.5, "Over-deduction")
        assert tracker.score == 0.0  # max(score, floor=0.0)

    def test_cap_limits_score(self):
        """Cap reduces score to maximum if currently above it."""
        tracker = ConfidenceTracker(initial=1.0)
        result = tracker.cap(0.7, "Pipeline degraded")
        assert result == pytest.approx(0.7)
        assert tracker.score == pytest.approx(0.7)

    def test_cap_no_effect_if_below(self):
        """Cap has no effect if score is already below the cap."""
        tracker = ConfidenceTracker(initial=0.5)
        tracker.cap(0.7, "Pipeline degraded")
        assert tracker.score == pytest.approx(0.5)

    def test_cap_records_deduction(self):
        """Cap records a deduction entry when it reduces the score."""
        tracker = ConfidenceTracker(initial=1.0)
        tracker.cap(0.7, "Pipeline degraded")
        assert len(tracker.deductions) == 1
        assert "capped at 0.70" in tracker.deductions[0]

    def test_boost_increases_score(self):
        """Boost increases the score."""
        tracker = ConfidenceTracker(initial=0.8)
        result = tracker.boost(0.1, "Network hospital bonus")
        assert result == pytest.approx(0.9)

    def test_boost_capped_at_one(self):
        """Boost cannot exceed 1.0."""
        tracker = ConfidenceTracker(initial=0.95)
        tracker.boost(0.2, "Big bonus")
        assert tracker.score == 1.0

    def test_boost_records_entry(self):
        """Boost records an entry in deductions list."""
        tracker = ConfidenceTracker(initial=0.8)
        tracker.boost(0.05, "Verified hospital")
        assert "+0.05: Verified hospital" in tracker.deductions[0]

    def test_factory_function(self):
        """start() factory creates a tracker with the given initial score."""
        tracker = start(0.9)
        assert isinstance(tracker, ConfidenceTracker)
        assert tracker.score == 0.9

    def test_full_pipeline_scenario(self):
        """Simulate a realistic pipeline: start at 1.0, multiple deductions and a boost."""
        tracker = ConfidenceTracker(initial=1.0)
        # Doc verifier finds poor quality
        tracker.deduct(0.05, "1 document with poor quality")
        assert tracker.score == pytest.approx(0.95)
        # Policy check OK, no deduction
        # Fraud: same-day claims
        tracker.deduct(0.15, "Same-day claims exceeded")
        assert tracker.score == pytest.approx(0.80)
        # LLM fallback
        tracker.deduct(0.05, "LLM fraud reasoning unavailable")
        assert tracker.score == pytest.approx(0.75)
        # Network hospital bonus
        tracker.boost(0.05, "Network hospital verified")
        assert tracker.score == pytest.approx(0.80)
        # Final deductions list should have 4 entries
        assert len(tracker.deductions) == 4

    def test_instant_reject_scenario(self):
        """Full 1.0 deduction simulates instant rejection."""
        tracker = ConfidenceTracker(initial=1.0)
        tracker.deduct(1.0, "Missing required documents")
        assert tracker.score == 0.0
        assert len(tracker.deductions) == 1
