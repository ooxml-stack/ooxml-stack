"""Stage tracking for chunk replay hard timeouts."""
from __future__ import annotations


class ChunkTimeout(BaseException):
    """Hard timeout that is not swallowed by broad replay exception handlers."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(f"chunk replay timeout during {stage}")


def new_stage() -> dict[str, str]:
    return {"value": "setup"}


def set_stage(stage: dict[str, str], value: str) -> None:
    stage["value"] = value


def stage_value(stage: dict[str, str]) -> str:
    return stage["value"]


def timeout_handler(stage: dict[str, str]):
    def handler(signum, frame) -> None:
        raise ChunkTimeout(stage["value"])
    return handler
