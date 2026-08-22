"""P90 SH semantic editability freeze summary builder."""

from __future__ import annotations

import hashlib, json, shutil, sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
PROFILE = ROOT / "ooxml-stack/release-profiles/p90-sh-semantic-editability.locked.json"
sys.path.insert(0, str(OUT))
from jsonl_artifacts import artifact_paths as _jsonl_artifact_paths, logical_exists as _jsonl_logical_exists, write_jsonl as _write_jsonl_artifact  # noqa: E402
from p90_anti_false_pass_audit import build_audit  # noqa: E402
from p90_row_builder import build_p90_rows  # noqa: E402

FULL_CLAIM = (
    "100% semantic-active editability under the P90 measured SH DOCX/PPTX "
    "semantic-object denominator, including the locked P80 former-preserve-only "
    "population, with deterministic validation, native Office acceptance, "
    "LLM-through-CLI/MCP black-box acceptance, and paired A/B comparison "
    "against model-default editing."
)
ARTIFACTS = [
    "docs/P81-P90-SH-SEMANTIC-EDITABILITY-OVERNIGHT-GOAL.md",
    "docs/P90-SH-SEMANTIC-EDITABILITY-FREEZE.md",
    "docs/P81-SH-ENGINE-CONTRACT.md",
    "docs/P82-SH-SEMANTIC-DENOMINATOR.md",
    "docs/P82R-SH-RECONNAISSANCE-GATE.md",
    "docs/P83-TEXT-SEMANTIC-ACTIVE-EDITING-GATE.md",
    "docs/P84-CUSTOM-XML-SEMANTIC-EDITING-GATE.md",
    "docs/P85-OMML-MATH-SEMANTIC-EDITING-GATE.md",
    "docs/P86-VML-DRAWING-SEMANTIC-EDITING-GATE.md",
    "docs/P87-CHART-OFFICE-EXTENSION-SEMANTIC-EDITING-GATE.md",
    "docs/P88-ALTERNATE-WPS-VENDOR-STRUCTURAL-SEMANTIC-GATE.md",
    "docs/P89-FULL-MEASURED-NATIVE-OFFICE-GATE.md",
    "release-evidence/p81/native-office-automation-preflight.json",
    "release-evidence/p82/sh-semantic-denominator-summary.json",
    "release-evidence/p82r/recon-overview-summary.json",
    "release-evidence/p82r/recon-search-summary.json",
    "release-evidence/p82r/recon-inspect-detail-summary.json",
    "release-evidence/p83/text-semantic-summary.json",
    "release-evidence/p83/text-semantic-batch-summary.json",
    "release-evidence/p84/custom-xml-semantic-summary.json",
    "release-evidence/p85/omml-semantic-summary.json",
    "release-evidence/p86/vml-semantic-summary.json",
    "release-evidence/p87/chart-extension-semantic-summary.json",
    "release-evidence/p88/structural-semantic-summary.json",
    "release-evidence/p89/native-office-gate-summary.json",
    "release-evidence/p89/native-office-gate.object-bound.jsonl",
]
REQUIRED_P90 = [
    "release-evidence/p90/native-office-gate.json",
    "release-evidence/p90/anti-false-pass-audit.json",
    "release-evidence/p90/p80-semantic-promotion-feasibility.json",
    "release-evidence/p90/p80-semantic-promotion-rows.jsonl",
    "release-evidence/p90/p80-semantic-promotion-summary.json",
    "release-evidence/p90/p80-semantic-promotion-office.json",
    "release-evidence/p90/p80-semantic-promotion-public-replay.jsonl",
    "release-evidence/p90/p80-semantic-promotion-public-summary.json",
    "release-evidence/p90/p90-public-path-replay.jsonl",
    "release-evidence/p90/p90-public-path-replay-summary.json",
    "release-evidence/p90/sh-semantic-editability-rows.jsonl",
    "release-evidence/p90/llm-acceptance/tasks.jsonl",
    "release-evidence/p90/llm-acceptance/cli-results.jsonl",
    "release-evidence/p90/llm-acceptance/mcp-results.jsonl",
    "release-evidence/p90/llm-acceptance/native-office-gate.json",
    "release-evidence/p90/llm-acceptance/verifier-summary.json",
    "release-evidence/p90/llm-ab-comparison/results.jsonl",
    "release-evidence/p90/llm-ab-comparison/summary.json",
]


def main() -> int:
    _sync_native_gate()
    rows = _rows()
    _write_jsonl(OUT / "sh-semantic-editability-rows.jsonl", rows)
    audit = build_audit(_initial_audit_lock_status())
    _write_json(OUT / "anti-false-pass-audit.json", audit)
    summary = _summary(audit)
    manifest = _manifest(summary)
    audit = build_audit(_audit_lock_status(manifest))
    _write_json(OUT / "anti-false-pass-audit.json", audit)
    summary = _summary(audit)
    manifest = _manifest(summary)
    _write_json(OUT / "sh-semantic-editability-summary.json", summary)
    _write_jsonl(OUT / "sh-semantic-editability-rows.jsonl", rows)
    _write_json(OUT / "manifest.json", manifest)
    _write_json(PROFILE, _profile(summary, manifest))
    return 0 if summary["gate_pass"] else 1


def _sync_native_gate() -> None:
    src = _stack_path("release-evidence/p90/llm-acceptance/native-office-gate.json")
    dst = _stack_path("release-evidence/p90/native-office-gate.json")
    if src.exists():
        shutil.copy2(src, dst)


def _initial_audit_lock_status() -> dict[str, bool]:
    return {
        "p90_anti_false_pass_audit_exists": False,
        "p90_anti_false_pass_audit_in_manifest": False,
        "p90_anti_false_pass_audit_hash_locked": False,
    }


