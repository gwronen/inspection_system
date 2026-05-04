"""Station-level metrics aggregation."""

import pytest

from domain.models import CameraCaptureStatus, CycleTiming, FinalStatus, InspectionReport


def _report(
    status: FinalStatus,
    cam_rows: dict,
    sla: list[str] | None = None,
) -> InspectionReport:
    return InspectionReport(
        cycle_id=1,
        part_id="P",
        final_status=status,
        camera_results=cam_rows,
        aggregated_defects=[],
        min_confidence=None,
        quality_flags=[],
        error_reasons=[],
        timing=CycleTiming(total_seconds=0.1),
        lifecycle=[],
        sla_violations=list(sla or []),
    )


def test_metrics_failure_rate_and_reliability():
    from observability.metrics import StationMetrics

    ok_row = {
        "capture_status": CameraCaptureStatus.OK.value,
        "low_confidence": False,
    }
    bad_row = {
        "capture_status": CameraCaptureStatus.FAILED.value,
        "low_confidence": False,
    }
    m = StationMetrics()
    m.record_cycle(_report(FinalStatus.PASS, {"CAM_A": ok_row, "CAM_B": ok_row}))
    m.record_cycle(_report(FinalStatus.ERROR, {"CAM_A": bad_row, "CAM_B": ok_row}))
    m.record_cycle(
        _report(
            FinalStatus.REVIEW_REQUIRED,
            {"CAM_A": {**ok_row, "low_confidence": True}, "CAM_B": ok_row},
        )
    )
    assert m.total_cycles == 3
    assert m.pass_count == 1
    assert m.error_count == 1
    assert m.review_count == 1
    assert m.failure_rate() == pytest.approx(2 / 3)
    assert m.low_confidence_cycles == 1
    assert m.low_confidence_pct() == pytest.approx(100 / 3)
    rel = m.camera_reliability()
    assert rel["CAM_A"] == pytest.approx(2 / 3)
    assert rel["CAM_B"] == 1.0
