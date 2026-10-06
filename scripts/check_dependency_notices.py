#!/usr/bin/env python3
"""Fail when a declared runtime dependency is missing from THIRD-PARTY-NOTICES.md.

The inventory must track what the package actually depends on. Dependencies that
belong to this workspace itself (`ooxml-*`, `python-docx`, `python-pptx`,
`python-xlsx`) are first-party components and are exempt; everything else has to
appear in the notices table with its license.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTICES = ROOT / "THIRD-PARTY-NOTICES.md"
PYPROJECT = ROOT / "pyproject.toml"
FIRST_PARTY = re.compile(r"^(ooxml-|python-xlsx$|python-docx$|python-pptx$)")
NAME = re.compile(r"^([A-Za-z0-9_.\-]+)")
TABLE_ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|")


def dependencies_from_pyproject() -> list[str]:
    try:
        import tomllib
    except ModuleNotFoundError:  # pragma: no cover - Python < 3.11
        import tomli as tomllib  # type: ignore[no-redef]
    data = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    names = []
    for spec in data.get("project", {}).get("dependencies", []):
        match = NAME.match(spec.strip())
        if match is not None:
            names.append(match.group(1))
    return names


def dependencies_from_requirements() -> list[str]:
    """Repositories without a package manifest pin their toolchain in ci/."""
    names: list[str] = []
    # Only the declared toolchain: generated report trees also contain
    # "installed-*-requirements.txt" snapshots of a resolved environment, which
    # are evidence rather than declared dependencies.
    for path in sorted(ROOT.glob("ci/*requirements*.txt")) + sorted(
        ROOT.glob("*requirements*.txt")
    ):
        if "reports" in path.parts:
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "-r", "-e", "--")):
                continue
            match = NAME.match(line)
            if match is not None:
                names.append(match.group(1))
    return names


def declared_dependencies() -> list[str]:
    names = (
        dependencies_from_pyproject()
        if PYPROJECT.exists()
        else dependencies_from_requirements()
    )
    third_party = [name for name in names if not FIRST_PARTY.match(name.lower())]
    return sorted(set(third_party))


def documented_dependencies() -> set[str]:
    if not NOTICES.exists():
        return set()
    documented = set()
    for line in NOTICES.read_text(encoding="utf-8").splitlines():
        match = TABLE_ROW.match(line)
        if match:
            documented.add(match.group(1))
    return documented


def main() -> int:
    declared = declared_dependencies()
    documented = documented_dependencies()
    missing = [name for name in declared if name not in documented]
    stale = sorted(name for name in documented if name not in declared)
    print(f"declared third-party runtime dependencies: {len(declared)}")
    print(f"documented in THIRD-PARTY-NOTICES.md: {len(documented)}")
    if stale:
        print(f"note: documented but no longer a direct dependency: {stale}")
    if missing:
        for name in missing:
            print(
                f"missing from THIRD-PARTY-NOTICES.md: {name}",
                file=sys.stderr,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
