"""Batch-level metrics for station health — offline counters only (no external sink)."""

from __future__ import annotations

from dataclasses import dataclass, field

from domain.models import CameraCaptureStatus, FinalStatus, InspectionReport


@dataclass
class StationMetrics:
    """Accumulated statistics across a run of sequential cycles."""

    total_cycles: int = 0
    pass_count: int = 0
    fail_count: int = 0
    error_count: int = 0
    review_count: int = 0
    sla_violation_cycles: int = 0
    low_confidence_cycles: int = 0
    camera_capture_ok: dict[str, int] = field(default_factory=dict)
    camera_capture_not_ok: dict[str, int] = field(default_factory=dict)
    max_cycle_seconds: float = 0.0
    sum_cycle_seconds: float = 0.0

    def record_cycle(self, report: InspectionReport) -> None:
        self.total_cycles += 1
        self.sum_cycle_seconds += report.timing.total_seconds
        self.max_cycle_seconds = max(self.max_cycle_seconds, report.timing.total_seconds)

        if report.final_status == FinalStatus.PASS:
            self.pass_count += 1
        elif report.final_status == FinalStatus.FAIL:
            self.fail_count += 1
        elif report.final_status == FinalStatus.ERROR:
            self.error_count += 1
        else:
            self.review_count += 1

        if report.sla_violations:
            self.sla_violation_cycles += 1

        for cam_id, row in report.camera_results.items():
            st = row.get("capture_status")
            if st == CameraCaptureStatus.OK.value:
                self.camera_capture_ok[cam_id] = self.camera_capture_ok.get(cam_id, 0) + 1
            else:
                self.camera_capture_not_ok[cam_id] = self.camera_capture_not_ok.get(cam_id, 0) + 1

        if any(row.get("low_confidence") for row in report.camera_results.values()):
            self.low_confidence_cycles += 1

    def failure_rate(self) -> float:
        if self.total_cycles == 0:
            return 0.0
        non_pass = self.fail_count + self.error_count + self.review_count
        return non_pass / self.total_cycles

    def avg_cycle_seconds(self) -> float:
        if self.total_cycles == 0:
            return 0.0
        return self.sum_cycle_seconds / self.total_cycles

    def low_confidence_pct(self) -> float:
        if self.total_cycles == 0:
            return 0.0
        return 100.0 * self.low_confidence_cycles / self.total_cycles

    def camera_reliability(self) -> dict[str, float]:
        """Share of cycles where each camera reported OK capture (same part still requires both)."""
        out: dict[str, float] = {}
        for cam_id in set(self.camera_capture_ok) | set(self.camera_capture_not_ok):
            ok = self.camera_capture_ok.get(cam_id, 0)
            bad = self.camera_capture_not_ok.get(cam_id, 0)
            tot = ok + bad
            out[cam_id] = (ok / tot) if tot else 0.0
        return out

    def summary_lines(self) -> list[str]:
        rel = self.camera_reliability()
        rel_fmt = ", ".join(f"{k}={v:.1%}" for k, v in sorted(rel.items()))
        return [
            f"total_cycles={self.total_cycles}",
            f"PASS={self.pass_count} FAIL={self.fail_count} ERROR={self.error_count} REVIEW_REQUIRED={self.review_count}",
            f"failure_rate={self.failure_rate():.1%}",
            f"avg_cycle_time_s={self.avg_cycle_seconds():.4f} max_cycle_time_s={self.max_cycle_seconds:.4f}",
            f"cycles_with_sla_violation={self.sla_violation_cycles}",
            f"low_confidence_cycle_pct={self.low_confidence_pct():.1f}%",
            f"camera_capture_ok_rate_by_camera: {rel_fmt or 'n/a'}",
        ]
