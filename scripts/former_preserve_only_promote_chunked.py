#!/usr/bin/env python3
"""Replay exact-row semantic promotion chunks with staged hard-audited merge."""
from __future__ import annotations

import argparse
import hashlib
import json
import signal
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import anyio
import former_preserve_only_promote_hydrated as promote
from former_preserve_only_promoted_index import split_alias_rows
from former_preserve_only_chunk_evidence import (
    append_checkpoint,
    boundary_record,
    enrich_rows,
    read_checkpoint,
    timing_markdown,
    timing_summary,
)
from former_preserve_only_promote_loop import audit_rows
from build_semantic_editability_chunk_plan import OUT, HYDRATED, ROW_IDS, SUMMARY as PLAN
from chunk_stage_tracker import ChunkTimeout, new_stage, set_stage, stage_value, timeout_handler

CHECKPOINT = OUT / "chunk-promotion-checkpoint.json"
TIMING = OUT / "replay-timing-summary.json"
TIMING_MD = OUT / "replay-timing-dashboard.md"
BOUNDARY = OUT / "chunk-boundary-summary.json"
STAGED = OUT / "staged-rows"
ALIASES = OUT / "alias-operation-rows.jsonl"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    plan_path = Path(args.plan)
    plan_hash = _file_hash(plan_path)
    chunks = _selected_chunks(_read_json(plan_path), args)
    if args.dry_run:
        print(json.dumps({"mode": "dry-run", "selected": chunks}, indent=2, sort_keys=True))
        return 0
    rows_by_id = {row["row_id"]: row for row in promote._read_jsonl(HYDRATED)}
    row_sets = _row_sets(ROW_IDS)
    checkpoint = read_checkpoint(args.checkpoint, plan_hash)
    records, started = [], time.monotonic()
    for chunk in chunks:
        if _skip_chunk(chunk, checkpoint, args):
            continue
        record = _run_chunk_guarded(chunk, row_sets.get(chunk["chunk_id"], []), rows_by_id, args)
        record["plan_hash"] = plan_hash
        records.append(record)
        checkpoint = append_checkpoint(args.checkpoint, record, plan_hash)
    _write_timing(records, started, args.checkpoint, plan_hash)
    print(json.dumps({"processed": len(records), "records": records}, indent=2, sort_keys=True))
    return 1 if any(row["status"] not in {"promoted", "office_boundary"} for row in records) else 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--plan", default=str(PLAN))
    parser.add_argument("--chunk-id", action="append", default=[])
    parser.add_argument("--max-chunks", type=int, default=1)
    parser.add_argument("--run-office", action="store_true")
    parser.add_argument("--requested-value", default="")
    parser.add_argument("--label-prefix", default="chunk")
    parser.add_argument("--chunk-timeout-seconds", type=int, default=600)
    parser.add_argument("--checkpoint", default=str(CHECKPOINT))
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def _run_chunk_guarded(chunk, row_ids, rows_by_id, args) -> dict[str, Any]:
    started = time.monotonic()
    label = _label(chunk, args.label_prefix)
    stage = new_stage()
    if not args.chunk_timeout_seconds:
        return run_chunk(chunk, row_ids, rows_by_id, args, stage)
    old_handler = signal.signal(signal.SIGALRM, timeout_handler(stage))
    signal.alarm(args.chunk_timeout_seconds)
    try:
        return run_chunk(chunk, row_ids, rows_by_id, args, stage)
    except ChunkTimeout as exc:
        return _record(chunk, "timeout", label, started, stage=exc.stage, error=str(exc))
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def run_chunk(
    chunk: dict[str, Any],
    row_ids: list[str],
    rows_by_id: dict[str, dict[str, Any]],
    args: argparse.Namespace,
    stage: dict[str, str] | None = None,
) -> dict[str, Any]:
    stage = stage or new_stage()
    started = time.monotonic()
    label = _label(chunk, args.label_prefix)
    timings: dict[str, float] = {}
    try:
        set_stage(stage, "row_select")
        phase = time.monotonic()
        plans = _plans_for_chunk(chunk, row_ids, rows_by_id, args)
        timings["row_selection"] = round(time.monotonic() - phase, 3)
    except ValueError as exc:
        return _record(chunk, "planned_row_mismatch", label, started, stage="row_select", stage_timings=timings, error=str(exc))
    try:
        set_stage(stage, "api")
        api_path = promote._copy(plans[0]["row"], f"api-{label}")
        api, cli, mcp = _run_public_paths(api_path, plans, label, timings, stage)
        set_stage(stage, "office_gate")
        phase = time.monotonic()
        office = promote._run_office(api_path, args.run_office)
        timings["office_gate"] = round(time.monotonic() - phase, 3)
    except Exception as exc:  # noqa: BLE001
        return _record(chunk, "infra_failed", label, started, stage=stage_value(stage), stage_timings=timings, error=f"{type(exc).__name__}: {exc}")
    rows = enrich_rows([promote._evidence_row(item, api_path, api, cli, mcp, office) for item in plans], chunk, label, office)
    _write_staged(chunk, rows)
    status = _status(rows, api, cli, mcp, office, args.run_office)
    if status != "promoted":
        _write_boundary(chunk, status, rows, office)
        return _record(chunk, status, label, started, stage="office_gate", rows=len(rows), office=office, stage_timings=timings, plans=plans, output=api_path)
    set_stage(stage, "hard_audit")
    phase = time.monotonic()
    audit = audit_rows(rows, expected_count=len(row_ids))
    timings["hard_audit"] = round(time.monotonic() - phase, 3)
    if audit.get("audit_pass") is not True:
        return _record(chunk, "hard_audit_failed", label, started, stage="hard_audit", audit=audit, rows=len(rows), stage_timings=timings, plans=plans, output=api_path)
    _merge_rows(rows, label)
    return _record(chunk, "promoted", label, started, stage="hard_audit", audit=audit, rows=len(rows), office=office, stage_timings=timings, plans=plans, output=api_path)


