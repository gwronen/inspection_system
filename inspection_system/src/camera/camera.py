"""Camera abstraction — mock hardware with configurable behavior."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Callable

from domain.models import Frame, utc_now


@dataclass
class CameraBehavior:
    """Per-cycle overrides for deterministic demos and failure-mode simulation."""

    fail_capture: bool = False
    """If True, capture raises (used with recover_after_fail for retry demos)."""
    recover_after_fail: bool = False
    """After first failure, clear fail_capture so a bounded retry can succeed."""
    simulate_disconnect: bool = False
    """Raises ConnectionError — models cable pull / driver drop."""
    extra_capture_delay_seconds: float = 0.0
    """Additional blocking delay (used with tight deadlines to exercise TIMEOUT)."""
    force_corrupted_frame: bool = False
    """Returns a frame that fails integrity validation (buffer corruption)."""
    force_high_glare: bool = False
    force_high_blur: bool = False
    force_low_brightness: bool = False
    force_low_completeness: bool = False


class MockCamera:
    """Simulates a single camera channel (no SDK — replace in production)."""

    def __init__(self, camera_id: str, rng: random.Random | None = None):
        self.camera_id = camera_id
        self._rng = rng or random.Random()

    def capture(
        self,
        cycle_id: int,
        part_id: str,
        delay_range: tuple[float, float],
        behavior: CameraBehavior | None = None,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> Frame:
        lo, hi = delay_range
        sleep_fn(self._rng.uniform(lo, hi))
        b = behavior or CameraBehavior()
        if b.extra_capture_delay_seconds > 0:
            sleep_fn(b.extra_capture_delay_seconds)
        if b.simulate_disconnect:
            raise ConnectionError(f"mock disconnect on {self.camera_id}")
        if b.fail_capture:
            raise RuntimeError(f"mock hardware fault on {self.camera_id}")

        brightness = self._rng.uniform(0.35, 0.75)
        blur = self._rng.uniform(0.1, 0.35)
        glare = self._rng.uniform(0.1, 0.4)
        completeness = self._rng.uniform(0.85, 1.0)

        if b.force_low_brightness:
            brightness = 0.08
        if b.force_high_glare:
            glare = 0.92
        if b.force_high_blur:
            blur = 0.88
        if b.force_low_completeness:
            completeness = 0.35

        integrity = not b.force_corrupted_frame
        return Frame(
            camera_id=self.camera_id,
            cycle_id=cycle_id,
            part_id=part_id,
            timestamp=utc_now(),
            brightness=brightness,
            blur=blur,
            glare=glare,
            completeness=completeness,
            integrity_ok=integrity,
        )
