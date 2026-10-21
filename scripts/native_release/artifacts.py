"""Create DMG and ZIP artifacts from a signed standalone payload."""

from __future__ import annotations

import shutil
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
    container = output / "container"
    shutil.rmtree(container, ignore_errors=True)
    container.mkdir()
    packaged = container / "OOXML"
    shutil.copytree(payload, packaged, symlinks=True)
    _create_zip(packaged, zip_path)
    installer = output / "dmg-installer"
    shutil.rmtree(installer, ignore_errors=True)
    installer.mkdir()
    shutil.copy2(zip_path, installer / zip_path.name)
    _write_installer(installer, zip_path.name, sha256_file(zip_path))
    _create_dmg(installer, dmg)
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
            "--norsrc",
            "--noextattr",
            "--noqtn",
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


def _write_installer(root: Path, zip_name: str, digest: str) -> None:
    script = root / "Install.command"
    script.write_text(
        f"""#!/bin/sh
set -eu
HERE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ZIP="$HERE/{zip_name}"
EXPECTED="{digest}"
ACTUAL=$(shasum -a 256 "$ZIP" | awk '{{print $1}}')
if [ "$ACTUAL" != "$EXPECTED" ]; then
  echo "ZIP checksum mismatch" >&2
  exit 1
fi
DEST="${{OOXML_INSTALL_DIR:-$HOME/.local/ooxml}}"
PARENT=$(dirname "$DEST")
mkdir -p "$PARENT"
TMP=$(mktemp -d "$PARENT/ooxml-install.XXXXXX")
trap 'rm -rf "$TMP"' EXIT
ditto -x -k --norsrc --noextattr --noqtn "$ZIP" "$TMP"
rm -rf "$DEST"
mv "$TMP/OOXML" "$DEST"
echo "Installed OOXML to $DEST"
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    (root / "INSTALL.md").write_text(
        "# OOXML macOS installation\n\nRun `Install.command`. It verifies the embedded ZIP SHA-256 before expanding the complete OOXML runtime to `~/.local/ooxml` by default. Set `OOXML_INSTALL_DIR` to choose another destination. Keep the installed directory together.\n",
        encoding="utf-8",
    )


def _create_dmg(content_root: Path, path: Path) -> None:
    result = subprocess.run(
        [
            "hdiutil",
            "create",
            "-volname",
            "OOXML",
            "-srcfolder",
            str(content_root),
            "-ov",
            "-format",
            "UDZO",
            "-fs",
            "HFS+",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ArtifactError(f"hdiutil create failed: {result.stderr.strip()}")
