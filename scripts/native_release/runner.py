"""CLI orchestration for native release development and publication."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from .artifacts import attach_notarization, create_artifacts
from .candidate import resolve_candidate
from .config import ConfigError, load_config
from .license_gate import LicenseGateError, validate_release_license
from .manifest import ManifestError, build_manifest
from .publish import run_external_transaction
from .reproducibility import AttestationError, collect_attestation
from .scan import ScanError, scan_dmg, scan_zip
from .signing import (
    SigningError,
    ad_hoc_sign_payload,
    notarize_artifacts,
    release_credentials,
    sign_disk_image,
    sign_payload,
    verify_gatekeeper,
    verify_payload_signatures,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="native-release")
    parser.add_argument(
        "command", choices=["dev", "test", "release", "plan", "license-check"]
    )
    parser.add_argument("--config", default="release/native-macos-arm64.yaml")
    parser.add_argument("--candidate")
    parser.add_argument("--stage-dir")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        result = _dispatch(args, config)
    except (
        ConfigError,
        LicenseGateError,
        ManifestError,
        ScanError,
        SigningError,
        AttestationError,
        ValueError,
    ) as exc:
        print(
            json.dumps({"status": "error", "error": str(exc)}, indent=2),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(result, indent=2))
    return 0


def _dispatch(args, config: dict[str, Any]) -> dict[str, Any]:
    if args.command == "plan":
        return {
            "status": "ok",
            "profile": config["profile"],
            "transaction": config["publish"]["transaction"],
        }
    if args.command == "license-check":
        return _license_check(config)
    if args.command == "dev":
        return _dev(config, args.stage_dir)
    if args.command == "test":
        return _test(config, args.candidate)
    return _release(config, args.stage_dir)


def _license_check(config: dict[str, Any]) -> dict[str, Any]:
    value = os.environ.get(config["entitlement"]["e2e_license_env"], "")
    if not value:
        raise LicenseGateError(
            f"{config['entitlement']['e2e_license_env']} is required"
        )
    return {"status": "ok", "license": validate_release_license(value, config)}


def _dev(config: dict[str, Any], stage_dir: str | None) -> dict[str, Any]:
    stage = _stage_target(config, "dev", stage_dir)
    _run_adapter(config, "dev", stage)
    _require_stage(stage)
    signed = ad_hoc_sign_payload(stage)
    output = _run_dir(config, "dev") / "artifacts"
    artifacts = create_artifacts(stage, output, config)
    return {
        "status": "ok",
        "mode": "dev",
        "stage": str(stage),
        "signed_macho": len(signed),
        "artifacts": artifacts,
    }


def _test(config: dict[str, Any], candidate: str | None) -> dict[str, Any]:
    artifact_root = _artifact_root(config)
    path = resolve_candidate(
        candidate, artifact_root, allow_latest_dev=not bool(os.environ.get("CI"))
    )
    _license_check(config)
    if path.suffix == ".dmg":
        scan = scan_dmg(path, config)
    elif path.suffix == ".zip":
        scan = scan_zip(path, config)
    else:
        raise ConfigError("candidate must be a .dmg or .zip artifact")
    if not scan["pass"]:
        raise ScanError(f"candidate scan failed: {path}")
    return {
        "status": "ok",
        "mode": "test",
        "candidate": str(path),
        "scan": _scan_summary(scan),
    }


def _release(config: dict[str, Any], stage_dir: str | None) -> dict[str, Any]:
    creds = release_credentials(config)
    license_summary = _license_check(config)["license"]
    _require_clean_sources(config)
    stage = _stage_target(config, "release", stage_dir)
    _run_adapter(config, "release", stage)
    _require_stage(stage)
    sign_payload(stage, creds.identity)
    team_id = verify_payload_signatures(stage, require_team=True)
    artifacts = create_artifacts(
        stage, _run_dir(config, "release") / "artifacts", config
    )
    sign_disk_image(Path(artifacts["dmg"]["path"]), creds.identity)
    notary = notarize_artifacts(
        Path(artifacts["dmg"]["path"]),
        Path(artifacts["zip"]["path"]),
        creds.notary_profile,
        config,
    )
    artifacts = attach_notarization(artifacts, notary)
    verify_gatekeeper(
        Path(artifacts["dmg"]["path"]),
        stage / "bin/ooxml",
        stage / "bin/ooxml-engine",
    )
    manifest = build_manifest(config, artifacts, team_id)
    scan = scan_dmg(Path(artifacts["dmg"]["path"]), config)
    zip_scan = scan_zip(Path(artifacts["zip"]["path"]), config)
    if not scan["pass"] or not zip_scan["pass"]:
        raise ScanError("final signed artifact scan failed")
    manifest_path = _run_dir(config, "release") / "public-manifest.json"
    publish_result = run_external_transaction(
        config, manifest, artifacts, manifest_path
    )
    wheelhouse = _wheelhouse(config)
    attestation = collect_attestation(
        config, Path(config["_repo_root"]), wheelhouse, stage
    )
    return {
        "status": "ok",
        "mode": "release",
        "license": license_summary,
        "team_id": team_id,
        "manifest": manifest,
        "scan": _scan_summary(scan),
        "zip_scan": _scan_summary(zip_scan),
        "attestation": attestation,
        "publish": publish_result,
    }


def _stage_target(config: dict[str, Any], mode: str, value: str | None) -> Path:
    candidate = (
        value
        or os.environ.get("OOXML_NATIVE_STAGE_DIR")
        or _run_dir(config, mode) / "stage"
    )
    return Path(candidate).expanduser().resolve()


def _require_stage(path: Path) -> None:
    if not path.is_dir() or not any(path.iterdir()):
        raise ConfigError(f"native build adapter produced no stage: {path}")


def _run_adapter(config: dict[str, Any], mode: str, stage: Path) -> None:
    command = os.environ.get("OOXML_NATIVE_BUILD_COMMAND")
    if not command:
        raise ConfigError(
            "OOXML_NATIVE_BUILD_COMMAND is required for the current build adapter"
        )
    env = {
        **os.environ,
        "NATIVE_CONFIG": config["_config_path"],
        "NATIVE_MODE": mode,
        "NATIVE_STAGE_DIR": str(stage),
        "NATIVE_RUN_DIR": str(_run_dir(config, mode)),
    }
    result = subprocess.run(
        shlex.split(command),
        env=env,
        cwd=config["_repo_root"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ConfigError(f"native build adapter failed: {result.stderr.strip()}")


def _require_clean_sources(config: dict[str, Any]) -> None:
    root = Path(config["_repo_root"])
    repos = [root, *(root / path for path in config["sources"].values())]
    dirty = []
    for repo in repos:
        result = subprocess.run(
            ["git", "-C", str(repo), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0 or result.stdout.strip():
            dirty.append(str(repo))
    if dirty:
        raise ConfigError(f"release requires clean repositories: {', '.join(dirty)}")


def _wheelhouse(config: dict[str, Any]) -> Path:
    value = os.environ.get(config["build"]["wheelhouse_env"])
    if not value:
        raise ConfigError(
            f"{config['build']['wheelhouse_env']} is required for attestation"
        )
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise ConfigError(f"wheelhouse does not exist: {path}")
    return path


def _artifact_root(config: dict[str, Any]) -> Path:
    default = Path(config["_repo_root"]).parent / ".delivery-evidence/artifacts"
    return Path(os.environ.get("OOXML_ARTIFACT_ROOT", default)).expanduser().resolve()


def _run_dir(config: dict[str, Any], mode: str) -> Path:
    root = _artifact_root(config) / "native" / mode
    root.mkdir(parents=True, exist_ok=True)
    return root


def _scan_summary(scan: dict[str, Any]) -> dict[str, Any]:
    return {
        key: scan[key]
        for key in (
            "pass",
            "entries",
            "forbidden_entries",
            "business_paths",
            "secrets",
            "allowed_strings",
            "debug_symbols",
        )
    }
