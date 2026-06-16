"""Pure-stdlib YAML subset reader/writer with optional PyYAML acceleration.

AgentTape's core has **zero required runtime dependencies**, but cassettes default
to YAML because it is the most diff-friendly and hand-editable format. To honour
both constraints we ship a small, dependency-free YAML implementation that round
trips the data shapes AgentTape produces (nested mappings, sequences, scalars and
multi-line literal block strings).

* Writing always uses our own emitter so output is byte-stable regardless of the
  environment (important for git-friendly diffs and deterministic cassettes).
* Reading uses PyYAML's ``safe_load`` when available (robust against arbitrary
  hand edits); otherwise it falls back to the bundled block-YAML parser.

Set ``AGENTTAPE_FORCE_STDLIB_YAML=1`` to force the stdlib path even when PyYAML is
installed (used by the test-suite to exercise the zero-dependency code path).
"""

from __future__ import annotations

import os
import re
from typing import Any

__all__ = ["dump", "load", "using_pyyaml"]


def _pyyaml_available() -> bool:
    if os.environ.get("AGENTTAPE_FORCE_STDLIB_YAML"):
        return False
    try:
        import yaml  # noqa: F401
    except Exception:
        return False
    return True


def using_pyyaml() -> bool:
    """Return ``True`` if YAML *loading* will use PyYAML."""

    return _pyyaml_available()


# --------------------------------------------------------------------------- #
# Emitter
# --------------------------------------------------------------------------- #

_PLAIN_SAFE_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9 _./@+-]*$")
# Strings that *look* like another YAML type must be quoted to stay strings.
_AMBIGUOUS_RE = re.compile(
    r"^(?:true|false|yes|no|on|off|null|~|none"
    r"|[+-]?\d+|[+-]?\d*\.\d+(?:[eE][+-]?\d+)?|[+-]?\d+[eE][+-]?\d+)$",
    re.IGNORECASE,
)


def dump(obj: Any) -> str:
    """Serialise ``obj`` to a YAML string using AgentTape's stable emitter."""

    lines: list[str] = []
    _emit(obj, 0, lines, top=True)
    text = "\n".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    return text


def _emit(obj: Any, indent: int, lines: list[str], *, top: bool = False) -> None:
    pad = "  " * indent
    if isinstance(obj, dict):
        if not obj:
            lines.append(f"{pad}{{}}" if not top else "{}")
            return
        for key, value in obj.items():
            _emit_pair(str(key), value, indent, lines)
    elif isinstance(obj, (list, tuple)):
        if not obj:
            lines.append(f"{pad}[]" if not top else "[]")
            return
        for item in obj:
            _emit_item(item, indent, lines)
    else:
        lines.append(f"{pad}{_scalar(obj)}")


def _emit_pair(key: str, value: Any, indent: int, lines: list[str]) -> None:
    pad = "  " * indent
    key_str = _scalar_key(key)
    if isinstance(value, dict):
        if not value:
            lines.append(f"{pad}{key_str}: {{}}")
        else:
            lines.append(f"{pad}{key_str}:")
            _emit(value, indent + 1, lines)
    elif isinstance(value, (list, tuple)):
        if not value:
            lines.append(f"{pad}{key_str}: []")
        else:
            lines.append(f"{pad}{key_str}:")
            for item in value:
                _emit_item(item, indent + 1, lines)
    elif isinstance(value, str) and "\n" in value:
        lines.append(f"{pad}{key_str}: {_block_header(value)}")
        _emit_block_scalar(value, indent + 1, lines)
    else:
        lines.append(f"{pad}{key_str}: {_scalar(value)}")


