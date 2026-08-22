"""Replay P80 promotion rows through batched public CLI and MCP paths."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jsonl_artifacts import read_jsonl as _read_jsonl_artifact  # noqa: E402
from p80_semantic_promotion_runner import (  # noqa: E402
    CORPUS,
    OUT,
    ROOT,
    _namespaces,
    _part_fingerprints,
    _tree,
    _write_json,
    _write_jsonl,
)
from evidence_artifact_store import store_artifact  # noqa: E402

ROWS = OUT / "p80-semantic-promotion-rows.jsonl"
REPLAY = OUT / "p80-semantic-promotion-public-replay.jsonl"
REPLAY_DIR = OUT / "p80-promotion-public-paths"
ENGINE = ROOT / "ooxml-operation-engine"
ARTIFACTS = ROOT / "ooxml-stack" / "release-evidence" / "artifact-blobs"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.rewrite_existing:
        return _rewrite_existing()
    selected = _select_rows(args)
    if not selected:
        return _write_empty()
    REPLAY_DIR.mkdir(parents=True, exist_ok=True)
    cli = _run_cli_batch(selected, args.label)
    mcp = anyio.run(_run_mcp_batch, selected, args.label)
    results = [_result(row, cli, mcp) for row in selected]
    merged = _merge(_existing_results(), results)
    _write_jsonl(REPLAY, merged)
    _write_json(OUT / "p80-semantic-promotion-public-summary.json", _summary(merged))
    return 0 if all(row["pass"] for row in results) else 1


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-rows", type=int, default=500)
    parser.add_argument("--package-id", default="")
    parser.add_argument("--label", default="batch")
    parser.add_argument("--rewrite-existing", action="store_true")
    return parser.parse_args(argv)


def _select_rows(args: argparse.Namespace) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    existing = {row["row_id"] for row in _existing_results() if row.get("pass") is True}
    for row in _promotion_rows():
        if row["row_id"] in existing or not _ready(row):
            continue
        if args.package_id and row.get("package_id") != args.package_id:
            continue
        groups[row["package_id"]].append(row)
    package = args.package_id or max(groups, key=lambda key: len(groups[key]), default="")
    return groups.get(package, [])[: args.max_rows]


def _promotion_rows() -> list[dict[str, Any]]:
    return _read_jsonl_artifact(ROWS)


def _ready(row: dict[str, Any]) -> bool:
    return row.get("pass") is True and bool(row.get("operation_params"))


def _run_cli_batch(rows: list[dict[str, Any]], label: str) -> dict[str, Any]:
    path = _copy_input(rows[0], f"cli-batch-{label}")
    plan = _write_plan(rows, f"cli-batch-{label}")
    before = _before(path, rows)
    cmd = ["uv", "run", "ooxml-engine", "apply", str(path), "--plan-jsonl", str(plan), "--save"]
    completed = subprocess.run(cmd, cwd=ENGINE, capture_output=True, text=True, check=False)
    _store_artifact(path)
    return _batch_check("cli", path, rows, before, completed.returncode, completed.stdout, completed.stderr)


async def _run_mcp_batch(rows: list[dict[str, Any]], label: str) -> dict[str, Any]:
    path = _copy_input(rows[0], f"mcp-batch-{label}")
    before = _before(path, rows)
    server = StdioServerParameters(command=sys.executable, args=["-m", "ooxml_operation_engine.mcp_server"], cwd=str(ENGINE))
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            code, stdout, stderr = await _mcp_apply_all(session, rows, path)
    _store_artifact(path)
    checked = _batch_check("mcp", path, rows, before, code, stdout, stderr)
    checked["list_tools_pass"] = bool(tools.tools)
    checked["call_tool_replay_pass"] = code == 0
    return checked


async def _mcp_apply_all(session: ClientSession, rows: list[dict[str, Any]], path: Path) -> tuple[int, str, str]:
    try:
        await _call(session, "ooxml_open", {"path": str(path)})
        await _call(session, "ooxml_apply", {"plan": [_payload(row) for row in rows]})
        validation = await _call(session, "ooxml_validate", {})
        await _call(session, "ooxml_save", {})
        return 0, json.dumps(validation), ""
    except Exception as exc:
        return 1, "", str(exc)
    finally:
        try:
            await _call(session, "ooxml_close", {})
        except Exception:
            pass


async def _call(session: ClientSession, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = await session.call_tool(name, arguments)
    if result.isError:
        raise RuntimeError(f"MCP tool {name} failed: {result.content}")
    return json.loads(result.content[0].text if result.content else "{}")


def _batch_check(interface: str, path: Path, rows: list[dict[str, Any]], before, code, stdout, stderr) -> dict[str, Any]:
    planned = _planned_targets(rows)
    after_parts = {part: _part_fingerprints(path, part) for part in before["parts"]}
    after_values = _after_values(path, rows)
    return {
        "interface": interface,
        "output_file": str(path.relative_to(ROOT)),
        "return_code": code,
        **_stream_meta(stdout, stderr),
        "rows": {row["row_id"]: _row_check(row, before, after_parts, after_values, planned, code) for row in rows},
    }


def _after_values(path: Path, rows: list[dict[str, Any]]) -> dict[str, str]:
    values: dict[str, str] = {}
    by_part: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_part[row["part_name"]].append(row)
    for part, part_rows in by_part.items():
        tree = _tree(path, part)
        ns = _namespaces(tree.getroot())
        for row in part_rows:
            node = tree.xpath(_selector(row), namespaces=ns)[0]
            attr = _attr(row)
            values[row["row_id"]] = node.get(attr, "") if attr else (node.text or "")
    return values


def _row_check(row: dict[str, Any], before, after_parts, after_values, planned, code: int) -> dict[str, Any]:
    after = after_values[row["row_id"]]
    expected = row["requested_semantic_change"]["value"]
    outside = _outside(before["parts"][row["part_name"]], after_parts[row["part_name"]], planned[row["part_name"]])
    return {"after_value": after, "expected_after_value": expected, "after_value_match": after == expected, "sibling_unexpected_semantic_mutation_count": outside, "pass": code == 0 and after == expected and outside == 0}


def _result(row: dict[str, Any], cli: dict[str, Any], mcp: dict[str, Any]) -> dict[str, Any]:
    c, m = cli["rows"][row["row_id"]], mcp["rows"][row["row_id"]]
    return {"row_id": row["row_id"], "source_row_id": row["source_row_id"], "operation_id": row["operation_id"], "operation_target": row["operation_target"], "cli": c | _meta(cli), "mcp": m | _meta(mcp) | {"mcp_list_tools_pass": mcp.get("list_tools_pass"), "mcp_call_tool_replay_pass": mcp.get("call_tool_replay_pass")}, "cli_path_checked": c["pass"], "mcp_path_checked": m["pass"], "batch_public_replay": True, "pass": c["pass"] and m["pass"]}


def _meta(batch: dict[str, Any]) -> dict[str, Any]:
    skip = {"rows", "list_tools_pass", "call_tool_replay_pass"}
    return {key: value for key, value in batch.items() if key not in skip}


def _stream_meta(stdout: str, stderr: str) -> dict[str, Any]:
    return _one_stream("stdout", stdout) | _one_stream("stderr", stderr)


def _one_stream(name: str, text: str) -> dict[str, Any]:
    data = text.encode("utf-8")
    low = text.lower()
    return {
        f"{name}_sha256": hashlib.sha256(data).hexdigest(),
        f"{name}_size": len(data),
        f"{name}_warning_text_count": low.count("warning"),
        f"{name}_error_text_count": low.count("error"),
        f"{name}_repair_warning_text_count": low.count("repair warning"),
        f"{name}_unreadable_text_count": low.count("unreadable"),
    }


def _rewrite_existing() -> int:
    rows = [_sanitize_result(row) for row in _existing_results()]
    _write_jsonl(REPLAY, rows)
    _write_json(OUT / "p80-semantic-promotion-public-summary.json", _summary(rows))
    return 0 if rows and all(row.get("pass") for row in rows) else 1


def _sanitize_result(row: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(row)
    for key in ("cli", "mcp"):
        if isinstance(sanitized.get(key), dict):
            sanitized[key] = _sanitize_payload(sanitized[key])
    return sanitized


def _sanitize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    clean = dict(payload)
    for stream in ("stdout", "stderr"):
        tail = clean.pop(f"{stream}_tail", "")
        if tail:
            clean[f"legacy_{stream}_redacted"] = True
            clean.update(_legacy_tail_counts(stream, tail))
    return clean


def _legacy_tail_counts(stream: str, text: str) -> dict[str, int]:
    low = text.lower()
    return {
        f"legacy_{stream}_warning_text_count": low.count("warning"),
        f"legacy_{stream}_error_text_count": low.count("error"),
        f"legacy_{stream}_repair_warning_text_count": low.count("repair warning"),
        f"legacy_{stream}_unreadable_text_count": low.count("unreadable"),
    }


def _payload(row: dict[str, Any]) -> dict[str, Any]:
    return {"operation_id": row["operation_id"], "target": row["operation_target"], "params": row["operation_params"]}


def _write_plan(rows: list[dict[str, Any]], label: str) -> Path:
    path = REPLAY_DIR / f"{label}-plan.jsonl"
    path.write_text("".join(json.dumps(_payload(row), sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    return path


def _copy_input(row: dict[str, Any], label: str) -> Path:
    src = CORPUS / row["input_file"]
    dst = REPLAY_DIR / f"{label}-{row['package_id']}{src.suffix}"
    shutil.copy2(src, dst)
    return dst
def _store_artifact(path: Path) -> None:
    store_artifact(path, ARTIFACTS, ROOT)


def _before(path: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    parts = {row["part_name"] for row in rows}
    return {"parts": {part: _part_fingerprints(path, part) for part in parts}}


def _planned_targets(rows: list[dict[str, Any]]) -> dict[str, set[str]]:
    planned: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        planned[row["part_name"]].add(row["selector"])
    return planned


def _outside(before: dict[str, str], after: dict[str, str], planned: set[str]) -> int:
    changed = [path for path, digest in before.items() if after.get(path) != digest]
    return sum(not any(_inside(path, target) for target in planned) for path in changed)


def _inside(path: str, target: str) -> bool:
    return path == target or path.startswith(target + "/") or target.startswith(path + "/")


def _selector(row: dict[str, Any]) -> str:
    return row.get("before_semantic_value", {}).get("value_selector") or row["selector"]


def _attr(row: dict[str, Any]) -> str | None:
    if row["operation_id"] == "office_extension.creation_id.set":
        qname = row.get("before_semantic_value", {}).get("qname", "")
        return "val" if "powerpoint/2010/main" in qname else "id"
    return row.get("operation_params", {}).get("attribute_name") or row.get("before_semantic_value", {}).get("attribute_name")


def _existing_results() -> list[dict[str, Any]]:
    return _read_jsonl_artifact(REPLAY)


def _merge(existing: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = {row["row_id"]: row for row in existing}
    for row in rows:
        merged[row["row_id"]] = row
    return list(merged.values())


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema_version": "p90-p80-promotion-public-replay-v1", "gate_pass": bool(rows) and all(row["pass"] for row in rows), "row_count": len(rows), "row_pass_count": sum(row["pass"] for row in rows), "cli_path_pass_count": sum(row["cli_path_checked"] for row in rows), "mcp_path_pass_count": sum(row["mcp_path_checked"] for row in rows)}


def _write_empty() -> int:
    _write_json(OUT / "p80-semantic-promotion-public-summary.json", _summary(_existing_results()))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
