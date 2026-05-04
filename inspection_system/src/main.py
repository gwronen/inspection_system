"""Entry point — runs 10 sequential mock inspection cycles for one production line."""

from __future__ import annotations

import json
import random
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

from aggregation.aggregator import aggregate
from camera.camera import CameraBehavior, MockCamera
from camera.capture_service import CaptureService
from config import DEFAULT_CONFIG, InspectionConfig
from controller.trigger import build_trigger
from domain.models import (
    CycleTiming,
    FinalStatus,
    InspectionReport,
    utc_now,
)
from observability.logger import get_logger
from observability.metrics import StationMetrics
from observability.sla import check_stage_budget, check_total_cycle_budget
from pipeline.inspection_pipeline import PipelineBehaviors, run_camera_pipeline
from pipeline.inference import InferenceBehavior
from reporting.reporter import build_report, print_console_summary, write_cycle_json

log = get_logger(__name__)


@dataclass
class CycleScenario:
    """Deterministic demo overrides per cycle."""

    capture: dict[str, CameraBehavior]
    pipeline: dict[str, PipelineBehaviors]


def default_scenario(cfg: InspectionConfig) -> CycleScenario:
    empty = {c: CameraBehavior() for c in cfg.camera_ids}
    return CycleScenario(capture=empty, pipeline={c: PipelineBehaviors() for c in cfg.camera_ids})


def build_demo_scenarios(cfg: InspectionConfig) -> dict[int, CycleScenario]:
    a, b = cfg.camera_ids
    d = default_scenario(cfg)

    s: dict[int, CycleScenario] = {}

    # 1 — nominal PASS
    s[1] = d

    # 2 — critical defect FAIL
    s[2] = CycleScenario(
        capture={a: CameraBehavior(), b: CameraBehavior()},
        pipeline={
            a: PipelineBehaviors(inference=InferenceBehavior(inject_critical_defect=True)),
            b: PipelineBehaviors(),
        },
    )

    # 3 — hard camera failure after bounded retries
    s[3] = CycleScenario(
        capture={a: CameraBehavior(), b: CameraBehavior(fail_capture=True, recover_after_fail=False)},
        pipeline={c: PipelineBehaviors() for c in cfg.camera_ids},
    )

    # 4 — glare / overexposure → invalid frame
    s[4] = CycleScenario(
        capture={a: CameraBehavior(force_high_glare=True), b: CameraBehavior()},
        pipeline={c: PipelineBehaviors() for c in cfg.camera_ids},
    )

    # 5 — low confidence inference
    s[5] = CycleScenario(
        capture={a: CameraBehavior(), b: CameraBehavior()},
        pipeline={
            a: PipelineBehaviors(inference=InferenceBehavior(force_low_confidence=True)),
            b: PipelineBehaviors(),
        },
    )

    # 6 — corrupted frame (integrity failure) — same handling path as other invalid frames
    s[6] = CycleScenario(
        capture={a: CameraBehavior(force_corrupted_frame=True), b: CameraBehavior()},
        pipeline={c: PipelineBehaviors() for c in cfg.camera_ids},
    )

    # 7 — transient capture fault, recovers on bounded retry
    s[7] = CycleScenario(
        capture={a: CameraBehavior(fail_capture=True, recover_after_fail=True), b: CameraBehavior()},
        pipeline={c: PipelineBehaviors() for c in cfg.camera_ids},
    )

    # 8 — blur / low spatial quality
    s[8] = CycleScenario(
        capture={a: CameraBehavior(), b: CameraBehavior(force_high_blur=True)},
        pipeline={c: PipelineBehaviors() for c in cfg.camera_ids},
    )

    # 9 — minor defect only → REVIEW_REQUIRED (not defect-free)
    s[9] = CycleScenario(
        capture={a: CameraBehavior(), b: CameraBehavior()},
        pipeline={
            a: PipelineBehaviors(inference=InferenceBehavior(inject_minor_defect=True)),
            b: PipelineBehaviors(),
        },
    )

    # 10 — nominal PASS
    s[10] = d
    return s


