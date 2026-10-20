"""Load and validate the native release contract."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

EXPECTED_TRANSACTION = [
    "artifact:dmg",
    "checksum:dmg",
    "artifact:zip",
    "checksum:zip",
    "manifest:versioned",
    "page:update",
    "verify:versioned",
    "latest:update",
    "verify:latest",
]
REQUIRED_ATTESTATION = {
    "source_commits",
    "source_dirty",
    "python_executable_sha256",
    "python_version",
    "nuitka_version",
    "xcode_version",
    "clang_version",
    "sdk_version",
    "wheelhouse_sha256",
    "source_tree_sha256",
    "compiler_flags",
    "strip_flags",
    "codesign_flags",
    "pre_sign_payload_sha256",
    "post_sign_payload_sha256",
}


class ConfigError(ValueError):
    """The release contract is internally inconsistent."""


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_config(path: str | Path) -> dict[str, Any]:
    config_path = Path(path).expanduser().resolve()
    try:
        loaded = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"cannot load native release config: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ConfigError("native release config must be a mapping")
    config = deepcopy(loaded)
    config["_config_path"] = str(config_path)
    config["_repo_root"] = str(config_path.parent.parent)
    _validate(config)
    return config


def _validate(config: dict[str, Any]) -> None:
    _expect(config, "schema_version", 1)
    _expect(config, "profile", "native-macos-arm64")
    _validate_target(config)
    _validate_runtime(config)
    _validate_artifacts(config)
    _validate_entitlement(config)
    _validate_publish(config)
    _validate_scan(config)
    _validate_reproducibility(config)


def _expect(config: dict[str, Any], key: str, value: Any) -> None:
    if config.get(key) != value:
        raise ConfigError(f"{key} must be {value!r}")


def _validate_target(config: dict[str, Any]) -> None:
    target = config.get("target", {})
    if target.get("os") != "macos" or target.get("architecture") != "arm64":
        raise ConfigError("native release target must be macOS arm64")
    build = config.get("build", {})
    if build.get("distribution") != "standalone-directory":
        raise ConfigError("distribution must be standalone-directory")
    for key in (
        "python",
        "python_version",
        "wheelhouse_env",
        "build_env_env",
        "requirements",
        "first_party_distributions",
        "include_packages",
        "package_data",
        "docs_dir",
        "nuitka",
        "client_entry",
        "engine_entry",
    ):
        if not build.get(key):
            raise ConfigError(f"build.{key} is required")


def _validate_runtime(config: dict[str, Any]) -> None:
    runtime = config.get("runtime", {})
    if runtime.get("classification") != "embedded-python":
        raise ConfigError("classification must remain embedded-python")
    if runtime.get("fully_native") is not False:
        raise ConfigError("fully_native must be false without runtime-free proof")
    if runtime.get("external_python_required") is not False:
        raise ConfigError("external_python_required must be false")
    for key in ("artifact_id", "client_version", "engine_version"):
        if not runtime.get(key):
            raise ConfigError(f"runtime.{key} is required")
    if str(runtime.get("artifact_id", "")).startswith("development-"):
        raise ConfigError("artifact_id must be a stamped release identity")


def _validate_artifacts(config: dict[str, Any]) -> None:
    artifacts = config.get("artifacts", {})
    if set(artifacts) != {"dmg", "zip"}:
        raise ConfigError("exactly dmg and zip artifacts are required")
    if artifacts["dmg"].get("page_visible") is not True:
        raise ConfigError("DMG must be the page-visible artifact")
    if artifacts["zip"].get("page_visible") is not False:
        raise ConfigError("ZIP must not be the page-visible artifact")
    notary = config.get("notarization", {})
    if notary.get("dmg", {}).get("staple") is not True:
        raise ConfigError("DMG notarization ticket must be stapled")
    if notary.get("zip", {}).get("staple") is not False:
        raise ConfigError("ZIP cannot be stapled")
    signing = config.get("signing", {})
    for key in ("identity_env", "identity_prefix"):
        if not signing.get(key):
            raise ConfigError(f"signing.{key} is required")
    if (
        signing.get("hardened_runtime") is not True
        or signing.get("timestamp") is not True
    ):
        raise ConfigError("release signing requires hardened runtime and timestamp")


def _validate_entitlement(config: dict[str, Any]) -> None:
    entitlement = config.get("entitlement", {})
    if entitlement.get("publication_mode") != "external-entitlement-channel":
        raise ConfigError("unsupported entitlement publication mode")
    if entitlement.get("license_required") is not True:
        raise ConfigError("license_required must be true")
    forbidden = set(entitlement.get("forbidden_license_ids", []))
    if "online-staging-acceptance" not in forbidden:
        raise ConfigError("staging license id must remain forbidden")
    allowed = set(entitlement.get("allowed_license_types", []))
    if not allowed or "release-test" not in allowed:
        raise ConfigError("release-test must be an allowed license type")
    public_key = entitlement.get("activation_public_key_hex")
    if not isinstance(public_key, str) or len(public_key) != 64:
        raise ConfigError("entitlement.activation_public_key_hex must be 32 bytes hex")


def _validate_publish(config: dict[str, Any]) -> None:
    publish = config.get("publish", {})
    if publish.get("transaction") != EXPECTED_TRANSACTION:
        raise ConfigError("publish transaction order is not the approved order")
    if not str(publish.get("base_url", "")).startswith("https://"):
        raise ConfigError("publish.base_url must use HTTPS")
    if not str(publish.get("product_page_url", "")).startswith("https://"):
        raise ConfigError("publish.product_page_url must use HTTPS")
    if publish.get("latest_cache") not in {"no-store", "public, max-age=60"}:
        raise ConfigError("latest cache must be no-store or at most 60 seconds")


def _validate_scan(config: dict[str, Any]) -> None:
    scan = config.get("scan", {})
    for suffix in (".py", ".pyc", ".pyo", ".whl"):
        if suffix not in scan.get("forbidden_suffixes", []):
            raise ConfigError(f"scan must forbid {suffix}")
    if "license.json" not in scan.get("forbidden_names", []):
        raise ConfigError("scan must forbid license.json")
    if scan.get("require_zero_dwarf") is not True:
        raise ConfigError("release scan must require zero DWARF")
    allowlist = Path(scan.get("allowed_toolchain_markers_file", ""))
    if not (repo_root() / allowlist).is_file():
        raise ConfigError(f"scan allowlist does not exist: {allowlist}")


def _validate_reproducibility(config: dict[str, Any]) -> None:
    reproduc = config.get("reproducibility", {})
    fields = set(reproduc.get("required_attestation_fields", []))
    missing = sorted(REQUIRED_ATTESTATION - fields)
    if missing:
        raise ConfigError(f"missing attestation fields: {', '.join(missing)}")
    exclusions = set(reproduc.get("normalized_payload_exclusions", []))
    for value in ("code_signature", "macho_uuid", "filesystem_metadata"):
        if value not in exclusions:
            raise ConfigError(f"normalized hash must exclude {value}")
