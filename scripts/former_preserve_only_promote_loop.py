#!/usr/bin/env python3
"""Conservative batch runner for hydrated former-preserve-only promotions."""
from __future__ import annotations
import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import former_preserve_only_promote_hydrated as promote
from former_preserve_only_batch_metrics import promotion_metrics
from former_preserve_only_office_boundaries import failed_office_packages
from former_preserve_only_promote_batch import OUT, ROWS
ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "artifacts/ooxml-element-capability-ledger.json"
RUNNER_NEEDLES = (
    "office_open_gate",
    "native_office_open_save_preserve",
)
REQUIRED_KEYS = (
    "row_id",
    "stable_id",
    "package_id",
    "part_name",
    "selector",
    "qname",
    "family",
    "operation_id",
    "before_semantic_value",
    "after_semantic_value",
    "public_api_path",
)
@dataclass(frozen=True)
class Candidate:
    package_id: str
    label: str
    planned: int
    rows: int
    skipped_policy: int
    family: str
def main(argv: list[str] | None = None) -> int:
    started = time.monotonic()
    args = parse_args(argv)
    blockers = active_office_runners()
    candidates = select_candidates(args)
    if not args.execute:
        return emit({"mode": "dry-run", "office_runners": blockers, "candidates": [c.__dict__ for c in candidates]})
    if blockers and not args.allow_active_office:
        return emit({"error": "office_runner_active", "office_runners": blockers}, code=2)
    if not args.run_office:
        return emit({"error": "execute_requires_run_office"}, code=2)
    before = ledger_counts()
    completed = run_candidates(candidates, args)
    if completed is None:
        return 1
    if args.refresh_dashboard and run_refresh() != 0:
        return 1
    after = ledger_counts()
    summary = batch_summary(candidates, completed, before, after, args, started)
    code = 1 if summary["hard_audit_failure_count"] else 0
    payload = {"mode": "execute", "completed": completed, "summary": summary, "delta": delta(before, after)}
    return emit(payload, code=code)
def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--run-office", action="store_true")
    parser.add_argument("--refresh-dashboard", action="store_true")
    parser.add_argument("--allow-active-office", action="store_true")
    parser.add_argument("--family", default="office_extension")
    parser.add_argument("--format", default="pptx")
    parser.add_argument("--max-packages", type=int, default=3)
    parser.add_argument("--min-planned", type=int, default=1)
    parser.add_argument("--max-planned", type=int, default=20)
    parser.add_argument("--max-rows", type=int, default=100)
    parser.add_argument("--max-package-mb", type=float, default=5.0)
    parser.add_argument("--label-prefix", default="ledger-officeext")
    parser.add_argument("--exclude-package", action="append", default=[])
    parser.add_argument("--skip-known-boundary", action="store_true", default=True)
    parser.add_argument("--checkpoint")
    return parser.parse_args(argv)
def select_candidates(args: argparse.Namespace) -> list[Candidate]:
    if not promote.HYDRATED.exists():
        raise SystemExit(f"missing local cache: {promote.HYDRATED}\nrun: make campaign-ledgers")
    used = set()
    evidence = evidence_text()
    known = failed_office_packages(OUT / "office-results") if args.skip_known_boundary else set()
    checkpointed = checkpoint_packages(args.checkpoint)
    args.skipped_known_boundary_count = len(known)
    excluded = set(args.exclude_package) | known | checkpointed
    candidates, seen = [], set()
    for row in promote._read_jsonl(promote.HYDRATED):
        pkg = row.get("package_id", "")
        if pkg in seen or pkg in excluded or row.get("family") != args.family or row.get("format") != args.format:
            continue
        seen.add(pkg)
        candidate = build_candidate(pkg, args, used, evidence)
        if candidate:
            candidates.append(candidate)
    candidates.sort(key=lambda c: (-c.planned, c.package_id))
    return candidates[: args.max_packages]
def build_candidate(package_id: str, args: argparse.Namespace, used: set[str], evidence: str) -> Candidate | None:
    ns = argparse.Namespace(
        family=args.family,
        operation_id="",
        package_id=package_id,
        max_package_mb=args.max_package_mb,
        max_rows=args.max_rows,
        requested_value="",
        skipped_policy_rows=0,
    )
    rows = promote._select_rows(ns)
    plans = promote._plans(rows, ns)
    if not args.min_planned <= len(plans) <= args.max_planned:
        return None
    label = next_available_label(package_id, args.label_prefix, used, evidence)
    used.add(label)
    return Candidate(package_id, label, len(plans), len(rows), ns.skipped_policy_rows, args.family)
