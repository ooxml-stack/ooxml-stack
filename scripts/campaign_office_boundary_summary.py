"""Summarize campaign Office gate boundary evidence."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from redact_release_evidence_paths import redact_user_paths

PACKAGE_RE = re.compile(r"(?:^|-)((?:docx|pptx|xlsx)_[A-Za-z0-9_.-]+)$")


def summarize_boundaries(root: Path) -> dict[str, Any]:
    office_dir = root / "release-evidence/former-preserve-only-semantic-editability/office-results"
    public_dir = root / "release-evidence/former-preserve-only-semantic-editability/public-paths"
    public_paths = {path.stem.removeprefix("cli-"): path for path in public_dir.glob("cli-*.jsonl")}
    files_by_status: Counter[str] = Counter()
    rows_by_status: Counter[str] = Counter()
    result_count = 0
    failed = []
    for office_path in sorted(office_dir.glob("*.json")):
        data = json.loads(office_path.read_text(encoding="utf-8"))
        status = primary_status(data)
        row_count = public_row_count(public_paths, office_path)
        files_by_status[status] += 1
        rows_by_status[status] += row_count
        result_count += 1
        if status != "pass":
            failed.append(failed_detail(root, public_paths, office_path, data, status, row_count))
    failed_rows = sum(count for status, count in rows_by_status.items() if status != "pass")
    failed_files = sum(count for status, count in files_by_status.items() if status != "pass")
    return {
        "office_result_file_count": result_count,
        "office_failed_file_count": failed_files,
        "candidate_row_count": sum(rows_by_status.values()),
        "candidate_rows_not_promoted_count": failed_rows,
        "files_by_status": dict(sorted(files_by_status.items())),
        "candidate_rows_by_status": dict(sorted(rows_by_status.items())),
        "failed_details": failed,
    }


def primary_status(data: dict[str, Any]) -> str:
    override = manual_override(data)
    if override:
        return str(override.get("status", "unknown"))
    statuses = [str(row.get("status", "unknown")) for row in data.get("results", [])]
    if statuses:
        return Counter(statuses).most_common(1)[0][0]
    by_status = data.get("summary", {}).get("by_status", {})
    if isinstance(by_status, dict) and by_status:
        return Counter({str(key): int(value) for key, value in by_status.items()}).most_common(1)[0][0]
    return "unknown"


def manual_override(data: dict[str, Any]) -> dict[str, Any]:
    override = data.get("manual_override", {})
    return override if isinstance(override, dict) and override.get("status") else {}


def public_row_count(public_paths: dict[str, Path], office_path: Path) -> int:
    label = matching_label(public_paths, office_path)
    if not label:
        return 0
    text = public_paths[label].read_text(encoding="utf-8")
    return sum(1 for line in text.splitlines() if line.strip())


def matching_label(public_paths: dict[str, Path], office_path: Path) -> str:
    stem = office_path.stem.removeprefix("api-")
    matches = [label for label in public_paths if stem.startswith(f"{label}-")]
    return max(matches, key=len) if matches else ""


def failed_detail(root: Path, public_paths: dict[str, Path], office_path: Path, data: dict[str, Any], status: str, row_count: int) -> dict[str, Any]:
    result = next(iter(data.get("results", [])), {})
    override = manual_override(data)
    label = matching_label(public_paths, office_path)
    package_id = package_id_from_result(result.get("file", "") or office_path.stem)
    message = redacted_message(str(override.get("message") or result.get("message", "")), root)
    return {
        "package_id": package_id,
        "status": status,
        "candidate_rows": row_count,
        "label": label,
        "excluded_from_future_selection": bool(package_id),
        "office_result_path": str(office_path.relative_to(root)),
        "message_excerpt": message[:160],
    }


def package_id_from_result(file_name: str) -> str:
    match = PACKAGE_RE.search(Path(file_name).stem)
    return match.group(1) if match else ""


def redacted_message(message: str, root: Path) -> str:
    return redact_user_paths(message, root)
