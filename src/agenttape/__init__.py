"""AgentTape — VCR.py for AI agents.

Deterministic record / replay of an agent's external interactions (LLM calls and
tool calls) into human-readable cassettes, so agent tests run offline, for free,
with zero side effects.

Quickstart::

    import agenttape

    with agenttape.use_cassette("hello", mode="record"):
        run_agent()                      # records real calls

    with agenttape.use_cassette("hello", mode="none"):
        run_agent()                      # replays, zero network, deterministic
"""

from __future__ import annotations

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
    UnmatchedInteractionError,
)
from .recorder import Session, active_session, record, replay, use_cassette
from .schema import Cassette, Interaction

try:  # populated from package metadata when installed
    from importlib.metadata import version as _version

    __version__ = _version("agenttape")
except Exception:  # pragma: no cover - editable/source tree fallback
    __version__ = "0.1.0"

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
]
