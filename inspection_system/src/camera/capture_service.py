"""Parallel capture across two cameras with bounded waits and configurable retry attempts."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from camera.camera import CameraBehavior, MockCamera
from config import InspectionConfig
from domain.models import CameraCaptureStatus, Frame
from observability.logger import get_logger

log = get_logger(__name__)


def _capture_one(
    cam: MockCamera,
    cycle_id: int,
    part_id: str,
    delay_range: tuple[float, float],
    behavior: CameraBehavior | None,
) -> tuple[str, Frame]:
    frame = cam.capture(cycle_id, part_id, delay_range, behavior=behavior)
    return cam.camera_id, frame


class CaptureService:
    """Runs exactly two cameras in parallel for the same part at the same instant (mock time)."""

    def __init__(self, cameras: list[MockCamera], config: InspectionConfig):
        self._cameras = {c.camera_id: c for c in cameras}
        self._config = config

    def capture_parallel(
        self,
        cycle_id: int,
        part_id: str,
        behaviors: dict[str, CameraBehavior] | None = None,
    ) -> dict[str, tuple[CameraCaptureStatus, Frame | None]]:
        """
        Returns per-camera (status, frame or None).

        Each camera runs up to ``capture_max_attempts`` attempts for transient faults only
        (never infinite retries). Each camera future is joined with ``per_camera_capture_deadline_seconds``
        so a hung SDK call cannot stall the station indefinitely.
        """
        behaviors = behaviors or {}
        results: dict[str, tuple[CameraCaptureStatus, Frame | None]] = {}

        def attempt_for(cam_id: str) -> tuple[str, CameraCaptureStatus, Frame | None]:
            cam = self._cameras[cam_id]
            base = behaviors.get(cam_id)
            max_att = max(1, self._config.capture_max_attempts)
            for attempt in range(1, max_att + 1):
                try:
                    behavior = base
                    if base is not None and attempt >= 2 and base.recover_after_fail:
                        behavior = replace(base, fail_capture=False)
                    _, frame = _capture_one(
                        cam,
                        cycle_id,
                        part_id,
                        self._config.mock_capture_delay_seconds,
                        behavior=behavior,
                    )
                    return cam_id, CameraCaptureStatus.OK, frame
                except Exception as exc:  # noqa: BLE001 — per-cycle isolation; never crash station
                    log.warning(
                        "capture_attempt_failed",
                        extra={
                            "camera_id": cam_id,
                            "cycle_id": cycle_id,
                            "attempt": attempt,
                            "error": str(exc),
                            "error_type": type(exc).__name__,
                        },
                    )
                    if attempt == max_att:
                        return cam_id, CameraCaptureStatus.FAILED, None
            return cam_id, CameraCaptureStatus.FAILED, None

        log.info(
            "capture_start",
            extra={
                "cycle_id": cycle_id,
                "part_id": part_id,
                "cameras": list(self._cameras),
            },
        )
        t0 = time.perf_counter()
        deadline = self._config.per_camera_capture_deadline_seconds
        with ThreadPoolExecutor(max_workers=len(self._cameras)) as pool:
            future_map = {pool.submit(attempt_for, cid): cid for cid in self._cameras}
            for fut, cam_id in future_map.items():
                try:
                    _cid, status, frame = fut.result(timeout=deadline)
                    results[_cid] = (status, frame)
                except TimeoutError:
                    log.warning(
                        "capture_timeout",
                        extra={
                            "cycle_id": cycle_id,
                            "part_id": part_id,
                            "camera_id": cam_id,
                            "deadline_seconds": deadline,
                        },
                    )
                    results[cam_id] = (CameraCaptureStatus.TIMEOUT, None)
        elapsed = time.perf_counter() - t0
        log.info(
            "capture_end",
            extra={"cycle_id": cycle_id, "part_id": part_id, "elapsed_seconds": round(elapsed, 4)},
        )
        return results
