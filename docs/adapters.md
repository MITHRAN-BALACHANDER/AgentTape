# Writing an adapter

AgentTape's core is framework-agnostic. Adapters translate a framework's native
events into the internal schema by routing boundary crossings through the active
session's engine. They keep third-party imports lazy so the core stays
dependency-free.

## Built-in adapters

| Adapter | Status |
|---------|--------|
| OpenAI (chat + responses + tool calling, sync + async) | full |
| LangGraph (graph-state checkpoints; LLM/tool calls via the transport adapters) | built-in |
| `httpx` / `requests` fallback | always on |
| LangChain · LlamaIndex · CrewAI · AutoGen · MCP | extension points |

The raw HTTP fallback captures **any** SDK built on httpx/requests, so unknown
frameworks still record and replay.

## Internal event vocabulary

Adapters map native callbacks onto these events:

```text
RUN_STARTED · RUN_FINISHED · LLM_REQUEST · LLM_RESPONSE · TOOL_START · TOOL_END ·
RETRIEVAL · MEMORY_READ · MEMORY_WRITE · PLANNER · SYSTEM_PROMPT · USER_MESSAGE ·
ERROR · RETRY · HUMAN_APPROVAL
```

## The extension interface

```python
from agenttape import active_session
from agenttape.adapters import Adapter, RefCountedPatch, register


class MyAdapter(Adapter):
    name = "myframework"

    def __init__(self) -> None:
        self._patch = RefCountedPatch()

    def available(self) -> bool:
        try:
            import myframework  # noqa: F401
        except Exception:
            return False
        return True

    def install(self, session) -> None:
        self._patch.acquire(self._do_install)

    def uninstall(self) -> None:
        self._patch.release()

    def _do_install(self):
        import myframework
        original = myframework.Client.call

        def patched(self, *args, **kwargs):
            session = active_session()
            if session is None:               # outside a session → pass through
                return original(self, *args, **kwargs)
            request = {"args": args, "kwargs": kwargs}
            return session.engine.intercept(
                "tool", request, boundary="myframework",
                executor=lambda: original(self, *args, **kwargs),
            )

        myframework.Client.call = patched
        return [lambda: setattr(myframework.Client, "call", original)]


register(MyAdapter())
```

## Key rules

- Patch with **reference counting** so nested sessions share one patch and route to
  whichever session is active at call time.
- Inside a patched callable, fetch `active_session()`; if `None`, call the original.
- Pass an `executor` that performs the real call. The engine decides whether to run
  it (record / live) or serve a recorded response (replay).
- Return the same shape on both paths (rehydrate replayed dicts into SDK objects if
  the SDK is installed). See `adapters/openai.py` for a reference implementation.

## Callback-based frameworks

For frameworks that expose callbacks instead of patch points (LangChain, …), use the
`agenttape.AgentTape()` listener object. Note callbacks are observational — they can
**record** but cannot substitute a return value, so deterministic **replay** still
relies on the transport-level adapters.
