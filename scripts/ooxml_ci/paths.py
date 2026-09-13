"""Workspace layout constants and root discovery, using the standard library only.

The dependency precheck runs before any third-party import, so everything it
needs -- where the artifacts live, and how the workspace root is found -- lives
here rather than in the parsing layer. Importing this module must never pull in
``packaging`` or ``yaml``.
"""

from __future__ import annotations

import pathlib

HOST_KEY = "ooxml-stack"  # owns the policy, the plan and the scan report
CORE_KEY = "ooxml-core"
POLICY_RELPATH = "ci/ecosystem-policy.json"
PLAN_RELPATH = "ci/ecosystem-plan.json"
SCAN_RELPATH = "ci/reports/scan.json"
REQUIREMENTS_RELPATH = "ci/ecosystem-inventory-requirements.txt"
WORKFLOW_GLOBS = (".github/workflows/*.yml", ".github/workflows/*.yaml")


class InputError(RuntimeError):
    """A required input could not be read; the caller must not write a plan."""


def find_root(start: pathlib.Path) -> pathlib.Path:
    """The workspace root: the nearest directory holding both host and core."""
    for candidate in [start, *start.parents]:
        if (candidate / HOST_KEY).is_dir() and (candidate / CORE_KEY).is_dir():
            return candidate
    raise InputError(f"no workspace root above {start} (need {HOST_KEY}/ and {CORE_KEY}/)")