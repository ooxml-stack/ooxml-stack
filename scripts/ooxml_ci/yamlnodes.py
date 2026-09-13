"""Safe YAML node access that keeps every value's source line.

The inventory composes the YAML node tree rather than constructing Python
objects: nothing in a workflow is instantiated, resolved or evaluated, and each
node still knows where it came from. Scalars are read as the text YAML resolved
them to, so implicit typing never leaks into the plan.
"""

from __future__ import annotations

from typing import Any

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode


class NodeError(RuntimeError):
    """The document is not shaped the way the inventory can read it."""


def compose(data: bytes) -> Node | None:
    """Parse to a node tree. Safe: no constructors run, so no object is built."""
    try:
        return yaml.compose(data, Loader=yaml.SafeLoader)
    except yaml.YAMLError as error:
        raise NodeError(f"invalid YAML: {error}") from error


def line_of(node: Node) -> int:
    return node.start_mark.line + 1


def is_standard_scalar(node: Node | None) -> bool:
    """A scalar carrying a normal YAML tag.

    A custom tag (``!Ref``) would otherwise be stripped silently, turning an
    unsupported construct into a plausible-looking string.
    """
    return isinstance(node, ScalarNode) and node.tag.startswith("tag:yaml.org,2002:")


def describe(node: Node | None) -> str:
    if node is None:
        return "nothing"
    if isinstance(node, ScalarNode):
        return f"a scalar tagged {node.tag!r}"
    if isinstance(node, SequenceNode):
        return "a sequence"
    return "a mapping"


def scalar(node: Node | None) -> str | None:
    """The resolved scalar text, or ``None`` when the node is not a plain scalar."""
    return node.value if is_standard_scalar(node) else None


def mapping(node: Node | None, where: str) -> list[tuple[str, Node, Node]]:
    """Mapping entries as ``(key, value, key_node)``.

    Rejects shapes whose meaning cannot be read literally: a repeated key would
    silently keep only the last value, and ``<<`` merge keys are not something
    Actions accepts. Both are reported instead of guessed at.
    """
    if node is None:
        return []
    if not isinstance(node, MappingNode):
        raise NodeError(f"{where} must be a mapping")
    items: list[tuple[str, Node, Node]] = []
    seen: set[str] = set()
    for key, value in node.value:
        if key.value == "<<":
            raise NodeError(f"{where} uses a YAML merge key ('<<'), which Actions does not support")
        if key.value in seen:
            raise NodeError(f"{where} repeats the key {key.value!r}")
        seen.add(key.value)
        items.append((key.value, value, key))
    return items


def as_dict(node: Node | None, where: str) -> dict[str, Node]:
    """A mapping keyed by name, for lookups that do not need source positions."""
    return {name: value for name, value, _ in mapping(node, where)}


def sequence(node: Node | None, where: str) -> list[Node]:
    if node is None:
        return []
    if not isinstance(node, SequenceNode):
        raise NodeError(f"{where} must be a sequence")
    return list(node.value)


def plain(node: Node | None, where: str) -> Any:
    """Structural conversion for values whose shape is meaningful (matrix, needs).

    Every level is validated the way the rest of the reader validates it:
    repeated keys, merge keys and non-standard scalar tags are rejected rather
    than silently collapsed into a plausible-looking value.
    """
    return _plain(node, where, frozenset())


def _plain(node: Node | None, where: str, seen: frozenset[int]) -> Any:
    if node is None:
        return None
    if isinstance(node, ScalarNode):
        if not is_standard_scalar(node):
            raise NodeError(f"{where} has an unsupported scalar tag {node.tag!r}")
        return node.value
    if not isinstance(node, (SequenceNode, MappingNode)):
        raise NodeError(f"{where} has an unsupported node type")
    if id(node) in seen:
        raise NodeError(f"{where} contains a recursive alias")
    nested = seen | {id(node)}
    if isinstance(node, SequenceNode):
        return [_plain(item, f"{where}[{index}]", nested) for index, item in enumerate(node.value)]
    return {name: _plain(value, f"{where}.{name}", nested) for name, value, _ in mapping(node, where)}