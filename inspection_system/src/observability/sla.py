"""SLA budget checks — advisory logging; does not override fail-safe inspection outcomes."""

from __future__ import annotations

from typing import TYPE_CHECKING

from observability.logger import get_logger

if TYPE_CHECKING:
    from config import InspectionConfig

log = get_logger(__name__)


def check_stage_budget(
    cycle_id: int,
    stage: str,
    elapsed_seconds: float,
    budget_seconds: float,
    violations: list[str],
) -> None:
    """If a stage exceeds its mock SLA budget, record and log (deterministic outcome unchanged)."""
    if budget_seconds <= 0:
        return
    if elapsed_seconds > budget_seconds:
        key = f"{stage}_budget_exceeded:{elapsed_seconds:.4f}s>{budget_seconds:.4f}s"
        violations.append(key)
        log.warning(
            "sla_violation",
            extra={
                "cycle_id": cycle_id,
                "stage": stage,
                "elapsed_seconds": round(elapsed_seconds, 4),
                "budget_seconds": budget_seconds,
            },
        )


def check_total_cycle_budget(cycle_id: int, total_seconds: float, cfg: "InspectionConfig", violations: list[str]) -> None:
    if cfg.max_cycle_seconds <= 0:
        return
    if total_seconds > cfg.max_cycle_seconds:
        violations.append(f"max_cycle_exceeded:{total_seconds:.4f}s>{cfg.max_cycle_seconds:.4f}s")
        log.warning(
            "sla_violation",
            extra={
                "cycle_id": cycle_id,
                "stage": "total_cycle",
                "elapsed_seconds": round(total_seconds, 4),
                "budget_seconds": cfg.max_cycle_seconds,
            },
        )
