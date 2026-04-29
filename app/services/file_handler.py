"""
Validate and store uploaded files.
Supports images (jpg, png, webp) and PDFs.
"""

from __future__ import annotations

import base64
import logging
import uuid
from pathlib import Path
from typing import Optional

from app.config import settings
from app.models.claim import DocumentMeta
from app.utils.exceptions import FileValidationError

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "application/pdf",
}


async def validate_and_store_file(
    filename: str,
    content: bytes,
    content_type: str,
) -> DocumentMeta:
    """Validate an uploaded file and store it. Returns metadata."""
    # Check extension
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise FileValidationError(
            f"File type '{ext}' is not supported. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}",
            details={"filename": filename, "extension": ext},
        )

    # Check content type
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        logger.warning(f"Unexpected content type: {content_type} for {filename}")

    # Check file size
    if len(content) > settings.max_file_size_bytes:
        raise FileValidationError(
            f"File '{filename}' exceeds maximum size of {settings.max_file_size_mb}MB.",
            details={"filename": filename, "size_bytes": len(content)},
        )

    # Check not empty
    if len(content) == 0:
        raise FileValidationError(
            f"File '{filename}' is empty.",
            details={"filename": filename},
        )

    # Generate unique filename and store
    file_id = f"F{uuid.uuid4().hex[:6].upper()}"
    stored_name = f"{file_id}_{filename}"
    upload_path = settings.upload_path / stored_name

    with open(upload_path, "wb") as f:
        f.write(content)

    logger.info(f"Stored file: {stored_name} ({len(content)} bytes)")

    return DocumentMeta(
        file_id=file_id,
        file_name=filename,
        file_path=str(upload_path),
        content_type=content_type,
    )


def file_to_base64(file_path: str) -> Optional[str]:
    """Read a file and return its base64 encoding."""
    try:
        with open(file_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        logger.error(f"Failed to read file {file_path}: {e}")
        return None


def get_content_type_from_path(file_path: str) -> str:
    """Infer content type from file extension."""
    ext = Path(file_path).suffix.lower()
    mapping = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".pdf": "application/pdf",
    }
    return mapping.get(ext, "application/octet-stream")