def _run_public_paths(api_path: Path, plans: list[dict[str, Any]], label: str, timings: dict[str, float], stage: dict[str, str]) -> tuple[dict, dict, dict]:
    set_stage(stage, "api")
    phase = time.monotonic()
    api = promote._run_api(api_path, plans)
    timings["api_replay"] = round(time.monotonic() - phase, 3)
    set_stage(stage, "cli")
    phase = time.monotonic()
    cli = promote._run_cli(plans, label)
    timings["cli_replay"] = round(time.monotonic() - phase, 3)
    set_stage(stage, "mcp")
    phase = time.monotonic()
    mcp = anyio.run(promote._run_mcp, plans, label)
    timings["mcp_replay"] = round(time.monotonic() - phase, 3)
    return api, cli, mcp


def _plans_for_chunk(chunk, row_ids, rows_by_id, args) -> list[dict[str, Any]]:
    if len(row_ids) != chunk.get("planned_row_count"):
        raise ValueError("row_id count differs from plan")
    if _row_ids_hash(row_ids) != chunk.get("row_ids_hash"):
        raise ValueError("row_ids_hash differs from plan")
    missing = [row_id for row_id in row_ids if row_id not in rows_by_id]
    if missing:
        raise ValueError(f"missing hydrated rows: {missing[:3]}")
    rows = [rows_by_id[row_id] for row_id in row_ids]
    opts = SimpleNamespace(package_id=chunk["package_id"], requested_value=args.requested_value, max_rows=len(row_ids), skipped_policy_rows=0)
    plans = promote._plans(rows, opts)
    planned_ids = [item["row"]["row_id"] for item in plans]
    if planned_ids != row_ids:
        raise ValueError("hydrated planner did not preserve exact row_id membership")
    return plans


def _status(rows, api, cli, mcp, office, run_office: bool) -> str:
    if not rows:
        return "planned_row_mismatch"
    if api.get("errors") or api.get("new_errors") or not all(row.get("semantic_edit_pass") for row in rows):
        return "public_api_failed"
    if cli.get("return_code") != 0 or not all(row.get("cli_path_checked") for row in rows):
        return "cli_failed"
    if mcp.get("return_code") != 0 or not all(row.get("mcp_path_checked") for row in rows):
        return "mcp_failed"
    if not run_office:
        return "office_not_run"
    if office.get("return_code") != 0 or office.get("status") != "pass":
        return _office_status(office)
    return "promoted"


