"""P83 object-level text semantic editing evidence runner."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "ooxml-operation-engine" / "src"))
sys.path.insert(0, str(ROOT / "ooxml-stack" / "scripts"))

from evidence_artifact_store import store_artifact  # noqa: E402
from ooxml_operation_engine.jsonrpc_server import JsonRpcServer  # noqa: E402
from ooxml_operation_engine.mcp_server import (  # noqa: E402
    ooxml_apply,
    ooxml_close,
    ooxml_enumerate,
    ooxml_open,
    ooxml_read,
    ooxml_save,
    ooxml_validate,
    _server as MCP_SERVER,
)

OUT = Path(__file__).resolve().parent
DENOMINATOR = OUT.parent / "p82" / "sh-semantic-denominator.jsonl"
GROUPS = [("docx", "text_container"), ("docx", "table_cell_text"), ("pptx", "text_container"), ("pptx", "table_cell_text")]
ARTIFACTS = ROOT / "ooxml-stack" / "release-evidence" / "artifact-blobs"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    shutil.rmtree(OUT / "outputs", ignore_errors=True)
    rows = _select_rows(args.max_per_group)
    smoke_rows = _select_rows(1, args.smoke_max_bytes)
    api_rows = [_run_api_row(row, i) for i, row in enumerate(rows)]
    cli_rows = [_run_cli_row(row, i) for i, row in enumerate(smoke_rows)]
    mcp_rows = [_run_mcp_row(row, i) for i, row in enumerate(smoke_rows)]
    summary = _summary(api_rows, cli_rows, mcp_rows, args.max_per_group)
    _write_json("text-semantic-edit-rows.json", {"rows": api_rows})
    _write_json("text-semantic-cli-smoke.json", {"rows": cli_rows})
    _write_json("text-semantic-mcp-smoke.json", {"rows": mcp_rows})
    _write_json("text-semantic-summary.json", summary)
    return 0 if summary["gate_pass"] else 1


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-per-group", type=int, default=2)
    parser.add_argument("--smoke-max-bytes", type=int, default=2_000_000)
    return parser.parse_args(argv)


def _select_rows(max_per_group: int, max_bytes: int | None = None) -> list[dict[str, Any]]:
    buckets = {group: [] for group in GROUPS}
    with DENOMINATOR.open() as f:
        for line in f:
            row = json.loads(line)
            group = (row.get("format"), row.get("family"))
            if group not in buckets or len(buckets[group]) >= max_per_group:
                continue
            if row.get("status") != "semantic-ready" or not row.get("text_preview"):
                continue
            if max_bytes is not None and _input_size(row) > max_bytes:
                continue
            buckets[group].append(row)
            if all(len(items) >= max_per_group for items in buckets.values()):
                break
    missing = {str(group): max_per_group - len(items) for group, items in buckets.items() if len(items) < max_per_group}
    if missing:
        raise RuntimeError(f"P83 row selection missing groups: {missing}")
    return [row for group in GROUPS for row in buckets[group]]


def _run_api_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    output = _copy_input(row, f"api-{index}")
    server = JsonRpcServer()
    server.handle("ooxml_open", {"path": str(output)})
    try:
        handle = _find_handle(server, row)
        recon = _run_recon(server, row, handle)
        after_text = _after_text(row, index, "api")
        result = server.handle("ooxml_apply", _apply_payload(handle, row, after_text))
        validation = server.handle("ooxml_validate", {})
        server.handle("ooxml_save", {})
        return _evidence_row(row, output, handle, result, validation, recon, after_text, "python-api")
    finally:
        _close_quiet(server)


def _run_cli_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    output = _copy_input(row, f"cli-{index}")
    handle, recon = _cli_discover(output, row)
    after_text = _after_text(row, index, "cli")
    apply_result = _run_cli_json(["apply", str(output), row["operation_id"], "--stable-id", handle["stable_id"], "--snapshot-id", handle["snapshot_id"], "--param", f"text={after_text}", "--save"])
    validation = _run_cli_json(["validate", str(output)])
    return _evidence_row(row, output, handle, apply_result, validation, recon, after_text, "cli")


def _run_mcp_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    output = _copy_input(row, f"mcp-{index}")
    ooxml_open(str(output))
    try:
        handles = MCP_SERVER.handle("ooxml_semantic_handles", {})["handles"]
        handle = _handle_for_row(handles, row)
        recon = _mcp_recon(row, handle)
        after_text = _after_text(row, index, "mcp")
        result = ooxml_apply(row["operation_id"], stable_id=handle["stable_id"], snapshot_id=handle["snapshot_id"], params={"text": after_text})
        validation = ooxml_validate()
        ooxml_save()
        return _evidence_row(row, output, handle, result, validation, recon, after_text, "mcp")
    finally:
        try:
            ooxml_close()
        except Exception:
            MCP_SERVER.cleanup()


def _find_handle(server: JsonRpcServer, row: dict[str, Any]) -> dict[str, Any]:
    catalog = server.handle("ooxml_semantic_handles", {})
    return _handle_for_row(catalog["handles"], row)


def _handle_for_row(handles: list[dict[str, Any]], row: dict[str, Any]) -> dict[str, Any]:
    for handle in handles:
        if handle["stable_id"] == row["stable_id"] and handle["target"] == row["selector"]:
            return handle
    raise RuntimeError(f"Handle not found for {row['row_id']}")


def _run_recon(server: JsonRpcServer, row: dict[str, Any], handle: dict[str, Any]) -> dict[str, Any]:
    overview = server.handle("ooxml_read", {"target": _overview_target(row), "mode": "overview"})
    search = server.handle("ooxml_enumerate", {"search": _query(handle["text"]), "scope": _scope(row), "limit": 25})
    detail = server.handle("ooxml_read", {"target": _detail_target(row), "mode": "detail"})
    return _recon_result(row, handle, overview, search, detail)


def _cli_discover(output: Path, row: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    handles = _run_cli_json(["semantic-handles", str(output)])["handles"]
    handle = _handle_for_row(handles, row)
    overview = _run_cli_json(["read", str(output), _overview_target(row), "--mode", "overview"])
    search = _run_cli_json(["enumerate", str(output), "--search", _query(handle["text"]), "--scope", _scope(row)])
    detail = _run_cli_json(["read", str(output), _detail_target(row), "--mode", "detail"])
    return handle, _recon_result(row, handle, overview, search, detail)


def _mcp_recon(row: dict[str, Any], handle: dict[str, Any]) -> dict[str, Any]:
    overview = ooxml_read(_overview_target(row), mode="overview")
    search = ooxml_enumerate(search=_query(handle["text"]), scope=_scope(row), limit=25)
    detail = ooxml_read(_detail_target(row), mode="detail")
    return _recon_result(row, handle, overview, search, detail)


def _recon_result(row: dict[str, Any], handle: dict[str, Any], overview: dict[str, Any], search: dict[str, Any], detail: dict[str, Any]) -> dict[str, Any]:
    found = any(item.get("stable_id") == handle["stable_id"] for item in search.get("targets", []))
    return {"overview_pass": overview["properties"].get("mode") == "overview", "search_found_stable_id": found, "detail_kind": detail.get("kind"), "raw_enumerate_used_as_overview": False}


def _evidence_row(row: dict[str, Any], output: Path, handle: dict[str, Any], result: dict[str, Any], validation: dict[str, Any], recon: dict[str, Any], after_text: str, path: str) -> dict[str, Any]:
    diff = result.get("semantic_diff", {})
    validation_gate_pass = result.get("provenance", {}).get("validation", {}).get("passed") is True
    return {
        "row_id": row["row_id"],
        "format": row["format"],
        "input_file": row["input_file"],
        "output_file": _rel(output),
        "artifact": store_artifact(output, ARTIFACTS, ROOT),
        "family": row["family"],
        "stable_id": handle["stable_id"],
        "selector": row["selector"],
        "operation_id": row["operation_id"],
        "interface": path,
        "semantic_model_id": "text.container.v1" if row["family"] == "text_container" else "table.cell.text.v1",
        "before_text": handle["text"],
        "after_text": after_text,
        "target_semantic_hit": diff.get("target_changed") is True,
        "sibling_unchanged": diff.get("sibling_safety_passed") is True,
        "sibling_checked_count": diff.get("sibling_checked_count", 0),
        "validation_pass": validation_gate_pass,
        "standalone_validation_pass": validation.get("passed") is True or validation.get("validation", {}).get("passed") is True,
        "recon": recon,
        "pass": _row_pass(diff, result, recon),
    }


def _row_pass(diff: dict[str, Any], validation: dict[str, Any], recon: dict[str, Any]) -> bool:
    valid = validation.get("provenance", {}).get("validation", {}).get("passed") is True
    return diff.get("target_changed") is True and diff.get("sibling_safety_passed") is True and valid and recon["overview_pass"] and recon["search_found_stable_id"]


def _summary(api_rows: list[dict[str, Any]], cli_rows: list[dict[str, Any]], mcp_rows: list[dict[str, Any]], max_per_group: int) -> dict[str, Any]:
    all_rows = api_rows + cli_rows + mcp_rows
    return {
        "claim": "P83 text semantic active editing object-level slice; not full P83 denominator completion.",
        "gate_pass": all(row["pass"] for row in all_rows),
        "full_denominator_pass": False,
        "max_per_group": max_per_group,
        "api_row_count": len(api_rows),
        "api_pass_count": sum(1 for row in api_rows if row["pass"]),
        "cli_smoke_pass_count": sum(1 for row in cli_rows if row["pass"]),
        "mcp_smoke_pass_count": sum(1 for row in mcp_rows if row["pass"]),
        "target_semantic_miss_count": sum(1 for row in all_rows if not row["target_semantic_hit"]),
        "sibling_unexpected_semantic_mutation_count": sum(1 for row in all_rows if not row["sibling_unchanged"]),
        "validation_failure_count": sum(1 for row in all_rows if not row["validation_pass"]),
        "recon_flow_fail_count": sum(1 for row in all_rows if not row["recon"]["search_found_stable_id"]),
        "groups": _group_counts(api_rows),
    }


def _copy_input(row: dict[str, Any], prefix: str) -> Path:
    src = ROOT / "ooxml-native-corpus" / row["input_file"]
    dst_dir = OUT / "outputs"
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"{prefix}-{row['package_id']}-{row['stable_id']}{src.suffix}"
    shutil.copy2(src, dst)
    return dst


def _input_size(row: dict[str, Any]) -> int:
    return (ROOT / "ooxml-native-corpus" / row["input_file"]).stat().st_size


def _apply_payload(handle: dict[str, Any], row: dict[str, Any], text: str) -> dict[str, Any]:
    return {"stable_id": handle["stable_id"], "snapshot_id": handle["snapshot_id"], "operation_id": row["operation_id"], "params": {"text": text}}


def _run_cli_json(args: list[str]) -> dict[str, Any]:
    result = subprocess.run(["uv", "run", "ooxml-engine", *args], cwd=ROOT / "ooxml-operation-engine", capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def _after_text(row: dict[str, Any], index: int, source: str) -> str:
    return f"P83 {source} semantic edit {index} {row['format']} {row['family']}"


def _query(text: str) -> str:
    for token in text.split():
        if len(token.strip()) >= 2:
            return token.strip()[:24]
    return text.strip()[:24]


def _overview_target(row: dict[str, Any]) -> str:
    return "presentation" if row["format"] == "pptx" else "body"


def _scope(row: dict[str, Any]) -> str:
    selector = row["selector"]
    return selector.split(".", 1)[0] if selector.startswith("slides[") else "body"


def _detail_target(row: dict[str, Any]) -> str:
    selector = row["selector"]
    return selector.split(".shapes[", 1)[0] if selector.startswith("slides[") else selector


def _group_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        key = f"{row['format']}:{row['family']}"
        counts[key] = counts.get(key, 0) + 1
    return counts


def _close_quiet(server: JsonRpcServer) -> None:
    try:
        server.handle("ooxml_close", {})
    except Exception:
        server.cleanup()


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _write_json(name: str, data: dict[str, Any]) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
