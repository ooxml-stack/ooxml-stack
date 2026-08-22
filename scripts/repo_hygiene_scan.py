"""Shared scanners for repository hygiene audits."""

from __future__ import annotations

import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

USER_TOKEN = "/" + "Users/"
USER_BYTES = USER_TOKEN.encode()
LARGE_BLOB_BYTES = 10 * 1024 * 1024
SECRET_KEYS = r"(api[_-]?key|secret|token|password|passwd|webhook(?:_url)?|bearer)"
SECRET_ASSIGN_RE = re.compile(rf"(?i)\b{SECRET_KEYS}\b\s*[:=]\s*[\"']?([^\s\"']{{8,}})")
BEARER_RE = re.compile(r"(?i)\bbearer\s+([A-Za-z0-9._~+/=-]{16,})")
WEBHOOK_RE = re.compile(r"https://[^\s\"']*/(?:webhook|hooks|services)/[^\s\"']+", re.I)
PRIVATE_KEY_RE = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")


def git(root: Path, *args: str, input_text: str | None = None, check: bool = True) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        input=input_text,
        check=check,
        capture_output=True,
        text=True,
    )
    return result.stdout


def object_rows(root: Path) -> list[dict[str, Any]]:
    objects = git(root, "rev-list", "--objects", "--all").splitlines()
    query = "\n".join(line.split(" ", 1)[0] for line in objects) + "\n"
    sizes = git(root, "cat-file", "--batch-check=%(objectname) %(objecttype) %(objectsize)", input_text=query)
    paths = paths_by_oid(objects)
    rows = []
    for line in sizes.splitlines():
        oid, object_type, size = line.split()
        if object_type == "blob":
            rows.append({"oid": oid, "size": int(size), "paths": sorted(paths.get(oid, []))})
    return rows


def paths_by_oid(lines: list[str]) -> dict[str, set[str]]:
    paths: dict[str, set[str]] = defaultdict(set)
    for line in lines:
        oid, _, path = line.partition(" ")
        if path:
            paths[oid].add(path)
    return paths


def lfs_paths(root: Path) -> set[str]:
    return set(git(root, "lfs", "ls-files", "-n", check=False).splitlines())


def current_worktree_hits(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "grep", "-I", "-n", "--fixed-strings", USER_TOKEN, "--", "."],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr)
    return result.stdout.splitlines()


def raw_release_evidence_hits(root: Path) -> list[str]:
    files = git(root, "ls-files", "release-evidence/**/*.json", "release-evidence/**/*.jsonl")
    hits = []
    for rel in files.splitlines():
        path = root / rel
        if not path.is_file():
            continue
        if USER_TOKEN in path.read_text(encoding="utf-8", errors="ignore"):
            hits.append(rel)
    return hits


def index_large_blobs(root: Path) -> list[dict[str, Any]]:
    lfs = lfs_paths(root)
    rows = []
    for line in git(root, "ls-files", "-s").splitlines():
        parts = line.split(maxsplit=3)
        if len(parts) != 4 or parts[3] in lfs:
            continue
        size = int(git(root, "cat-file", "-s", parts[1]).strip())
        if size > LARGE_BLOB_BYTES:
            rows.append({"path": parts[3], "oid": parts[1], "size": size})
    return rows


def git_lfs_clean(root: Path) -> bool:
    return git(root, "lfs", "status", "--porcelain", check=False).strip() == ""


