import pytest
from app.utils.confidence import ConfidenceTracker, start

def test_confidence_initialization():
    tracker = start()
    assert tracker.score == 1.0
    assert len(tracker.deductions) == 0

def test_confidence_deduction():
    tracker = start()
    tracker.deduct(0.2, "Test deduction")
    assert tracker.score == 0.8
    assert len(tracker.deductions) == 1
    assert "Test deduction" in tracker.deductions[0]

def test_confidence_floor():
    tracker = start()
    tracker.floor(0.5)
    tracker.deduct(0.8, "Huge deduction")
    assert tracker.score == 0.5
    
def test_confidence_cap():
    tracker = start()
    tracker.cap(0.8, "Capped at 80%")
    assert tracker.score == 0.8
    assert "Capped" in tracker.deductions[0]
