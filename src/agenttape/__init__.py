"""AgentTape — deterministic record/replay for AI agents.

Deterministic record / replay of an agent's external interactions (LLM calls and
tool calls) into human-readable cassettes, so agent tests run offline, for free,
with zero side effects.

Quickstart::

    import agenttape

    with agenttape.use_cassette("hello", mode="record"):
        run_agent()                      # records real calls

    with agenttape.use_cassette("hello", mode="none"):
        run_agent()                      # replays, zero network, deterministic

The public names below are imported **lazily** (PEP 562): ``import agenttape`` only
pulls in the engine, freeze layer and adapters the first time you touch one of them.
This keeps the import side-effect-free and cheap — and, because the package is
imported by the pytest plugin entry point before coverage starts, it also means
``pytest --cov=agenttape`` measures the engine modules correctly (they load during
tests, not at plugin-registration time).
"""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .boundaries import memory_read, memory_write, record_call, retrieval, tool
    from .callbacks import AgentTape
    from .config import Config
    from .errors import (
        AgentTapeError,
        CassetteCorruptError,
        CassetteNotFoundError,
        ConfigError,
        DeterminismDriftWarning,
        SchemaVersionError,
        StreamingNotRecordedWarning,
        StreamingReplayError,
        UnmatchedInteractionError,
    )
    from .recorder import Session, active_session, record, replay, use_cassette
    from .schema import Cassette, Interaction

try:  # populated from package metadata when installed
    from importlib.metadata import version as _version

    __version__ = _version("agenttape")
except Exception:  # pragma: no cover - editable/source tree fallback
    __version__ = "0.1.0"

# Public name -> (submodule, attribute). Resolved on first access by __getattr__.
_LAZY: dict[str, tuple[str, str]] = {
    # Core API
    "use_cassette": ("recorder", "use_cassette"),
    "record": ("recorder", "record"),
    "replay": ("recorder", "replay"),
    "Session": ("recorder", "Session"),
    "active_session": ("recorder", "active_session"),
    # Boundary helpers
    "tool": ("boundaries", "tool"),
    "retrieval": ("boundaries", "retrieval"),
    "memory_read": ("boundaries", "memory_read"),
    "memory_write": ("boundaries", "memory_write"),
    "record_call": ("boundaries", "record_call"),
    # Callback object
    "AgentTape": ("callbacks", "AgentTape"),
    # Data model
    "Cassette": ("schema", "Cassette"),
    "Interaction": ("schema", "Interaction"),
    "Config": ("config", "Config"),
    # Errors
    "AgentTapeError": ("errors", "AgentTapeError"),
    "UnmatchedInteractionError": ("errors", "UnmatchedInteractionError"),
    "CassetteCorruptError": ("errors", "CassetteCorruptError"),
    "CassetteNotFoundError": ("errors", "CassetteNotFoundError"),
    "SchemaVersionError": ("errors", "SchemaVersionError"),
    "ConfigError": ("errors", "ConfigError"),
    "DeterminismDriftWarning": ("errors", "DeterminismDriftWarning"),
    "StreamingReplayError": ("errors", "StreamingReplayError"),
    "StreamingNotRecordedWarning": ("errors", "StreamingNotRecordedWarning"),
}


def __getattr__(name: str) -> Any:
    target = _LAZY.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = importlib.import_module(f".{target[0]}", __name__)
    value = getattr(module, target[1])
    globals()[name] = value  # cache so subsequent access skips __getattr__
    return value


def __dir__() -> list[str]:
    return sorted(__all__)


__all__ = [  # noqa: RUF022 - grouped by concern for readability, not alphabetised
    "__version__",
    # Core API
    "use_cassette",
    "record",
    "replay",
    "Session",
    "active_session",
    # Boundary helpers
    "tool",
    "retrieval",
    "memory_read",
    "memory_write",
    "record_call",
    # Callback object
    "AgentTape",
    # Data model
    "Cassette",
    "Interaction",
    "Config",
    # Errors
    "AgentTapeError",
    "UnmatchedInteractionError",
    "CassetteCorruptError",
    "CassetteNotFoundError",
    "SchemaVersionError",
    "ConfigError",
    "DeterminismDriftWarning",
    "StreamingReplayError",
    "StreamingNotRecordedWarning",
]