def _office_status(office: dict[str, Any]) -> str:
    status = str(office.get("status", "missing"))
    if status in {"repair_dialog", "unreadable_content", "close_error", "security_dialog", "crash"}:
        return "office_boundary"
    if status == "timeout":
        return "timeout"
    return "office_boundary"


def _merge_rows(rows: list[dict[str, Any]], label: str) -> None:
    existing = promote._read_jsonl(promote.ROWS)
    merged = promote._merge(existing, rows)
    promoted, aliases = split_alias_rows(merged)
    tmp = promote.ROWS.with_suffix(".jsonl.tmp")
    promote._write_jsonl(tmp, promoted)
    tmp.replace(promote.ROWS)
    if aliases:
        alias_rows = promote._merge(promote._read_jsonl(ALIASES), aliases)
        promote._write_jsonl(ALIASES, alias_rows)
    promote._write_json(promote.SUMMARY, promote._summary(promoted, len(rows) - len(aliases), label))


def _selected_chunks(plan: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    chunks = plan.get("chunks", [])
    if args.chunk_id:
        wanted = set(args.chunk_id)
        chunks = [chunk for chunk in chunks if chunk.get("chunk_id") in wanted]
    return chunks[: args.max_chunks] if args.max_chunks else chunks


def _skip_chunk(chunk: dict[str, Any], checkpoint: dict[str, Any], args: argparse.Namespace) -> bool:
    if args.retry_failed:
        return False
    done = {row.get("chunk_id") for row in checkpoint.get("records", [])}
    return chunk.get("chunk_id") in done


def _record(chunk, status, label, started, **extra) -> dict[str, Any]:
    rows = int(extra.get("rows", 0))
    office = extra.get("office", {})
    output = extra.get("output")
    plans = extra.get("plans", [])
    return {
        "chunk_id": chunk.get("chunk_id"),
        "package_id": chunk.get("package_id"),
        "family": chunk.get("family"),
        "operation_ids": chunk.get("operation_ids", []),
        "row_ids_hash": chunk.get("row_ids_hash"),
        "planned_row_count": chunk.get("planned_row_count"),
        "promoted_row_count": rows if status == "promoted" else 0,
        "office_result_file": office.get("office_json", ""),
        "public_path_file": f"release-evidence/former-preserve-only-semantic-editability/public-paths/cli-{label}.jsonl",
        "hard_audit_result": extra.get("audit", {}),
        "input_package_hash": _input_hash(plans),
        "output_package_hash": _sha256(output) if output else "",
        "label": label,
        "stage": extra.get("stage", ""),
        "status": status,
        "duration_s": round(time.monotonic() - started, 3),
        **{key: value for key, value in extra.items() if key not in {"plans", "output"}},
    }


def _row_sets(path: Path) -> dict[str, list[str]]:
    rows = promote._read_jsonl(path)
    return {row["chunk_id"]: row["row_ids"] for row in rows}


def _write_staged(chunk: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    STAGED.mkdir(parents=True, exist_ok=True)
    promote._write_jsonl(STAGED / f"{chunk['chunk_id']}.jsonl", rows)


def _write_boundary(chunk, status, rows, office) -> None:
    existing = _read_json(BOUNDARY).get("records", [])
    existing.append(boundary_record(chunk, status, rows, office))
    promote._write_json(BOUNDARY, {"records": existing})


def _write_timing(records: list[dict[str, Any]], started: float, checkpoint_path: str, plan_hash: str) -> None:
    cumulative = read_checkpoint(checkpoint_path, plan_hash).get("records", [])
    summary = timing_summary(records, cumulative, started)
    promote._write_json(TIMING, summary)
    TIMING_MD.write_text(timing_markdown(summary), encoding="utf-8")


def _label(chunk: dict[str, Any], prefix: str) -> str:
    digest = chunk["row_ids_hash"][:10]
    return f"{prefix}-{chunk['chunk_index']:04d}-{digest}"


def _row_ids_hash(row_ids: list[str]) -> str:
    return hashlib.sha256(("\n".join(row_ids) + "\n").encode()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def _input_hash(plans: list[dict[str, Any]]) -> str:
    if not plans:
        return ""
    return _sha256(promote.CORPUS / plans[0]["row"]["input_file"])


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path and path.exists() else ""


if __name__ == "__main__":
    raise SystemExit(main())
