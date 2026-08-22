from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

PACKAGE_RE = re.compile(r"(?:^|-)((?:docx|pptx|xlsx)_[A-Za-z0-9_.-]+)$")


def failed_office_packages(office_dir: Path) -> set[str]:
    packages: set[str] = set()
    for path in office_dir.glob("api-*.json"):
        data = _read_json(path)
        gate_pass = data.get("summary", {}).get("gate_pass") is True
        for item in data.get("results", []):
            if gate_pass and item.get("status", "") in {"", "pass"}:
                continue
            package_id = _package_id(item.get("file", ""))
            if package_id:
                packages.add(package_id)
    return packages


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _package_id(file_name: str) -> str:
    stem = Path(file_name).stem
    match = PACKAGE_RE.search(stem)
    return match.group(1) if match else ""
