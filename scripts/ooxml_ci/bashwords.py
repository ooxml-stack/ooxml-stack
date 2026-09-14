"""Shell command extraction for workflow ``run`` bodies.

The bash grammar decides where one command ends and the next begins, so quoting,
escaping and comments are resolved by the grammar rather than re-read from text.
Actions expressions (``${{ ... }}``) are not shell: they are masked to a plain
placeholder word before parsing, so the grammar never has to error-recover
around them, while the placeholder keeps the argument position of the original
expression. Nothing is executed and no expansion is evaluated.
"""

from __future__ import annotations

import re
from typing import NamedTuple

import tree_sitter_bash
from tree_sitter import Language, Parser

from .urls import is_remote_repo

# ``git clone`` options that consume the following token; everything else that
# starts with ``-`` is a flag. Not a git parser: just enough to find the repo.
CLONE_VALUE_OPTIONS = frozenset(
    {
        "-b", "--branch", "-o", "--origin", "-u", "--upload-pack", "-c", "--config",
        "-j", "--jobs", "--depth", "--shallow-since", "--shallow-exclude", "--filter",
        "--reference", "--reference-if-able", "--separate-git-dir", "--template",
    }
)
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")

_PARSER = Parser(Language(tree_sitter_bash.language()))
# What can stand as a command's argument. Anything else on a ``command`` node --
# a leading ``VAR=value``, a redirection -- is not part of the command line.
_ARGUMENT = frozenset(
    {
        "word", "number", "raw_string", "ansi_c_string", "string", "concatenation", "simple_expansion",
        "expansion", "command_substitution", "arithmetic_expansion", "process_substitution",
    }
)
# Nodes whose value the shell computes at run time; kept verbatim, never guessed.
_DYNAMIC = frozenset(
    {
        "simple_expansion", "expansion", "command_substitution", "arithmetic_expansion",
        "process_substitution",
    }
)

_EXPR_START = b"${{"
_MARKER_BASE = "__ooxml_actions_expr"


class Shell(NamedTuple):
    """One ``run`` body: its commands, its expressions and what could not be read."""

    commands: list[tuple[int, list[tuple[str, bool]]]]
    expressions: list[str]
    problems: list[str]
    unreadable: bool
    marker_prefix: str


def _marker_prefix(raw: bytes) -> str:
    """A placeholder prefix that does not occur in the original text.

    A ``run`` body may legitimately contain the placeholder spelling; adding
    underscores keeps a real word from ever being mistaken for a mask.
    """
    prefix = _MARKER_BASE
    while prefix.encode("ascii") in raw:
        prefix += "_"
    return prefix


def _marker_pattern(prefix: str) -> re.Pattern[str]:
    return re.compile(re.escape(prefix) + r"_(\d+)__")


def _expression_end(raw: bytes, index: int) -> int:
    """Index just past the ``}}`` closing an expression, or ``-1`` if unterminated.

    Quoted strings inside the expression are skipped, so a ``}}`` inside a
    literal never ends the expression early.
    """
    quote = b""
    while index < len(raw):
        char = raw[index : index + 1]
        if quote == b"'":
            if char == b"'":
                quote = b""
        elif quote == b'"':
            if char == b"\\":
                index += 1
            elif char == b'"':
                quote = b""
        elif char in (b"'", b'"'):
            quote = char
        elif char == b"}" and raw.startswith(b"}}", index):
            return index + 2
        index += 1
    return -1


def mask_expressions(
    text: str,
) -> tuple[bytes, list[str], list[str], list[tuple[int, int, int, int]], str]:
    """Replace ``${{ ... }}`` with placeholder words, keeping byte spans.

    Returns the adapted bytes, the original expression sources, a problem for
    each expression that never closes, the spans needed to map an offset in the
    adapted text back to the original ``run`` text, and the placeholder prefix.
    """
    raw = text.encode("utf-8")
    prefix = _marker_prefix(raw)
    pieces: list[bytes] = []
    expressions: list[str] = []
    problems: list[str] = []
    spans: list[tuple[int, int, int, int]] = []
    index = 0
    adapted = 0
    while True:
        start = raw.find(_EXPR_START, index)
        if start < 0:
            pieces.append(raw[index:])
            break
        pieces.append(raw[index:start])
        adapted += start - index
        end = _expression_end(raw, start + len(_EXPR_START))
        if end < 0:
            problems.append(f"unterminated Actions expression {raw[start:].decode('utf-8')!r}")
            end = len(raw)
        expressions.append(raw[start:end].decode("utf-8"))
        marker = f"{prefix}_{len(expressions) - 1}__".encode("ascii")
        pieces.append(marker)
        spans.append((adapted, adapted + len(marker), start, end))
        adapted += len(marker)
        index = end
        if end >= len(raw):
            break
    return b"".join(pieces), expressions, problems, spans, prefix


