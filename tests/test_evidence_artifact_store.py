from __future__ import annotations

import os
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from evidence_artifact_store import store_artifact


def test_store_artifact_replaces_duplicate_paths_with_single_blob(tmp_path: Path) -> None:
    root = tmp_path
    store = root / "release-evidence" / "artifact-blobs"
    left = root / "release-evidence" / "run" / "left.pptx"
    right = root / "release-evidence" / "run" / "right.pptx"
    left.parent.mkdir(parents=True)
    left.write_bytes(b"office package bytes")
    right.write_bytes(b"office package bytes")

    left_meta = store_artifact(left, store, root)
    right_meta = store_artifact(right, store, root)

    assert left.read_bytes() == b"office package bytes"
    assert right.read_bytes() == b"office package bytes"
    assert left_meta["artifact_sha256"] == right_meta["artifact_sha256"]
    assert left_meta["artifact_blob"] == right_meta["artifact_blob"]
    assert Path(root / left_meta["artifact_blob"]).exists()
    manifest = store / "artifact-manifest.jsonl"
    records = [json.loads(line) for line in manifest.read_text(encoding="utf-8").splitlines()]
    assert [record["logical_path"] for record in records] == [
        "release-evidence/run/left.pptx",
        "release-evidence/run/right.pptx",
    ]
    if os.name == "posix":
        assert left.stat().st_ino == right.stat().st_ino
        assert left.stat().st_ino == (root / left_meta["artifact_blob"]).stat().st_ino
