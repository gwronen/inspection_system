"""Domain-specific errors for the inspection system."""


class InspectionError(Exception):
    """Base class for inspection-related failures."""

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.code = code or "INSPECTION_ERROR"


class CameraCaptureError(InspectionError):
    """Raised when a camera fails to capture after retries."""

    def __init__(self, message: str, camera_id: str | None = None):
        super().__init__(message, code="CAMERA_CAPTURE_ERROR")
        self.camera_id = camera_id


class FrameValidationError(InspectionError):
    """Frame failed quality or completeness checks."""

    def __init__(self, message: str, reason: str | None = None):
        super().__init__(message, code="FRAME_VALIDATION_ERROR")
        self.reason = reason or "INVALID_FRAME"


class AggregationError(InspectionError):
    """Logical error during result aggregation."""

    pass
