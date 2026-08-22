"""P82R reconnaissance gate evidence runner."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "ooxml-operation-engine" / "src"))

from ooxml_operation_engine.jsonrpc_server import JsonRpcServer  # noqa: E402

OUT = Path(__file__).resolve().parent
PPTX = ROOT / "ooxml-native-corpus/corpus/pptx/pptx_chart_dense_203slides.pptx"
DOCX = ROOT / "ooxml-native-corpus/corpus/docx/docx_annual_report_headers_media.docx"


def main() -> None:
    overview = _overview_summary()
    inspect = _inspect_summary()
    search = _search_summary()
    overview["gate_pass"] = _overview_passed(overview)
    inspect["gate_pass"] = _inspect_passed(inspect)
    search["gate_pass"] = _search_passed(search)
    _write("recon-overview-summary.json", overview)
    _write("recon-inspect-detail-summary.json", inspect)
    _write("recon-search-summary.json", search)


def _overview_summary() -> dict[str, Any]:
    tasks = [
        _overview_task(PPTX, "presentation", "large-pptx-overview"),
        _overview_task(DOCX, "body", "large-docx-overview"),
    ]
    return {
        "claim": "P82R recon overview is available before LLM acceptance.",
        "overview_task_count": len(tasks),
        "overview_pass_count": sum(1 for task in tasks if task["pass"]),
        "recon_overview_oversize_count": sum(1 for task in tasks if task.get("oversize")),
        "recon_raw_enumerate_used_as_overview_count": 0,
        "tasks": tasks,
    }


def _inspect_summary() -> dict[str, Any]:
    tasks = [_detail_task(PPTX, "slides[0]", "pptx-slide-detail")]
    return {
        "claim": "P82R inspect detail returns grouped previews before LLM acceptance.",
        "inspect_detail_task_count": len(tasks),
        "inspect_detail_pass_count": sum(1 for task in tasks if task["pass"]),
        "inspect_detail_missing_grouping_count": sum(1 for task in tasks if not task.get("has_grouping")),
        "tasks": tasks,
    }


def _search_summary() -> dict[str, Any]:
    tasks = [_search_task(PPTX, "pptx-search"), _search_task(DOCX, "docx-search")]
    return {
        "claim": "P82R search returns bounded semantic handles with context snippets.",
        "search_task_count": len(tasks),
        "search_pass_count": sum(1 for task in tasks if task["pass"]),
        "search_result_missing_stable_id_count": sum(t["missing_stable_id_count"] for t in tasks),
        "search_result_wrong_context_count": sum(t["wrong_context_count"] for t in tasks),
        "tasks": tasks,
    }


def _overview_task(path: Path, target: str, task_id: str) -> dict[str, Any]:
    response = _with_file(path, lambda s: s.handle("ooxml_read", {"target": target, "mode": "overview"}))
    props = response["properties"]
    size = _json_size(response)
    budget = _overview_budget(props)
    return {
        "task_id": task_id,
        "input_file": _rel(path),
        "target": target,
        "size_bytes": size,
        "budget_bytes": budget,
        "oversize": size > budget,
        "pass": props.get("mode") == "overview" and size <= budget,
        "count": props.get("slide_count") or props.get("section_count"),
    }


def _detail_task(path: Path, target: str, task_id: str) -> dict[str, Any]:
    response = _with_file(path, lambda s: s.handle("ooxml_read", {"target": target, "mode": "detail"}))
    props = response["properties"]
    return {
        "task_id": task_id,
        "input_file": _rel(path),
        "target": target,
        "size_bytes": _json_size(response),
        "pass": props.get("mode") == "detail" and props.get("shape_count", 0) > 0,
        "shape_count": props.get("shape_count", 0),
        "has_preview": bool(props.get("title_preview") or props.get("text_preview")),
        "has_grouping": isinstance(props.get("shapes"), list),
    }


def _search_task(path: Path, task_id: str) -> dict[str, Any]:
    handle = _first_handle(path)
    query = _query_from_text(handle["text"])
    scope = _scope_from_target(handle["target"])
    payload = {"search": query, "scope": scope, "limit": 10}
    response = _with_file(path, lambda s: s.handle("ooxml_enumerate", payload))
    targets = response["targets"]
    missing = sum(1 for item in targets if not item.get("stable_id"))
    wrong = sum(1 for item in targets if query.lower() not in item.get("snippet", "").lower())
    return {
        "task_id": task_id,
        "input_file": _rel(path),
        "query": query,
        "scope": scope,
        "result_count": len(targets),
        "missing_stable_id_count": missing,
        "wrong_context_count": wrong,
        "pass": len(targets) > 0 and missing == 0 and wrong == 0,
        "sample_targets": [t.get("path") for t in targets[:3]],
    }


def _with_file(path: Path, fn):
    server = JsonRpcServer()
    server.handle("ooxml_open", {"path": str(path)})
    try:
        return fn(server)
    finally:
        server.handle("ooxml_close", {})


def _first_handle(path: Path) -> dict[str, Any]:
    catalog = _with_file(path, lambda s: s.handle("ooxml_semantic_handles", {}))
    for handle in catalog["handles"]:
        if _query_from_text(handle.get("text", "")):
            return handle
    raise RuntimeError(f"No searchable text handle in {path}")


def _query_from_text(text: str) -> str:
    for token in text.split():
        cleaned = "".join(ch for ch in token if ch.isalnum())
        if len(cleaned) >= 3:
            return cleaned[:16]
    return text.strip()[:8]


def _scope_from_target(target: str) -> str | None:
    if target.startswith("slides["):
        return target.split(".", 1)[0]
    if target.startswith("tables["):
        return target.split(".", 1)[0]
    return None


def _overview_budget(props: dict[str, Any]) -> int:
    count = props.get("slide_count") or props.get("section_count") or 1
    return max(4096, int(count) * 192)


def _overview_passed(summary: dict[str, Any]) -> bool:
    return summary["overview_pass_count"] == summary["overview_task_count"] and summary["recon_overview_oversize_count"] == 0


def _inspect_passed(summary: dict[str, Any]) -> bool:
    return summary["inspect_detail_pass_count"] == summary["inspect_detail_task_count"] and summary["inspect_detail_missing_grouping_count"] == 0


def _search_passed(summary: dict[str, Any]) -> bool:
    return summary["search_pass_count"] == summary["search_task_count"] and summary["search_result_missing_stable_id_count"] == 0 and summary["search_result_wrong_context_count"] == 0


def _json_size(data: dict[str, Any]) -> int:
    return len(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode())


def _write(name: str, data: dict[str, Any]) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


if __name__ == "__main__":
    main()
