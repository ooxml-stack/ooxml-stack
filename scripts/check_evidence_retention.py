"""Block accidental committed Office packages in release evidence."""

from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from pathlib import Path

OFFICE_EXTENSIONS = {".docx", ".docm", ".dotx", ".pptx", ".pptm", ".potx", ".ppsx", ".xlsx", ".xlsm"}
DEFAULT_ALLOWLIST = Path("release-evidence/RETAINED-ARTIFACTS.txt")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    paths = changed_paths(root, args.base_ref)
    allowlist = read_allowlist(root / args.allowlist)
    blocked = forbidden_evidence_paths(paths, allowlist)
    if not blocked:
        return 0
    print("Refusing new Office packages under release-evidence:", file=sys.stderr)
    for path in blocked:
        print(f"  - {path}", file=sys.stderr)
    print("", file=sys.stderr)
    print("Keep pass evidence as JSON/JSONL rows with hashes.", file=sys.stderr)
    print("Only failure, release, or pinned samples may be allowlisted.", file=sys.stderr)
    return 1


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--base-ref", default=None)
    parser.add_argument("--allowlist", type=Path, default=DEFAULT_ALLOWLIST)
    return parser.parse_args(argv)


def changed_paths(root: Path, base_ref: str | None) -> list[str]:
    if base_ref and not is_null_ref(base_ref):
        output = git(root, "diff", "--name-status", "--diff-filter=AR", f"{base_ref}...HEAD")
        return [status_path(line) for line in output.splitlines() if line]
    return status_paths(root)


def status_paths(root: Path) -> list[str]:
    paths = []
    for line in git(root, "status", "--porcelain").splitlines():
        status = line[:2]
        if "A" not in status and "R" not in status and status != "??":
            continue
        paths.append(status_path(line[3:]))
    return paths


def status_path(line: str) -> str:
    if "\t" in line:
        return line.split("\t")[-1].strip()
    return line.rsplit(" -> ", 1)[-1].strip()


def read_allowlist(path: Path) -> list[str]:
    if not path.exists():
        return []
    patterns = []
    for line in path.read_text(encoding="utf-8").splitlines():
        item = line.strip()
        if item and not item.startswith("#"):
            patterns.append(item)
    return patterns


def forbidden_evidence_paths(paths: list[str], allowlist: list[str]) -> list[str]:
    blocked = []
    for path in paths:
        if is_office_evidence(path) and not is_allowlisted(path, allowlist):
            blocked.append(path)
    return sorted(blocked)


def is_office_evidence(path: str) -> bool:
    rel = Path(path)
    return path.startswith("release-evidence/") and rel.suffix.lower() in OFFICE_EXTENSIONS


def is_allowlisted(path: str, allowlist: list[str]) -> bool:
    return any(path == pattern or fnmatch.fnmatchcase(path, pattern) for pattern in allowlist)


def is_null_ref(ref: str) -> bool:
    return set(ref) == {"0"}


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout


if __name__ == "__main__":
    raise SystemExit(main())
