"""Version comparison, skew grouping and the version-related diagnostics.

Ordering and constraint evaluation are delegated to ``packaging``, the reference
PEP 440 implementation. A hand-rolled comparator is how ``1.0+local !=1.0``,
``1.0 ==1.0.0.*`` and ``1.0.dev ==1.0`` were each mis-evaluated, so the generator
depends on ``packaging`` instead of approximating the spec.

``satisfies`` returns ``None`` -- never a silent ``False`` -- when either side is
not a valid PEP 440 version or specifier, so the caller reports
``unsupported_constraint`` rather than pretending the constraint held.
"""

from __future__ import annotations

from typing import Any

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from .facts import Facts


def satisfies(version: str, spec: str) -> bool | None:
    """Evaluate a PEP 440 specifier; ``None`` means it cannot be evaluated."""
    if not spec:
        return None
    try:
        return Version(version) in SpecifierSet(spec)
    except (InvalidVersion, InvalidSpecifier):
        return None


# ------------------------------------------------------------------ grouping


def version_groups(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for edge in edges:
        if edge["kind"] in ("ci", "data"):
            continue
        if not edge["expected"]["version"]:
            continue
        key = (edge["to"], edge["role"])
        group = groups.setdefault(key, {"upstream": edge["to"], "role": edge["role"], "repos": []})
        group["repos"].append(
            {
                "repo": edge["from"],
                "version": edge["expected"]["version"],
                "ref": edge["declared"]["ref_raw"],
                "source_file": edge["source_file"],
            }
        )
    for group in groups.values():
        group["repos"].sort(key=lambda item: item["repo"])
        versions = sorted({item["version"] for item in group["repos"]})
        group["versions"] = versions
        group["uniform"] = len(versions) == 1
    return [groups[key] for key in sorted(groups)]


def uniform_requirement(policy: dict[str, Any], upstream: str, role: str, repo: str) -> dict | None:
    """A ``require_uniform`` entry covering this repo; ``repos`` scoping is honoured."""
    for requirement in policy.get("require_uniform", []):
        if requirement.get("upstream") != upstream or requirement.get("role") != role:
            continue
        scoped = requirement.get("repos")
        if scoped and repo not in scoped:
            continue
        return requirement
    return None


def exception_for(policy: dict[str, Any], upstream: str, role: str, repo: str) -> dict | None:
    for exception in policy.get("exceptions", []):
        if exception.get("upstream") != upstream or exception.get("role") != role:
            continue
        repos = exception.get("repos")
        if repos and repo not in repos:
            continue
        return exception
    return None


def _scope(facts: Facts, group: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    required = [
        item["repo"]
        for item in group["repos"]
        if uniform_requirement(facts.policy, group["upstream"], group["role"], item["repo"])
    ]
    excepted = [
        item["repo"]
        for item in group["repos"]
        if exception_for(facts.policy, group["upstream"], group["role"], item["repo"])
    ]
    return ("required" if required else "unscoped"), required, excepted


def skew_diagnostics(facts: Facts, groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for group in groups:
        if group["uniform"]:
            continue
        scope, required, excepted = _scope(facts, group)
        group["scope"] = scope
        group["required_repos"] = required
        group["exceptions_matched"] = excepted
        diagnostics.append(
            {
                "code": "version_skew",
                "level": "warning",
                "where": f"{group['upstream']} ({group['role']})",
                "detail": "; ".join(f"{item['repo']}={item['version']}" for item in group["repos"]),
                "scope": scope,
                "exceptions_matched": excepted,
            }
        )
    return diagnostics