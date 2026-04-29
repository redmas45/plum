"""
Confidence score calculator.
Starts at 1.0 and deductions bring it down.
Provides explicit reasons for every deduction.
"""

from __future__ import annotations


class ConfidenceTracker:
    """Tracks confidence score with explicit deduction reasons."""

    def __init__(self, initial: float = 1.0):
        self._score = initial
        self._deductions: list[str] = []
        self._floor = 0.0

    @property
    def score(self) -> float:
        return max(self._score, self._floor)

    @property
    def deductions(self) -> list[str]:
        return self._deductions.copy()

    def deduct(self, amount: float, reason: str) -> float:
        """Deduct from confidence with a reason. Returns new score."""
        self._score -= amount
        self._deductions.append(f"-{amount:.2f}: {reason}")
        return self.score

    def cap(self, maximum: float, reason: str) -> float:
        """Cap the confidence score at a maximum value."""
        if self._score > maximum:
            diff = self._score - maximum
            self._score = maximum
            self._deductions.append(f"capped at {maximum:.2f} (-{diff:.2f}): {reason}")
        return self.score

    def floor(self, minimum: float) -> None:
        """Set a floor — score never goes below this."""
        self._floor = minimum

    def boost(self, amount: float, reason: str) -> float:
        """Small boost (e.g., network hospital bonus). Capped at 1.0."""
        self._score = min(1.0, self._score + amount)
        self._deductions.append(f"+{amount:.2f}: {reason}")
        return self.score


def start(initial: float = 1.0) -> ConfidenceTracker:
    """Factory function — start a new confidence tracker."""
    return ConfidenceTracker(initial)
