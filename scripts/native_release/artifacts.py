"""Create DMG and ZIP artifacts from a signed standalone payload."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .reproducibility import sha256_file


class ArtifactError(ValueError):
    """Artifact creation failed."""


def create_artifacts(
    payload: Path, output: Path, config: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    output.mkdir(parents=True, exist_ok=True)
    dmg = output / config["artifacts"]["dmg"]["filename"]
    zip_path = output / config["artifacts"]["zip"]["filename"]
    _create_zip(payload, zip_path)
    _create_dmg(payload, dmg)
    return {
        "dmg": {
            "path": str(dmg),
            "sha256": sha256_file(dmg),
            "size": dmg.stat().st_size,
        },
        "zip": {
            "path": str(zip_path),
            "sha256": sha256_file(zip_path),
            "size": zip_path.stat().st_size,
        },
    }


def attach_notarization(
    artifacts: dict[str, dict[str, Any]], notarization: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    result = {}
    for kind, row in artifacts.items():
        status = notarization.get(kind, {})
        result[kind] = {
            **row,
            "notarization": {
                "status": status.get("status"),
                "request_id": status.get("request_id"),
                "stapled": bool(status.get("stapled")),
                "mode": status.get(
                    "mode", "notarized" if status.get("stapled") else "online-notarized"
                ),
            },
        }
    return result


def _create_zip(payload: Path, path: Path) -> None:
    result = subprocess.run(
        [
            "ditto",
            "-c",
            "-k",
            "--keepParent",
            "--zlibCompressionLevel",
            "9",
            str(payload),
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ArtifactError(f"ditto create failed: {result.stderr.strip()}")


def _create_dmg(payload: Path, path: Path) -> None:
    result = subprocess.run(
        [
            "hdiutil",
            "create",
            "-volname",
            "OOXML",
            "-srcfolder",
            str(payload),
            "-ov",
            "-format",
            "UDZO",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ArtifactError(f"hdiutil create failed: {result.stderr.strip()}")
