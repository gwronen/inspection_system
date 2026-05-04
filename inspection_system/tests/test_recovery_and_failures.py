"""Recovery, bounded capture, and failure-mode wiring."""

import random
import time

import pytest

from aggregation.aggregator import aggregate
from camera.camera import CameraBehavior, MockCamera
from camera.capture_service import CaptureService
from config import InspectionConfig
from config import DEFAULT_CONFIG
from domain.models import (
    CameraCaptureStatus,
    CameraPipelineResult,
    FinalStatus,
    Frame,
    InferenceOutput,
    utc_now,
)
from pipeline.inspection_pipeline import validate_frame


def test_capture_recovers_after_transient_fault(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    cfg = InspectionConfig(
        mock_capture_delay_seconds=(0.0, 0.0),
        per_camera_capture_deadline_seconds=5.0,
        capture_max_attempts=2,
    )
    cams = [MockCamera("CAM_A", rng=random.Random(1)), MockCamera("CAM_B", rng=random.Random(2))]
    svc = CaptureService(cams, cfg)
    behaviors = {
        "CAM_A": CameraBehavior(fail_capture=True, recover_after_fail=True),
        "CAM_B": CameraBehavior(),
    }
    out = svc.capture_parallel(1, "P1", behaviors=behaviors)
    assert out["CAM_A"][0] == CameraCaptureStatus.OK
    assert out["CAM_A"][1] is not None
    assert out["CAM_B"][0] == CameraCaptureStatus.OK


def test_capture_stays_failed_without_recovery(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_: None)
    cfg = InspectionConfig(
        mock_capture_delay_seconds=(0.0, 0.0),
        per_camera_capture_deadline_seconds=5.0,
        capture_max_attempts=2,
    )
    cams = [MockCamera("CAM_A", rng=random.Random(3)), MockCamera("CAM_B", rng=random.Random(4))]
    svc = CaptureService(cams, cfg)
    behaviors = {"CAM_A": CameraBehavior(fail_capture=True, recover_after_fail=False), "CAM_B": CameraBehavior()}
    out = svc.capture_parallel(2, "P1", behaviors=behaviors)
    assert out["CAM_A"][0] == CameraCaptureStatus.FAILED
    assert out["CAM_A"][1] is None


def test_capture_times_out_instead_of_blocking():
    cfg = InspectionConfig(
        mock_capture_delay_seconds=(0.0, 0.0),
        per_camera_capture_deadline_seconds=0.05,
        capture_max_attempts=1,
    )
    cams = [MockCamera("CAM_A", rng=random.Random(5)), MockCamera("CAM_B", rng=random.Random(6))]
    svc = CaptureService(cams, cfg)
    behaviors = {"CAM_A": CameraBehavior(extra_capture_delay_seconds=0.2), "CAM_B": CameraBehavior()}
    out = svc.capture_parallel(3, "P1", behaviors=behaviors)
    assert out["CAM_A"][0] == CameraCaptureStatus.TIMEOUT
    assert out["CAM_B"][0] == CameraCaptureStatus.OK


def test_corrupted_frame_flags_invalid():
    cfg = InspectionConfig()
    f = Frame(
        camera_id="X",
        cycle_id=1,
        part_id="P",
        timestamp=utc_now(),
        brightness=0.5,
        blur=0.1,
        glare=0.1,
        completeness=1.0,
        integrity_ok=False,
    )
    flags = validate_frame(f, cfg)
    assert any(x.value == "CORRUPTED_FRAME" for x in flags)
    assert any(x.value == "INVALID_FRAME" for x in flags)


@pytest.mark.parametrize(
    "status",
    [CameraCaptureStatus.FAILED, CameraCaptureStatus.TIMEOUT],
)
def test_aggregation_error_on_non_ok_capture(status):
    cfg = DEFAULT_CONFIG
    a, b = cfg.camera_ids
    good = Frame(
        camera_id=b,
        cycle_id=1,
        part_id="P1",
        timestamp=utc_now(),
        brightness=0.5,
        blur=0.1,
        glare=0.1,
        completeness=1.0,
    )
    rows = [
        CameraPipelineResult(
            camera_id=a,
            cycle_id=1,
            frame=None,
            capture_status=status,
            quality_flags=[],
            inference=None,
            low_confidence=False,
        ),
        CameraPipelineResult(
            camera_id=b,
            cycle_id=1,
            frame=good,
            capture_status=CameraCaptureStatus.OK,
            quality_flags=[],
            inference=InferenceOutput(defects=[], confidence=0.9),
            low_confidence=False,
        ),
    ]
    out = aggregate(rows, cfg.camera_ids, cycle_id=99)
    assert out.status == FinalStatus.ERROR
