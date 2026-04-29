"""
Load and cache policy_terms.json at startup.
Provides the policy data to all agents.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from app.config import settings
from app.models.policy import PolicyTerms

logger = logging.getLogger(__name__)

_cached_policy: Optional[PolicyTerms] = None


def load_policy(file_path: Optional[str] = None) -> PolicyTerms:
    """Load policy terms from JSON file. Caches after first load."""
    global _cached_policy

    if _cached_policy is not None:
        return _cached_policy

    path = Path(file_path or settings.policy_file)
    if not path.exists():
        raise FileNotFoundError(f"Policy file not found: {path}")

    logger.info(f"Loading policy terms from {path}")
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    _cached_policy = PolicyTerms(**raw)
    logger.info(
        f"Policy loaded: {_cached_policy.policy_id} — "
        f"{len(_cached_policy.members)} members, "
        f"{len(_cached_policy.opd_categories)} categories"
    )
    return _cached_policy


def get_policy() -> PolicyTerms:
    """Get the cached policy or load it."""
    return load_policy()


def reload_policy(file_path: Optional[str] = None) -> PolicyTerms:
    """Force reload the policy from disk."""
    global _cached_policy
    _cached_policy = None
    return load_policy(file_path)
