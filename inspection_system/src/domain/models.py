"""Core domain models for triggers, frames, pipeline output, and reports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class FinalStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class CameraCaptureStatus(str, Enum):
    OK = "OK"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    MISSING = "MISSING"


class FrameQualityFlag(str, Enum):
    INVALID_FRAME = "INVALID_FRAME"
    CORRUPTED_FRAME = "CORRUPTED_FRAME"
    LOW_BRIGHTNESS = "LOW_BRIGHTNESS"
    HIGH_GLARE = "HIGH_GLARE"
    HIGH_BLUR = "HIGH_BLUR"
    INCOMPLETE = "INCOMPLETE_CAPTURE"


class DefectSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class TriggerEvent:
    cycle_id: int
    part_id: str
    timestamp: datetime = field(default_factory=utc_now)


@dataclass
class Frame:
    camera_id: str
    cycle_id: int
    part_id: str
    timestamp: datetime
    brightness: float
    blur: float
    glare: float
    completeness: float
    integrity_ok: bool = True
    """False simulates corrupted buffer / checksum failure — must not reach trusted inference."""


@dataclass
class DefectFinding:
    code: str
    severity: DefectSeverity
    description: str = ""


@dataclass
class InferenceOutput:
    defects: list[DefectFinding]
    confidence: float
    raw_scores: dict[str, float] = field(default_factory=dict)


@dataclass
class CameraPipelineResult:
    camera_id: str
    cycle_id: int
    frame: Frame | None
    capture_status: CameraCaptureStatus
    quality_flags: list[FrameQualityFlag]
    inference: InferenceOutput | None
    low_confidence: bool
    processing_notes: list[str] = field(default_factory=list)


@dataclass
class CycleTiming:
    capture_seconds: float = 0.0
    processing_seconds: float = 0.0
    aggregation_seconds: float = 0.0
    report_seconds: float = 0.0
    total_seconds: float = 0.0


@dataclass
class InspectionReport:
    cycle_id: int
    part_id: str
    final_status: FinalStatus
    camera_results: dict[str, dict[str, Any]]
    aggregated_defects: list[dict[str, Any]]
    min_confidence: float | None
    quality_flags: list[str]
    error_reasons: list[str]
    timing: CycleTiming
    created_at: datetime = field(default_factory=utc_now)
    lifecycle: list[dict[str, Any]] = field(default_factory=list)
    """Ordered stages with ISO timestamps for traceability (trigger through report)."""
    sla_violations: list[str] = field(default_factory=list)
    """Advisory SLA breaches — do not replace inspection outcome logic."""

    def to_json_dict(self) -> dict[str, Any]:
        return {
            "cycle_id": self.cycle_id,
            "part_id": self.part_id,
            "final_status": self.final_status.value,
            "camera_results": self.camera_results,
            "defects": self.aggregated_defects,
            "confidence": self.min_confidence,
            "quality_flags": self.quality_flags,
            "error_reasons": self.error_reasons,
            "timing": {
                "capture_seconds": self.timing.capture_seconds,
                "processing_seconds": self.timing.processing_seconds,
                "aggregation_seconds": self.timing.aggregation_seconds,
                "report_seconds": self.timing.report_seconds,
                "total_seconds": self.timing.total_seconds,
            },
            "lifecycle": self.lifecycle,
            "sla_violations": self.sla_violations,
            "created_at": self.created_at.isoformat(),
        }