def run_inspection_cycle(
    cycle_id: int,
    part_id: str,
    cfg: InspectionConfig,
    capture: CaptureService,
    scenario: CycleScenario,
    reports_dir: Path,
) -> InspectionReport:
    wall_t0 = time.perf_counter()
    timing = CycleTiming()
    sla_violations: list[str] = []
    lifecycle: list[dict] = []

    def _life(stage: str, started: str, ended: str, **extra: str | float) -> None:
        row: dict = {"stage": stage, "started_at": started, "ended_at": ended}
        row.update(extra)
        lifecycle.append(row)

    # --- Trigger ---
    ts = utc_now().isoformat()
    log.info("cycle_stage_start", extra={"cycle_id": cycle_id, "stage": "trigger", "part_id": part_id})
    log.info("trigger_received", extra={"cycle_id": cycle_id, "part_id": part_id})
    log.info("cycle_stage_end", extra={"cycle_id": cycle_id, "stage": "trigger"})
    te = utc_now().isoformat()
    _life("trigger", ts, te, part_id=part_id)

    # --- Parallel capture ---
    log.info("cycle_stage_start", extra={"cycle_id": cycle_id, "stage": "capture_parallel"})
    cs = utc_now().isoformat()
    t_cap = time.perf_counter()
    cap_map = capture.capture_parallel(cycle_id, part_id, behaviors=scenario.capture)
    timing.capture_seconds = time.perf_counter() - t_cap
    ce = utc_now().isoformat()
    log.info("cycle_stage_end", extra={"cycle_id": cycle_id, "stage": "capture_parallel"})
    _life("capture_parallel", cs, ce)
    check_stage_budget(cycle_id, "capture", timing.capture_seconds, cfg.capture_budget_seconds, sla_violations)

    # --- Per-camera processing (sequential across cameras) ---
    log.info("cycle_stage_start", extra={"cycle_id": cycle_id, "stage": "processing"})
    ps = utc_now().isoformat()
    t_proc = time.perf_counter()
    camera_rows = []
    for cam_id in sorted(cfg.camera_ids):
        status, frame = cap_map[cam_id]
        pipe = scenario.pipeline.get(cam_id, PipelineBehaviors())
        row = run_camera_pipeline(cam_id, cycle_id, status, frame, cfg, behaviors=pipe)
        camera_rows.append(row)
    timing.processing_seconds = time.perf_counter() - t_proc
    pe = utc_now().isoformat()
    log.info("cycle_stage_end", extra={"cycle_id": cycle_id, "stage": "processing"})
    _life("processing", ps, pe)
    check_stage_budget(cycle_id, "processing", timing.processing_seconds, cfg.processing_budget_seconds, sla_violations)

    # --- Aggregation ---
    log.info("cycle_stage_start", extra={"cycle_id": cycle_id, "stage": "aggregation"})
    ags = utc_now().isoformat()
    t_agg = time.perf_counter()
    log.info("aggregation_start", extra={"cycle_id": cycle_id})
    outcome = aggregate(camera_rows, cfg.camera_ids, cycle_id=cycle_id)
    log.info(
        "aggregation_done",
        extra={"cycle_id": cycle_id, "status": outcome.status.value},
    )
    timing.aggregation_seconds = time.perf_counter() - t_agg
    age = utc_now().isoformat()
    log.info("cycle_stage_end", extra={"cycle_id": cycle_id, "stage": "aggregation"})
    _life("aggregation", ags, age)
    check_stage_budget(
        cycle_id,
        "aggregation",
        timing.aggregation_seconds,
        cfg.aggregation_budget_seconds,
        sla_violations,
    )

    # --- Report: JSON write is timed; wall total includes persistence; SLA checks run after timings are known ---
    log.info("cycle_stage_start", extra={"cycle_id": cycle_id, "stage": "report"})
    rs = utc_now().isoformat()
    re = utc_now().isoformat()
    log.info("cycle_stage_end", extra={"cycle_id": cycle_id, "stage": "report"})
    full_lifecycle = list(lifecycle) + [{"stage": "report", "started_at": rs, "ended_at": re}]

    report = build_report(
        cycle_id,
        part_id,
        camera_rows,
        outcome,
        timing,
        lifecycle=full_lifecycle,
        sla_violations=list(sla_violations),
    )

    pre_sla_len = len(sla_violations)
    t_wr = time.perf_counter()
    write_cycle_json(report, reports_dir)
    timing.report_seconds = time.perf_counter() - t_wr
    timing.total_seconds = time.perf_counter() - wall_t0
    report.timing.report_seconds = timing.report_seconds
    report.timing.total_seconds = timing.total_seconds

    check_stage_budget(cycle_id, "report", timing.report_seconds, cfg.report_budget_seconds, sla_violations)
    check_total_cycle_budget(cycle_id, timing.total_seconds, cfg, sla_violations)
    report.sla_violations = list(sla_violations)

    if len(sla_violations) > pre_sla_len:
        write_cycle_json(report, reports_dir)

    print_console_summary(report)

    log.info("report_created", extra={"cycle_id": cycle_id, "status": report.final_status.value})
    return report


