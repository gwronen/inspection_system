"""Mock inference — returns defects, confidence, severity."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass

from domain.models import DefectFinding, DefectSeverity, InferenceOutput
from observability.logger import get_logger

log = get_logger(__name__)


@dataclass
class InferenceBehavior:
    """Deterministic hooks for demo cycles."""

    force_low_confidence: bool = False
    inject_critical_defect: bool = False
    inject_minor_defect: bool = False


def run_inference(
    preprocessed: dict,
    mock_delay: tuple[float, float],
    behavior: InferenceBehavior | None = None,
    rng: random.Random | None = None,
) -> InferenceOutput:
    """Pretend neural net — latency + structured output only."""
    rng = rng or random.Random()
    time.sleep(rng.uniform(*mock_delay))
    b = behavior or InferenceBehavior()
    defects: list[DefectFinding] = []
    if b.inject_critical_defect:
        defects.append(
            DefectFinding("SCRATCH_TOP", DefectSeverity.CRITICAL, "edge scratch cluster"),
        )
    if b.inject_minor_defect:
        defects.append(DefectFinding("COSMETIC_01", DefectSeverity.LOW, "minor blemish"))

    confidence = rng.uniform(0.78, 0.96)
    if b.force_low_confidence:
        confidence = 0.55

    frame = preprocessed.get("frame")
    cam = getattr(frame, "camera_id", "?")
    cyc = getattr(frame, "cycle_id", None)
    log.info(
        "inference_done",
        extra={"camera_id": cam, "cycle_id": cyc, "confidence": round(confidence, 3)},
    )
    return InferenceOutput(defects=defects, confidence=confidence, raw_scores={"ok": confidence})
