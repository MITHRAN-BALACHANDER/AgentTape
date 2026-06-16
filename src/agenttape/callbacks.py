"""The ``AgentTape`` callback/hook object — the third interception mechanism.

Some frameworks (LangChain, LlamaIndex, CrewAI) expose *callbacks/listeners* rather
than letting you patch their client. ``AgentTape`` is a duck-typed callback handler
implementing the common ``on_*`` method names; pass an instance into such a
framework and it will record LLM/tool/retrieval boundaries into the active session.

Note (honest framing): callbacks are *observational* — a framework calls them after
the fact and does not let the handler substitute a return value. So the callback
object is primarily for **recording** and event normalisation. Deterministic
**replay** still relies on the transport-level adapters (OpenAI / httpx / requests),
which can actually serve a recorded response in place of a real call.
"""

from __future__ import annotations

import time
from typing import Any

from .events import (
    LLM_REQUEST,
    RETRIEVAL,
    RUN_FINISHED,
    RUN_STARTED,
    TOOL_START,
)
from .recorder import active_session
from .schema import Interaction


class AgentTape:
    """A framework-agnostic callback/listener that records into the active session."""

    def __init__(self, *, tag: str | None = None) -> None:
        self.tag = tag
        self._starts: dict[Any, float] = {}
        self.events: list[dict[str, Any]] = []

    # -- generic event sink ------------------------------------------------ #

    def emit(self, event: str, **payload: Any) -> None:
        """Record a normalised internal event (for inspection/timeline)."""

        self.events.append({"event": event, **payload})

    def _record(
        self,
        kind: str,
        request: dict[str, Any],
        response: Any,
        *,
        boundary: str | None = None,
        latency_ms: float | None = None,
        usage: dict[str, Any] | None = None,
    ) -> None:
        session = active_session()
        if session is None:
            return
        interaction = Interaction(
            index=0,
            kind=kind,
            request=request,
            response=response,
            boundary=boundary or kind,
            latency_ms=latency_ms,
            usage=usage,
            tags=[self.tag] if self.tag else [],
        )
        # Append to both the executed and timeline buffers so it persists when the
        # session writes a cassette in a recording mode.
        session.engine.executed.append(interaction)
        session.engine.timeline.append(interaction)

    # -- LangChain-style handler methods ----------------------------------- #

    def on_chain_start(self, serialized: Any, inputs: Any, **kwargs: Any) -> None:
        self.emit(RUN_STARTED, inputs=_jsonable(inputs))

    def on_chain_end(self, outputs: Any, **kwargs: Any) -> None:
        self.emit(RUN_FINISHED, outputs=_jsonable(outputs))

    def on_llm_start(self, serialized: Any, prompts: Any, **kwargs: Any) -> None:
        run_id = kwargs.get("run_id", id(prompts))
        self._starts[run_id] = time.perf_counter()
        self.emit(LLM_REQUEST, prompts=_jsonable(prompts))

    def on_llm_end(self, response: Any, **kwargs: Any) -> None:
        run_id = kwargs.get("run_id")
        latency = self._latency(run_id)
        self._record(
            "llm",
            {"prompts": "<via-callback>"},
            _jsonable(response),
            boundary="llm",
            latency_ms=latency,
        )

    def on_tool_start(self, serialized: Any, input_str: Any, **kwargs: Any) -> None:
        run_id = kwargs.get("run_id", id(input_str))
        self._starts[run_id] = time.perf_counter()
        name = (serialized or {}).get("name", "tool") if isinstance(serialized, dict) else "tool"
        self.emit(TOOL_START, name=name, input=_jsonable(input_str))

    def on_tool_end(self, output: Any, **kwargs: Any) -> None:
        run_id = kwargs.get("run_id")
        name = kwargs.get("name", "tool")
        latency = self._latency(run_id)
        self._record(
            "tool",
            {"name": name},
            _jsonable(output),
            boundary=name,
            latency_ms=latency,
        )

    def on_retriever_start(self, serialized: Any, query: Any, **kwargs: Any) -> None:
        run_id = kwargs.get("run_id", id(query))
        self._starts[run_id] = time.perf_counter()
        self.emit(RETRIEVAL, query=_jsonable(query))

    def on_retriever_end(self, documents: Any, **kwargs: Any) -> None:
        run_id = kwargs.get("run_id")
        latency = self._latency(run_id)
        self._record(
            "retrieval",
            {"query": "<via-callback>"},
            _jsonable(documents),
            boundary="retrieval",
            latency_ms=latency,
        )

    # -- helpers ----------------------------------------------------------- #

    def _latency(self, run_id: Any) -> float | None:
        start = self._starts.pop(run_id, None)
        if start is None:
            return None
        return round((time.perf_counter() - start) * 1000.0, 3)


def _jsonable(obj: Any) -> Any:
    from .engine import _to_jsonable

    return _to_jsonable(obj)


__all__ = ["AgentTape"]
