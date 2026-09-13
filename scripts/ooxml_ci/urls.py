"""Repository URL normalization shared by the plan and the scan."""

from __future__ import annotations

import re

_SCHEME = re.compile(r"^(?:git\+)?(?:https?|ssh|git)://")
_SCP = re.compile(r"^[^@/]+@(?P<host>[^:/]+):(?P<path>.+)$")


def normalize_repo(url: str) -> str:
    """``git@github.com:ooxml-stack/x.git`` and ``https://github.com/ooxml-stack/x`` -> ``github.com/ooxml-stack/x``."""
    value = url.strip()
    match = _SCP.match(value)
    if match:
        value = f"{match.group('host')}/{match.group('path')}"
    else:
        value = _SCHEME.sub("", value)
    value = value.split("?", 1)[0].split("#", 1)[0]
    if value.endswith(".git"):
        value = value[:-4]
    return value.strip("/")


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