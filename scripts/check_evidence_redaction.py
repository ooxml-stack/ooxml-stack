#!/usr/bin/env python3
"""Keep credentials out of committed evidence.

Policy: `docs/EVIDENCE-REDACTION.md`. Two checks run over committed evidence
directories:

* **Hard failure** on high-confidence credential patterns (GitHub tokens,
  private-key blocks, base64 basic-auth headers, AWS access key ids). These must
  never be committed, and a match means the value has to be rotated as well as
  removed.
* **Reported** absolute home-path counts (a home directory prefix followed by a
  user name). They leak a local username and make evidence non-portable; they
  are reported so the count goes down deliberately rather than blocking every
  change.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIRS = ("reports", "artifacts", "evidence", "ci/reports", "docs")
TEXT_SUFFIXES = {".md", ".json", ".txt", ".log", ".yml", ".yaml", ".csv", ".sarif"}

SECRETS = {
    "github token": re.compile(
        r"\b(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})"
    ),
    "private key block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "basic auth header": re.compile(r"x-access-token:[A-Za-z0-9+/=]{20,}"),
    "aws access key id": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
}
# Built from parts so this file does not itself contain a machine-specific path
# literal; the same rule it enforces applies to the gate's own source.
_HOME_ROOTS = ("/" + "Users/", "/" + "home/")
HOME_PATHS = re.compile("(" + "|".join(_HOME_ROOTS) + r")[A-Za-z0-9._-]+/")


def evidence_files() -> list[Path]:
    files: list[Path] = []
    for name in EVIDENCE_DIRS:
        base = ROOT / name
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if (
                path.is_file()
                and path.suffix in TEXT_SUFFIXES
                and ".venv" not in path.parts
            ):
                files.append(path)
    return files


def main() -> int:
    files = evidence_files()
    secrets: list[str] = []
    path_hits = 0
    path_files = 0
    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = path.relative_to(ROOT)
        for label, pattern in SECRETS.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                secrets.append(f"{rel}:{line}: {label}")
        count = len(HOME_PATHS.findall(text))
        if count:
            path_files += 1
            path_hits += count

    print(f"evidence files scanned: {len(files)}")
    print(
        f"absolute home paths: {path_hits} occurrences in {path_files} files (reported, not blocking)"
    )
    if secrets:
        for finding in secrets:
            print(f"credential pattern committed: {finding}", file=sys.stderr)
        print(
            "remove the value, rotate it, and keep only a placeholder such as "
            "${OOXML_STACK_TOKEN}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
