"""Parsers for the files a plan is derived from.

Every function takes bytes, never a path: the plan must be a function of the
selected input bytes, so nothing here may re-read the working tree.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass
from typing import Any

GIT_SPEC = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9._-]+)\s*@\s*(?:git\+(?P<url>\S+?))"
    r"(?:@(?P<ref>[^;\s]+))?\s*(?:;.*)?$"
)
PLAIN_SPEC = re.compile(
    r"^\s*(?P<name>[A-Za-z0-9._-]+)(?:\[(?P<extras>[^\]]*)\])?(?P<spec>[^\s;].*?)?\s*(?:;.*)?$"
)
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
LOCK_GIT = re.compile(r"(?P<url>[^?#]+)(?:\?(?P<query>[^#]*))?(?:#(?P<fragment>[0-9a-f]{40}))?$")
DYNAMIC_ATTR = re.compile(r"^\s*version\s*=\s*\{\s*attr\s*=\s*[\"'](?P<attr>[^\"']+)[\"']")


@dataclass(frozen=True)
class Declaration:
    """One dependency declaration site in a pyproject."""

    repo: str
    section: str
    kind: str
    name: str
    url: str | None
    ref_raw: str | None
    ref_declared_kind: str
    version_spec: str
    group: str | None = None


def classify_declared_ref(raw: str | None) -> str:
    """Syntax-level classification only; the authoritative kind needs a scan."""
    if not raw:
        return "none"
    return "sha" if SHA_RE.match(raw) else "unknown"


def split_git_spec(spec: str) -> tuple[str, str | None, str | None]:
    """``name @ git+https://host/repo.git@ref ; marker`` -> (name, url, ref)."""
    match = GIT_SPEC.match(spec)
    if not match:
        return spec.strip(), None, None
    return match.group("name"), match.group("url"), match.group("ref")


def _declaration(repo: str, section: str, kind: str, spec: str, group: str | None) -> Declaration:
    name, url, ref = split_git_spec(spec)
    version_spec = ""
    if url is None:
        plain = PLAIN_SPEC.match(spec)
        if plain:
            name = plain.group("name")
            version_spec = (plain.group("spec") or "").strip()
    return Declaration(
        repo=repo,
        section=section,
        kind=kind,
        name=name,
        url=url,
        ref_raw=ref,
        ref_declared_kind=classify_declared_ref(ref),
        version_spec=version_spec,
        group=group,
    )


def parse_pyproject(data: bytes, repo: str) -> list[Declaration]:
    document = tomllib.loads(data.decode("utf-8"))
    project = document.get("project", {})
    out: list[Declaration] = []
    for spec in project.get("dependencies", []) or []:
        out.append(_declaration(repo, "project.dependencies", "runtime", spec, None))
    for extra, specs in (project.get("optional-dependencies") or {}).items():
        kind = "codegen" if extra == "codegen" else "dev"
        for spec in specs or []:
            out.append(_declaration(repo, "project.optional-dependencies", kind, spec, extra))
    for group, specs in (document.get("dependency-groups") or {}).items():
        for spec in specs or []:
            if isinstance(spec, str):
                out.append(_declaration(repo, "dependency-groups", "dev", spec, group))
    return out


def dynamic_version_attr(data: bytes) -> str | None:
    """The ``attr = "pkg.__version__"`` target of a dynamic project version."""
    document = tomllib.loads(data.decode("utf-8"))
    dynamic = (document.get("tool", {}).get("setuptools", {}).get("dynamic", {}) or {}).get("version")
    if isinstance(dynamic, dict) and isinstance(dynamic.get("attr"), str):
        return dynamic["attr"]
    for line in data.decode("utf-8").splitlines():
        match = DYNAMIC_ATTR.match(line)
        if match:
            return match.group("attr")
    return None


def dynamic_version_path(attr_ref: str) -> str | None:
    """``pkg.__version__`` -> ``src/pkg/__init__.py`` (the only layout in use)."""
    parts = attr_ref.split(".")
    if len(parts) < 2:
        return None
    return "/".join(["src", *parts[:-1], "__init__.py"])


def parse_project_version(
    pyproject: bytes | None, repo: str, version_blob: bytes | None
) -> tuple[str | None, str | None]:
    """Project version, following setuptools' ``dynamic = {attr = ...}`` form."""
    if pyproject is None:
        return None, None
    document = tomllib.loads(pyproject.decode("utf-8"))
    version = (document.get("project", {}) or {}).get("version")
    if isinstance(version, str) and version:
        return version, "pyproject.toml#project.version"
    attr = dynamic_version_attr(pyproject)
    if not attr or version_blob is None:
        return None, None
    leaf = attr.split(".")[-1]
    pattern = re.compile(rf"^\s*{re.escape(leaf)}\s*=\s*[\"']([^\"']+)[\"']")
    for line in version_blob.decode("utf-8").splitlines():
        match = pattern.match(line)
        if match:
            relpath = dynamic_version_path(attr)
            return match.group(1), f"{relpath}#{leaf}"
    return None, None


def parse_uv_sources(data: bytes) -> dict[str, dict[str, Any]]:
    """``[tool.uv.sources]`` entries keyed by distribution name."""
    document = tomllib.loads(data.decode("utf-8"))
    sources = (document.get("tool", {}).get("uv", {}) or {}).get("sources", {}) or {}
    out: dict[str, dict[str, Any]] = {}
    for name, value in sources.items():
        if isinstance(value, dict) and value.get("git"):
            out[name] = dict(value)
        elif isinstance(value, list):
            for entry in value:
                if isinstance(entry, dict) and entry.get("git"):
                    out[name] = dict(entry)
    return out


def split_lock_git(raw: str) -> tuple[str, str | None, str | None]:
    match = LOCK_GIT.match(raw)
    if not match:
        return raw, None, None
    ref = None
    for part in (match.group("query") or "").split("&"):
        if part.startswith(("tag=", "rev=", "branch=")):
            ref = part.split("=", 1)[1]
    return match.group("url"), ref, match.group("fragment")


def parse_uv_lock(data: bytes) -> dict[str, dict[str, Any]]:
    """Git packages recorded in uv.lock: expected version, ref and commit."""
    document = tomllib.loads(data.decode("utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for package in document.get("package", []) or []:
        git = (package.get("source") or {}).get("git")
        if not git:
            continue
        url, ref, commit = split_lock_git(git)
        out[package["name"]] = {
            "version": package.get("version"),
            "url": url,
            "ref": ref,
            "expected_commit": commit,
            "raw": git,
        }
    return out


def parse_environment_json(data: bytes) -> dict[str, Any]:
    return json.loads(data.decode("utf-8"))