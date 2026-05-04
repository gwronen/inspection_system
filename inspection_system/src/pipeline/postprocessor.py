"""Post-process mock outputs — thresholding and label cleanup."""

from __future__ import annotations

import time

from domain.models import InferenceOutput
from observability.logger import get_logger

log = get_logger(__name__)


def postprocess(inference: InferenceOutput, mock_delay: tuple[float, float]) -> InferenceOutput:
    import random

    time.sleep(random.uniform(*mock_delay))
    log.info("postprocess_done", extra={"defect_count": len(inference.defects)})
    return inference
