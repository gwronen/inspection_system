"""Combine per-camera pipeline results into a single fail-safe line decision."""

from __future__ import annotations

from dataclasses import dataclass

from domain.models import (
    CameraCaptureStatus,
    CameraPipelineResult,
    DefectFinding,
    DefectSeverity,
    FinalStatus,
    FrameQualityFlag,
)
from observability.logger import get_logger

log = get_logger(__name__)


@dataclass
class AggregationOutcome:
    status: FinalStatus
    reasons: list[str]
    aggregated_defects: list[DefectFinding]


def _severity_fails_line(sev: DefectSeverity) -> bool:
    return sev in (DefectSeverity.CRITICAL, DefectSeverity.HIGH)


def _severity_needs_review(sev: DefectSeverity) -> bool:
    return sev in (DefectSeverity.MEDIUM, DefectSeverity.LOW)


def aggregate(
    camera_results: list[CameraPipelineResult],
    expected_cameras: tuple[str, ...],
    cycle_id: int | None = None,
) -> AggregationOutcome:
    """
    Strict rules:
    - Any missing / failed capture → ERROR (INSPECTION_INCOMPLETE)
    - Any invalid frame → REVIEW_REQUIRED (inference skipped / unreliable)
    - Any low confidence → REVIEW_REQUIRED
    - Any CRITICAL/HIGH defect → FAIL
    - Any lower-severity defect → REVIEW_REQUIRED (not PASS — not defect-free)
    - PASS only when both cameras OK, frames valid, confidence OK, zero defects
    """
    reasons: list[str] = []
    defects_out: list[DefectFinding] = []

    by_cam = {r.camera_id: r for r in camera_results}

    _cx = {"cycle_id": cycle_id} if cycle_id is not None else {}

    for cam_id in expected_cameras:
        if cam_id not in by_cam:
            reasons.append(f"INSPECTION_INCOMPLETE: missing pipeline result for {cam_id}")
            log.warning("aggregation_missing_camera", extra={"camera_id": cam_id, **_cx})
            return AggregationOutcome(FinalStatus.ERROR, reasons, defects_out)

    for cam_id in expected_cameras:
        r = by_cam[cam_id]
        if r.capture_status != CameraCaptureStatus.OK or r.frame is None:
            reasons.append(f"INSPECTION_INCOMPLETE: camera {cam_id} capture not OK ({r.capture_status.value})")
            log.warning(
                "aggregation_incomplete_capture",
                extra={"camera_id": cam_id, "status": r.capture_status.value, **_cx},
            )
            return AggregationOutcome(FinalStatus.ERROR, reasons, defects_out)

    for cam_id in expected_cameras:
        r = by_cam[cam_id]
        if FrameQualityFlag.INVALID_FRAME in r.quality_flags:
            reasons.append(f"INVALID_FRAME on {cam_id}")
            # Continue collecting other issues for the report

    if any(FrameQualityFlag.INVALID_FRAME in by_cam[c].quality_flags for c in expected_cameras):
        log.warning("aggregation_invalid_frame", extra={"cameras": list(expected_cameras), **_cx})
        return AggregationOutcome(FinalStatus.REVIEW_REQUIRED, reasons, defects_out)

    for cam_id in expected_cameras:
        r = by_cam[cam_id]
        if r.low_confidence:
            reasons.append(f"LOW_CONFIDENCE on {cam_id}")

    if any(by_cam[c].low_confidence for c in expected_cameras):
        return AggregationOutcome(FinalStatus.REVIEW_REQUIRED, reasons, defects_out)

    for cam_id in expected_cameras:
        r = by_cam[cam_id]
        inf = r.inference
        if inf is None:
            reasons.append(f"INCOMPLETE_INFERENCE on {cam_id}")
            return AggregationOutcome(FinalStatus.ERROR, reasons, defects_out)
        for d in inf.defects:
            defects_out.append(d)
            if _severity_fails_line(d.severity):
                reasons.append(f"DEFECT_FAIL:{d.code}:{d.severity.value}")
            elif _severity_needs_review(d.severity):
                reasons.append(f"DEFECT_REVIEW:{d.code}:{d.severity.value}")

    for d in defects_out:
        if _severity_fails_line(d.severity):
            log.warning(
                "aggregation_fail_defect",
                extra={"code": d.code, "severity": d.severity.value, **_cx},
            )
            return AggregationOutcome(FinalStatus.FAIL, reasons, defects_out)

    if defects_out:
        return AggregationOutcome(FinalStatus.REVIEW_REQUIRED, reasons, defects_out)

    log.info("aggregation_pass", extra={"cameras": list(expected_cameras), **_cx})
    return AggregationOutcome(FinalStatus.PASS, [], defects_out)