def restore(text: str, expressions: list[str], prefix: str) -> str:
    """Put the original expressions back into a masked token."""

    def _replace(match: re.Match[str]) -> str:
        index = int(match.group(1))
        return expressions[index] if index < len(expressions) else match.group(0)

    return _marker_pattern(prefix).sub(_replace, text)


def _original_offset(offset: int, spans: list[tuple[int, int, int, int]]) -> int:
    """Map a byte offset in the adapted text back to the original ``run`` text."""
    shift = 0
    for adapted_start, adapted_end, original_start, original_end in spans:
        if offset >= adapted_end:
            shift += (original_end - original_start) - (adapted_end - adapted_start)
        elif offset > adapted_start:
            return original_start
    return offset + shift


def _decode_unquoted(raw: str) -> str:
    """A bare word: a backslash escapes the next character, and is dropped."""
    out: list[str] = []
    index = 0
    while index < len(raw):
        char = raw[index]
        if char == "\\" and index + 1 < len(raw):
            if raw[index + 1] == "\n":
                index += 2
                continue
            out.append(raw[index + 1])
            index += 2
            continue
        out.append(char)
        index += 1
    return "".join(out)


def _decode_double(inner: str) -> str:
    """A double-quoted body: a backslash escapes only ``$ ` " \\`` and newline."""
    out: list[str] = []
    index = 0
    while index < len(inner):
        char = inner[index]
        if char == "\\" and index + 1 < len(inner):
            nxt = inner[index + 1]
            if nxt == "\n":
                index += 2
                continue
            if nxt in '$`"\\':
                out.append(nxt)
                index += 2
                continue
        out.append(char)
        index += 1
    return "".join(out)


def _word_text(node, source: bytes, marker: re.Pattern[str]) -> tuple[str, bool]:
    """A word's literal text, and whether the shell computes it at run time.

    A double-quoted string is still expanded by the shell, so its children are
    inspected too: ``"https://host/${REPO}.git"`` is exactly as dynamic as the
    unquoted form, and must not be read as a repository named ``${REPO}``.
    """
    if node.type == "concatenation":
        parts = [_word_text(child, source, marker) for child in node.named_children]
        return "".join(text for text, _ in parts), any(dynamic for _, dynamic in parts)
    raw = source[node.start_byte : node.end_byte].decode("utf-8")
    if node.type == "ansi_c_string":
        text = raw[2:-1]
        if "\\" in text:
            return raw, True  # keep the argument without guessing Bash escape semantics
    elif node.type == "raw_string":
        text = raw[1:-1]
    elif node.type == "string":
        text = _decode_double(raw[1:-1])
    elif node.type == "word":
        text = _decode_unquoted(raw)
    else:
        text = raw
    dynamic = node.type in _DYNAMIC or any(child.type in _DYNAMIC for child in node.named_children)
    return text, dynamic or bool(marker.search(text))


def commands(text: str) -> Shell:
    """Commands in a shell body, with their words and their line offsets.

    The whole scalar is parsed at once, so a quoted ``;`` stays an argument and a
    newline inside quotes does not start a command. Line offsets are counted in
    the original ``run`` text, so masking an expression never shifts a later line.
    """
    adapted, expressions, problems, spans, prefix = mask_expressions(text)
    marker = _marker_pattern(prefix)
    original = text.encode("utf-8")
    root = _PARSER.parse(adapted).root_node
    found: list[tuple[int, list[tuple[str, bool]]]] = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "command":
            words = [
                _word_text(child, adapted, marker)
                for child in node.named_children
                if child.type == "command_name" or child.type in _ARGUMENT
            ]
            if words:
                offset = _original_offset(node.start_byte, spans)
                found.append((original.count(b"\n", 0, offset), words))
        stack.extend(reversed(node.children))
    return Shell(found, expressions, problems, root.has_error, prefix)


def clone_target(tokens: list[tuple[str, bool]]) -> tuple[str, str] | None:
    """The repository argument of a ``git clone`` command.

    ``("url", url)`` for a statically known repository, ``("dynamic", raw)`` when
    the argument is computed at run time, and ``None`` when the command is not a
    ``git clone`` or names a target the inventory does not model.
    """
    index = 0
    while index < len(tokens) and ASSIGNMENT.match(tokens[index][0]):
        index += 1  # a leading VAR=value prefix is not part of the command
    if [text for text, _ in tokens[index : index + 2]] != ["git", "clone"]:
        return None
    index += 2
    while index < len(tokens):
        text, dynamic = tokens[index]
        if text == "--":
            index += 1
            break
        if not text.startswith("-"):
            break
        if "=" in text:
            index += 1  # ``--opt=value`` carries its own value, dynamic or not
            continue
        if dynamic:
            return ("dynamic", text)  # an option whose shape cannot be read
        index += 2 if text in CLONE_VALUE_OPTIONS else 1
    if index >= len(tokens):
        return None
    text, dynamic = tokens[index]
    if dynamic:
        return ("dynamic", text)
    return ("url", text) if is_remote_repo(text) else None