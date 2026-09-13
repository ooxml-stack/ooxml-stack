"""Shared constants and the immutable snapshot every derivation reads from."""

from __future__ import annotations

import pathlib
from dataclasses import dataclass, field
from typing import Any

from .parsers import Declaration
from .paths import (
    HOST_KEY as HOST_KEY,
    PLAN_RELPATH as PLAN_RELPATH,
    POLICY_RELPATH as POLICY_RELPATH,
    SCAN_RELPATH as SCAN_RELPATH,
    WORKFLOW_GLOBS as WORKFLOW_GLOBS,
)

SCHEMA_VERSION = 1


@dataclass
class Facts:
    """Everything the plan is derived from, parsed from captured bytes only."""

    root: pathlib.Path
    policy: dict[str, Any]
    inputs: dict[str, bytes]
    digest: str
    missing: list[dict[str, Any]] = field(default_factory=list)
    declarations: list[Declaration] = field(default_factory=list)
    uv_sources: dict[str, dict[str, Any]] = field(default_factory=dict)
    locks: dict[str, dict[str, Any]] = field(default_factory=dict)
    versions: dict[str, tuple[str | None, str | None]] = field(default_factory=dict)
    environment: dict[str, Any] = field(default_factory=dict)
    workflow_uses: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    workflow_jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    clone_refs: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    workflow_errors: list[dict[str, Any]] = field(default_factory=list)