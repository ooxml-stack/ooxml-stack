"""Repository URL normalization shared by the plan and the scan."""

from __future__ import annotations

import re

_SCHEME = re.compile(r"^(?:git\+)?(?:https?|ssh|git)://", re.IGNORECASE)
_SCP = re.compile(r"^[^@/]+@(?P<host>[^:/]+):(?P<path>.+)$")
# The scheme forms a ``git clone`` argument may take. ``git+https://`` is a
# packaging VCS prefix, not a git transport, so it is deliberately absent.
_REMOTE_SCHEME = re.compile(r"^(?:https?|ssh|git)://\S+$", re.IGNORECASE)


def is_remote_repo(url: str) -> bool:
    """Whether ``url`` names a remote repository the inventory can model.

    The scp branch reuses ``_SCP``, the same rule ``normalize_repo`` extracts
    with, so the clone gate and the normalizer cannot drift apart: every form
    the normalizer understands is a form the gate lets through. A local path
    (``../local``) or a non-remote URL (``file://``) is not remote.
    """
    return bool(_REMOTE_SCHEME.match(url) or _SCP.match(url))


def _drop_userinfo(value: str) -> str:
    """``git@github.com/ooxml-stack/x`` -> ``github.com/ooxml-stack/x``.

    The same repository must compare equal whether it was written as
    ``https://github.com/…``, ``ssh://git@github.com/…`` or ``git@github.com:…``.
    """
    head, sep, tail = value.partition("/")
    return head.rsplit("@", 1)[-1] + sep + tail if "@" in head else value


def normalize_repo(url: str) -> str:
    """``git@github.com:ooxml-stack/x.git`` and ``https://github.com/ooxml-stack/x`` -> ``github.com/ooxml-stack/x``."""
    value = url.strip()
    match = _SCP.match(value)
    if match:
        value = f"{match.group('host')}/{match.group('path')}"
    else:
        value = _drop_userinfo(_SCHEME.sub("", value))
    value = value.split("?", 1)[0].split("#", 1)[0].strip("/")
    if value.endswith(".git"):
        value = value[:-4]
    return value


def repo_name(url: str) -> str | None:
    slug = normalize_repo(url)
    return slug.rsplit("/", 1)[-1] if "/" in slug else None


def repo_from_uses(uses: str) -> str | None:
    """``owner/repo/.github/workflows/x.yml`` -> ``repo``."""
    parts = uses.split("/")
    return parts[1] if len(parts) >= 2 and parts[1] else None


def owner_from_uses(uses: str) -> str | None:
    """``owner/repo/.github/workflows/x.yml`` -> ``owner``."""
    parts = uses.split("/")
    return parts[0] if len(parts) >= 2 and parts[0] else None


def url_from_uses(uses: str) -> str | None:
    """``owner/repo/...@ref`` -> ``https://github.com/owner/repo`` (the declared URL)."""
    owner, repo = owner_from_uses(uses), repo_from_uses(uses)
    if not owner or not repo:
        return None
    return f"https://github.com/{owner}/{repo}"


def owner_of(url: str) -> str | None:
    """``https://github.com/ooxml-stack/x.git`` -> ``ooxml-stack``."""
    slug = normalize_repo(url)
    parts = slug.split("/")
    return parts[-2] if len(parts) >= 2 else None