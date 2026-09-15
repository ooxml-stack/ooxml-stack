"""Generic subprocess execution with live logs, timeouts and secret scrubbing.

Moved out of the engine so there is exactly one implementation of "run a gate
command": the same streaming scrubber, the same bounded termination, the same
partial-log preservation and the same abort marker for every repository.

Nothing here builds a shell string. Arguments are passed as a list, so a path
containing spaces or shell metacharacters is delivered verbatim and is never
interpreted.
"""

from __future__ import annotations

import base64
import os
import selectors
import signal
import subprocess
import time
from pathlib import Path

ABORT_MARKER = "CI_COMMAND_ABORTED"
_READ_CHUNK = 65536
_KILL_GRACE_SECONDS = 10


class CommandError(RuntimeError):
    """A gate command exited nonzero or did not finish."""

    def __init__(self, message: str, *, exit_code: int | None, log_path: str | None):
        super().__init__(message)
        self.exit_code = exit_code
        self.log_path = log_path


def scrub(text: str) -> str:
    """Replace every complete secret occurrence in a finished string."""
    token = os.environ.get("OOXML_STACK_TOKEN", "")
    if not token:
        return text
    encoded = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    return text.replace(token, "***").replace(encoded, "***")


def stream_scrubber():
    """Stateful scrubber for chunked output; secrets may straddle chunks.

    After replacing complete secrets, the last ``max_secret_len - 1`` characters
    are withheld: any still-incomplete secret can only live there. Each call
    emits the safe prefix; ``flush`` drains the carry at EOF or abort.
    """
    token = os.environ.get("OOXML_STACK_TOKEN", "")
    secrets = [token, base64.b64encode(f"x-access-token:{token}".encode()).decode()] if token else []
    max_len = max((len(secret) for secret in secrets), default=0)
    carry = ""

    def feed(chunk: str) -> str:
        nonlocal carry
        carry += chunk
        for secret in secrets:
            carry = carry.replace(secret, "***")
        if len(carry) <= max_len - 1:
            return ""
        cut = len(carry) - (max_len - 1)
        safe, carry = carry[:cut], carry[cut:]
        return safe

    def flush() -> str:
        nonlocal carry
        safe, carry = carry, ""
        return safe

    return feed, flush


def _append(log, text: str) -> None:
    if text:
        log.write(text.encode())
        log.flush()


def _read_until_exit(process, log, deadline, pieces, feed) -> None:
    """Stream merged output into the log as it arrives, never an unsafe chunk."""
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(process.args, deadline)
        if not selector.select(min(remaining, 1.0)):
            continue
        chunk = os.read(process.stdout.fileno(), _READ_CHUNK)
        if not chunk:
            return
        pieces.append(chunk)
        safe = feed(chunk.decode("utf-8", errors="replace"))
        if safe:
            log.write(safe.encode())
            log.flush()


def _kill_and_drain(process) -> bytes:
    """Kill the whole process group, then drain whatever it already wrote."""
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        return process.communicate(timeout=_KILL_GRACE_SECONDS)[0] or b""
    except Exception:  # noqa: BLE001 - an aborted process is best-effort drained
        return b""


def run_command(args, name: str, cwd, reports, timeout: float = 5400, env=None) -> str:
    """Run one gate command, writing its log live. Returns the scrubbed output.

    On timeout or interruption the process group is killed, the remaining output
    is drained through the same scrubber, and an explicit abort marker is
    appended. The partial log is preserved, never overwritten.
    """
    path = Path(reports) / f"{name}.log"
    Path(reports).mkdir(parents=True, exist_ok=True)
    print(f"[{name}] {' '.join(map(str, args))}", flush=True)
    process = subprocess.Popen(
        list(map(str, args)), cwd=cwd, env=env, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, start_new_session=True,
    )
    pieces: list[bytes] = []
    feed, flush = stream_scrubber()
    try:
        with path.open("wb") as log:
            _read_until_exit(process, log, time.monotonic() + timeout, pieces, feed)
            process.wait(timeout=_KILL_GRACE_SECONDS)
            _append(log, flush())
    except BaseException as exc:
        tail = _kill_and_drain(process)
        with path.open("ab") as log:
            _append(log, feed(tail.decode("utf-8", errors="replace")) + flush())
            _append(log, f"{ABORT_MARKER} name={name} reason={type(exc).__name__}\n")
        if isinstance(exc, subprocess.TimeoutExpired):
            # Preserve the historical contract: callers already handle
            # ``TimeoutExpired`` as a distinct, retryable failure.
            raise
        raise
    output = scrub(b"".join(pieces).decode("utf-8", errors="replace"))
    if process.returncode:
        print("\n".join(output.splitlines()[-45:]), flush=True)
        raise CommandError(
            f"{name} failed with exit {process.returncode}; see {path.name}",
            exit_code=process.returncode, log_path=str(path),
        )
    return output