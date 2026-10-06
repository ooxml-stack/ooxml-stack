#!/usr/bin/env python3
"""Check formatting only for Python files changed by this branch/commit.

Full-repository formatting would rewrite large amounts of historical code. This
gate intentionally checks only files changed relative to FORMAT_BASE, or to
origin/main/origin/master/FETCH_HEAD in CI, and HEAD^ locally.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = ("src", "tests", "backend", "mcp", "scripts", "tools", "codegen")


def git(*args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, text=True, capture_output=True, check=False
    ).stdout.strip()


def resolve_base() -> str:
    explicit = os.environ.get("FORMAT_BASE", "").strip()
    if explicit and explicit != "0000000000000000000000000000000000000000":
        return explicit
    if os.environ.get("CI"):
        for ref in ("origin/main", "origin/master", "FETCH_HEAD"):
            if git("rev-parse", "--verify", ref):
                return ref
    return "HEAD^"


def changed_python_files(base: str) -> list[str]:
    output = git("diff", "--name-only", "--diff-filter=ACMRTUXB", f"{base}...HEAD")
    if not output:
        output = git("diff", "--name-only", "--diff-filter=ACMRTUXB", base, "HEAD")
    files: list[str] = []
    for line in output.splitlines():
        path = Path(line)
        if path.suffix != ".py":
            continue
        if path.parts and path.parts[0] in SOURCE_ROOTS:
            files.append(line)
    return sorted(set(files))


def main() -> int:
    base = resolve_base()
    files = changed_python_files(base)
    print(f"format-check base: {base}")
    if not files:
        print("format-check: no changed Python files")
        return 0
    cmd = ["uvx", "ruff==0.16.5", "format", "--check", *files]
    print("format-check:", " ".join(cmd))
    return subprocess.run(cmd, cwd=ROOT, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
