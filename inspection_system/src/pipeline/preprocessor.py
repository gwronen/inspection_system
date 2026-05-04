"""Frame preprocessing — mock normalization and metadata attachment."""

from __future__ import annotations

import time

from domain.models import Frame
from observability.logger import get_logger

log = get_logger(__name__)


def preprocess_frame(frame: Frame, mock_delay: tuple[float, float]) -> dict:
    """Return a simple dict carrying the frame forward (real system: tensors, ROI, etc.)."""
    import random

    time.sleep(random.uniform(*mock_delay))
    log.info("preprocess_done", extra={"camera_id": frame.camera_id, "cycle_id": frame.cycle_id})
    return {"frame": frame, "normalized": True}
