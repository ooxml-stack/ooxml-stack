"""Helpers for resolving object selectors against XML parts."""

from __future__ import annotations

import hashlib
from typing import Any

from lxml import etree


def select_one(matches: list[Any], row: dict[str, Any]) -> list[Any]:
    if len(matches) <= 1:
        return matches
    digest = row.get("before_canonical_xml_digest") or row.get("before_digest")
    if not digest:
        return matches
    filtered = [item for item in matches if isinstance(item, etree._Element) and safe_digest(item) == digest]
    return filtered if len(filtered) == 1 else matches


def canonical_digest(element: etree._Element) -> str:
    data = etree.tostring(element, method="c14n")
    return "sha256:" + hashlib.sha256(data).hexdigest()


def safe_digest(element: etree._Element) -> str:
    try:
        return canonical_digest(element)
    except etree.C14NError:
        return ""