def _emit_item(item: Any, indent: int, lines: list[str]) -> None:
    pad = "  " * indent
    if isinstance(item, dict):
        if not item:
            lines.append(f"{pad}- {{}}")
            return
        first = True
        for key, value in item.items():
            if first:
                # Inline the first key on the same line as the dash.
                stash: list[str] = []
                _emit_pair(str(key), value, indent + 1, stash)
                stash[0] = f"{pad}- {stash[0].lstrip()}"
                lines.extend(stash)
                first = False
            else:
                _emit_pair(str(key), value, indent + 1, lines)
    elif isinstance(item, (list, tuple)):
        if not item:
            lines.append(f"{pad}- []")
            return
        stash2: list[str] = []
        _emit(item, indent + 1, stash2)
        stash2[0] = f"{pad}- {stash2[0].lstrip()}"
        lines.extend(stash2)
    elif isinstance(item, str) and "\n" in item:
        lines.append(f"{pad}- {_block_header(item)}")
        _emit_block_scalar(item, indent + 1, lines)
    else:
        lines.append(f"{pad}- {_scalar(item)}")


def _block_header(value: str) -> str:
    # Use a literal block scalar. Choose chomping indicator to preserve content.
    if value.endswith("\n"):
        return "|"  # clip: single trailing newline preserved
    return "|-"  # strip: no trailing newline


def _emit_block_scalar(value: str, indent: int, lines: list[str]) -> None:
    pad = "  " * indent
    content = value[:-1] if value.endswith("\n") else value
    for line in content.split("\n"):
        lines.append(f"{pad}{line}" if line else "")


def _scalar_key(key: str) -> str:
    if _PLAIN_SAFE_RE.match(key) and not _AMBIGUOUS_RE.match(key):
        return key
    return _quote(key)


