"""Redact local user paths from tracked release evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

USER_PREFIX = "/" + "Users/"
USER_FILE_RE = re.compile(re.escape(USER_PREFIX) + r".*?(\.(?:docx|pptx|xlsx|json|jsonl|csv|txt))")
USER_PATH_RE = re.compile(re.escape(USER_PREFIX) + r"[^ \"'\n\r\t]+")


def redact_user_paths(text: str, repo_root: Path | None = None) -> str:
    if repo_root is not None:
        root = repo_root.resolve()
        replacements = (
            (root.parent / "ooxml-native-corpus", "<native-corpus>"),
            (root, "<repo>"),
            (root.parent, "<workspace>"),
        )
        for path, label in replacements:
            text = text.replace(str(path), label)
    text = USER_FILE_RE.sub(r"<local-path>\1", text)
    return USER_PATH_RE.sub("<local-path>", text)


def tracked_evidence_files(root: Path) -> list[Path]:
    patterns = ("release-evidence/**/*.json", "release-evidence/**/*.jsonl")
    tracked = subprocess.run(
        ["git", "ls-files", *patterns],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard", *patterns],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    lines = {*tracked.stdout.splitlines(), *untracked.stdout.splitlines()}
    return [path for line in sorted(lines) if line.strip() and (path := root / line).is_file()]


def redact_files(root: Path, write: bool) -> list[Path]:
    changed = []
    for path in tracked_evidence_files(root):
        text = path.read_text(encoding="utf-8")
        redacted = redact_user_paths(text, root)
        if text == redacted:
            continue
        changed.append(path)
        if write:
            path.write_text(redacted, encoding="utf-8")
    return changed


def refresh_locks(root: Path, changed: set[Path]) -> list[Path]:
    refreshed = []
    for path in lock_files(root):
        data = json.loads(path.read_text(encoding="utf-8"))
        if refresh_node(data, root, path.parent, changed):
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            refreshed.append(path)
    return refreshed


def lock_files(root: Path) -> list[Path]:
    manifests = root.glob("release-evidence/**/manifest.json")
    profiles = root.glob("release-profiles/*.json")
    return sorted(path for path in (*manifests, *profiles) if path.is_file())


def refresh_node(node: object, root: Path, base: Path, changed: set[Path]) -> bool:
    updated = False
    if isinstance(node, dict):
        target = resolved_path(root, base, node.get("path"))
        if target in changed and "sha256" in node:
            node["sha256"] = sha256(target)
            if "size" in node:
                node["size"] = target.stat().st_size
            if "size_bytes" in node:
                node["size_bytes"] = target.stat().st_size
            updated = True
        for value in node.values():
            updated = refresh_node(value, root, base, changed) or updated
        return updated
    if isinstance(node, list):
        for value in node:
            updated = refresh_node(value, root, base, changed) or updated
        return updated
    return False


def resolved_path(root: Path, base: Path, value: object) -> Path | None:
    if not isinstance(value, str):
        return None
    for candidate in (root / value, base / value):
        path = candidate.resolve()
        if path.exists():
            return path
    return None


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--refresh-locks", action="store_true")
    parser.add_argument("--refresh-path", action="append", default=[])
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    changed = redact_files(root, args.write)
    if changed and not args.write:
        for path in changed:
            print(path.relative_to(root))
        return 1
    refresh_paths = {path for raw in args.refresh_path if (path := (root / raw).resolve()).exists()}
    changed_set = set(changed) | refresh_paths
    refreshed = refresh_locks(root, changed_set) if args.write and args.refresh_locks else []
    for path in [*changed, *refreshed]:
        print(path.relative_to(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
