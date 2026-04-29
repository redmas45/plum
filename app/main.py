"""
FastAPI application factory.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.services import claim_store
from app.services.policy_loader import load_policy


def setup_logging():
    """Configure application logging."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    setup_logging()
    logger = logging.getLogger(__name__)

    # Load policy at startup
    logger.info("Loading policy terms...")
    load_policy()
    logger.info("Policy loaded successfully")

    # Initialize database
    logger.info("Initializing database...")
    await claim_store.init_db()
    logger.info("Database ready")

    # Create upload directory
    settings.upload_path.mkdir(parents=True, exist_ok=True)

    logger.info(f"Plum Claims API ready — {settings.app_env} mode")
    yield
    logger.info("Shutting down...")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Plum Claims Processing System",
        description="AI-powered health insurance claims processing with multi-agent pipeline",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routes
    from app.api.routes.health import router as health_router
    from app.api.routes.claims import router as claims_router
    from app.api.routes.eval import router as eval_router

    app.include_router(health_router)
    app.include_router(claims_router)
    app.include_router(eval_router)

    # Serve frontend
    frontend_dir = Path(__file__).parent.parent / "frontend"
    if frontend_dir.exists():
        app.mount("/static", StaticFiles(directory=str(frontend_dir)), name="static")

        @app.get("/")
        async def serve_frontend():
            return FileResponse(str(frontend_dir / "index.html"))

    return app


app = create_app()
