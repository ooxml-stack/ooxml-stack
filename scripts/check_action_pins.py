#!/usr/bin/env python3
"""Fail when a workflow pins an action to a mutable ref instead of a commit SHA.

A tag such as ``actions/checkout@v6`` is a moving pointer: whoever controls the
action's repository can repoint it at new code that then runs with this
repository's token. Every external action and reusable workflow must therefore
be pinned to a full 40-character commit SHA, with the human-readable tag kept in
a trailing comment. Local reusable workflows (``./...``) and expressions are
exempt.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
USE = re.compile(r"uses:\s*[\"']?([^\s\"'#]+)")
SHA = re.compile(r"@[0-9a-f]{40}$")
EXEMPT_PREFIXES = ("./", "${{", "docker://")


def main() -> int:
    problems: list[str] = []
    checked = 0
    files = sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))
    for path in files:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            match = USE.search(line)
            if match is None:
                continue
            ref = match.group(1)
            if ref.startswith(EXEMPT_PREFIXES):
                continue
            checked += 1
            if not SHA.search(ref):
                problems.append(f"{path.relative_to(ROOT)}:{lineno}: {ref}")
    print(f"workflow files: {len(files)}; pinned action references: {checked}")
    if problems:
        for problem in problems:
            print(f"unpinned action: {problem}", file=sys.stderr)
        print(
            "pin every action and reusable workflow to a full commit SHA and keep "
            "the tag in a trailing comment",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