def _scalar(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value:  # NaN
            return ".nan"
        if value == float("inf"):
            return ".inf"
        if value == float("-inf"):
            return "-.inf"
        return repr(value)
    text = str(value)
    if text == "":
        return "''"
    if _PLAIN_SAFE_RE.match(text) and not _AMBIGUOUS_RE.match(text):
        return text
    return _quote(text)


def _quote(text: str) -> str:
    # Single-quoted style; escape embedded single quotes by doubling them.
    return "'" + text.replace("'", "''") + "'"


# --------------------------------------------------------------------------- #
# Loader
# --------------------------------------------------------------------------- #


def load(text: str) -> Any:
    """Parse a YAML string into Python objects."""

    if _pyyaml_available():
        import yaml

        return yaml.safe_load(text)
    return _StdlibParser(text).parse()


class _StdlibParser:
    """A small recursive block-YAML parser covering the AgentTape subset.

    Handles block mappings, block sequences, single/double quoted scalars, literal
    and folded block scalars (``|``, ``|-``, ``|+``, ``>``, ``>-``, ``>+``), basic
    flow collections (``[]`` / ``{}``) and scalar type inference. It is intentionally
    forgiving: it is a fallback for environments without PyYAML, and the primary
    job is to round-trip what our own emitter writes plus reasonable hand edits.
    """

    def __init__(self, text: str) -> None:
        raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        # Strip a leading document marker if present.
        self._lines = raw
        self._n = len(raw)

    def parse(self) -> Any:
        idx = self._skip_blanks(0)
        if idx >= self._n:
            return None
        value, _ = self._parse_block(idx, self._indent_of(idx))
        return value

    # -- helpers ----------------------------------------------------------- #

    def _indent_of(self, idx: int) -> int:
        line = self._lines[idx]
        return len(line) - len(line.lstrip(" "))

    def _is_blank(self, idx: int) -> bool:
        stripped = self._lines[idx].strip()
        return stripped == "" or stripped.startswith("#")

    def _skip_blanks(self, idx: int) -> int:
        while idx < self._n and self._is_blank(idx):
            idx += 1
        return idx

    # -- block parsing ----------------------------------------------------- #

    def _parse_block(self, idx: int, indent: int) -> tuple[Any, int]:
        idx = self._skip_blanks(idx)
        if idx >= self._n:
            return None, idx
        line = self._lines[idx]
        cur_indent = len(line) - len(line.lstrip(" "))
        if cur_indent < indent:
            return None, idx
        stripped = line.strip()
        if stripped.startswith("- "):
            return self._parse_sequence(idx, cur_indent)
        if stripped == "-":
            return self._parse_sequence(idx, cur_indent)
        if stripped in ("{}", "[]"):
            return ([] if stripped == "[]" else {}), idx + 1
        if stripped.startswith(("[", "{")):
            return _parse_flow(stripped), idx + 1
        if _looks_like_mapping_entry(stripped):
            return self._parse_mapping(idx, cur_indent)
        # A bare top-level scalar document (e.g. ".nan", "42", "hello").
        return _parse_scalar(stripped), idx + 1

    def _parse_sequence(self, idx: int, indent: int) -> tuple[list[Any], int]:
        items: list[Any] = []
        while idx < self._n:
            idx = self._skip_blanks(idx)
            if idx >= self._n:
                break
            line = self._lines[idx]
            cur_indent = len(line) - len(line.lstrip(" "))
            if cur_indent != indent:
                break
            stripped = line.strip()
            if not (stripped == "-" or stripped.startswith("- ")):
                break
            rest = stripped[1:].lstrip(" ")
            if rest == "":
                # Nested block on following lines.
                nxt = self._skip_blanks(idx + 1)
                if nxt < self._n and self._indent_of(nxt) > indent:
                    value, idx = self._parse_block(nxt, self._indent_of(nxt))
                else:
                    value, idx = None, idx + 1
                items.append(value)
            else:
                # The dash introduces an element that may itself be a mapping or
                # scalar. Compute the effective indent of the inlined content.
                content_indent = indent + (len(stripped) - len(rest))
                value, idx = self._parse_inline_after_dash(
                    idx, indent, content_indent, rest
                )
                items.append(value)
        return items, idx

    def _parse_inline_after_dash(
        self, idx: int, dash_indent: int, content_indent: int, rest: str
    ) -> tuple[Any, int]:
        block = _detect_block_scalar(rest)
        if block is not None:
            value, idx = self._read_block_scalar(idx + 1, content_indent, block)
            return value, idx
        if rest == "-" or rest.startswith("- "):
            # Nested sequence introduced inline after the dash ("- - 1").
            self._lines[idx] = " " * content_indent + rest
            return self._parse_sequence(idx, content_indent)
        if _looks_like_mapping_entry(rest):
            # Rewrite the line so the mapping parser sees aligned content.
            self._lines[idx] = " " * content_indent + rest
            return self._parse_mapping(idx, content_indent)
        if rest in ("{}", "[]"):
            return ([] if rest == "[]" else {}), idx + 1
        if rest.startswith(("[", "{")):
            return _parse_flow(rest), idx + 1
        return _parse_scalar(rest), idx + 1

    def _parse_mapping(self, idx: int, indent: int) -> tuple[dict[str, Any], int]:
        mapping: dict[str, Any] = {}
        while idx < self._n:
            idx = self._skip_blanks(idx)
            if idx >= self._n:
                break
            line = self._lines[idx]
            cur_indent = len(line) - len(line.lstrip(" "))
            if cur_indent != indent:
                break
            stripped = line.strip()
            if stripped.startswith("- ") or stripped == "-":
                break
            key, sep, value_part = _split_key(stripped)
            if not sep:
                break
            value_part = value_part.strip()
            block = _detect_block_scalar(value_part)
            if value_part == "" or block is not None:
                if block is not None:
                    value, idx = self._read_block_scalar(idx + 1, indent, block)
                else:
                    nxt = self._skip_blanks(idx + 1)
                    if nxt < self._n and self._indent_of(nxt) > indent:
                        value, idx = self._parse_block(nxt, self._indent_of(nxt))
                    else:
                        value, idx = None, idx + 1
                mapping[key] = value
            elif value_part in ("{}", "[]"):
                mapping[key] = [] if value_part == "[]" else {}
                idx += 1
            elif value_part.startswith(("[", "{")):
                mapping[key] = _parse_flow(value_part)
                idx += 1
            else:
                mapping[key] = _parse_scalar(value_part)
                idx += 1
        return mapping, idx

    def _read_block_scalar(
        self, idx: int, parent_indent: int, spec: tuple[str, str]
    ) -> tuple[str, int]:
        style, chomp = spec
        collected: list[str] = []
        block_indent: int | None = None
        while idx < self._n:
            line = self._lines[idx]
            if line.strip() == "":
                collected.append("")
                idx += 1
                continue
            cur_indent = len(line) - len(line.lstrip(" "))
            if cur_indent <= parent_indent:
                break
            if block_indent is None:
                block_indent = cur_indent
            collected.append(line[block_indent:])
            idx += 1
        # Trim trailing blank lines that belong to the next node.
        while collected and collected[-1] == "":
            collected.pop()
        if style == ">":  # folded
            text = _fold(collected)
        else:  # literal
            text = "\n".join(collected)
        if chomp == "keep" or chomp == "clip":
            text += "\n"
        # strip: leave as-is (no trailing newline)
        return text, idx


# --------------------------------------------------------------------------- #
# Scalar / flow helpers
# --------------------------------------------------------------------------- #


def _split_key(stripped: str) -> tuple[str, bool, str]:
    """Split ``key: value`` honouring quoted keys. Returns (key, found, value)."""

    if stripped.startswith(("'", '"')):
        quote = stripped[0]
        i = 1
        buf: list[str] = []
        while i < len(stripped):
            ch = stripped[i]
            if ch == quote:
                if quote == "'" and i + 1 < len(stripped) and stripped[i + 1] == "'":
                    buf.append("'")
                    i += 2
                    continue
                break
            buf.append(ch)
            i += 1
        key = "".join(buf)
        rest = stripped[i + 1 :].lstrip()
        if rest.startswith(":"):
            return key, True, rest[1:]
        return stripped, False, ""
    if ":" not in stripped:
        return stripped, False, ""
    # Find the first ": " or trailing ":" not inside brackets.
    depth = 0
    for i, ch in enumerate(stripped):
        if ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        elif ch == ":" and depth == 0:
            after = stripped[i + 1 :]
            if after == "" or after.startswith(" "):
                return stripped[:i].strip(), True, after
    return stripped, False, ""


def _detect_block_scalar(token: str) -> tuple[str, str] | None:
    token = token.strip()
    if not token or token[0] not in "|>":
        return None
    # Optional comment after the indicator.
    indicator = token.split("#", 1)[0].strip()
    style = indicator[0]
    chomp = "clip"
    for ch in indicator[1:]:
        if ch == "-":
            chomp = "strip"
        elif ch == "+":
            chomp = "keep"
        elif ch.isdigit():
            continue
        else:
            return None
    return style, chomp


def _looks_like_mapping_entry(token: str) -> bool:
    key, sep, _ = _split_key(token)
    return sep


def _fold(lines: list[str]) -> str:
    out: list[str] = []
    prev_blank = True
    for line in lines:
        if line == "":
            out.append("\n")
            prev_blank = True
        else:
            if not prev_blank:
                out.append(" ")
            out.append(line)
            prev_blank = False
    return "".join(out)


def _parse_scalar(token: str) -> Any:
    token = _strip_inline_comment(token).strip()
    if token == "" or token == "~" or token.lower() == "null":
        return None
    if token.startswith("'"):
        return _unquote_single(token)
    if token.startswith('"'):
        return _unquote_double(token)
    low = token.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    if low in (".nan", ".NaN".lower()):
        return float("nan")
    if low in (".inf", "+.inf"):
        return float("inf")
    if low == "-.inf":
        return float("-inf")
    if re.fullmatch(r"[+-]?\d+", token):
        try:
            return int(token)
        except ValueError:
            return token
    if re.fullmatch(r"[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?", token) and (
        "." in token or "e" in low
    ):
        try:
            return float(token)
        except ValueError:
            return token
    return token


def _strip_inline_comment(token: str) -> str:
    # Remove a trailing " #..." comment that is not inside quotes.
    in_single = in_double = False
    for i, ch in enumerate(token):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            if i == 0 or token[i - 1] == " ":
                return token[:i]
    return token


def _unquote_single(token: str) -> str:
    token = token.strip()
    if len(token) >= 2 and token.endswith("'"):
        inner = token[1:-1]
        return inner.replace("''", "'")
    return token[1:]


def _unquote_double(token: str) -> str:
    token = token.strip()
    if len(token) >= 2 and token.endswith('"'):
        inner = token[1:-1]
    else:
        inner = token[1:]
    return _decode_escapes(inner)


_ESCAPES = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    '"': '"',
    "\\": "\\",
    "0": "\0",
    "/": "/",
    "b": "\b",
    "f": "\f",
}


