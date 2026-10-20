"""CLI orchestration for native release development and publication."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from .artifacts import create_artifacts
from .builder import BuildError, build_stage
from .candidate_gate import verify_candidate
from .candidate import resolve_candidate, write_latest_dev
from .config import ConfigError, load_config
from .evidence import EvidenceSeal
from .functional import FunctionalError, run_functional
from .input_lock import InputLockError
from .license_gate import (
    LicenseGateError,
    validate_internal_license,
    validate_release_license,
)
from .manifest import ManifestError
from .release import run_release
from .reproducibility import AttestationError
from .scan import ScanError, scan_dmg, scan_zip
from .signing import SigningError, ad_hoc_sign_payload, strip_payload


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="native-release")
    parser.add_argument(
        "command", choices=["dev", "test", "release", "plan", "license-check"]
    )
    parser.add_argument("--config", default="release/native-macos-arm64.yaml")
    parser.add_argument("--candidate")
    parser.add_argument("--stage-dir")
    parser.add_argument("--internal-license", action="store_true")
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
        BuildError,
        FunctionalError,
        InputLockError,
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
        return _license_check(config, args.internal_license)
    if args.command == "dev":
        return _dev(config, args.stage_dir)
    if args.command == "test":
        return _test(config, args.candidate, args.internal_license)
    return _release(config, args.stage_dir)


def _license_check(config: dict[str, Any], internal: bool = False) -> dict[str, Any]:
    value = os.environ.get(config["entitlement"]["e2e_license_env"], "")
    if not value:
        raise LicenseGateError(
            f"{config['entitlement']['e2e_license_env']} is required"
        )
    validator = validate_internal_license if internal else validate_release_license
    return {"status": "ok", "license": validator(value, config)}


def _dev(config: dict[str, Any], stage_dir: str | None) -> dict[str, Any]:
    stage = _stage_target(config, "dev", stage_dir)
    build_stage(config, stage, "dev")
    _require_stage(stage)
    strip_payload(stage)
    signed = ad_hoc_sign_payload(stage)
    output = _run_dir(config, "dev") / "artifacts"
    artifacts = create_artifacts(stage, output, config)
    write_latest_dev(_artifact_root(config), artifacts["zip"]["path"])
    return {
        "status": "ok",
        "mode": "dev",
        "stage": str(stage),
        "signed_macho": len(signed),
        "artifacts": artifacts,
    }


def _test(
    config: dict[str, Any], candidate: str | None, internal: bool = False
) -> dict[str, Any]:
    artifact_root = _artifact_root(config)
    path = resolve_candidate(
        candidate, artifact_root, allow_latest_dev=not bool(os.environ.get("CI"))
    )
    license_summary = _license_check(config, internal)["license"]
    if path.suffix == ".dmg":
        scan = scan_dmg(path, config)
    elif path.suffix == ".zip":
        scan = scan_zip(path, config)
    else:
        raise ConfigError("candidate must be a .dmg or .zip artifact")
    if not scan["pass"]:
        raise ScanError(f"candidate scan failed: {path}")
    evidence = EvidenceSeal(_run_dir(config, "test") / path.stem)
    evidence.write(
        "preflight.json",
        {"mode": "test", "candidate": str(path), "license": license_summary},
    )
    evidence.write("scan.json", _scan_summary(scan))
    signing = verify_candidate(path, config)
    evidence.write("signing-notarization.json", signing)
    functional = run_functional(path, config, evidence.root, internal)
    result = {
        "status": "ok",
        "mode": "DEV_ONLY" if internal else "PUBLIC",
        "candidate": str(path),
        "license": license_summary,
        "scan": _scan_summary(scan),
        "signing": signing,
        "functional_pass": functional["pass"],
    }
    result["evidence"] = evidence.finalize(result)
    return result


def _release(config: dict[str, Any], stage_dir: str | None) -> dict[str, Any]:
    return run_release(config, stage_dir)


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
