"""Per-cycle JSON report materialization and console summary."""

from __future__ import annotations

import json
import os
from pathlib import Path

from aggregation.aggregator import AggregationOutcome
from domain.models import CameraPipelineResult, CycleTiming, FinalStatus, InspectionReport
from observability.logger import get_logger

log = get_logger(__name__)


def camera_result_to_dict(r: CameraPipelineResult) -> dict:
    inf = r.inference
    return {
        "camera_id": r.camera_id,
        "capture_status": r.capture_status.value,
        "frame_integrity_ok": (r.frame.integrity_ok if r.frame is not None else None),
        "quality_flags": [f.value for f in r.quality_flags],
        "low_confidence": r.low_confidence,
        "defects": (
            [{"code": d.code, "severity": d.severity.value, "description": d.description} for d in inf.defects]
            if inf
            else []
        ),
        "confidence": inf.confidence if inf else None,
        "processing_notes": r.processing_notes,
    }


def build_report(
    cycle_id: int,
    part_id: str,
    cameras: list[CameraPipelineResult],
    outcome: AggregationOutcome,
    timing: CycleTiming,
    lifecycle: list[dict] | None = None,
    sla_violations: list[str] | None = None,
) -> InspectionReport:
    cam_map = {c.camera_id: camera_result_to_dict(c) for c in cameras}
    min_conf = None
    confidences = [c.inference.confidence for c in cameras if c.inference]
    if confidences:
        min_conf = min(confidences)

    quality = []
    for c in cameras:
        quality.extend([f"{c.camera_id}:{q.value}" for q in c.quality_flags])

    return InspectionReport(
        cycle_id=cycle_id,
        part_id=part_id,
        final_status=outcome.status,
        camera_results=cam_map,
        aggregated_defects=[
            {"code": d.code, "severity": d.severity.value, "description": d.description} for d in outcome.aggregated_defects
        ],
        min_confidence=min_conf,
        quality_flags=quality,
        error_reasons=outcome.reasons.copy(),
        timing=timing,
        lifecycle=list(lifecycle or []),
        sla_violations=list(sla_violations or []),
    )


def write_cycle_json(report: InspectionReport, directory: Path) -> Path:
    """Persist JSON via temp file + ``os.replace`` so observers never read a partial file."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"cycle_{report.cycle_id:03d}.json"
    tmp = path.with_name(f"{path.name}.tmp")
    payload = json.dumps(report.to_json_dict(), indent=2)
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, path)
    log.info(
        "report_written",
        extra={"path": str(path), "cycle_id": report.cycle_id, "part_id": report.part_id},
    )
    return path


def print_console_summary(report: InspectionReport) -> None:
    line = (
        f"[cycle {report.cycle_id:02d}] {report.part_id} -> {report.final_status.value} "
        f"(total {report.timing.total_seconds:.3f}s)"
    )
    print(line)
    if report.error_reasons:
        print(f"  reasons: {', '.join(report.error_reasons)}")