def _audit_lock_status(manifest: dict[str, Any]) -> dict[str, bool]:
    rel = "release-evidence/p90/anti-false-pass-audit.json"
    artifacts = {item["path"]: item for item in manifest.get("artifacts", [])}
    artifact = artifacts.get(rel, {})
    return {
        "p90_anti_false_pass_audit_exists": _stack_path(rel).exists(),
        "p90_anti_false_pass_audit_in_manifest": rel in artifacts,
        "p90_anti_false_pass_audit_hash_locked": bool(artifact.get("sha256")) and artifact.get("size", 0) > 0,
    }


def _summary(audit: dict[str, Any]) -> dict[str, Any]:
    p89 = _json("release-evidence/p89/native-office-gate-summary.json")
    recon_overview = _json("release-evidence/p82r/recon-overview-summary.json")
    recon_search = _json("release-evidence/p82r/recon-search-summary.json")
    recon_inspect = _json("release-evidence/p82r/recon-inspect-detail-summary.json")
    llm = _optional_json("release-evidence/p90/llm-acceptance/verifier-summary.json")
    ab = _optional_json("release-evidence/p90/llm-ab-comparison/summary.json")
    p80_feasibility = _optional_json("release-evidence/p90/p80-semantic-promotion-feasibility.json") or {}
    metrics = audit.get("metrics", {})
    missing = [path for path in REQUIRED_P90 if not _required_exists(path)]
    gate_pass = _gate_pass(p89, recon_overview, recon_search, recon_inspect, llm, ab, missing, audit)
    return {
        "claim": FULL_CLAIM if gate_pass else "P90 FAIL: current evidence does not satisfy the full P81-P90 SH semantic editability target.",
        "gate_pass": gate_pass,
        "object_row_count": metrics.get("p90_object_row_count", 0),
        "sh_object_count": metrics.get("sh_object_count", 0),
        "semantic_active_editable_count": metrics.get("p90_object_row_count", 0),
        "p90_anti_false_pass_gate_pass": audit.get("gate_pass") is True,
        "p90_anti_false_pass_failures": audit.get("failures", []),
        "p90_anti_false_pass_metrics": audit.get("metrics", {}),
        "native_office_pass": f"{p89.get('p89_office_pass_package_count', 0)} / {p89.get('p89_edited_package_count', 0)}",
        "p80_semantic_value_available_count": p80_feasibility.get("semantic_value_available_count", 0),
        "p80_semantic_value_missing_count": p80_feasibility.get("semantic_value_missing_count", 0),
        "p80_semantic_feasibility_blocks_full_claim": p80_feasibility.get("blocks_full_p90_claim") is True,
        "repair_security_crash_timeout": [p89.get("p89_repair_dialog_count", 0), p89.get("p89_security_dialog_count", 0), p89.get("p89_crash_count", 0), p89.get("p89_timeout_count", 0)],
        "recon_overview_pass": f"{recon_overview.get('overview_pass_count', 0)} / {recon_overview.get('overview_task_count', 0)}",
        "recon_search_pass": f"{recon_search.get('search_pass_count', 0)} / {recon_search.get('search_task_count', 0)}",
        "recon_inspect_detail_pass": f"{recon_inspect.get('inspect_detail_pass_count', 0)} / {recon_inspect.get('inspect_detail_task_count', 0)}",
        "llm_acceptance_present": llm is not None,
        "paired_ab_present": ab is not None,
        "missing_required_p90_artifacts": missing,
        "p89_gate_pass": p89.get("gate_pass") is True,
        "p82r_gate_pass": all(item.get("gate_pass") is True for item in (recon_overview, recon_search, recon_inspect)),
    }


def _gate_pass(p89, overview, search, inspect, llm, ab, missing, audit) -> bool:
    return (
        not missing
        and audit.get("gate_pass") is True
        and p89.get("gate_pass") is True
        and overview.get("gate_pass") is True
        and search.get("gate_pass") is True
        and inspect.get("gate_pass") is True
        and isinstance(llm, dict) and llm.get("gate_pass") is True
        and isinstance(ab, dict) and ab.get("gate_pass") is True
    )


def _rows() -> list[dict[str, Any]]:
    return build_p90_rows()


def _manifest(summary: dict[str, Any]) -> dict[str, Any]:
    paths = []
    for path in [*ARTIFACTS, *[p for p in REQUIRED_P90 if _required_exists(p)]]:
        paths.extend(_manifest_paths(path))
    artifacts = [_artifact(path) for path in paths]
    return {"schema_version": "p90-manifest-v1", "gate_pass": summary["gate_pass"], "artifact_count": len(artifacts), "artifacts": artifacts}


def _required_exists(rel: str) -> bool:
    return _jsonl_logical_exists(ROOT / "ooxml-stack", rel)


def _manifest_paths(rel: str) -> list[str]:
    return _jsonl_artifact_paths(ROOT / "ooxml-stack", rel)


def _artifact(rel: str) -> dict[str, Any]:
    path = _stack_path(rel)
    data = path.read_bytes()
    return {"path": rel, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _profile(summary: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    return {"claim": summary["claim"], "ok": summary["gate_pass"], "summary": summary, "manifest": manifest}


def _json(rel: str) -> dict[str, Any]:
    return json.loads(_stack_path(rel).read_text(encoding="utf-8"))


def _optional_json(rel: str) -> dict[str, Any] | None:
    path = _stack_path(rel)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _stack_path(rel: str) -> Path:
    return ROOT / "ooxml-stack" / rel


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    _write_jsonl_artifact(path, rows)


if __name__ == "__main__":
    raise SystemExit(main())
