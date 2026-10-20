"""Transactional publication ordering for immutable artifacts and aliases."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

from .config import ConfigError

RELEASE_COMMIT = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class PublishResult:
    versioned_manifest_url: str
    latest_manifest_url: str
    steps: list[str]


def validate_transaction_shape(
    config: dict[str, Any], manifest: dict[str, Any]
) -> None:
    transaction = config["publish"]["transaction"]
    if transaction[-2:] != ["latest:update", "verify:latest"]:
        raise ConfigError("latest must be updated last and then verified")
    if "verify:versioned" not in transaction or transaction.index(
        "verify:versioned"
    ) > transaction.index("latest:update"):
        raise ConfigError(
            "versioned artifacts must be verified before latest is updated"
        )
    page_index = transaction.index("page:update")
    if page_index < transaction.index("manifest:versioned"):
        raise ConfigError(
            "product page cannot update before the versioned manifest exists"
        )
    dmg = manifest["artifacts"]["dmg"]
    if "/latest/" in dmg["url"]:
        raise ConfigError("product-page artifact must use an immutable versioned URL")


def run_transaction(
    config: dict[str, Any],
    manifest: dict[str, Any],
    callbacks: dict[str, Callable[[], Any]],
) -> PublishResult:
    validate_transaction_shape(config, manifest)
    completed = []
    for step in config["publish"]["transaction"]:
        callback = callbacks.get(step)
        if callback is None:
            raise ConfigError(f"publish callback missing for {step}")
        try:
            callback()
        except Exception as exc:
            raise ConfigError(f"publish transaction stopped at {step}: {exc}") from exc
        completed.append(step)
    dmg_url = manifest["artifacts"]["dmg"]["url"]
    return PublishResult(
        versioned_manifest_url=dmg_url.rsplit("/", 1)[0] + "/manifest.json",
        latest_manifest_url=config["publish"]["latest_manifest_url"],
        steps=completed,
    )


def release_target(config: dict[str, Any]) -> str:
    env_name = config["publish"]["release_commit_env"]
    value = os.environ.get(env_name, "").strip().lower()
    if not RELEASE_COMMIT.fullmatch(value):
        raise ConfigError(
            f"{env_name} must contain the explicit 40-character release commit"
        )
    return value


def assert_remote_branch_contains(target: str) -> list[str]:
    _run_command(["git", "rev-parse", "--verify", f"{target}^{{commit}}"])
    _run_command(
        [
            "git",
            "fetch",
            "--quiet",
            "--no-tags",
            "origin",
            "+refs/heads/*:refs/remotes/origin/*",
        ]
    )
    raw = _run_command(
        [
            "git",
            "for-each-ref",
            "--contains",
            target,
            "--format=%(refname)",
            "refs/remotes/origin",
        ]
    ).stdout
    branches = [
        line.strip()
        for line in raw.splitlines()
        if line.strip() and not line.strip().endswith("/HEAD")
    ]
    if not branches:
        raise ConfigError(
            f"release target {target} is not reachable from a remote branch"
        )
    return branches


def run_external_transaction(
    config: dict[str, Any],
    manifest: dict[str, Any],
    artifacts: dict[str, Any],
    manifest_path,
) -> dict[str, Any]:
    command = os.environ.get("OOXML_NATIVE_PUBLISH_STEP_COMMAND")
    if not command:
        raise ConfigError(
            "OOXML_NATIVE_PUBLISH_STEP_COMMAND must select an approved publisher"
        )
    target = release_target(config)
    assert_remote_branch_contains(target)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    callbacks = {
        step: lambda step=step: _run_publish_step(
            command, config, step, manifest_path, artifacts, target
        )
        for step in config["publish"]["transaction"]
    }
    result = run_transaction(config, manifest, callbacks)
    return {
        "versioned_manifest_url": result.versioned_manifest_url,
        "latest_manifest_url": result.latest_manifest_url,
        "steps": result.steps,
    }


def _run_publish_step(command, config, step, manifest, artifacts, target) -> None:
    env = {
        **os.environ,
        "NATIVE_PUBLISH_STEP": step,
        "NATIVE_MANIFEST": str(manifest),
        "NATIVE_DMG": artifacts["dmg"]["path"],
        "NATIVE_ZIP": artifacts["zip"]["path"],
        "NATIVE_RELEASE_COMMIT": target,
        "NATIVE_PRODUCT_PAGE_URL": config["publish"]["product_page_url"],
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
        raise ConfigError(f"native publish step {step} failed: {result.stderr.strip()}")


def _run_command(command: list[str]):
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ConfigError(
            f"{' '.join(command)} failed: {(result.stderr or result.stdout).strip()}"
        )
    return result
