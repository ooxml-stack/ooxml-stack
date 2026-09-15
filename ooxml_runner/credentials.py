"""Private-dependency credentials for the in-container run.

The host writes the token to the container's stdin. Reading it and turning it
into Git's HTTP authorization header used to live in the engine's gate; it is
shared here because every repository that installs pinned private dependencies
needs exactly the same handling.

The token is never printed, never written to a report, and never passed as a
command-line argument where it would show up in a process listing.
"""

from __future__ import annotations

import base64
import os
import sys

TOKEN_VAR = "OOXML_STACK_TOKEN"
_GIT_HEADER = "http.https://github.com/.extraheader"


def _existing_entries() -> list[tuple[str, str]]:
    """Collect the Git config entries the caller already exported.

    The container entrypoint injects its own entries (notably
    ``safe.directory`` for the bind-mounted runner) through the same
    ``GIT_CONFIG_*`` protocol. Appending instead of overwriting keeps those
    entries alive once credentials are configured.
    """
    try:
        count = int(os.environ.get("GIT_CONFIG_COUNT", "0") or "0")
    except ValueError:
        count = 0
    entries = []
    for index in range(max(count, 0)):
        key = os.environ.get(f"GIT_CONFIG_KEY_{index}")
        value = os.environ.get(f"GIT_CONFIG_VALUE_{index}")
        if key is not None and value is not None:
            entries.append((key, value))
    return entries


def configure(token: str | None = None) -> str:
    """Read (or accept) the token and export it for Git and for the scrubber."""
    if token is None:
        token = sys.stdin.readline().strip()
    if not token:
        raise RuntimeError("private dependency credentials unavailable")
    encoded = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    entries = [pair for pair in _existing_entries() if pair[0] != _GIT_HEADER]
    entries.append((_GIT_HEADER, "AUTHORIZATION: basic " + encoded))
    env = {
        TOKEN_VAR: token,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_COUNT": str(len(entries)),
    }
    for index, (key, value) in enumerate(entries):
        env[f"GIT_CONFIG_KEY_{index}"] = key
        env[f"GIT_CONFIG_VALUE_{index}"] = value
    os.environ.update(env)
    return token