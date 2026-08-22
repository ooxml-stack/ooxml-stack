from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from evidence_artifact_store import store_artifact


OFFICE_EXTENSIONS = {".docx", ".docm", ".dotx", ".pptx", ".pptm", ".potx", ".ppsx", ".xlsx", ".xlsm"}


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    root = args.root.resolve()
    evidence = root / args.evidence_dir
    records = collect_artifacts(evidence, root, args.include_blobs, args.hash_content)
    summary = summarize(records)
    if args.apply_hardlinks:
        summary["applied"] = apply_hardlinks(records, root, root / args.store_dir)
    output = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--evidence-dir", default="release-evidence")
    parser.add_argument("--store-dir", default="release-evidence/artifact-blobs")
    parser.add_argument("--include-blobs", action="store_true")
    parser.add_argument("--hash-content", action="store_true")
    parser.add_argument("--apply-hardlinks", action="store_true")
    parser.add_argument("-o", "--output", type=Path)
    return parser.parse_args(argv)


def collect_artifacts(evidence: Path, root: Path, include_blobs: bool = False, hash_content: bool = False) -> list[dict[str, Any]]:
    records = []
    hashes: dict[tuple[int, int], str] = {}
    if not evidence.exists():
        return records
    for path in evidence.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in OFFICE_EXTENSIONS:
            continue
        if not include_blobs and "artifact-blobs" in path.parts:
            continue
        stat = path.stat()
        record = {"path": str(path.relative_to(root)), "size": stat.st_size, "dev": stat.st_dev, "ino": stat.st_ino}
        if hash_content:
            key = (stat.st_dev, stat.st_ino)
            if key not in hashes:
                hashes[key] = _sha256(path)
            record["sha256"] = hashes[key]
        records.append(record)
    return records


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    by_inode: dict[tuple[int, int], int] = {}
    suffix_counts: dict[str, int] = defaultdict(int)
    logical_bytes = 0
    for record in records:
        logical_bytes += int(record["size"])
        by_inode[(int(record["dev"]), int(record["ino"]))] = int(record["size"])
        suffix_counts[Path(str(record["path"])).suffix.lower()] += 1
    physical_bytes = sum(by_inode.values())
    return {
        "schema_version": "ooxml-evidence-artifact-audit-v1",
        "file_count": len(records),
        "logical_bytes": logical_bytes,
        "hardlink_physical_bytes": physical_bytes,
        "hardlink_saved_bytes": max(logical_bytes - physical_bytes, 0),
        **_content_summary(records),
        "by_extension": dict(sorted(suffix_counts.items())),
    }


def apply_hardlinks(records: list[dict[str, Any]], root: Path, store_dir: Path) -> dict[str, Any]:
    applied = []
    for record in records:
        path = root / str(record["path"])
        applied.append(store_artifact(path, store_dir, root))
    return {"stored_count": len(applied), "manifest": str((store_dir / "artifact-manifest.jsonl").relative_to(root))}


def _content_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records or "sha256" not in records[0]:
        return {"content_hashes_computed": False}
    by_sha: dict[str, int] = {}
    for record in records:
        by_sha.setdefault(str(record["sha256"]), int(record["size"]))
    unique_bytes = sum(by_sha.values())
    logical_bytes = sum(int(record["size"]) for record in records)
    return {
        "content_hashes_computed": True,
        "content_unique_count": len(by_sha),
        "content_unique_bytes": unique_bytes,
        "content_duplicate_bytes": max(logical_bytes - unique_bytes, 0),
    }


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
