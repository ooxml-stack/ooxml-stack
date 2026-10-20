"""Layered static scanning of final distributed payloads."""

from __future__ import annotations

import json
import math
import re
import subprocess
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any

PEM_BLOCK = re.compile(
    rb"-----BEGIN (?:OPENSSH |RSA |EC |DSA )?PRIVATE KEY-----\s+[A-Za-z0-9+/=\r\n]{64,}-----END"
)
BEARER_VALUE = re.compile(rb"(?i)authorization:\s*bearer\s+[A-Za-z0-9._~+/=-]{20,}")
CREDENTIAL_ASSIGNMENT = re.compile(
    rb"(?i)(?:token|secret|password|api_key)\s*[=:]\s*['\"]?([A-Za-z0-9._~+/=-]{24,})"
)


class ScanError(ValueError):
    """A final artifact violates the public release scan policy."""


def load_allowlist(path: str | Path) -> dict[str, dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ScanError("scan allowlist entries must be a list")
    result = {}
    for entry in entries:
        required = {"value", "kind", "component", "reviewer", "reason"}
        if not isinstance(entry, dict) or not required <= set(entry):
            raise ScanError("scan allowlist entry is incomplete")
        result[entry["value"]] = entry
    return result


def scan_directory(root: str | Path, config: dict[str, Any]) -> dict[str, Any]:
    base = Path(root)
    allowlist = load_allowlist(
        Path(config["_repo_root"]) / config["scan"]["allowed_toolchain_markers_file"]
    )
    result = {
        "root": str(base),
        "entries": 0,
        "forbidden_entries": [],
        "business_paths": [],
        "secrets": [],
        "allowed_strings": [],
        "debug_symbols": [],
    }
    for path in sorted(base.rglob("*")):
        relative = path.relative_to(base).as_posix()
        if path.is_symlink():
            continue
        if path.is_file():
            result["entries"] += 1
            _scan_entry(path, relative, config["scan"], result)
            data = path.read_bytes()
            _scan_markers(data, relative, config["scan"], allowlist, result)
            _scan_secrets(data, relative, result)
            if _is_macho(path):
                _scan_debug(path, relative, result)
    result["pass"] = not any(
        result[key]
        for key in ("forbidden_entries", "business_paths", "secrets", "debug_symbols")
    )
    return result


def scan_zip(path: str | Path, config: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as folder, zipfile.ZipFile(path) as archive:
        archive.extractall(folder)
        return scan_directory(folder, config)


def scan_dmg(path: str | Path, config: dict[str, Any]) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as folder:
        mount = Path(folder) / "mnt"
        mount.mkdir()
        result = subprocess.run(
            [
                "hdiutil",
                "attach",
                str(path),
                "-nobrowse",
                "-readonly",
                "-mountpoint",
                str(mount),
                "-plist",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise ScanError(f"cannot mount DMG: {result.stderr.strip()}")
        try:
            return scan_directory(mount, config)
        finally:
            subprocess.run(["hdiutil", "detach", str(mount), "-quiet"], check=False)


def _scan_entry(
    path: Path, relative: str, scan: dict[str, Any], result: dict[str, Any]
) -> None:
    if (
        path.suffix.lower() in scan["forbidden_suffixes"]
        or path.name in scan["forbidden_names"]
    ):
        result["forbidden_entries"].append(relative)


def _scan_markers(
    data: bytes,
    relative: str,
    scan: dict[str, Any],
    allowlist: dict[str, Any],
    result: dict[str, Any],
) -> None:
    for marker in scan["business_source_markers"]:
        raw = marker.encode()
        if raw in data:
            result["business_paths"].append({"path": relative, "marker": marker})
    for value in allowlist:
        if value.encode() in data:
            result["allowed_strings"].append(
                {
                    "path": relative,
                    "value": value,
                    "reviewer": allowlist[value]["reviewer"],
                }
            )


def _scan_secrets(data: bytes, relative: str, result: dict[str, Any]) -> None:
    if PEM_BLOCK.search(data):
        result["secrets"].append({"path": relative, "kind": "private-key-block"})
    for match in BEARER_VALUE.finditer(data):
        result["secrets"].append({"path": relative, "kind": "bearer-value"})
    for match in CREDENTIAL_ASSIGNMENT.finditer(data):
        value = match.group(1).decode("ascii", "ignore")
        if _entropy(value) >= 4.0:
            result["secrets"].append(
                {"path": relative, "kind": "high-entropy-assignment"}
            )


def _entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    return -sum(
        (count / len(value)) * math.log2(count / len(value))
        for count in counts.values()
    )


def _is_macho(path: Path) -> bool:
    result = subprocess.run(
        ["file", "-b", str(path)], capture_output=True, text=True, check=False
    )
    return "Mach-O" in result.stdout


def _scan_debug(path: Path, relative: str, result: dict[str, Any]) -> None:
    output = subprocess.run(
        ["otool", "-l", str(path)], capture_output=True, text=True, check=False
    ).stdout
    if "__DWARF" in output:
        result["debug_symbols"].append(relative)
