"""End-to-end single-camera pipeline smoke test."""

import time

from domain.models import CameraCaptureStatus
from pipeline.inspection_pipeline import PipelineBehaviors, run_camera_pipeline
from domain.models import Frame, utc_now
from config import InspectionConfig


def test_pipeline_runs_single_cycle(monkeypatch):
    cfg = InspectionConfig(
        mock_capture_delay_seconds=(0.0, 0.0),
        mock_inference_delay_seconds=(0.0, 0.0),
    )
    monkeypatch.setattr(time, "sleep", lambda *_: None)

    frame = Frame(
        camera_id="CAM_TEST",
        cycle_id=1,
        part_id="P1",
        timestamp=utc_now(),
        brightness=0.55,
        blur=0.1,
        glare=0.1,
        completeness=1.0,
    )
    result = run_camera_pipeline(
        "CAM_TEST",
        1,
        CameraCaptureStatus.OK,
        frame,
        cfg,
        behaviors=PipelineBehaviors(),
    )
    assert result.capture_status == CameraCaptureStatus.OK
    assert result.inference is not None
    assert result.inference.confidence > 0
    assert not result.quality_flags
