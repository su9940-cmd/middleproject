"""Application-specific exceptions."""


class MLServiceError(RuntimeError):
    """Base error raised by the ML inference service."""

    error_code = "MODEL_PREDICTION_FAILED"


class ModelArtifactError(MLServiceError):
    """Raised when a model artifact or its metadata cannot be loaded."""

    error_code = "MODEL_LOAD_FAILED"


class ModelInputError(MLServiceError):
    """Raised when sensor data cannot satisfy the model schema."""

    error_code = "SENSOR_VALIDATION_FAILED"
