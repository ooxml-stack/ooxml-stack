"""Replay P80 semantic-promotion rows through public CLI and MCP paths."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

sys.path.insert(0, str(Path(__file__).resolve().parent))
from jsonl_artifacts import read_jsonl as _read_jsonl_artifact  # noqa: E402
from p80_semantic_promotion_runner import (  # noqa: E402
    _outside_changes,
    _part_fingerprints,
    _read_value,
    _write_json,
    _write_jsonl,
)
from evidence_artifact_store import store_artifact  # noqa: E402

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "ooxml-stack" / "release-evidence" / "p90"
CORPUS = ROOT / "ooxml-native-corpus"
ROWS = OUT / "p80-semantic-promotion-rows.jsonl"
REPLAY_DIR = OUT / "p80-promotion-public-paths"
ARTIFACTS = ROOT / "ooxml-stack" / "release-evidence" / "artifact-blobs"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    rows = _candidate_rows(args.max_rows)
    REPLAY_DIR.mkdir(parents=True, exist_ok=True)
    existing = _existing_results()
    results = [_replay_or_reuse(row, index, existing) for index, row in enumerate(rows)]
    summary = _summary(results)
    _write_jsonl(OUT / "p80-semantic-promotion-public-replay.jsonl", results)
    _write_json(OUT / "p80-semantic-promotion-public-summary.json", summary)
    return 0 if summary["gate_pass"] else 1


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-rows", type=int, default=20)
    return parser.parse_args(argv)


def _candidate_rows(limit: int) -> list[dict[str, Any]]:
    rows = _read_jsonl_artifact(ROWS)
    ready = [row for row in rows if row.get("pass") is True and row.get("operation_params")]
    return ready[:limit]


def _replay_row(row: dict[str, Any], index: int) -> dict[str, Any]:
    cli = _run_cli(row, index)
    mcp = anyio.run(_run_mcp, row, index)
    return {
        "row_id": row["row_id"],
        "source_row_id": row["source_row_id"],
        "operation_id": row["operation_id"],
        "operation_target": row["operation_target"],
        "cli": cli,
        "mcp": mcp,
        "cli_path_checked": cli["pass"],
        "mcp_path_checked": mcp["pass"],
        "pass": cli["pass"] and mcp["pass"],
    }


def _replay_or_reuse(row: dict[str, Any], index: int, existing: dict[str, dict[str, Any]]) -> dict[str, Any]:
    prior = existing.get(row["row_id"])
    return prior if prior and prior.get("pass") is True else _replay_row(row, index)


def _existing_results() -> dict[str, dict[str, Any]]:
    rows = _read_jsonl_artifact(OUT / "p80-semantic-promotion-public-replay.jsonl")
    return {row["row_id"]: row for row in rows}


def _run_cli(row: dict[str, Any], index: int) -> dict[str, Any]:
    path = _copy_input(row, index, "cli")
    before = _part_fingerprints(path, row["part_name"])
    cmd = ["uv", "run", "ooxml-engine", "apply", str(path), row["operation_id"], row["operation_target"], "--save"]
    for key, value in sorted(row["operation_params"].items()):
        cmd.extend(["--param", f"{key}={json.dumps(value, ensure_ascii=False)}"])
    completed = subprocess.run(cmd, cwd=ROOT / "ooxml-operation-engine", capture_output=True, text=True, check=False)
    _store_artifact(path)
    return _checked_result("cli", path, row, before, completed.returncode, completed.stdout, completed.stderr)


async def _run_mcp(row: dict[str, Any], index: int) -> dict[str, Any]:
    path = _copy_input(row, index, "mcp")
    before = _part_fingerprints(path, row["part_name"])
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ooxml_operation_engine.mcp_server"],
        cwd=str(ROOT / "ooxml-operation-engine"),
    )
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            return await _mcp_calls(session, tools.tools, path, row, before)


async def _mcp_calls(session, tools, path: Path, row: dict[str, Any], before: dict[str, str]) -> dict[str, Any]:
    await _call(session, "ooxml_open", {"path": str(path)})
    try:
        await _call(session, "ooxml_apply", {
            "operation_id": row["operation_id"],
            "target": row["operation_target"],
            "params": row["operation_params"],
        })
        validation = await _call(session, "ooxml_validate", {})
        await _call(session, "ooxml_save", {})
        _store_artifact(path)
        result = _checked_result("mcp", path, row, before, 0, json.dumps(validation), "")
        return result | {"mcp_list_tools_pass": bool(tools), "mcp_call_tool_replay_pass": True}
    finally:
        await _call(session, "ooxml_close", {})


async def _call(session: ClientSession, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = await session.call_tool(name, arguments)
    if result.isError:
        raise RuntimeError(f"MCP tool {name} failed: {result.content}")
    text = result.content[0].text if result.content else "{}"
    return json.loads(text)


def _checked_result(interface: str, path: Path, row: dict[str, Any], before: dict[str, str], code: int, stdout: str, stderr: str) -> dict[str, Any]:
    attr = row.get("operation_params", {}).get("attribute_name")
    if row.get("operation_id") == "office_extension.creation_id.set":
        attr = _creation_id_attr(row)
    after = _read_value(path, row["part_name"], row["before_semantic_value"]["value_selector"], attr)
    expected = row["requested_semantic_change"]["value"]
    outside = _outside_changes(before, _part_fingerprints(path, row["part_name"]), row["selector"])
    return {
        "interface": interface,
        "output_file": str(path.relative_to(ROOT)),
        "return_code": code,
        "after_value": after,
        "expected_after_value": expected,
        "after_value_match": after == expected,
        "sibling_unexpected_semantic_mutation_count": outside,
        **_stream_meta(stdout, stderr),
        "pass": code == 0 and after == expected and outside == 0,
    }


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


def _creation_id_attr(row: dict[str, Any]) -> str:
    qname = row.get("before_semantic_value", {}).get("qname", "")
    return "val" if "powerpoint/2010/main" in qname or "p14:creationId" in row.get("operation_target", "") else "id"


def _copy_input(row: dict[str, Any], index: int, label: str) -> Path:
    src = CORPUS / row["input_file"]
    dst = REPLAY_DIR / f"{label}-{index:03d}-{row['package_id']}-{row['stable_id'].replace(':', '_')}{src.suffix}"
    shutil.copy2(src, dst)
    return dst
def _store_artifact(path: Path) -> None:
    store_artifact(path, ARTIFACTS, ROOT)


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "p90-p80-promotion-public-replay-v1",
        "gate_pass": bool(results) and all(row["pass"] for row in results),
        "row_count": len(results),
        "row_pass_count": sum(row["pass"] for row in results),
        "cli_path_pass_count": sum(row["cli_path_checked"] for row in results),
        "mcp_path_pass_count": sum(row["mcp_path_checked"] for row in results),
    }


if __name__ == "__main__":
    raise SystemExit(main())
