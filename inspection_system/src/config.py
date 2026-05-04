"""Central configuration for thresholds, timeouts, retries, and mock SLA budgets."""

from dataclasses import dataclass


@dataclass(frozen=True)
class InspectionConfig:
    """Fail-safe thresholds and bounded-wait policy — tune per SKU and line speed."""

    camera_ids: tuple[str, ...] = ("CAM_A", "CAM_B")

    # --- Frame / inference quality thresholds ---
    min_brightness: float = 0.15
    max_brightness: float = 0.95
    max_glare: float = 0.85
    max_blur: float = 0.75
    min_completeness: float = 0.5
    min_inference_confidence: float = 0.72

    # --- Capture: bounded wait (never block indefinitely on a hung driver thread) ---
    per_camera_capture_deadline_seconds: float = 3.0
    """Wall-clock bound for each camera's capture attempts (includes retries)."""
    capture_max_attempts: int = 2
    """Total capture attempts per camera (default 2 = one failure + one retry)."""

    # --- Mock SLA budgets (advisory logging; mock latencies kept small enough to pass by default) ---
    max_cycle_seconds: float = 1.0
    """Mock line budget for end-to-end cycle wall time (production lines often target ~200ms)."""
    capture_budget_seconds: float = 0.35
    processing_budget_seconds: float = 0.55
    aggregation_budget_seconds: float = 0.05
    report_budget_seconds: float = 0.05

    # --- Legacy field kept for SDK integration notes; parallel capture uses per_camera_capture_deadline_seconds ---
    capture_timeout_seconds: float = 5.0

    mock_capture_delay_seconds: tuple[float, float] = (0.02, 0.08)
    mock_inference_delay_seconds: tuple[float, float] = (0.01, 0.04)


DEFAULT_CONFIG = InspectionConfig()
