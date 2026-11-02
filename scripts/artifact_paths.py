"""Resolve generated artifacts outside source checkouts."""

import os
from pathlib import Path


def artifact_dir(area="release-evidence"):
    configured = os.environ.get("OOXML_ARTIFACT_ROOT")
    if configured:
        base = Path(configured).expanduser()
    else:
        workspace = next((p for p in Path(__file__).resolve().parents
                          if (p / ".delivery-evidence").is_dir()), None)
        base = (workspace / ".delivery-evidence/artifacts" if workspace
                else Path.home() / ".local/share/ooxml/artifacts")
    target = (base / "ooxml-stack" / area).resolve()
    if any((p / ".git").exists() for p in (target, *target.parents)):
        raise ValueError("OOXML artifacts must be stored outside Git checkouts")
    return target


def artifact_file(area, name, ensure=True):
    """Resolve one output file path under the artifact root.

    Single-output API: a run emits exactly one artifact file through this
    call, so manifests stay one entry per run. ``name`` must be relative,
    without ``..`` components, and must never target a ``.git`` directory.
    """
    name_path = Path(name)
    if not name_path.parts or name_path.is_absolute() or ".." in name_path.parts:
        raise ValueError("artifact file name must be a relative path without '..'")
    target = (artifact_dir(area) / name_path).resolve()
    if ".git" in target.parts:
        raise ValueError("artifact paths must not target .git directories")
    if ensure:
        target.parent.mkdir(parents=True, exist_ok=True)
    return target
