"""Exception and warning types for AgentTape.

Every error is designed to be *actionable*: it should tell the user exactly which
flag to pass or which edit to make to fix the situation. AgentTape's guiding
principle is "fail loud, never silent" — a missing or mismatched recording raises
rather than silently performing a real side effect.
"""

from __future__ import annotations

from typing import Any


class AgentTapeError(Exception):
    """Base class for all AgentTape errors."""


class ConfigError(AgentTapeError):
    """Raised when ``agenttape.toml`` or runtime configuration is invalid."""


class CassetteNotFoundError(AgentTapeError):
    """Raised when a cassette is required (e.g. ``mode="none"``) but does not exist."""


class CassetteCorruptError(AgentTapeError):
    """Raised when a cassette file cannot be parsed or violates the schema."""


class SchemaVersionError(AgentTapeError):
    """Raised when a cassette uses an unsupported schema version.

    The message includes a migration hint pointing at ``agenttape validate`` and
    the supported version range.
    """


class FieldDiff:
    """A single field-level difference between an incoming and a recorded request."""

    __slots__ = ("expected", "path", "received")

    def __init__(self, path: str, expected: Any, received: Any) -> None:
        self.path = path
        self.expected = expected
        self.received = received

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"FieldDiff(path={self.path!r}, expected={self.expected!r}, received={self.received!r})"
        )

    def render(self) -> str:
        return f"  - {self.path}: expected {self.expected!r}, received {self.received!r}"


class UnmatchedInteractionError(AgentTapeError):
    """Raised when an incoming request has no matching recording.

    Carries the canonical request, the closest recorded candidate (if any), and a
    field-level diff explaining *why* the closest candidate did not match. This is
    the error users see most often, so the message is verbose and prescriptive.
    """

    def __init__(
        self,
        *,
        kind: str,
        canonical_request: Any,
        cassette_path: str | None = None,
        closest: Any = None,
        field_diffs: list[FieldDiff] | None = None,
        mode: str | None = None,
        boundary_name: str | None = None,
    ) -> None:
        self.kind = kind
        self.canonical_request = canonical_request
        self.cassette_path = cassette_path
        self.closest = closest
        self.field_diffs = field_diffs or []
        self.mode = mode
        self.boundary_name = boundary_name
        super().__init__(self._build_message())

    def _build_message(self) -> str:
        import json

        lines: list[str] = []
        target = self.boundary_name or self.kind
        lines.append(
            f"No recorded {self.kind} interaction matched this incoming request ({target})."
        )
        if self.cassette_path:
            lines.append(f"Cassette: {self.cassette_path}")
        if self.mode:
            lines.append(f"Mode: {self.mode}")
        lines.append("")
        lines.append("Incoming (canonical) request:")
        lines.append(_indent(json.dumps(self.canonical_request, indent=2, default=str)))
        if self.closest is not None:
            lines.append("")
            lines.append("Closest recorded request:")
            lines.append(_indent(json.dumps(self.closest, indent=2, default=str)))
        if self.field_diffs:
            lines.append("")
            lines.append("Field differences (expected = recorded, received = incoming):")
            for fd in self.field_diffs:
                lines.append(fd.render())
        lines.append("")
        lines.append("How to fix:")
        lines.append(
            "  * If this request is new and expected, re-record with "
            "mode='all'/'new_episodes' or the --agenttape-record flag."
        )
        lines.append(
            "  * If a volatile field is causing the mismatch, add it to "
            "ignore_volatile_fields in agenttape.toml."
        )
        lines.append(
            "  * To run this boundary for real during replay, add it to the "
            "live={...} set of use_cassette()."
        )
        return "\n".join(lines)


class DeterminismDriftWarning(UserWarning):
    """Warning emitted when the replay environment drifts from the recorded one.

    For example, a whitelisted environment variable changed value between record
    and replay. Non-fatal by design; surfaces silently-broken determinism early.
    """


def _indent(text: str, prefix: str = "    ") -> str:
    return "\n".join(prefix + line for line in text.splitlines())
