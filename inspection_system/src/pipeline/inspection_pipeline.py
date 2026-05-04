"""Per-camera sequential pipeline: preprocess → inference → postprocess."""

from __future__ import annotations

import time
from dataclasses import dataclass

from config import InspectionConfig
from domain.models import (
    CameraCaptureStatus,
    CameraPipelineResult,
    Frame,
    FrameQualityFlag,
    InferenceOutput,
)
from pipeline.inference import InferenceBehavior, run_inference
from pipeline.postprocessor import postprocess
from pipeline.preprocessor import preprocess_frame
from observability.logger import get_logger

log = get_logger(__name__)


@dataclass
class PipelineBehaviors:
    inference: InferenceBehavior | None = None


def validate_frame(frame: Frame, cfg: InspectionConfig) -> list[FrameQualityFlag]:
    """Fail-safe frame QC — invalid frames must not be trusted for PASS."""
    flags: list[FrameQualityFlag] = []
    if not frame.integrity_ok:
        flags.append(FrameQualityFlag.CORRUPTED_FRAME)
    if frame.brightness < cfg.min_brightness:
        flags.append(FrameQualityFlag.LOW_BRIGHTNESS)
    if frame.brightness > cfg.max_brightness:
        flags.append(FrameQualityFlag.INVALID_FRAME)
    if frame.glare > cfg.max_glare:
        flags.append(FrameQualityFlag.HIGH_GLARE)
    if frame.blur > cfg.max_blur:
        flags.append(FrameQualityFlag.HIGH_BLUR)
    if frame.completeness < cfg.min_completeness:
        flags.append(FrameQualityFlag.INCOMPLETE)

    if flags:
        flags.append(FrameQualityFlag.INVALID_FRAME)
    return flags


def run_camera_pipeline(
    camera_id: str,
    cycle_id: int,
    capture_status: CameraCaptureStatus,
    frame: Frame | None,
    cfg: InspectionConfig,
    behaviors: PipelineBehaviors | None = None,
) -> CameraPipelineResult:
    """Execute full per-camera path; missing frame skips inference (fail-safe)."""
    t0 = time.perf_counter()
    behaviors = behaviors or PipelineBehaviors()
    notes: list[str] = []

    if capture_status != CameraCaptureStatus.OK or frame is None:
        log.info(
            "pipeline_skipped_missing_capture",
            extra={"camera_id": camera_id, "cycle_id": cycle_id, "status": capture_status.value},
        )
        return CameraPipelineResult(
            camera_id=camera_id,
            cycle_id=cycle_id,
            frame=None,
            capture_status=capture_status,
            quality_flags=[],
            inference=None,
            low_confidence=False,
            processing_notes=["no_frame_skip_inference"],
        )

    log.info(
        "pipeline_stage_start",
        extra={"cycle_id": cycle_id, "camera_id": camera_id, "stage": "validate_frame"},
    )
    quality = validate_frame(frame, cfg)
    invalid = FrameQualityFlag.INVALID_FRAME in quality
    log.info(
        "pipeline_stage_end",
        extra={"cycle_id": cycle_id, "camera_id": camera_id, "stage": "validate_frame"},
    )

    if invalid:
        notes.append("INVALID_FRAME_inference_skipped_for_safety")
        log.warning(
            "invalid_frame_skip_inference",
            extra={"camera_id": camera_id, "cycle_id": cycle_id, "quality": [f.value for f in quality]},
        )
        elapsed = time.perf_counter() - t0
        log.info(
            "processing_camera_done",
            extra={"camera_id": camera_id, "cycle_id": cycle_id, "seconds": round(elapsed, 4)},
        )
        return CameraPipelineResult(
            camera_id=camera_id,
            cycle_id=cycle_id,
            frame=frame,
            capture_status=capture_status,
            quality_flags=quality,
            inference=None,
            low_confidence=False,
            processing_notes=notes,
        )

    log.info(
        "pipeline_stage_start",
        extra={"cycle_id": cycle_id, "camera_id": camera_id, "stage": "preprocess"},
    )
    pre = preprocess_frame(frame, cfg.mock_inference_delay_seconds)
    log.info(
        "pipeline_stage_end",
        extra={"cycle_id": cycle_id, "camera_id": camera_id, "stage": "preprocess"},
    )
    log.info(
        "pipeline_stage_start",
        extra={"cycle_id": cycle_id, "camera_id": camera_id, "stage": "inference"},
    )
    inf = run_inference(pre, cfg.mock_inference_delay_seconds, behavior=behaviors.inference)
    log.info(
        "pipeline_stage_end",
        extra={"cycle_id": cycle_id, "camera_id": camera_id, "stage": "inference"},
    )
    log.info(
        "pipeline_stage_start",
        extra={"cycle_id": cycle_id, "camera_id": camera_id, "stage": "postprocess"},
    )
    inf = postprocess(inf, cfg.mock_inference_delay_seconds)
    log.info(
        "pipeline_stage_end",
        extra={"cycle_id": cycle_id, "camera_id": camera_id, "stage": "postprocess"},
    )
    low_conf = inf.confidence < cfg.min_inference_confidence
    if low_conf:
        notes.append("LOW_CONFIDENCE")

    elapsed = time.perf_counter() - t0
    log.info(
        "processing_camera_done",
        extra={"camera_id": camera_id, "cycle_id": cycle_id, "seconds": round(elapsed, 4)},
    )
    return CameraPipelineResult(
        camera_id=camera_id,
        cycle_id=cycle_id,
        frame=frame,
        capture_status=capture_status,
        quality_flags=quality,
        inference=inf,
        low_confidence=low_conf,
        processing_notes=notes,
    )
