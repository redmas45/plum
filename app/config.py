"""
Application configuration via Pydantic BaseSettings.
Reads from environment variables / .env file.
"""

from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # ── Application ────────────────────────────────────
    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    log_level: str = Field(default="info", alias="LOG_LEVEL")

    # ── Groq API ───────────────────────────────────────
    groq_api_key: str = Field(default="", alias="GROQ_API_KEY")

    # ── Database ───────────────────────────────────────
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/claims.db",
        alias="DATABASE_URL",
    )

    # ── LLM Model Config ──────────────────────────────
    vision_model: str = Field(
        default="meta-llama/llama-4-scout-17b-16e-instruct",
        alias="VISION_MODEL",
    )
    text_model: str = Field(
        default="meta-llama/llama-3.3-70b-versatile",
        alias="TEXT_MODEL",
    )

    # ── File Uploads ───────────────────────────────────
    upload_dir: str = Field(default="./uploads", alias="UPLOAD_DIR")
    max_file_size_mb: int = Field(default=10, alias="MAX_FILE_SIZE_MB")

    # ── Confidence ─────────────────────────────────────
    initial_confidence: float = Field(
        default=1.0, alias="INITIAL_CONFIDENCE",
        description="Starting confidence score for the pipeline (0.0-1.0)"
    )
    # Deduction values per scenario
    confidence_deduct_unreadable_doc: float = Field(default=0.5, alias="CONFIDENCE_DEDUCT_UNREADABLE_DOC")
    confidence_deduct_missing_doc: float = Field(default=1.0, alias="CONFIDENCE_DEDUCT_MISSING_DOC")
    confidence_deduct_patient_mismatch: float = Field(default=1.0, alias="CONFIDENCE_DEDUCT_PATIENT_MISMATCH")
    confidence_deduct_poor_quality: float = Field(default=0.05, alias="CONFIDENCE_DEDUCT_POOR_QUALITY")
    confidence_deduct_doc_agent_error: float = Field(default=0.3, alias="CONFIDENCE_DEDUCT_DOC_AGENT_ERROR")
    confidence_deduct_component_failure: float = Field(default=0.2, alias="CONFIDENCE_DEDUCT_COMPONENT_FAILURE")
    confidence_deduct_policy_violation: float = Field(default=1.0, alias="CONFIDENCE_DEDUCT_POLICY_VIOLATION")
    confidence_deduct_policy_agent_error: float = Field(default=0.25, alias="CONFIDENCE_DEDUCT_POLICY_AGENT_ERROR")
    confidence_deduct_llm_fallback: float = Field(default=0.05, alias="CONFIDENCE_DEDUCT_LLM_FALLBACK")
    confidence_deduct_fraud_same_day: float = Field(default=0.15, alias="CONFIDENCE_DEDUCT_FRAUD_SAME_DAY")
    confidence_deduct_doc_inconsistency: float = Field(default=0.1, alias="CONFIDENCE_DEDUCT_DOC_INCONSISTENCY")
    confidence_deduct_fraud_agent_error: float = Field(default=0.2, alias="CONFIDENCE_DEDUCT_FRAUD_AGENT_ERROR")

    # ── Paths ──────────────────────────────────────────
    policy_file: str = Field(
        default="./data/policy_terms.json", alias="POLICY_FILE"
    )
    test_cases_file: str = Field(
        default="./data/test_cases.json", alias="TEST_CASES_FILE"
    )
    db_path: str = Field(default="./data/claims.db", alias="DB_PATH")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "populate_by_name": True,
        "extra": "ignore",
    }

    @property
    def upload_path(self) -> Path:
        p = Path(self.upload_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


settings = Settings()
