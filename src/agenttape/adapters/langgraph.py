"""LangGraph adapter — graph-state checkpoint capture.

LangGraph runs a graph of nodes; LLM and tool calls inside nodes already flow
through the OpenAI / httpx transport adapters (so they replay for free). This
adapter adds the piece unique to LangGraph:

* **Graph-state checkpoints** — each ``Pregel.invoke`` call is wrapped and its final
  state recorded as a ``memory_write`` interaction (boundary ``graph_state``),
  enabling state/memory diffs between runs.

``Pregel.stream`` is intentionally **not** checkpointed: it yields a sequence of
partial states through a generator, which cannot be captured as a single
deterministic ``memory_write`` without exhausting the stream out from under the
caller. ``.stream`` runs normally; the LLM/tool calls inside it still record and
replay through the transport adapters, so determinism is preserved.

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
        """Wrap ``Pregel.invoke`` to checkpoint final graph state as memory_write.

        ``.stream`` is deliberately left untouched (see the module docstring): it
        cannot be captured deterministically without consuming the caller's generator.
        """

        try:
            from langgraph.pregel import Pregel  # type: ignore
        except Exception:
            return []

        restores: list[Callable[[], None]] = []
        for method_name in ("invoke",):
            original = getattr(Pregel, method_name, None)
            if original is None:
                continue

            @functools.wraps(original)  # type: ignore
            def wrapper(  # type: ignore
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
