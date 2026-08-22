#!/usr/bin/env python3
"""Safe subset policy for Word 2010 extension metadata rows."""
from __future__ import annotations

from typing import Any

W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"

_SAFE_ATTR_ENUMS = {
    (W14_NS, "numForm", "val"): ("default", "lining", "oldStyle"),
    (W14_NS, "numSpacing", "val"): ("default", "proportional", "tabular"),
}


def w14_safe_attr_values(row: dict[str, Any]) -> tuple[str, ...]:
    uri, local = _qname_parts(str(row.get("qname", "")))
    attr_uri, attr = _qname_parts(str(row.get("attribute_name", "")))
    if attr_uri != W14_NS:
        return ()
    return _SAFE_ATTR_ENUMS.get((uri, local, attr), ())


def _qname_parts(qname: str) -> tuple[str, str]:
    if not qname.startswith("{"):
        return "", qname.split(":", 1)[-1]
    uri, local = qname[1:].split("}", 1)
    return uri, local
