"""Pinned tool dependencies: the declaration, the gate and the scan observation.

The plan is a deterministic function of its selected inputs, and the pinned
dependency declaration is one of those inputs. A run whose interpreter does not
match that declaration is refused before anything is read or written, so a
different ``packaging`` release can never silently change a verdict.

This module is imported *before* the gate runs, so it uses the standard library
only: a missing third-party package must produce a preparation command, never an
``ImportError`` traceback.
"""

from __future__ import annotations

import importlib.metadata
import pathlib
import re
import sys
from typing import Any

from .paths import HOST_KEY, REQUIREMENTS_RELPATH

# Distribution names, exactly as the requirements file pins them. ``packaging``
# compares versions; ``PyYAML`` parses workflows; the ``tree-sitter`` pair parses
# the shell inside ``run``. All are mandatory: a declaration missing any one of
# them would silently weaken the gate.
REQUIRED = ("packaging", "PyYAML", "tree-sitter", "tree-sitter-bash")
DEFAULT_VENV = ".venv-ecosystem-inventory"
REQUIREMENT = re.compile(r"^(?P<name>[A-Za-z0-9_.-]+)==(?P<version>[0-9][0-9A-Za-z.!+_-]*)$")


class DependencyError(RuntimeError):
    """The pinned environment is absent or does not match the declaration."""


def normalize(name: str) -> str:
    """PEP 503 normalization, so ``PyYAML`` and ``pyyaml`` are one package."""
    return re.sub(r"[-_.]+", "-", name).lower()


_CANONICAL = {normalize(name): name for name in REQUIRED}


def requirements_path(root: pathlib.Path) -> pathlib.Path:
    return root / HOST_KEY / REQUIREMENTS_RELPATH


def prepare_command(venv: str = DEFAULT_VENV) -> str:
    """The exact steps a clean checkout needs; never run implicitly.

    Run from the workspace root: the host repo is where both the Makefile target
    and the relative requirements path resolve.
    """
    override = "" if venv == DEFAULT_VENV else f" ECOSYSTEM_VENV={venv}"
    return f"cd {HOST_KEY} && make ecosystem-inventory-deps{override}"


def parse_requirements(text: str) -> dict[str, str]:
    """The complete ``name==version`` pin set this tool requires.

    Only this tool's own dependencies are supported. Anything else -- an unknown
    package, a range, an extra, a marker, an include -- is a declaration error
    rather than something to interpret loosely.
    """
    pinned: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        match = REQUIREMENT.match(line)
        if match is None:
            raise DependencyError(f"dependency must be pinned as name==version: {line!r}")
        canonical = _CANONICAL.get(normalize(match.group("name")))
        if canonical is None:
            raise DependencyError(
                f"unsupported dependency {match.group('name')!r}; "
                f"this tool needs {', '.join(REQUIRED)}"
            )
        if canonical in pinned:
            raise DependencyError(f"duplicate declaration for {canonical}: {line!r}")
        pinned[canonical] = match.group("version")
    missing = [name for name in REQUIRED if name not in pinned]
    if missing:
        raise DependencyError("declaration is incomplete; missing " + ", ".join(missing))
    return pinned


def installed() -> dict[str, str | None]:
    """What this interpreter actually has. Observation only; never enters the plan."""
    found: dict[str, str | None] = {}
    for distribution in REQUIRED:
        try:
            found[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            found[distribution] = None
    return found


def observation() -> dict[str, Any]:
    """Environment facts for the scan report (not the plan)."""
    return {
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "packages": installed(),
    }


def check(root: pathlib.Path) -> dict[str, Any]:
    """Validate the declaration, then compare it with the running interpreter.

    Completeness comes first: an empty or partial file must never read as "no
    problems" merely because nothing was left to compare.
    """
    path = requirements_path(root)
    report: dict[str, Any] = {
        "requirements": f"{HOST_KEY}/{REQUIREMENTS_RELPATH}",
        "pinned": {},
        "installed": {},
        "problems": [],
    }
    if not path.is_file():
        report["problems"].append(f"dependency declaration is absent: {report['requirements']}")
        return report
    try:
        report["pinned"] = parse_requirements(path.read_text(encoding="utf-8"))
    except DependencyError as error:
        report["problems"].append(str(error))
        return report
    report["installed"] = installed()
    for name, wanted in sorted(report["pinned"].items()):
        found = report["installed"].get(name)
        if found is None:
            report["problems"].append(f"{name}=={wanted} is declared but not installed")
        elif found != wanted:
            report["problems"].append(f"{name}=={found} is installed but {wanted} is declared")
    return report