def _decode_escapes(s: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s):
            nxt = s[i + 1]
            if nxt in _ESCAPES:
                out.append(_ESCAPES[nxt])
                i += 2
                continue
            if nxt == "u" and i + 5 < len(s) + 1:
                try:
                    out.append(chr(int(s[i + 2 : i + 6], 16)))
                    i += 6
                    continue
                except ValueError:
                    pass
            out.append(nxt)
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _parse_flow(token: str) -> Any:
    """Parse a single-line flow collection: ``[a, b]`` or ``{k: v}``."""

    token = _strip_inline_comment(token).strip()
    value, _ = _parse_flow_value(token, 0)
    return value


def _parse_flow_value(s: str, i: int) -> tuple[Any, int]:
    i = _skip_ws(s, i)
    if i >= len(s):
        return None, i
    if s[i] == "[":
        return _parse_flow_seq(s, i + 1)
    if s[i] == "{":
        return _parse_flow_map(s, i + 1)
    return _parse_flow_scalar(s, i)


def _parse_flow_seq(s: str, i: int) -> tuple[list[Any], int]:
    items: list[Any] = []
    i = _skip_ws(s, i)
    if i < len(s) and s[i] == "]":
        return items, i + 1
    while i < len(s):
        value, i = _parse_flow_value(s, i)
        items.append(value)
        i = _skip_ws(s, i)
        if i < len(s) and s[i] == ",":
            i = _skip_ws(s, i + 1)
            continue
        if i < len(s) and s[i] == "]":
            return items, i + 1
        break
    return items, i


