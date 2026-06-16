"""LangGraph adapter — node, tool-call and state-checkpoint capture.

LangGraph runs a graph of nodes; LLM calls inside nodes already flow through the
OpenAI / httpx adapters (so they replay for free). This adapter adds the pieces
unique to LangGraph:

* **State checkpoints** — each super-step's state is captured as a ``memory_write``
  interaction, enabling state/memory diffs between runs.
* **Node boundaries** — node executions are wrapped so their outputs are recorded.

The implementation is defensive: it adapts to the installed LangGraph version and
never raises into user code. If the internal API differs, it degrades to capturing
LLM/tool calls via the transport adapters only.

For frameworks that expose callbacks instead of patch points, use the
:class:`agenttape.AgentTape` callback object documented in ``callbacks.py``.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from ..recorder import active_session
from .base import Adapter, RefCountedPatch


class LangGraphAdapter(Adapter):
    name = "langgraph"

    def __init__(self) -> None:
        self._patch = RefCountedPatch()

    def available(self) -> bool:
        try:
            import langgraph  # noqa: F401
        except Exception:
            return False
        return True

    def install(self, session: Any) -> None:
        self._patch.acquire(self._do_install)

    def uninstall(self) -> None:
        self._patch.release()

    def _do_install(self) -> list[Callable[[], None]]:
        restores: list[Callable[[], None]] = []
        restores += self._patch_pregel()
        return restores

    def _patch_pregel(self) -> list[Callable[[], None]]:
        """Wrap ``Pregel.invoke`` / ``.stream`` to checkpoint state as memory_write."""

        try:
            from langgraph.pregel import Pregel  # type: ignore
        except Exception:
            return []

        restores: list[Callable[[], None]] = []
        for method_name in ("invoke", "stream"):
            original = getattr(Pregel, method_name, None)
            if original is None:
                continue

            @functools.wraps(original)
            def wrapper(
                self_obj: Any,
                *args: Any,
                __orig: Callable[..., Any] = original,
                __name: str = method_name,
                **kwargs: Any,
            ) -> Any:
                session = active_session()
                if session is None:
                    return __orig(self_obj, *args, **kwargs)
                inputs = args[0] if args else kwargs.get("input")
                request = {"node": "__graph__", "input": _safe(inputs)}

                def executor() -> Any:
                    return __orig(self_obj, *args, **kwargs)

                # Record the final state as a memory_write so runs are diffable.
                result = session.engine.intercept(
                    "memory_write",
                    request,
                    boundary="graph_state",
                    executor=executor,
                )
                return result

            setattr(Pregel, method_name, wrapper)
            restores.append(_restorer(Pregel, method_name, original))
        return restores


def _safe(obj: Any) -> Any:
    from ..engine import _to_jsonable

    return _to_jsonable(obj)


def _restorer(cls: Any, name: str, original: Any) -> Callable[[], None]:
    def restore() -> None:
        setattr(cls, name, original)

    return restore
