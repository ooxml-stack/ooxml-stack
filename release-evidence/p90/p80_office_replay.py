"""Replay P80 promotion Office evidence one output package at a time."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any

from jsonl_artifacts import read_jsonl

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "ooxml-stack/release-evidence/p90"
ROWS = OUT / "p80-semantic-promotion-rows.jsonl"
OFFICE_JSON = OUT / "p80-semantic-promotion-office.json"
SMOKE_JSON = OUT / "p80-semantic-promotion-office.smoke.json"
ITEM_JSON = OUT / "p80-semantic-promotion-office.current.json"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    paths = _paths(args.limit)
    report_path = _report_path(args)
    report = _initial_report(args, paths, report_path)
    for index, path in enumerate(paths):
        key = _rel(path)
        existing = _result_map(report).get(key)
        if args.resume and existing and existing.get("status") == "pass":
            continue
        item = _run_one(path, args)
        report = _merge(report, item, args, paths)
        _write(report, report_path)
        print(f"{index + 1}/{len(paths)} {item.get('status')} {key}", flush=True)
        if args.fail_fast and item.get("status") != "pass":
            break
    _write(report, report_path)
    return 0 if report["summary"]["gate_pass"] else 1


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout-seconds", type=int, default=240)
    parser.add_argument("--dialog-wait-seconds", type=int, default=30)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    return parser.parse_args(argv)


def _paths(limit: int) -> list[Path]:
    seen: list[Path] = []
    for row in read_jsonl(ROWS):
        path = ROOT / row["output_file"]
        if path not in seen:
            seen.append(path)
    return seen[:limit] if limit else seen


def _initial_report(args: argparse.Namespace, paths: list[Path], report_path: Path) -> dict[str, Any]:
    if args.resume and report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        meta = report.get("meta", {})
        if meta.get("timeout_seconds") == args.timeout_seconds and meta.get("dialog_wait_seconds") == args.dialog_wait_seconds:
            expected = {_rel(path) for path in paths}
            report["results"] = [row for row in report.get("results", []) if _rel_key(row.get("file", "")) in expected]
            report["summary"] = _summary(report["results"], paths)
            return report
    return {"meta": _meta(args, paths), "summary": {}, "results": []}


def _run_one(path: Path, args: argparse.Namespace) -> dict[str, Any]:
    ITEM_JSON.unlink(missing_ok=True)
    cmd = [
        "uv", "run", "python", "tools/office-open-gate/office_open_gate.py", str(path),
        "--timeout-seconds", str(args.timeout_seconds), "--dialog-wait-seconds", str(args.dialog_wait_seconds),
        "--path-root", str(ROOT), "-o", str(ITEM_JSON),
    ]
    try:
        subprocess.run(cmd, cwd=ROOT / "ooxml-test-framework", check=False, timeout=args.timeout_seconds + 90)
    except subprocess.TimeoutExpired:
        return {"file": _rel(path), "status": "timeout", "message": f">{args.timeout_seconds + 90}s wrapper"}
    data = json.loads(ITEM_JSON.read_text(encoding="utf-8")) if ITEM_JSON.exists() else {"results": []}
    return data.get("results", [{}])[0] | {"file": _rel(path)}


def _merge(report: dict[str, Any], item: dict[str, Any], args: argparse.Namespace, paths: list[Path]) -> dict[str, Any]:
    results = _result_map(report)
    results[_rel_key(item.get("file", ""))] = item
    merged = {"meta": _meta(args, paths), "results": list(results.values())}
    merged["summary"] = _summary(merged["results"], paths)
    return merged


def _summary(results: list[dict[str, Any]], paths: list[Path]) -> dict[str, Any]:
    counts = Counter(row.get("status", "missing") for row in results)
    expected = {_rel(path) for path in paths}
    actual = {_rel_key(row.get("file", "")) for row in results}
    return {
        "total": len(results), "pass": counts.get("pass", 0), "pass_total": counts.get("pass", 0),
        "repair_dialog_count": counts.get("repair_dialog", 0) + counts.get("unreadable_content", 0),
        "unreadable_content_count": counts.get("unreadable_content", 0),
        "security_dialog_count": counts.get("pass_with_security_dialog", 0),
        "benign_dialog_count": counts.get("pass_with_dialog", 0), "office_crash_count": counts.get("office_crash", 0),
        "macro_security_dialog_count": counts.get("macro_security_dialog", 0), "macro_timeout_count": counts.get("macro_timeout", 0),
        "by_status": dict(sorted(counts.items())), "expected_output_file_count": len(expected),
        "result_file_count": len(actual), "missing_result_file_count": len(expected - actual),
        "extra_result_file_count": len(actual - expected),
        "gate_pass": len(results) == len(paths) and counts.get("pass", 0) == len(paths),
    }


def _meta(args: argparse.Namespace, paths: list[Path]) -> dict[str, Any]:
    return {
        "tool": "p80_office_replay", "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "timeout_seconds": args.timeout_seconds, "dialog_wait_seconds": args.dialog_wait_seconds,
        "expected_output_file_count": len(paths),
    }


def _report_path(args: argparse.Namespace) -> Path:
    return SMOKE_JSON if args.limit and not args.resume else OFFICE_JSON


def _write(report: dict[str, Any], path: Path) -> None:
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _result_map(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {_rel_key(row.get("file", "")): row for row in report.get("results", [])}


def _rel(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def _rel_key(path: str) -> str:
    candidate = Path(path)
    return _rel(candidate) if candidate.is_absolute() else path


if __name__ == "__main__":
    raise SystemExit(main())
