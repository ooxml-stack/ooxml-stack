"""Real MCP protocol replay helpers for P90."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[3]


def run_mcp_protocol_replay(
    path: Path,
    row: dict[str, Any],
    params: dict[str, Any],
    overview_target: str,
    detail_target: str,
    scope: str,
) -> dict[str, Any]:
    return anyio.run(_run_replay, path, row, params, overview_target, detail_target, scope)


async def _run_replay(
    path: Path,
    row: dict[str, Any],
    params: dict[str, Any],
    overview_target: str,
    detail_target: str,
    scope: str,
) -> dict[str, Any]:
    server = StdioServerParameters(
        command=sys.executable,
        args=["-m", "ooxml_operation_engine.mcp_server"],
        cwd=str(ROOT / "ooxml-operation-engine"),
    )
    async with stdio_client(server) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            tool_names = [tool.name for tool in tools.tools]
            return await _run_calls(session, tool_names, path, row, params, overview_target, detail_target, scope)


async def _run_calls(
    session: ClientSession,
    tool_names: list[str],
    path: Path,
    row: dict[str, Any],
    params: dict[str, Any],
    overview_target: str,
    detail_target: str,
    scope: str,
) -> dict[str, Any]:
    await _call(session, "ooxml_open", {"path": str(path)})
    try:
        catalog = await _call(session, "ooxml_semantic_handles", {})
        handle = _handle(catalog["handles"], row)
        recon = await _recon(session, handle, overview_target, detail_target, scope)
        result = await _call(session, "ooxml_apply", _apply_payload(row, handle, params))
        validation = await _call(session, "ooxml_validate", {})
        await _call(session, "ooxml_save", {})
        return _result(tool_names, handle, recon, result, validation)
    finally:
        await _call(session, "ooxml_close", {})


async def _recon(
    session: ClientSession,
    handle: dict[str, Any],
    overview_target: str,
    detail_target: str,
    scope: str,
) -> dict[str, Any]:
    overview = await _call(session, "ooxml_read", {"target": overview_target, "mode": "overview"})
    search = await _call(session, "ooxml_enumerate", {"search": _query(_search_term(handle)), "scope": scope, "limit": 25})
    detail = await _call(session, "ooxml_read", {"target": detail_target, "mode": "detail"})
    return {
        "overview_pass": overview["properties"].get("mode") == "overview",
        "search_found_stable_id": any(t.get("stable_id") == handle["stable_id"] for t in search.get("targets", [])),
        "detail_kind": detail.get("kind"),
        "raw_enumerate_used_as_overview": False,
    }


async def _call(session: ClientSession, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    result = await session.call_tool(name, arguments)
    if result.isError:
        raise RuntimeError(f"MCP tool {name} failed: {result.content}")
    text = result.content[0].text if result.content else "{}"
    return json.loads(text)


def _handle(handles: list[dict[str, Any]], row: dict[str, Any]) -> dict[str, Any]:
    for handle in handles:
        if handle["stable_id"] == row["stable_id"] and handle["target"] == row["selector"]:
            return handle
    raise RuntimeError(row["row_id"])


def _apply_payload(row: dict[str, Any], handle: dict[str, Any], params: dict[str, Any]) -> dict[str, Any]:
    return {
        "operation_id": row["operation_id"],
        "stable_id": handle["stable_id"],
        "snapshot_id": handle["snapshot_id"],
        "params": params,
    }


def _result(tool_names, handle, recon, result, validation) -> dict[str, Any]:
    return {
        "tool_names": tool_names,
        "handle": handle,
        "recon": recon,
        "result": result,
        "validation": validation,
        "mcp_list_tools_pass": bool(tool_names),
        "mcp_call_tool_replay_pass": True,
        "real_mcp_protocol_replay_pass": True,
    }


def _query(text: str) -> str:
    return next((token[:24] for token in text.split() if len(token) >= 2), text[:24] or "semantic")


def _search_term(handle: dict[str, Any]) -> str:
    return handle.get("text") or handle.get("family") or handle.get("target") or handle["stable_id"]
