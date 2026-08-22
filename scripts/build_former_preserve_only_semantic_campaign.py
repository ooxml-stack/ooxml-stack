#!/usr/bin/env python3
"""Build former-preserve-only semantic editability campaign evidence."""

from __future__ import annotations

import argparse
import json
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from former_preserve_only_gap_rows import build_gap_rows


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "release-evidence/former-preserve-only-semantic-editability"


def read_json(path: str) -> dict:
    full = ROOT / path
    if not full.exists():
        return {}
    return json.loads(full.read_text())


def write_json(path: Path, data: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def git(args: list[str], cwd: Path) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def dirty_paths() -> list[dict]:
    raw = git(
        [
            "status",
            "--porcelain=v1",
            "--",
            "release-evidence/p90",
            "release-profiles/p90-sh-semantic-editability.locked.json",
        ],
        ROOT,
    )
    rows = []
    for line in raw.splitlines():
        if not line:
            continue
        rows.append({"status": line[:2], "path": line[3:]})
    return rows


def parse_state(path: str) -> dict:
    full = ROOT / path
    if not full.exists() or full.is_dir():
        return {"exists": full.exists(), "parse_ok": None, "size": 0}
    info = {"exists": True, "parse_ok": None, "size": full.stat().st_size}
    if full.suffix == ".json":
        try:
            json.loads(full.read_text())
            info["parse_ok"] = True
        except json.JSONDecodeError as exc:
            info.update({"parse_ok": False, "parse_error": str(exc)})
    return info


def classify_dirty(path: str, status: str, state: dict) -> tuple[str, str]:
    name = Path(path).name
    if name.endswith(".smoke.json") or name.endswith(".current.json"):
        return "smoke_artifact", "explicit smoke/current Office JSON; do not promote"
    if path.endswith(".locked.json"):
        return "unknown_do_not_touch", "release profile changed; needs profile audit"
    if name.endswith(".py"):
        if status == "??":
            return "temporary_runner", "untracked helper runner; review before commit"
        return "unknown_do_not_touch", "modified runner source; needs code review"
    if ".jsonl.d/" in path:
        return "needs_rerun", "split JSONL part/index changed; needs manifest audit"
    if state.get("parse_ok") is False:
        return "needs_rerun", "JSON parse failure"
    if name in {
        "anti-false-pass-audit.json",
        "p80-semantic-promotion-feasibility.json",
        "p80-semantic-promotion-summary.json",
        "p80-semantic-promotion-public-summary.json",
        "p80-semantic-promotion-office.json",
        "sh-semantic-editability-summary.json",
    }:
        return "validated_campaign_input", "parseable summary used for current gap accounting"
    if name == "manifest.json":
        return "needs_rerun", "manifest changed; must be regenerated after inputs settle"
    return "unknown_do_not_touch", "not enough information to classify safely"


def evidence_hygiene() -> dict:
    entries = []
    for row in dirty_paths():
        state = parse_state(row["path"])
        klass, reason = classify_dirty(row["path"], row["status"], state)
        entries.append({**row, **state, "classification": klass, "reason": reason})
    counts = Counter(entry["classification"] for entry in entries)
    return {"entries": entries, "classification_counts": dict(sorted(counts.items()))}


def family_rows(feasibility: dict) -> list[dict]:
    rows = []
    for family, counts in feasibility.get("family_counts", {}).items():
        if not isinstance(counts, dict):
            continue
        missing = int(counts.get("no_descendant_value", 0))
        resolve = int(counts.get("resolve_fail", 0))
        total = sum(int(value) for value in counts.values())
        rows.append({"family": family, "total": total, "no_semantic_value": missing, "resolve_failure": resolve})
    return sorted(rows, key=lambda row: (-row["total"], row["family"]))


def gap_row(family: str, blocker: str, count: int, detail: str) -> dict:
    return {
        "row_id": f"aggregate-gap|{family}|{blocker}",
        "format": "mixed",
        "input_file": "aggregate",
        "package_id": "aggregate-gap",
        "part_name": "aggregate",
        "stable_id": f"aggregate:{family}:{blocker}",
        "selector": "aggregate family blocker; expand to object rows before promotion",
        "qname": "aggregate",
        "family": family,
        "current_tier": "surface-editable",
        "missing_proof": missing_proof(blocker),
        "blocker_type": blocker,
        "blocker_detail": detail,
        "next_operation_model": next_operation(family, blocker),
        "required_oracle": required_oracle(blocker),
        "owner_repo": "ooxml-test-framework",
        "priority": "p0" if count > 1000 else "p1",
        "status": "todo",
        "count": count,
    }


def missing_proof(blocker: str) -> list[str]:
    if blocker == "resolve_failure":
        return ["stable_selector", "parser"]
    if blocker == "no_semantic_value":
        return ["semantic_model", "semantic_value"]
    return ["public_path", "office_bound_oracle", "manifest_lock"]


def next_operation(family: str, blocker: str) -> str:
    if blocker == "no_semantic_value":
        return f"{family}.semantic_value.model"
    if blocker == "resolve_failure":
        return f"{family}.stable_selector.resolve"
    return "campaign.object_level_public_replay"


def required_oracle(blocker: str) -> str:
    if blocker == "resolve_failure":
        return "exactly one object resolves, stale and ambiguous handles reject"
    if blocker == "no_semantic_value":
        return "extract before/requested/after semantic value for an owned field"
    return "exact after-value, CLI/MCP replay, Office-bound output proof"


def gap_ledger(feasibility: dict, audit: dict) -> tuple[list[dict], dict]:
    metrics = audit.get("metrics", {})
    baseline = int(metrics.get("p80_former_preserve_only_baseline_count", 0))
    promoted = int(metrics.get("p90_p80_semantic_promoted_count", 0))
    available = int(metrics.get("p80_semantic_value_available_count", 0))
    rows = []
    for family in family_rows(feasibility):
        if family["no_semantic_value"]:
            rows.append(gap_row(family["family"], "no_semantic_value", family["no_semantic_value"], "no owned semantic value modeled"))
        if family["resolve_failure"]:
            rows.append(gap_row(family["family"], "resolve_failure", family["resolve_failure"], "stable selector or XML parse failed"))
    pending = max(available - promoted, 0)
    if pending:
        rows.append(gap_row("all_families", "semantic_value_available_pending_proof", pending, "semantic value exists but full object-level proof is not locked"))
    summary = build_summary(rows, baseline, promoted, feasibility, audit)
    return rows, summary


def build_summary(rows: list[dict], baseline: int, promoted: int, feasibility: dict, audit: dict) -> dict:
    by_blocker = Counter()
    by_family = Counter()
    for row in rows:
        by_blocker[row["blocker_type"]] += row["count"]
        by_family[row["family"]] += row["count"]
    office = audit.get("office_freshness", {})
    metrics = audit.get("metrics", {})
    return {
        "former_preserve_only_denominator": baseline,
        "semantic_editable_count": promoted,
        "semantic_editable_remaining": max(baseline - promoted, 0),
        "remaining_by_blocker": dict(by_blocker),
        "remaining_by_family": dict(by_family.most_common()),
        "family_totals": family_rows(feasibility),
        "anti_false_pass_gate": audit.get("gate_pass", False),
        "full_semantic_claim_proven": read_json("release-evidence/p90/sh-semantic-editability-summary.json").get("gate_pass", False),
        "office_blocker_count": office.get("p80_office_blocker_count", "n/a"),
        "cli_path_unchecked_count": metrics.get("p90_cli_path_unchecked_count", "n/a"),
        "mcp_path_unchecked_count": metrics.get("p90_mcp_path_unchecked_count", "n/a"),
        "object_level_gap_rows_materialized": False,
    }


def build_campaign() -> tuple[dict, list[dict], dict]:
    hygiene = evidence_hygiene()
    gaps, summary = build_gap_rows()
    return hygiene, gaps, summary


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows))


