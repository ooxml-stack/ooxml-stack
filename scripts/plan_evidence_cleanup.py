"""Plan cleanup of successful generated Office evidence artifacts."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

OFFICE_EXTENSIONS = {".docx", ".docm", ".dotx", ".pptx", ".pptm", ".potx", ".ppsx", ".xlsx", ".xlsm"}
GENERATED_OUTPUT_DIRS = (
    "release-evidence/former-preserve-only-semantic-editability/promotion-outputs/",
    "release-evidence/p90/p80-promotion-outputs/",
    "release-evidence/p90/p80-promotion-public-paths/",
    "release-evidence/p90/p90-public-paths/",
)
OUTPUT_KEYS = {"output_file", "cli_output_file", "mcp_output_file"}
PASS_STATUSES = {"pass", "passed", "ok", "success", "pass_with_dialog"}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = args.root.resolve()
    evidence = root / args.evidence_dir
    referenced = collect_referenced_outputs(evidence, root)
    artifacts = collect_office_artifacts(evidence, root)
    summary, candidates = plan_cleanup(artifacts, referenced)
    output = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    if args.candidate_list:
        args.candidate_list.parent.mkdir(parents=True, exist_ok=True)
        text = "\n".join(a["path"] for a in candidates)
        args.candidate_list.write_text(text + ("\n" if text else ""), encoding="utf-8")
    return 0


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--evidence-dir", default="release-evidence")
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--candidate-list", type=Path)
    return parser.parse_args(argv)


def collect_referenced_outputs(evidence: Path, root: Path) -> dict[str, list[str]]:
    refs: dict[str, list[str]] = defaultdict(list)
    for path in evidence.rglob("*"):
        if path.suffix.lower() not in {".json", ".jsonl"} or not path.is_file():
            continue
        for row in read_rows(path):
            disposition = row_disposition(row)
            for output in output_paths(row):
                refs[normalize_path(output, root)].append(disposition)
    return refs


def collect_office_artifacts(evidence: Path, root: Path) -> list[dict[str, Any]]:
    artifacts = []
    for path in evidence.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in OFFICE_EXTENSIONS:
            continue
        stat = path.stat()
        rel = str(path.relative_to(root))
        artifacts.append({"path": rel, "size": stat.st_size, "dev": stat.st_dev, "ino": stat.st_ino, "nlink": stat.st_nlink})
    return artifacts


def plan_cleanup(artifacts: list[dict[str, Any]], refs: dict[str, list[str]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    candidates = sorted(candidate_artifacts(artifacts, refs), key=lambda a: a["path"])
    kept = [a for a in artifacts if a not in candidates]
    summary = {
        "schema_version": "ooxml-evidence-cleanup-plan-v1",
        "policy": "dry-run only; remove successful generated Office outputs, keep failures/release/pinned/unknown",
        "total": artifact_summary(artifacts),
        "cleanup_candidates": artifact_summary(candidates),
        "kept_or_unknown": artifact_summary(kept),
        "candidate_dirs": dir_summary(candidates),
        "kept_dirs": dir_summary(kept),
        "sample_candidates": [a["path"] for a in candidates[:25]],
        "sample_kept": [a["path"] for a in kept[:25]],
    }
    return summary, candidates


def candidate_artifacts(artifacts: list[dict[str, Any]], refs: dict[str, list[str]]) -> list[dict[str, Any]]:
    return [a for a in artifacts if cleanup_candidate(a["path"], refs.get(a["path"], []))]


def cleanup_candidate(path: str, dispositions: list[str]) -> bool:
    if not any(path.startswith(prefix) for prefix in GENERATED_OUTPUT_DIRS):
        return False
    return bool(dispositions) and all(item == "pass" for item in dispositions)


def artifact_summary(artifacts: list[dict[str, Any]]) -> dict[str, Any]:
    by_inode: dict[tuple[int, int], dict[str, Any]] = {}
    candidate_links: Counter[tuple[int, int]] = Counter()
    logical_bytes = 0
    for artifact in artifacts:
        key = (int(artifact["dev"]), int(artifact["ino"]))
        by_inode[key] = artifact
        candidate_links[key] += 1
        logical_bytes += int(artifact["size"])
    unique_bytes = sum(int(item["size"]) for item in by_inode.values())
    releasable = releasable_bytes(by_inode, candidate_links)
    return {
        "file_count": len(artifacts),
        "logical_bytes": logical_bytes,
        "unique_inode_bytes": unique_bytes,
        "estimated_releasable_bytes": releasable,
    }


def releasable_bytes(by_inode: dict[tuple[int, int], dict[str, Any]], links: Counter[tuple[int, int]]) -> int:
    total = 0
    for key, artifact in by_inode.items():
        if int(artifact["nlink"]) <= links[key]:
            total += int(artifact["size"])
    return total


def dir_summary(artifacts: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for artifact in artifacts:
        groups[bucket(artifact["path"])].append(artifact)
    return {name: artifact_summary(items) for name, items in sorted(groups.items())}


def bucket(path: str) -> str:
    parts = path.split("/")
    if path.startswith("release-evidence/former-preserve-only-semantic-editability/"):
        return "/".join(parts[:3])
    if path.startswith("release-evidence/p90/") and len(parts) >= 3:
        return "/".join(parts[:3])
    return "/".join(parts[:2])


def read_rows(path: Path) -> list[Any]:
    if path.suffix.lower() == ".jsonl":
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else [data]


def output_paths(value: Any) -> list[str]:
    paths = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in OUTPUT_KEYS and isinstance(item, str) and Path(item).suffix.lower() in OFFICE_EXTENSIONS:
                paths.append(item)
            paths.extend(output_paths(item))
    elif isinstance(value, list):
        for item in value:
            paths.extend(output_paths(item))
    return paths


def row_disposition(row: Any) -> str:
    values = list(status_values(row))
    if any(value is False or failure_status(value) for value in values):
        return "fail"
    if values and all(value is True or pass_status(value) for value in values):
        return "pass"
    return "unknown"


def status_values(value: Any) -> list[Any]:
    values = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"pass", "native_office_result", "status"}:
                values.append(item)
            values.extend(status_values(item))
    elif isinstance(value, list):
        for item in value:
            values.extend(status_values(item))
    return values


def pass_status(value: Any) -> bool:
    return isinstance(value, str) and value.lower() in PASS_STATUSES


def failure_status(value: Any) -> bool:
    return isinstance(value, str) and value.lower() in {"fail", "failed", "failure", "error", "repair_dialog"}


def normalize_path(path: str, root: Path) -> str:
    if path.startswith("ooxml-stack/"):
        return path.removeprefix("ooxml-stack/")
    if path.startswith("release-evidence/"):
        return path
    try:
        source = Path(path)
        if not source.is_absolute():
            source = root / source
        return str(source.resolve().relative_to(root))
    except (OSError, ValueError):
        return path


if __name__ == "__main__":
    raise SystemExit(main())