def evidence_text() -> str:
    chunks = []
    if ROWS.exists():
        chunks.append(ROWS.read_text(encoding="utf-8"))
    for folder in (OUT / "office-results", OUT / "public-paths", OUT / "promotion-outputs"):
        for path in folder.glob("*"):
            chunks.append(path.name)
    return "\n".join(chunks)
def next_available_label(package_id: str, prefix: str, reserved: set[str], evidence: str) -> str:
    label = next_label(package_id, prefix, reserved)
    while label_exists(label, evidence) or label in reserved:
        reserved.add(label)
        label = next_label(package_id, prefix, reserved)
    return label
def next_label(package_id: str, prefix: str, used: set[str]) -> str:
    base = f"{prefix}-{slug_package(package_id)}"
    for index in range(1, 100):
        label = f"{base}-b{index}"
        if label not in used:
            return label
    raise RuntimeError(f"no free label for {package_id}")
def label_exists(label: str, evidence: str) -> bool:
    tokens = (f"api-{label}-", f"cli-{label}-", f"mcp-{label}-", f"cli-{label}.jsonl")
    return any(token in evidence for token in tokens)
def slug_package(package_id: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", package_id.lower()).strip("-")
    slug = slug.replace("pptx-ms-expansion-", "pptx", 1)
    return slug[:96]
def active_office_runners() -> list[str]:
    result = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True, check=False)
    lines = []
    for line in result.stdout.splitlines():
        if "pew notify" in line:
            continue
        if any(needle in line for needle in RUNNER_NEEDLES):
            lines.append(line.strip())
    return lines
def run_candidates(candidates: list[Candidate], args: argparse.Namespace) -> list[dict[str, Any]] | None:
    completed = []
    for candidate in candidates:
        blockers = active_office_runners()
        if blockers and not args.allow_active_office:
            emit({"error": "office_runner_active", "candidate": candidate.__dict__, "office_runners": blockers}, code=0)
            return None
        return_code = run_candidate(candidate, args)
        if return_code != 0:
            record = {"candidate": candidate.__dict__, "status": "boundary_or_failed", "return_code": return_code}
            completed.append(record)
            update_checkpoint(args.checkpoint, record)
            continue
        audit = audit_labels([candidate.label], candidate.planned)
        if not audit["audit_pass"]:
            record = {"candidate": candidate.__dict__, "status": "hard_audit_failed", "audit": audit}
            completed.append(record)
            update_checkpoint(args.checkpoint, record)
            return completed
        record = {"candidate": candidate.__dict__, "status": "promoted", "audit": audit}
        completed.append(record)
        update_checkpoint(args.checkpoint, record)
    return completed
def checkpoint_packages(path: str | None) -> set[str]:
    data = read_checkpoint(path)
    return {str(pkg) for pkg in data.get("completed_packages", [])}
def read_checkpoint(path: str | None) -> dict[str, Any]:
    if not path or not Path(path).exists():
        return {"completed_packages": [], "records": []}
    return json.loads(Path(path).read_text(encoding="utf-8"))
def update_checkpoint(path: str | None, record: dict[str, Any]) -> None:
    if not path:
        return
    data = read_checkpoint(path)
    data.setdefault("records", []).append(record)
    if record["status"] == "promoted":
        data.setdefault("completed_packages", []).append(record["candidate"]["package_id"])
        data["completed_packages"] = sorted(set(data["completed_packages"]))
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
def batch_summary(candidates, completed, before, after, args, started) -> dict[str, Any]:
    statuses = [row.get("status") for row in completed]
    audits = [row.get("audit", {}) for row in completed]
    labels = [row.get("candidate", {}).get("label", "") for row in completed]
    return {
        "selected_package_count": len(candidates),
        "completed_package_count": len(completed),
        "promoted_row_count": sum(int(audit.get("row_count", 0)) for audit in audits if audit.get("audit_pass")),
        "boundary_package_count": statuses.count("boundary_or_failed"),
        "hard_audit_pass_count": sum(audit.get("audit_pass") is True for audit in audits),
        "hard_audit_failure_count": statuses.count("hard_audit_failed"),
        "skipped_known_boundary_count": getattr(args, "skipped_known_boundary_count", 0),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "starting_semantic_editable_count": before.get("semantic_editable"),
        "ending_semantic_editable_count": after.get("semantic_editable"),
        "starting_remaining_count": before.get("unsupported_or_not_proven"),
        "ending_remaining_count": after.get("unsupported_or_not_proven"),
        "skipped_policy_count": sum(candidate.skipped_policy for candidate in candidates),
        **promotion_metrics(ROWS, OUT, labels),
    }
