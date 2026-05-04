"""SLA helpers record violations without mutating inspection outcomes."""

from config import InspectionConfig
from observability.sla import check_stage_budget, check_total_cycle_budget


def test_check_stage_budget_appends_violation():
    v: list[str] = []
    check_stage_budget(7, "capture", 1.0, 0.5, v)
    assert v and "capture_budget_exceeded" in v[0]


def test_check_total_cycle_budget():
    v: list[str] = []
    cfg = InspectionConfig(max_cycle_seconds=0.01)
    check_total_cycle_budget(3, 0.5, cfg, v)
    assert any("max_cycle_exceeded" in x for x in v)
