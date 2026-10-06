#!/usr/bin/env python3
"""Run the CI lint/type regression gates.

The critical lint gate (ruff E9/F63/F7/F82) must stay at zero. The pyright gate
is a ratchet: the repository currently has a bounded number of known type
diagnostics outside the strict dynamic-XML surface, and CI must not increase
that count.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "quality-baselines.json"
RUFF_SELECT = "E9,F63,F7,F82"
RUFF_PIN = "ruff==0.16.5"


def tool_path(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    candidate = Path(sys.executable).with_name(name)
    if candidate.exists():
        return str(candidate)
    raise SystemExit(f"{name} not found on PATH or next to {sys.executable}")


def ruff_command() -> list[str]:
    """Return the pinned ruff command, falling back to `uvx` like format_gate.py."""
    found = shutil.which("ruff")
    if found:
        return [found]
    uvx = shutil.which("uvx")
    if uvx:
        return [uvx, RUFF_PIN]
    raise SystemExit(f"neither ruff nor uvx is available to run {RUFF_PIN}")


def load_baseline() -> dict[str, Any]:
    if not BASELINE_PATH.exists():
        return {}
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def write_baseline(data: dict[str, Any]) -> None:
    BASELINE_PATH.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def lint_paths() -> list[str]:
    """Return the source roots that exist, so a repo without `src/` still lints.

    Repositories differ (`src`, `scripts`, `backend`, `mcp`, `codegen`); passing
    a missing directory to ruff is an E902 error rather than a skipped tree.
    """
    candidates = ("src", "tests", "scripts", "examples", "backend", "mcp", "codegen", "tools")
    return [name for name in candidates if (ROOT / name).is_dir()]


def run_ruff(update: bool) -> int:
    """Run the critical rule subset and the full configured rule set.

    The critical subset (E9/F63/F7/F82) must stay at zero everywhere. The
    configured set from `[tool.ruff.lint]` covers the whole repository and is
    also held at zero; `quality-baselines.json` records both counts so a
    regression is visible even if a future change relaxes the configuration.
    """
    failures = 0
    for label, extra in (
        ("ruff critical findings", ["--select", RUFF_SELECT]),
        ("ruff configured findings", []),
    ):
        cmd = [
            *ruff_command(),
            "check",
            *extra,
            "--output-format=json",
            *lint_paths(),
        ]
        result = subprocess.run(
            cmd, cwd=ROOT, text=True, capture_output=True, check=False
        )
        findings = json.loads(result.stdout or "[]")
        count = len(findings)
        print(f"{label}: {count}")
        for finding in findings[:40]:
            print(
                f"{finding.get('filename')}:{finding.get('location', {}).get('row')}: "
                f"{finding.get('code')} {finding.get('message')}"
            )
        if len(findings) > 40:
            print(f"... {len(findings) - 40} more")
        if update:
            baseline = load_baseline()
            key = "ruff_critical_findings" if extra else "ruff_findings"
            baseline[key] = count
            write_baseline(baseline)
        if count:
            failures += 1
    return 1 if failures else 0


def run_pyright(update: bool, strict: bool) -> int:
    config = "pyrightconfig.strict.json" if strict else "pyrightconfig.ci.json"
    baseline_key = "pyright_strict_errors" if strict else "pyright_errors"
    label = "pyright strict errors" if strict else "pyright errors"
    cmd = [
        tool_path("pyright"),
        "-p",
        config,
        "--outputjson",
    ]
    result = subprocess.run(cmd, cwd=ROOT, text=True, capture_output=True, check=False)
    payload = json.loads(result.stdout or "{}")
    diagnostics = payload.get("generalDiagnostics", [])
    errors = [d for d in diagnostics if d.get("severity") == "error"]
    count = len(errors)
    baseline = load_baseline()
    allowed = int(baseline.get(baseline_key, 0))
    print(f"{label}: {count}; baseline: {allowed}")
    for diagnostic in errors[:40]:
        start = diagnostic.get("range", {}).get("start", {})
        print(
            f"{diagnostic.get('file')}:{start.get('line')}:{start.get('character')}: "
            f"{diagnostic.get('rule')} {diagnostic.get('message')}"
        )
    if len(errors) > 40:
        print(f"... {len(errors) - 40} more")
    if update:
        baseline[baseline_key] = count
        write_baseline(baseline)
        return 0
    if count > allowed:
        print(
            "type regression: pyright errors exceed the checked-in baseline; "
            "fix the new diagnostics or update quality-baselines.json deliberately",
            file=sys.stderr,
        )
        return 1
    if count < allowed:
        print("pyright errors decreased; consider lowering quality-baselines.json")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tool", choices=("ruff", "pyright"))
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    if args.tool == "ruff":
        return run_ruff(args.update_baseline)
    return run_pyright(args.update_baseline, args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
