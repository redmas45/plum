"""
Custom exception hierarchy for the claims processing system.
"""


class ClaimException(Exception):
    """Base exception for all claim processing errors."""

    def __init__(self, message: str, code: str = "CLAIM_ERROR", details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}


class DocumentVerificationError(ClaimException):
    """Raised when document verification fails (wrong type, unreadable, etc.)."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="DOCUMENT_VERIFICATION_ERROR", details=details)


class DocumentParsingError(ClaimException):
    """Raised when document parsing / extraction fails."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="DOCUMENT_PARSING_ERROR", details=details)


class PolicyCheckError(ClaimException):
    """Raised when policy check encounters an error (not a rejection)."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="POLICY_CHECK_ERROR", details=details)


class FraudDetectionError(ClaimException):
    """Raised when fraud detection encounters an error."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="FRAUD_DETECTION_ERROR", details=details)


class LLMError(ClaimException):
    """Raised when LLM call fails (timeout, parse error, etc.)."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="LLM_ERROR", details=details)


class MemberNotFoundError(ClaimException):
    """Raised when a member ID is not found in the policy."""

    def __init__(self, member_id: str):
        super().__init__(
            f"Member '{member_id}' not found in the policy roster.",
            code="MEMBER_NOT_FOUND",
            details={"member_id": member_id},
        )


class FileValidationError(ClaimException):
    """Raised when an uploaded file fails validation."""

    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="FILE_VALIDATION_ERROR", details=details)
