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


def configure(token: str | None = None) -> str:
    """Read (or accept) the token and export it for Git and for the scrubber."""
    if token is None:
        token = sys.stdin.readline().strip()
    if not token:
        raise RuntimeError("private dependency credentials unavailable")
    encoded = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    os.environ.update(
        **{
            TOKEN_VAR: token,
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": _GIT_HEADER,
            "GIT_CONFIG_VALUE_0": "AUTHORIZATION: basic " + encoded,
        }
    )
    return token