def markdown_table(headers: list[str], rows: list[list[object]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    for row in rows:
        out.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(out)


def dashboard(summary: dict, hygiene: dict) -> str:
    family_rows_md = [[k, v] for k, v in list(summary["remaining_by_family"].items())[:20]]
    blocker_rows = [[k, v] for k, v in summary["remaining_by_blocker"].items()]
    qname_rows = [[k, v] for k, v in list(summary.get("remaining_by_qname_top20", {}).items())[:20]]
    hygiene_rows = [[k, v] for k, v in hygiene["classification_counts"].items()]
    return "\n".join([
        "# Former Preserve-Only Semantic Editability Campaign Dashboard",
        "",
        f"- Denominator: {summary['former_preserve_only_denominator']}",
        f"- Semantic-editable: {summary['semantic_editable_count']}",
        f"- Remaining: {summary['semantic_editable_remaining']}",
        f"- Anti-false-pass gate: {summary['anti_false_pass_gate']}",
        f"- Full semantic claim proven: {summary['full_semantic_claim_proven']}",
        f"- Object-level gap rows materialized: {summary['object_level_gap_rows_materialized']}",
        "",
        "## Remaining By Blocker",
        markdown_table(["Blocker", "Count"], blocker_rows),
        "",
        "## Remaining By Family",
        markdown_table(["Family", "Count"], family_rows_md),
        "",
        "## Remaining Top QNames",
        markdown_table(["QName", "Count"], qname_rows),
        "",
        "## P90 Evidence Hygiene",
        markdown_table(["Classification", "Count"], hygiene_rows),
        "",
    ])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(OUT))
    args = parser.parse_args()
    out = Path(args.out)
    hygiene, gaps, summary = build_campaign()
    write_json(out / "p90-evidence-hygiene.json", hygiene)
    write_jsonl(out / "gap-ledger.jsonl", gaps)
    write_json(out / "gap-summary.json", summary)
    (out / "gap-dashboard.md").write_text(dashboard(summary, hygiene))
    print(out)


if __name__ == "__main__":
    main()
