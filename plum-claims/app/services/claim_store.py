"""
aiosqlite CRUD for storing and retrieving claims.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import aiosqlite

from app.config import settings
from app.models.claim import ClaimRecord, ClaimStatus

logger = logging.getLogger(__name__)

_db_path: Optional[str] = None


def get_db_path() -> str:
    global _db_path
    if _db_path is None:
        _db_path = settings.db_path
    return _db_path


async def init_db() -> None:
    """Create the claims table if it doesn't exist."""
    path = get_db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"Initializing database at {path}")

    async with aiosqlite.connect(path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS claims (
                claim_id TEXT PRIMARY KEY,
                member_id TEXT NOT NULL,
                policy_id TEXT NOT NULL,
                claim_category TEXT NOT NULL,
                treatment_date TEXT NOT NULL,
                claimed_amount REAL NOT NULL,
                hospital_name TEXT,
                status TEXT NOT NULL DEFAULT 'SUBMITTED',
                decision_json TEXT,
                trace_json TEXT,
                documents_json TEXT,
                submitted_at TEXT NOT NULL,
                decided_at TEXT,
                ytd_claims_amount REAL DEFAULT 0,
                claims_history_json TEXT,
                simulate_component_failure INTEGER DEFAULT 0
            )
        """)
        await db.commit()
    logger.info("Database initialized successfully")


async def save_claim(record: ClaimRecord) -> ClaimRecord:
    """Insert or update a claim record."""
    path = get_db_path()
    async with aiosqlite.connect(path) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO claims
            (claim_id, member_id, policy_id, claim_category, treatment_date,
             claimed_amount, hospital_name, status, decision_json, trace_json,
             documents_json, submitted_at, decided_at, ytd_claims_amount,
             claims_history_json, simulate_component_failure)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.claim_id,
                record.member_id,
                record.policy_id,
                record.claim_category.value,
                record.treatment_date,
                record.claimed_amount,
                record.hospital_name,
                record.status.value,
                record.decision.model_dump_json() if record.decision else None,
                json.dumps(record.trace) if record.trace else None,
                json.dumps([d.model_dump() for d in record.documents]),
                record.submitted_at,
                record.decided_at,
                record.ytd_claims_amount,
                json.dumps(record.claims_history) if record.claims_history else None,
                1 if record.simulate_component_failure else 0,
            ),
        )
        await db.commit()
    return record


async def get_claim(claim_id: str) -> Optional[ClaimRecord]:
    """Retrieve a claim by ID."""
    path = get_db_path()
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM claims WHERE claim_id = ?", (claim_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_record(row)


async def list_claims(
    member_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ClaimRecord]:
    """List claims with optional filters."""
    path = get_db_path()
    query = "SELECT * FROM claims"
    params: list = []
    conditions = []

    if member_id:
        conditions.append("member_id = ?")
        params.append(member_id)
    if status:
        conditions.append("status = ?")
        params.append(status)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY submitted_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(query, params)
        rows = await cursor.fetchall()
        return [_row_to_record(row) for row in rows]


async def count_claims(member_id: Optional[str] = None) -> int:
    """Count total claims."""
    path = get_db_path()
    query = "SELECT COUNT(*) FROM claims"
    params: list = []
    if member_id:
        query += " WHERE member_id = ?"
        params.append(member_id)

    async with aiosqlite.connect(path) as db:
        cursor = await db.execute(query, params)
        row = await cursor.fetchone()
        return row[0] if row else 0


def _row_to_record(row) -> ClaimRecord:
    """Convert a database row to a ClaimRecord."""
    from app.models.claim import ClaimDecision, ClaimCategory, DocumentMeta

    decision = None
    if row["decision_json"]:
        decision = ClaimDecision.model_validate_json(row["decision_json"])

    trace = None
    if row["trace_json"]:
        trace = json.loads(row["trace_json"])

    documents = []
    if row["documents_json"]:
        docs_raw = json.loads(row["documents_json"])
        documents = [DocumentMeta(**d) for d in docs_raw]

    claims_history = None
    if row["claims_history_json"]:
        claims_history = json.loads(row["claims_history_json"])

    return ClaimRecord(
        claim_id=row["claim_id"],
        member_id=row["member_id"],
        policy_id=row["policy_id"],
        claim_category=ClaimCategory(row["claim_category"]),
        treatment_date=row["treatment_date"],
        claimed_amount=row["claimed_amount"],
        hospital_name=row["hospital_name"],
        status=ClaimStatus(row["status"]),
        decision=decision,
        trace=trace,
        documents=documents,
        submitted_at=row["submitted_at"],
        decided_at=row["decided_at"],
        ytd_claims_amount=row["ytd_claims_amount"] or 0,
        claims_history=claims_history,
        simulate_component_failure=bool(row["simulate_component_failure"]),
    )
