"""
Health check endpoint.
"""

from fastapi import APIRouter

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check():
    """Simple health check."""
    return {
        "status": "healthy",
        "service": "plum-claims",
        "version": "1.0.0",
    }