def run_station(cfg: InspectionConfig | None = None) -> list[InspectionReport]:
    cfg = cfg or DEFAULT_CONFIG
    reports_dir = Path(__file__).resolve().parent.parent / "reports"
    cameras = [MockCamera(cid, rng=random.Random(1000 + i)) for i, cid in enumerate(cfg.camera_ids)]
    capture = CaptureService(cameras, cfg)
    scenarios = build_demo_scenarios(cfg)
    reports: list[InspectionReport] = []

    print("=== Inspection station demo (10 sequential cycles) ===\n")

    for cycle_id in range(1, 11):
        wall_t0 = time.perf_counter()
        trig = build_trigger(cycle_id)
        scenario = scenarios.get(cycle_id, default_scenario(cfg))
        try:
            rep = run_inspection_cycle(
                trig.cycle_id,
                trig.part_id,
                cfg,
                capture,
                scenario,
                reports_dir,
            )
            reports.append(rep)
        except Exception as exc:  # noqa: BLE001 — station must never crash the batch
            log.exception("cycle_fatal", extra={"cycle_id": cycle_id, "error": str(exc)})
            timing = CycleTiming(total_seconds=time.perf_counter() - wall_t0)
            err_report = InspectionReport(
                cycle_id=cycle_id,
                part_id=trig.part_id,
                final_status=FinalStatus.ERROR,
                camera_results={},
                aggregated_defects=[],
                min_confidence=None,
                quality_flags=[],
                error_reasons=[f"UNHANDLED_EXCEPTION:{exc}", traceback.format_exc()],
                timing=timing,
                lifecycle=[],
                sla_violations=[],
            )
            write_cycle_json(err_report, reports_dir)
            print_console_summary(err_report)
            reports.append(err_report)

    return reports


def print_batch_summary(reports: list[InspectionReport]) -> None:
    metrics = StationMetrics()
    for r in reports:
        metrics.record_cycle(r)
    print("\n=== Batch summary (metrics) ===")
    for line in metrics.summary_lines():
        print(line)


def main() -> None:
    reports = run_station()
    print_batch_summary(reports)
    metrics = StationMetrics()
    for r in reports:
        metrics.record_cycle(r)
    summary = {
        "total": len(reports),
        "passed": metrics.pass_count,
        "failed": metrics.fail_count,
        "errors": metrics.error_count,
        "review_required": metrics.review_count,
        "failure_rate": metrics.failure_rate(),
        "avg_cycle_seconds": metrics.avg_cycle_seconds(),
        "max_cycle_seconds": metrics.max_cycle_seconds,
        "low_confidence_cycle_pct": metrics.low_confidence_pct(),
        "camera_reliability": metrics.camera_reliability(),
        "sla_violation_cycles": metrics.sla_violation_cycles,
    }
    print("\n" + json.dumps({"batch": summary}))


if __name__ == "__main__":
    main()
