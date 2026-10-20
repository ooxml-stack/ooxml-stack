"""Extract DMG and ZIP candidates into standalone payload roots."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class ArtifactIOError(ValueError):
    """Artifact extraction failed."""


def extract_candidate(candidate: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    if candidate.suffix == ".zip":
        _run(["ditto", "-x", "-k", str(candidate), str(destination)])
    elif candidate.suffix == ".dmg":
        return _extract_dmg(candidate, destination)
    else:
        raise ArtifactIOError("candidate must be .dmg or .zip")
    roots = [p.parent.parent for p in destination.rglob("bin/ooxml") if p.is_file()]
    if len(roots) != 1:
        raise ArtifactIOError("cannot identify packaged OOXML root")
    return roots[0]


def _extract_dmg(candidate: Path, destination: Path) -> Path:
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


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise ArtifactIOError(f"{' '.join(command)} failed: {detail}")
