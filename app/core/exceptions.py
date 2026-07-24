"""Exception hierarchy shared by every application component."""

from typing import Any


class ApplicationError(RuntimeError):
    """Base error with a stable machine-readable error code."""

    error_code = "APPLICATION_ERROR"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.details = details or {}


class SensorValidationError(ApplicationError):
    """Raised when an incoming sensor reading violates the shared schema."""

    error_code = "SENSOR_VALIDATION_FAILED"


class ModelLoadError(ApplicationError):
    """Raised when a persisted model or metadata artifact cannot be loaded."""

    error_code = "MODEL_LOAD_FAILED"


class ModelPredictionError(ApplicationError):
    """Raised when model inference fails after input validation."""

    error_code = "MODEL_PREDICTION_FAILED"


class RiskPolicyError(ApplicationError):
    """Raised when risk-policy evaluation cannot be completed."""

    error_code = "RISK_POLICY_FAILED"


class RAGRetrievalError(ApplicationError):
    """Raised when safety-document retrieval fails."""

    error_code = "RAG_RETRIEVAL_FAILED"


class MemoryLookupError(ApplicationError):
    """Raised when prior alert or maintenance history cannot be loaded."""

    error_code = "MEMORY_LOOKUP_FAILED"


class ActionDraftError(ApplicationError):
    """Raised when an action draft cannot be composed."""

    error_code = "ACTION_DRAFT_FAILED"


class ChecklistValidationError(ApplicationError):
    """Raised when a grounded checklist cannot be validated."""

    error_code = "CHECKLIST_VALIDATION_FAILED"


class NotificationError(ApplicationError):
    """Raised when an immediate notification cannot be sent."""

    error_code = "NOTIFICATION_FAILED"


class WorkerResponseSaveError(ApplicationError):
    """Raised when a worker response cannot be persisted."""

    error_code = "WORKER_RESPONSE_SAVE_FAILED"


class WorkerResponseValidationError(ApplicationError):
    """Raised when a resumed worker response violates the incident contract."""

    error_code = "WORKER_RESPONSE_VALIDATION_FAILED"


class RecheckRequestError(ApplicationError):
    """Raised when an immediate sensor recheck cannot be requested."""

    error_code = "RECHECK_REQUEST_FAILED"


class DatabaseOperationError(ApplicationError):
    """Raised when a required persistence operation fails."""

    error_code = "DATABASE_OPERATION_FAILED"


class MLServiceError(ModelPredictionError):
    """Backward-compatible base error raised by the ML inference adapter."""


class ModelArtifactError(MLServiceError):
    """Raised when a model artifact or its metadata cannot be loaded."""

    error_code = "MODEL_LOAD_FAILED"


class ModelInputError(MLServiceError):
    """Raised when sensor data cannot satisfy the model schema."""

    error_code = "SENSOR_VALIDATION_FAILED"
