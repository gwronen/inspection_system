"""Aggregation rules — fail-safe outcomes."""

from domain.models import (
    CameraCaptureStatus,
    CameraPipelineResult,
    DefectFinding,
    DefectSeverity,
    FinalStatus,
    Frame,
    FrameQualityFlag,
    InferenceOutput,
    utc_now,
)
from aggregation.aggregator import aggregate
from config import DEFAULT_CONFIG


def _frame(cam: str, cycle: int = 1) -> Frame:
    return Frame(
        camera_id=cam,
        cycle_id=cycle,
        part_id="P1",
        timestamp=utc_now(),
        brightness=0.5,
        blur=0.2,
        glare=0.2,
        completeness=1.0,
    )


def test_aggregation_fail_on_critical_defect():
    cfg = DEFAULT_CONFIG
    a, b = cfg.camera_ids
    rows = [
        CameraPipelineResult(
            camera_id=a,
            cycle_id=1,
            frame=_frame(a),
            capture_status=CameraCaptureStatus.OK,
            quality_flags=[],
            inference=InferenceOutput(
                defects=[DefectFinding("X", DefectSeverity.CRITICAL, "")],
                confidence=0.9,
            ),
            low_confidence=False,
        ),
        CameraPipelineResult(
            camera_id=b,
            cycle_id=1,
            frame=_frame(b),
            capture_status=CameraCaptureStatus.OK,
            quality_flags=[],
            inference=InferenceOutput(defects=[], confidence=0.9),
            low_confidence=False,
        ),
    ]
    out = aggregate(rows, cfg.camera_ids)
    assert out.status == FinalStatus.FAIL


def test_aggregation_error_on_missing_camera():
    cfg = DEFAULT_CONFIG
    a = cfg.camera_ids[0]
    rows = [
        CameraPipelineResult(
            camera_id=a,
            cycle_id=1,
            frame=_frame(a),
            capture_status=CameraCaptureStatus.OK,
            quality_flags=[],
            inference=InferenceOutput(defects=[], confidence=0.9),
            low_confidence=False,
        ),
    ]
    out = aggregate(rows, cfg.camera_ids)
    assert out.status == FinalStatus.ERROR
    assert any("INSPECTION_INCOMPLETE" in r for r in out.reasons)


def test_aggregation_pass_when_all_valid():
    cfg = DEFAULT_CONFIG
    a, b = cfg.camera_ids
    rows = [
        CameraPipelineResult(
            camera_id=a,
            cycle_id=1,
            frame=_frame(a),
            capture_status=CameraCaptureStatus.OK,
            quality_flags=[],
            inference=InferenceOutput(defects=[], confidence=0.9),
            low_confidence=False,
        ),
        CameraPipelineResult(
            camera_id=b,
            cycle_id=1,
            frame=_frame(b),
            capture_status=CameraCaptureStatus.OK,
            quality_flags=[],
            inference=InferenceOutput(defects=[], confidence=0.91),
            low_confidence=False,
        ),
    ]
    out = aggregate(rows, cfg.camera_ids)
    assert out.status == FinalStatus.PASS
    assert not out.aggregated_defects


def test_aggregation_review_on_invalid_frame():
    cfg = DEFAULT_CONFIG
    a, b = cfg.camera_ids
    rows = [
        CameraPipelineResult(
            camera_id=a,
            cycle_id=1,
            frame=_frame(a),
            capture_status=CameraCaptureStatus.OK,
            quality_flags=[FrameQualityFlag.HIGH_GLARE, FrameQualityFlag.INVALID_FRAME],
            inference=None,
            low_confidence=False,
        ),
        CameraPipelineResult(
            camera_id=b,
            cycle_id=1,
            frame=_frame(b),
            capture_status=CameraCaptureStatus.OK,
            quality_flags=[],
            inference=InferenceOutput(defects=[], confidence=0.9),
            low_confidence=False,
        ),
    ]
    out = aggregate(rows, cfg.camera_ids)
    assert out.status == FinalStatus.REVIEW_REQUIRED