def blob_bytes(root: Path, oid: str) -> bytes:
    return subprocess.run(
        ["git", "cat-file", "blob", oid],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout


def history_content_hits(
    root: Path,
    rows: list[dict[str, Any]],
    max_scan_bytes: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    path_hits: list[dict[str, Any]] = []
    secret_hits: list[dict[str, Any]] = []
    scanned = 0
    for row in rows:
        if row["size"] > max_scan_bytes:
            continue
        scanned += 1
        data = blob_bytes(root, row["oid"])
        if USER_BYTES in data:
            path_hits.append(hit_row(root, row, "local_user_path", data))
        if looks_text(data):
            matches = secret_matches(data.decode("utf-8", errors="ignore"), row["paths"])
            if matches:
                secret_hits.append(hit_row(root, row, "secret_like", data, matches))
    return path_hits, secret_hits, scanned


def hit_row(
    root: Path,
    row: dict[str, Any],
    kind: str,
    data: bytes,
    matches: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    hit = {
        "kind": kind,
        "oid": row["oid"],
        "size": row["size"],
        "paths": row["paths"][:8],
        "redacted_preview": redacted_preview(data),
        "introducing_commit": introducing_commit(root, row["oid"]),
    }
    if matches:
        hit["matches"] = matches[:5]
    return hit


def looks_text(data: bytes) -> bool:
    return b"\x00" not in data[:4096]


def secret_matches(text: str, paths: list[str]) -> list[dict[str, str]]:
    matches = env_path_matches(paths)
    for line in text.splitlines():
        clipped = line[:500]
        if PRIVATE_KEY_RE.search(clipped):
            matches.append({"type": "private_key_marker", "preview": "private key marker redacted"})
        for regex, kind in secret_regexes():
            if regex.search(clipped):
                matches.append({"type": kind, "preview": redact_secret(clipped)})
        if len(matches) >= 5:
            break
    return matches


def secret_regexes() -> tuple[tuple[re.Pattern[str], str], ...]:
    return (
        (SECRET_ASSIGN_RE, "secret_assignment"),
        (BEARER_RE, "bearer_token"),
        (WEBHOOK_RE, "webhook_url"),
    )


def env_path_matches(paths: list[str]) -> list[dict[str, str]]:
    return [{"type": "env_path", "preview": path} for path in paths[:5] if Path(path).name.startswith(".env")]


def redact_secret(line: str) -> str:
    line = SECRET_ASSIGN_RE.sub(lambda m: m.group(0).split(m.group(2))[0] + "<redacted>", line)
    line = BEARER_RE.sub("Bearer <redacted>", line)
    line = WEBHOOK_RE.sub("https://<redacted-webhook>", line)
    return redact_local_paths(line)


def redacted_preview(data: bytes) -> str:
    text = data.decode("utf-8", errors="ignore")
    for line in text.splitlines():
        if USER_TOKEN in line or any(token in line.lower() for token in ("token", "secret", "password", "webhook")):
            return redact_secret(line[:500])
    return ""


def redact_local_paths(text: str) -> str:
    return re.sub(re.escape(USER_TOKEN) + r"[^ \"'\n\r\t]+", "<local-path>", text)


def introducing_commit(root: Path, oid: str) -> dict[str, str] | None:
    lines = git(root, "log", "--all", f"--find-object={oid}", "--format=%H%x09%s", "--reverse", check=False)
    if not lines:
        return None
    commit, _, subject = lines.splitlines()[0].partition("\t")
    return {"commit": commit, "subject": subject}


def large_blob_summary(root: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    large = [row for row in rows if row["size"] > LARGE_BLOB_BYTES]
    top = sorted(large, key=lambda row: row["size"], reverse=True)[:50]
    return {
        "count_gt_10mb": len(large),
        "count_gt_50mb": sum(1 for row in rows if row["size"] > 50 * 1024 * 1024),
        "count_gt_100mb": sum(1 for row in rows if row["size"] > 100 * 1024 * 1024),
        "top_50": [large_row(root, row) for row in top],
    }


def large_row(root: Path, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "oid": row["oid"],
        "size": row["size"],
        "size_mb": round(row["size"] / 1024 / 1024, 2),
        "category": classify_paths(row["paths"]),
        "paths": row["paths"][:8],
        "introducing_commit": introducing_commit(root, row["oid"]),
    }


def classify_paths(paths: list[str]) -> str:
    text = " ".join(paths).lower()
    if "release-evidence" in text:
        if ".jsonl" in text:
            return "jsonl_ledger_evidence"
        if any(ext in text for ext in (".pptx", ".docx", ".xlsx")):
            return "office_package_evidence"
        if ".json" in text:
            return "json_evidence"
        return "release_evidence"
    if "__pycache__" in text or ".pytest_cache" in text:
        return "generated_cache"
    if any(ext in text for ext in (".pptx", ".docx", ".xlsx")):
        return "office_package"
    return "unknown"


def lfs_policy(root: Path) -> dict[str, Any]:
    attrs = (root / ".gitattributes").read_text(encoding="utf-8") if (root / ".gitattributes").exists() else ""
    lfs = lfs_paths(root)
    required = lfs_required_patterns()
    should_lfs = []
    for p in git(root, "ls-files", "release-evidence").splitlines():
        path = root / p
        if path.is_file() and path.stat().st_size and Path(p).suffix in {".jsonl", ".pptx", ".docx", ".xlsx"}:
            should_lfs.append(p)
    return {
        "required_patterns_present": {pattern: pattern in attrs and "filter=lfs" in attrs for pattern in required},
        "current_files_should_be_lfs_but_are_not": [p for p in should_lfs if p not in lfs][:100],
        "lfs_status_clean": git_lfs_clean(root),
    }


def lfs_required_patterns() -> tuple[str, ...]:
    return (
        "release-evidence/**/*.jsonl",
        "release-evidence/**/*.pptx",
        "release-evidence/**/*.docx",
        "release-evidence/**/*.xlsx",
    )
