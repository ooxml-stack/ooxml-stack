"""Resolve release candidates without implicit artifact selection."""

from __future__ import annotations

from pathlib import Path


class CandidateError(ValueError):
    """The candidate selection is ambiguous or missing."""


def resolve_candidate(
    value: str | None, artifact_root: str | Path, allow_latest_dev: bool
) -> Path:
    if not value:
        raise CandidateError("CANDIDATE is required; pass an explicit artifact path")
    root = Path(artifact_root).expanduser().resolve()
    if value == "latest-dev":
        if not allow_latest_dev:
            raise CandidateError("latest-dev is not allowed in production or CI")
        pointer = root / "native" / "latest-dev.json"
        if not pointer.is_file():
            raise CandidateError(f"latest-dev pointer does not exist: {pointer}")
        import json

        payload = json.loads(pointer.read_text(encoding="utf-8"))
        value = payload.get("candidate", "")
        if not value:
            raise CandidateError("latest-dev pointer is invalid")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise CandidateError("candidate path must be absolute")
    if not path.is_file():
        raise CandidateError(f"candidate does not exist: {path}")
    return path


def write_latest_dev(artifact_root: str | Path, candidate: str | Path) -> Path:
    import json

    root = Path(artifact_root).expanduser().resolve()
    path = root / "native" / "latest-dev.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"candidate": str(Path(candidate).resolve())}, indent=2) + "\n",
        encoding="utf-8",
    )
    return path
