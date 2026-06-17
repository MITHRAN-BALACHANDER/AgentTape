"""The internal cassette schema — one schema to which all adapters translate.

A :class:`Cassette` is an ordered list of :class:`Interaction` objects plus run
metadata. Every adapter (OpenAI, LangGraph, raw HTTP, …) maps its native events
into these structures, so the engine, CLI, diff and viewer are all framework
agnostic.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .errors import CassetteCorruptError, SchemaVersionError

SCHEMA_VERSION = "1"
SUPPORTED_VERSIONS = frozenset({"1"})

# The boundary kinds we record. ``http`` is the always-on fallback layer.
KINDS = frozenset({"llm", "tool", "retrieval", "memory_read", "memory_write", "http"})


@dataclass
class Interaction:
    """One captured boundary crossing."""

    index: int
    kind: str
    request: dict[str, Any]
    response: Any = None
    error: dict[str, Any] | None = None
    match_key: str = ""
    latency_ms: float | None = None
    usage: dict[str, Any] | None = None
    tags: list[str] = field(default_factory=list)
    # The named boundary this interaction belongs to (e.g. a tool name or "llm").
    # Used by mixed replay to decide live vs. frozen.
    boundary: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in KINDS:
            raise CassetteCorruptError(
                f"Unknown interaction kind {self.kind!r}; expected one of {sorted(KINDS)}."
            )

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "index": self.index,
            "kind": self.kind,
        }
        if self.boundary is not None:
            data["boundary"] = self.boundary
        data["request"] = self.request
        if self.error is not None:
            data["error"] = self.error
        else:
            data["response"] = self.response
        if self.match_key:
            data["match_key"] = self.match_key
        if self.latency_ms is not None:
            data["latency_ms"] = self.latency_ms
        if self.usage is not None:
            data["usage"] = self.usage
        if self.tags:
            data["tags"] = list(self.tags)
        if self.metadata:
            data["metadata"] = self.metadata
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Interaction:
        if not isinstance(data, dict):
            raise CassetteCorruptError(f"Interaction must be a mapping, got {type(data)!r}.")
        try:
            kind = data["kind"]
            index = int(data["index"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CassetteCorruptError(f"Interaction missing required field: {exc}") from exc
        has_error = "error" in data and data["error"] is not None
        if not has_error and "response" not in data:
            raise CassetteCorruptError(
                f"Interaction #{index} ({kind!r}) has neither a 'response' nor an "
                f"'error'. A recorded interaction must carry one or the other; this "
                f"cassette is corrupt or was hand-edited incorrectly."
            )
        return cls(
            index=index,
            kind=kind,
            request=data.get("request") or {},
            response=None if has_error else data.get("response"),
            error=data.get("error") if has_error else None,
            match_key=data.get("match_key", ""),
            latency_ms=data.get("latency_ms"),
            usage=data.get("usage"),
            tags=list(data.get("tags") or []),
            boundary=data.get("boundary"),
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass
class Cassette:
    """An ordered collection of interactions for one logical run."""

    version: str = SCHEMA_VERSION
    created_at: str = ""
    run_id: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
    interactions: list[Interaction] = field(default_factory=list)

    def add(self, interaction: Interaction) -> None:
        interaction.index = len(self.interactions)
        self.interactions.append(interaction)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "created_at": self.created_at,
            "run_id": self.run_id,
            "meta": self.meta,
            "interactions": [i.to_dict() for i in self.interactions],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Cassette:
        if not isinstance(data, dict):
            raise CassetteCorruptError("Cassette root must be a mapping.")
        version = str(data.get("version", SCHEMA_VERSION))
        if version not in SUPPORTED_VERSIONS:
            raise SchemaVersionError(
                f"Cassette schema version {version!r} is not supported by this "
                f"AgentTape (supports {sorted(SUPPORTED_VERSIONS)}). "
                f"Run `agenttape validate <cassette>` for a migration hint, or "
                f"re-record with `--agenttape-record`."
            )
        raw_interactions = data.get("interactions") or []
        if not isinstance(raw_interactions, list):
            raise CassetteCorruptError("'interactions' must be a list.")
        interactions = [Interaction.from_dict(i) for i in raw_interactions]
        return cls(
            version=version,
            created_at=str(data.get("created_at", "")),
            run_id=str(data.get("run_id", "")),
            meta=dict(data.get("meta") or {}),
            interactions=interactions,
        )
