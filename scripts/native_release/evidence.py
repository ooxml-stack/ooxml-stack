"""Write and seal native release evidence files."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class EvidenceSeal:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def write(self, name: str, payload: Any) -> Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return path

    def finalize(self, result: dict[str, Any]) -> dict[str, Any]:
        self.write("release-evidence.json", result)
        rows = []
        for path in sorted(self.root.rglob("*")):
            if path.is_file() and path.name != "seal.json":
                data = path.read_bytes()
                rows.append(
                    {
                        "path": path.relative_to(self.root).as_posix(),
                        "size": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )
        seal = {"schema_version": 1, "files": rows}
        self.write("seal.json", seal)
        return {"root": str(self.root), "files": rows}
