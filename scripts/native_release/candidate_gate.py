"""Verify Developer ID, notarization, staple, and Gatekeeper gates."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .signing import (
    SigningError,
    macho_files,
    verify_gatekeeper,
    verify_payload_signatures,
)


def verify_candidate(
    candidate: Path, config: dict[str, Any], metadata_path: Path | None = None
) -> dict[str, Any]:
    metadata = _metadata(candidate, metadata_path)
    expected_team = config["signing"]["expected_team_id"]
    with tempfile.TemporaryDirectory() as folder:
        root = _extract(candidate, Path(folder))
        team = verify_payload_signatures(root, require_team=True)
        if team != expected_team:
            raise SigningError(f"TeamIdentifier {team!r} is not {expected_team!r}")
        _verify_hardened(root)
        client = root / "bin/ooxml"
        engine = root / "bin/ooxml-engine"
        if candidate.suffix == ".dmg":
            _verify_dmg(candidate)
            verify_gatekeeper(candidate, client, engine)
    _verify_metadata(candidate, metadata, expected_team)
    return {"candidate": str(candidate), "team_id": team, "metadata": metadata}


def _metadata(candidate: Path, metadata_path: Path | None) -> dict[str, Any]:
    path = metadata_path or candidate.with_suffix(candidate.suffix + ".json")
    if not path.is_file():
        raise SigningError(f"candidate metadata does not exist: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SigningError(f"cannot read candidate metadata: {exc}") from exc
    if not isinstance(payload, dict):
        raise SigningError("candidate metadata must be an object")
    return payload


def _verify_metadata(
    candidate: Path, metadata: dict[str, Any], expected_team: str
) -> None:
    if metadata.get("team_id") != expected_team:
        raise SigningError("candidate metadata TeamIdentifier mismatch")
    notary = metadata.get("notarization")
    if not isinstance(notary, dict) or notary.get("status") != "notarized":
        raise SigningError("candidate metadata is not notarized")
    if not notary.get("request_id"):
        raise SigningError("candidate metadata is missing notary request ID")
    if candidate.suffix == ".dmg" and notary.get("stapled") is not True:
        raise SigningError("DMG metadata must be stapled")


def _extract(candidate: Path, destination: Path) -> Path:
    if candidate.suffix == ".zip":
        _run(["ditto", "-x", "-k", str(candidate), str(destination)])
    elif candidate.suffix == ".dmg":
        mount = destination / "mnt"
        mount.mkdir()
        _run(
            [
                "hdiutil",
                "attach",
                str(candidate),
                "-nobrowse",
                "-readonly",
                "-mountpoint",
                str(mount),
            ]
        )
        try:
            tree = next(mount.iterdir())
            shutil.copytree(tree, destination / "payload", symlinks=True)
        finally:
            subprocess.run(["hdiutil", "detach", str(mount), "-quiet"], check=False)
        return destination / "payload"
    else:
        raise SigningError("candidate must be .dmg or .zip")
    roots = [p.parent.parent for p in destination.rglob("bin/ooxml") if p.is_file()]
    if len(roots) != 1:
        raise SigningError("cannot identify candidate payload root")
    return roots[0]


def _verify_hardened(root: Path) -> None:
    for path in macho_files(root):
        details = subprocess.run(
            ["codesign", "-dv", "--verbose=4", str(path)],
            capture_output=True,
            text=True,
            check=False,
        ).stderr
        if "runtime" not in details:
            raise SigningError(f"hardened runtime flag is missing: {path}")


def _verify_dmg(path: Path) -> None:
    _run(["codesign", "--verify", "--strict", "--verbose=4", str(path)])
    _run(["xcrun", "stapler", "validate", str(path)])


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SigningError(f"{' '.join(command)} failed: {detail}")