def _parse_flow_map(s: str, i: int) -> tuple[dict[str, Any], int]:
    mapping: dict[str, Any] = {}
    i = _skip_ws(s, i)
    if i < len(s) and s[i] == "}":
        return mapping, i + 1
    while i < len(s):
        key, i = _parse_flow_scalar(s, i, stop=":,}")
        i = _skip_ws(s, i)
        if i < len(s) and s[i] == ":":
            value, i = _parse_flow_value(s, i + 1)
        else:
            value = None
        mapping[str(key)] = value
        i = _skip_ws(s, i)
        if i < len(s) and s[i] == ",":
            i = _skip_ws(s, i + 1)
            continue
        if i < len(s) and s[i] == "}":
            return mapping, i + 1
        break
    return mapping, i


def _parse_flow_scalar(s: str, i: int, stop: str = ",]}") -> tuple[Any, int]:
    i = _skip_ws(s, i)
    if i < len(s) and s[i] in "'\"":
        quote = s[i]
        j = i + 1
        buf: list[str] = []
        while j < len(s):
            if s[j] == quote:
                if quote == "'" and j + 1 < len(s) and s[j + 1] == "'":
                    buf.append("'")
                    j += 2
                    continue
                j += 1
                break
            buf.append(s[j])
            j += 1
        raw = "".join(buf)
        return (raw if quote == "'" else _decode_escapes(raw)), j
    j = i
    while j < len(s) and s[j] not in stop:
        j += 1
    return _parse_scalar(s[i:j].strip()), j


def _skip_ws(s: str, i: int) -> int:
    while i < len(s) and s[i] in " \t":
        i += 1
    return i
