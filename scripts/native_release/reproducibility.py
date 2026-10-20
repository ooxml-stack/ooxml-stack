"""Build attestations and normalized payload hashing."""

from __future__ import annotations

import hashlib
import os
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .config import REQUIRED_ATTESTATION

IGNORED_DIRECTORIES = {
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".venv-ecosystem-inventory",
}


class AttestationError(ValueError):
    """Required reproducibility evidence is missing."""


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_payload_sha256(root: str | Path, normalize_macho: bool = True) -> str:
    base = Path(root)
    digest = hashlib.sha256()
    for path in sorted(
        item
        for item in base.rglob("*")
        if _included(item) and (item.is_file() or item.is_symlink())
    ):
        relative = path.relative_to(base).as_posix().encode()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        if path.is_symlink():
            digest.update(b"L")
            digest.update(os.readlink(path).encode())
            continue
        digest.update(b"E" if os.access(path, os.X_OK) else b"F")
        digest.update(_normalized_file_bytes(path, normalize_macho))
    return digest.hexdigest()


def collect_attestation(
    config: dict[str, Any],
    source_tree: Path,
    wheelhouse: Path,
    payload: Path,
    pre_sign_payload_sha256: str | None = None,
    container_hashes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    runtime = config["runtime"]
    result = {
        "profile": config["profile"],
        "artifact_id": runtime["artifact_id"],
        "client_version": runtime["client_version"],
        "engine_version": runtime["engine_version"],
        "source_commits": _source_commits(config),
        "source_dirty": _source_dirty(config),
        "python_executable_sha256": sha256_file(config["build"]["python"]),
        "python_version": _run([config["build"]["python"], "-V"]),
        "nuitka_version": config["build"]["nuitka"],
        "xcode_version": _run(["xcodebuild", "-version"], check=False),
        "clang_version": _run(["clang", "--version"], check=False),
        "sdk_version": _run(
            ["xcrun", "--sdk", "macosx", "--show-sdk-version"], check=False
        ),
        "wheelhouse_sha256": normalized_payload_sha256(wheelhouse),
        "source_tree_sha256": normalized_payload_sha256(source_tree),
        "compiler_flags": config["build"].get("compiler_flags", []),
        "strip_flags": ["-x"],
        "codesign_flags": ["--options", "runtime", "--timestamp"],
        "pre_sign_payload_sha256": pre_sign_payload_sha256
        or normalized_payload_sha256(payload, normalize_macho=False),
        "post_sign_payload_sha256": normalized_payload_sha256(
            payload, normalize_macho=True
        ),
        "container_hashes": container_hashes or {},
        "symbols": symbol_summary(payload),
    }
    missing = sorted(REQUIRED_ATTESTATION - set(result))
    if missing:
        raise AttestationError(f"attestation missing fields: {', '.join(missing)}")
    return result


def symbol_summary(root: Path) -> dict[str, Any]:
    rows = []
    for path in sorted(root.rglob("*")):
        if (
            not path.is_file()
            or path.is_symlink()
            or b"Mach-O"
            not in subprocess.run(
                ["file", "-b", str(path)], capture_output=True, check=False
            ).stdout
        ):
            continue
        output = subprocess.run(
            ["nm", "-gU", str(path)], capture_output=True, text=True, check=False
        ).stdout
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "line_count": len(output.splitlines()),
                "undefined_count": sum(
                    1 for line in output.splitlines() if " U " in line
                ),
            }
        )
    return {"macho_count": len(rows), "files": rows}


def _included(path: Path) -> bool:
    return not any(part in IGNORED_DIRECTORIES for part in path.parts)


def _normalized_file_bytes(path: Path, normalize_macho: bool) -> bytes:
    data = path.read_bytes()
    if (
        not normalize_macho
        or b"Mach-O" not in _run(["file", "-b", str(path)], check=False).encode()
    ):
        return data
    with tempfile.TemporaryDirectory() as folder:
        copy = Path(folder) / path.name
        shutil.copy2(path, copy)
        subprocess.run(
            ["codesign", "--remove-signature", str(copy)],
            capture_output=True,
            check=False,
        )
        return _zero_macho_uuid(copy.read_bytes())


def _zero_macho_uuid(data: bytes) -> bytes:
    if len(data) < 32 or data[:4] != b"\xcf\xfa\xed\xfe":
        return data
    mutable = bytearray(data)
    ncmds = struct.unpack_from("<I", mutable, 16)[0]
    offset = 32
    for _ in range(ncmds):
        if offset + 8 > len(mutable):
            break
        command, size = struct.unpack_from("<II", mutable, offset)
        if size < 8 or offset + size > len(mutable):
            break
        if command == 0x1B and size >= 24:
            mutable[offset + 8 : offset + 24] = b"\0" * 16
        offset += size
    return bytes(mutable)


def _source_commits(config: dict[str, Any]) -> dict[str, str]:
    root = Path(config["_repo_root"])
    commits = {}
    for name, path in config["sources"].items():
        result = subprocess.run(
            ["git", "-C", str(root / path), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        commits[name] = result.stdout.strip() if result.returncode == 0 else "missing"
    return commits


def _source_dirty(config: dict[str, Any]) -> dict[str, list[str]]:
    root = Path(config["_repo_root"])
    dirty = {}
    for name, path in config["sources"].items():
        result = subprocess.run(
            ["git", "-C", str(root / path), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )
        dirty[name] = (
            result.stdout.splitlines() if result.returncode == 0 else ["missing"]
        )
    return dirty


def _run(command: list[str], check: bool = True) -> str:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if check and result.returncode != 0:
        raise AttestationError(f"{' '.join(command)} failed: {result.stderr.strip()}")
    return (result.stdout or result.stderr).strip()
