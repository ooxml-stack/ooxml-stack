"""License-free artifact smoke gate."""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .artifact_io import extract_candidate


class ArtifactOnlyError(ValueError):
    """The artifact is not independently installable or launchable."""


def run_artifact_only(candidate: Path, evidence_root: Path) -> dict[str, Any]:
    run_root = evidence_root / "artifact-only"
    run_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=run_root) as folder:
        payload = extract_candidate(candidate, Path(folder))
        home = Path(folder) / "home"
        install = home / ".local/ooxml"
        install.parent.mkdir(parents=True)
        shutil.copytree(payload, install, symlinks=True)
        env = {"HOME": str(home), "PATH": f"{install / 'bin'}:/usr/bin:/bin"}
        client = install / "bin/ooxml"
        version = _step([str(client), "--version"], env)
        status = _step([str(client), "status"], env)
    result = {
        "pass": _pass(version, status),
        "candidate": str(candidate),
        "steps": {"version": version, "status": status},
    }
    (evidence_root / "artifact-only.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    if not result["pass"]:
        raise ArtifactOnlyError(
            f"artifact-only gate failed: {evidence_root / 'artifact-only.json'}"
        )
    return result


def _pass(version: dict[str, Any], status: dict[str, Any]) -> bool:
    status_json = status.get("json") or {}
    return (
        version.get("exit_code") == 0
        and status.get("exit_code") == 0
        and status_json.get("serving") == "inactive"
        and status_json.get("reason") == "license_missing"
    )


def _step(command: list[str], env: dict[str, str]) -> dict[str, Any]:
    result = subprocess.run(
        command, env=env, capture_output=True, text=True, timeout=120, check=False
    )
    try:
        parsed = json.loads(result.stdout) if result.stdout.strip() else None
    except ValueError:
        parsed = None
    return {
        "command": command,
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "json": parsed,
    }
