"""Build a standalone native payload from a frozen wheelhouse."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .sbom import write_sbom


class BuildError(ValueError):
    """The native build adapter failed."""


def build_stage(config: dict[str, Any], stage: Path, mode: str, env=None) -> Path:
    values = os.environ if env is None else env
    wheelhouse = _wheelhouse(config, values)
    run_dir = stage.parent
    run_dir.mkdir(parents=True, exist_ok=True)
    build_env, fresh = _build_env(config, run_dir, values, mode)
    if fresh:
        _install_dependencies(config, build_env, wheelhouse)
    wrappers = _write_wrappers(run_dir, config)
    client_dist = _build_client(config, build_env, wrappers["client"], run_dir)
    engine_dist = _build_engine(config, build_env, wrappers["engine"], run_dir)
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True)
    _assemble(config, client_dist, engine_dist, stage, wheelhouse)
    return stage


def _wheelhouse(config: dict[str, Any], env) -> Path:
    value = env.get(config["build"]["wheelhouse_env"])
    if not value:
        raise BuildError(f"{config['build']['wheelhouse_env']} is required")
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise BuildError(f"wheelhouse does not exist: {path}")
    return path


def _build_env(config: dict[str, Any], run_dir: Path, env, mode: str):
    configured = env.get(config["build"]["build_env_env"])
    if configured:
        if mode == "release":
            raise BuildError("release must not reuse OOXML_NATIVE_BUILD_ENV")
        path = Path(configured).expanduser().resolve()
        if not (path / "bin/python").is_file():
            raise BuildError(f"build environment is invalid: {path}")
        return path, False
    path = run_dir / "build-env"
    result = _run([config["build"]["python"], "-m", "venv", str(path)])
    if result.returncode != 0:
        raise BuildError(f"venv creation failed: {result.stderr.strip()}")
    return path, True


def _install_dependencies(config: dict[str, Any], env: Path, wheelhouse: Path) -> None:
    python = env / "bin/python"
    commands = [
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--find-links",
            str(wheelhouse),
            f"Nuitka=={config['build']['nuitka']}",
        ],
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--find-links",
            str(wheelhouse),
            "-r",
            str(Path(config["_repo_root"]) / config["build"]["requirements"]),
        ],
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-index",
            "--find-links",
            str(wheelhouse),
            "--no-deps",
            *config["build"]["first_party_distributions"],
        ],
    ]
    for command in commands:
        result = _run(command)
        if result.returncode != 0:
            raise BuildError(f"dependency install failed: {result.stderr.strip()}")


def _write_wrappers(run_dir: Path, config: dict[str, Any]) -> dict[str, Path]:
    wrappers = {
        "client": run_dir / config["build"]["client_entry"],
        "engine": run_dir / config["build"]["engine_entry"],
    }
    wrappers["client"].write_text(
        "from ooxml_client.cli import main\n\nraise SystemExit(main())\n",
        encoding="utf-8",
    )
    wrappers["engine"].write_text(
        'import importlib\n\ncli = importlib.import_module("ooxml_operation_engine.cli")\nraise SystemExit(cli.main())\n',
        encoding="utf-8",
    )
    return wrappers


def _build_client(
    config: dict[str, Any], env: Path, wrapper: Path, run_dir: Path
) -> Path:
    return _nuitka(
        config, env, wrapper, run_dir / "client", "ooxml", ["ooxml_client", "mcp"]
    )


def _build_engine(
    config: dict[str, Any], env: Path, wrapper: Path, run_dir: Path
) -> Path:
    includes = [
        name for name in config["build"]["include_packages"] if name != "ooxml_client"
    ]
    includes = [name for name in includes if name not in {"pymupdf", "fitz"}]
    return _nuitka(config, env, wrapper, run_dir / "engine", "ooxml-engine", includes)


def _nuitka(
    config: dict[str, Any],
    env: Path,
    wrapper: Path,
    output: Path,
    filename: str,
    includes: list[str],
) -> Path:
    command = [
        str(env / "bin/python"),
        "-m",
        "nuitka",
        "--standalone",
        "--deployment",
        "--assume-yes-for-downloads",
        "--disable-cache=ccache",
        "--noinclude-pytest-mode=nofollow",
        f"--output-dir={output}",
        f"--output-filename={filename}",
        "--remove-output",
    ]
    for name in config["build"]["exclude_imports"]:
        command.append(f"--nofollow-import-to={name}")
    for name in includes:
        command.append(f"--include-package={name}")
    for name in config["build"]["package_data"]:
        command.append(f"--include-package-data={name}")
    command.append(str(wrapper))
    result = _run(command)
    if result.returncode != 0:
        raise BuildError(f"Nuitka build failed: {result.stderr.strip()}")
    dists = list(output.glob("*.dist"))
    if len(dists) != 1:
        raise BuildError(f"expected one Nuitka dist for {filename}")
    return dists[0]


def _assemble(
    config: dict[str, Any], client: Path, engine: Path, stage: Path, wheelhouse: Path
) -> None:
    (stage / "bin").mkdir()
    (stage / "lib").mkdir()
    (stage / "docs").mkdir()
    shutil.copytree(client, stage / "lib/ooxml-client", symlinks=True)
    shutil.copytree(engine, stage / "lib/ooxml-engine", symlinks=True)
    (stage / "lib/ooxml-client/ooxml-engine").symlink_to("../ooxml-engine/ooxml-engine")
    (stage / "bin/ooxml").symlink_to("../lib/ooxml-client/ooxml")
    (stage / "bin/ooxml-engine").symlink_to("../lib/ooxml-engine/ooxml-engine")
    _copy_public_metadata(config, stage, wheelhouse)


def _copy_public_metadata(
    config: dict[str, Any], stage: Path, wheelhouse: Path
) -> None:
    root = Path(config["_repo_root"])
    docs = root / config["build"]["docs_dir"]
    for name in (
        "INSTALL.md",
        "RUNTIME-BOUNDARY.md",
        "RELEASE-NOTES.md",
        "THIRD-PARTY-NOTICES.md",
    ):
        shutil.copy2(docs / name, stage / "docs" / name)
    shutil.copy2(
        root / config["sources"]["client"] / "LICENSE", stage / "LICENSE-CLIENT"
    )
    shutil.copy2(
        root / config["sources"]["engine"] / "LICENSE", stage / "LICENSE-ENGINE"
    )
    (stage / "docs/ACTIVATION-PUBLIC-KEY.txt").write_text(
        config["entitlement"]["activation_public_key_hex"] + "\n", encoding="utf-8"
    )
    write_sbom(stage / "SBOM.cdx.json", config, wheelhouse)


def _run(command: list[str]):
    return subprocess.run(command, capture_output=True, text=True, check=False)
