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
