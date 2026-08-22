"""VML text semantic value helpers."""
from __future__ import annotations

from lxml import etree

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def visible_vml_text(node: etree._Element) -> str:
    tokens = [item.text or "" for item in node.iter(f"{{{W_NS}}}t")]
    if tokens:
        return _normalize("".join(tokens))
    return _normalize("".join(node.itertext()))


def _normalize(value: str) -> str:
    return " ".join(value.split())
