"""
FastAPI dependency injection — get_policy(), get_db(), get_llm_client().
"""

from __future__ import annotations

from app.config import settings
from app.models.policy import PolicyTerms
from app.services.llm_client import LLMClient
from app.services.policy_loader import get_policy as _get_policy


_llm_client = None


def get_policy() -> PolicyTerms:
    """Get the cached policy terms."""
    return _get_policy()


def get_llm_client() -> LLMClient:
    """Get or create the LLM client singleton."""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client
