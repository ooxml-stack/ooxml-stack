"""The two graph views over one edge set: one traversal, two edge filters."""

from __future__ import annotations

from typing import Any

IMPACT_KINDS = ("runtime", "dev", "codegen", "ci", "data")
ORDER_KINDS = ("runtime", "codegen")


def traverse(edges: list[dict[str, Any]], start: str, kinds: tuple[str, ...], reverse: bool) -> set[str]:
    seen = {start}
    frontier = [start]
    while frontier:
        current = frontier.pop()
        for edge in edges:
            if edge["kind"] not in kinds:
                continue
            if reverse:
                if edge["to"] != current:
                    continue
                nxt = edge["from"]
            else:
                if edge["from"] != current:
                    continue
                nxt = edge["to"]
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)
    return seen


def impact_graph(edges: list[dict[str, Any]], start: str) -> dict[str, Any]:
    return {
        "view": "impact",
        "kinds": list(IMPACT_KINDS),
        "reverse": True,
        "start": start,
        "reaches": sorted(traverse(edges, start, IMPACT_KINDS, reverse=True)),
        "cycles_allowed": True,
    }


def order_graph(edges: list[dict[str, Any]]) -> dict[str, Any]:
    """Positive runtime+codegen edges; a cycle here is a structural error."""
    scoped = [edge for edge in edges if edge["kind"] in ORDER_KINDS]
    nodes = sorted({edge["from"] for edge in scoped} | {edge["to"] for edge in scoped})
    adjacency = {node: set() for node in nodes}
    for edge in scoped:
        adjacency[edge["from"]].add(edge["to"])
    return {
        "view": "partial_release_order",
        "kinds": list(ORDER_KINDS),
        "reverse": False,
        "edges": [
            {"from": edge["from"], "to": edge["to"], "kind": edge["kind"]}
            for edge in sorted(scoped, key=lambda e: (e["from"], e["to"], e["kind"]))
        ],
        "cycle": find_cycle(adjacency),
        "note": "Partial order over runtime and codegen dependencies only, not a full release sequence.",
    }


def find_cycle(adjacency: dict[str, set[str]]) -> list[str] | None:
    WHITE, GREY, BLACK = 0, 1, 2
    colour = {node: WHITE for node in adjacency}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        colour[node] = GREY
        stack.append(node)
        for neighbour in sorted(adjacency.get(node, ())):
            if colour.get(neighbour, WHITE) == GREY:
                return stack[stack.index(neighbour) :] + [neighbour]
            if colour.get(neighbour, WHITE) == WHITE:
                found = visit(neighbour)
                if found:
                    return found
        stack.pop()
        colour[node] = BLACK
        return None

    for node in sorted(adjacency):
        if colour[node] == WHITE:
            found = visit(node)
            if found:
                return found
    return None