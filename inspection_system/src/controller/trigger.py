"""Trigger simulation — one event per inspection cycle."""

from __future__ import annotations

from datetime import datetime, timedelta

from domain.models import TriggerEvent, utc_now


def build_trigger(cycle_id: int, part_id: str | None = None, at: datetime | None = None) -> TriggerEvent:
    """Construct a trigger for a single sequential cycle."""
    ts = at or utc_now()
    pid = part_id or f"PART-{cycle_id:05d}"
    return TriggerEvent(cycle_id=cycle_id, part_id=pid, timestamp=ts)


def staggered_triggers(count: int, base: datetime | None = None) -> list[TriggerEvent]:
    """Generate `count` triggers with monotonic timestamps (simulates line pacing)."""
    start = base or utc_now()
    return [build_trigger(i + 1, at=start + timedelta(milliseconds=50 * i)) for i in range(count)]
