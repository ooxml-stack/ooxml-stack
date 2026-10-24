"""Build a frozen macOS wheelhouse from clean first-party source trees."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .input_lock import wheelhouse_lock


class WheelhouseError(ValueError):
    """A source tree is unsafe or a wheel build failed."""


def build_wheelhouse(
    config: dict[str, Any], output: Path, lock_path: Path, env=None
) -> dict[str, Any]:
    values = os.environ if env is None else env
    output = output.expanduser().resolve()
    lock_path = lock_path.expanduser().resolve()
    if output.exists() and any(output.iterdir()):
        raise WheelhouseError(f"wheelhouse output must be empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    states = source_states(config)
    dirty = [name for name, row in states.items() if row["dirty"]]
    if dirty:
        raise WheelhouseError(f"source checkouts are dirty: {', '.join(dirty)}")
    python = _python(config, values)
    with tempfile.TemporaryDirectory(prefix="ooxml-wheelhouse-") as folder:
        staging = Path(folder)
        _third_party_wheels(config, python, staging)
        _first_party_wheels(config, python, staging)
        lock = wheelhouse_lock(staging)
        for wheel in sorted(staging.glob("*.whl")):
            shutil.copy2(wheel, output / wheel.name)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(
        __import__("json").dumps(lock, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "output": str(output),
        "lock": str(lock_path),
        "wheelhouse": lock,
        "sources": states,
    }


def source_states(config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    root = Path(config["_repo_root"])
    states = {}
    for name, relative in config["sources"].items():
        repo = (root / relative).resolve()
        head = _git(repo, "rev-parse", "HEAD")
        status = _git(repo, "status", "--porcelain")
        states[name] = {"path": str(repo), "commit": head, "dirty": bool(status)}
    return states


def _third_party_wheels(config: dict[str, Any], python: Path, output: Path) -> None:
    requirements = Path(config["_repo_root"]) / config["build"]["requirements"]
    _run(
        [
            str(python),
            "-m",
            "pip",
            "wheel",
            "--only-binary=:all:",
            "--wheel-dir",
            str(output),
            "-r",
            str(requirements),
        ]
    )
    _run(
        [
            str(python),
            "-m",
            "pip",
            "wheel",
            "--only-binary=:all:",
            "--wheel-dir",
            str(output),
            f"Nuitka=={config['build']['nuitka']}",
        ]
    )


def _first_party_wheels(config: dict[str, Any], python: Path, output: Path) -> None:
    root = Path(config["_repo_root"])
    for relative in config["sources"].values():
        source = (root / relative).resolve()
        _run(
            [
                str(python),
                "-m",
                "pip",
                "wheel",
                "--no-deps",
                "--wheel-dir",
                str(output),
                str(source),
            ]
        )


def _python(config: dict[str, Any], env) -> Path:
    value = env.get("OOXML_NATIVE_WHEELHOUSE_PYTHON") or config["build"]["python"]
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise WheelhouseError(f"wheelhouse Python does not exist: {path}")
    return path


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise WheelhouseError(
            f"git {' '.join(args)} failed for {repo}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise WheelhouseError(
            f"{' '.join(command)} failed: {(result.stderr or result.stdout).strip()}"
        )