def run_candidate(candidate: Candidate, args: argparse.Namespace) -> int:
    cmd = [
        sys.executable,
        "scripts/former_preserve_only_promote_hydrated.py",
        "--family",
        candidate.family,
        "--package-id",
        candidate.package_id,
        "--max-rows",
        str(args.max_rows),
        "--max-package-mb",
        str(args.max_package_mb),
        "--label",
        candidate.label,
        "--run-office",
    ]
    return subprocess.run(cmd, cwd=ROOT, check=False).returncode
def audit_labels(labels: list[str], expected_count: int | None = None) -> dict[str, Any]:
    rows = [row for row in read_rows(ROWS) if any(row_has_label(row, label) for label in labels)]
    return audit_rows(rows, expected_count)
def audit_rows(rows: list[dict[str, Any]], expected_count: int | None = None) -> dict[str, Any]:
    checks = {
        "pass": lambda r: r.get("pass") is True,
        "semantic_edit_pass": lambda r: r.get("semantic_edit_pass") is True,
        "cli_path_checked": lambda r: r.get("cli_path_checked") is True and r.get("cli_return_code") == 0,
        "mcp_path_checked": lambda r: r.get("mcp_path_checked") is True and r.get("mcp_return_code") == 0,
        "mcp_protocol": lambda r: r.get("mcp_list_tools_pass") is True and r.get("mcp_call_tool_replay_pass") is True,
        "native_office_result": lambda r: r.get("native_office_result") == "pass",
        "stable_id_scope": lambda r: r.get("stable_id_scope") == "package-local",
        "sibling_unchanged": lambda r: r.get("sibling_unexpected_semantic_mutation_count") == 0,
        "target_changed": lambda r: r.get("target_semantic_changed") is True,
        "package_invariant_pass": lambda r: r.get("package_invariant_pass") is True,
        "required_identity": lambda r: all(r.get(key) for key in REQUIRED_KEYS),
    }
    failures = {name: [row.get("row_id") for row in rows if not check(row)] for name, check in checks.items()}
    failures = {name: bad for name, bad in failures.items() if bad}
    count_ok = expected_count is None or len(rows) == expected_count
    return {
        "row_count": len(rows),
        "expected_count": expected_count,
        "failures": failures,
        "audit_pass": bool(rows) and count_ok and not failures,
    }
def row_has_label(row: dict[str, Any], label: str) -> bool:
    tokens = (f"api-{label}-", f"cli-{label}-", f"mcp-{label}-", f"cli-{label}.jsonl")
    fields = ("office_result_id", "output_file", "cli_output_file", "mcp_output_file")
    return any(token in str(row.get(field, "")) for field in fields for token in tokens)
def read_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
def run_refresh() -> int:
    commands = [
        ["make", "ledger"],
        ["make", "dashboard-md", "OUT=docs/OOXML-ELEMENT-CAPABILITY-LEDGER.md"],
        ["make", "dashboard", "OUT=/tmp/ooxml-ledger-dashboard.html", "OPEN=0"],
    ]
    for command in commands:
        if subprocess.run(command, cwd=ROOT, check=False).returncode != 0:
            return 1
    return 0
def ledger_counts() -> dict[str, int | bool]:
    if not LEDGER.exists():
        return {}
    data = json.loads(LEDGER.read_text(encoding="utf-8"))
    return {
        "semantic_editable": data["levels"]["semantic_editable"]["count"],
        "unsupported_or_not_proven": data["levels"]["unsupported_or_not_proven"]["count"],
        "pending": data["blockers"]["by_reason"].get("semantic_value_available_pending_proof", 0),
        "full_claim_proven": data["full_claim_proven"],
    }
def delta(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {key: {"before": before.get(key), "after": after.get(key)} for key in sorted(set(before) | set(after))}
def emit(payload: dict[str, Any], code: int = 0) -> int:
    print(json.dumps(payload, indent=2, sort_keys=True))
    return code
if __name__ == "__main__":
    raise SystemExit(main())
