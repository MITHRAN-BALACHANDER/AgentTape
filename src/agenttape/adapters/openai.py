"""OpenAI adapter — the primary, fully-built adapter.

Patches ``chat.completions.create`` and ``responses.create`` (sync + async) on the
OpenAI Python SDK so each LLM call is recorded/replayed as an ``llm`` interaction.

* The request is the model + messages + tool schema + sampling params.
* The response is recorded via the SDK object's ``model_dump()``.
* On replay the recorded dict is rehydrated back into a real SDK object when the
  SDK is importable, or into an attribute-accessible :class:`~agenttape._box.Box`
  otherwise — so replay works fully offline even without ``openai`` installed.

Streaming responses are passed through untouched (not deterministically
recordable); everything else is captured.
"""

from __future__ import annotations

import functools
import warnings
from collections.abc import Callable
from typing import Any

from .._box import box
from ..errors import StreamingNotRecordedWarning, StreamingReplayError
from ..recorder import active_session
from .base import Adapter, RefCountedPatch

_STREAM_LIVE_MSG = (
    "Streaming OpenAI responses are not captured by AgentTape (a token stream "
    "cannot be recorded deterministically); this call runs live and is NOT added to "
    "the cassette. Record without stream=True if you want it replayed."
)
_STREAM_REPLAY_MSG = (
    "A streaming OpenAI call was made during offline replay, but streaming responses "
    "cannot be replayed deterministically and AgentTape will not silently hit the "
    "network. Re-record this interaction without stream=True, or mark the 'llm' "
    "boundary live (e.g. use_cassette(..., live={'llm'})) to run it for real."
)


def _guard_stream(session: Any) -> None:
    """Allow a streaming pass-through only when the boundary would execute for real.

    In any offline-replay disposition this raises instead of silently calling the
    real API, preserving the "zero network in replay" guarantee.
    """

    if session.engine.executes_for_real("llm", "llm"):
        warnings.warn(_STREAM_LIVE_MSG, StreamingNotRecordedWarning, stacklevel=3)
        return
    raise StreamingReplayError(_STREAM_REPLAY_MSG)


# Request kwargs that are transport/volatile rather than semantic.
_DROP_KEYS = frozenset(
    {"stream", "timeout", "extra_headers", "extra_query", "extra_body", "stream_options"}
)


def _build_request(kind: str, kwargs: dict[str, Any]) -> dict[str, Any]:
    request: dict[str, Any] = {"endpoint": kind}
    for key, value in kwargs.items():
        if key in _DROP_KEYS or value is None:
            continue
        request[key] = value
    return request


def _dump(resp: Any) -> Any:
    if hasattr(resp, "model_dump"):
        try:
            # ``mode="json"`` yields JSON-native primitives (enums -> str, datetimes
            # -> ISO strings) so the recorded form is faithful and re-validates on
            # replay; the plain call is the fallback for objects that reject the kwarg.
            return resp.model_dump(mode="json")
        except TypeError:
            try:
                return resp.model_dump()
            except Exception:  # pragma: no cover - defensive
                pass
        except Exception:  # pragma: no cover - defensive
            pass
    if isinstance(resp, dict):
        return resp
    return resp


def _rehydrate_chat(data: Any) -> Any:
    try:
        from openai.types.chat import ChatCompletion

        return ChatCompletion.model_validate(data)
    except Exception:
        return box(data)


def _rehydrate_response(data: Any) -> Any:
    try:
        from openai.types.responses import Response

        return Response.model_validate(data)
    except Exception:
        return box(data)


def _rehydrate_embeddings(data: Any) -> Any:
    try:
        from openai.types import CreateEmbeddingResponse

        return CreateEmbeddingResponse.model_validate(data)
    except Exception:
        return box(data)


def _extract_usage(result: Any) -> dict[str, Any] | None:
    usage = result.get("usage") if isinstance(result, dict) else getattr(result, "usage", None)
    if usage is None:
        return None
    if hasattr(usage, "model_dump"):
        try:
            return dict(usage.model_dump())
        except Exception:  # pragma: no cover
            return None
    if isinstance(usage, dict):
        return usage
    return None


def _route(
    orig: Callable[..., Any],
    self_obj: Any,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    *,
    kind: str,
    rehydrate: Callable[[Any], Any],
) -> Any:
    session = active_session()
    if session is None:
        return orig(self_obj, *args, **kwargs)
    if kwargs.get("stream"):
        _guard_stream(session)
        return orig(self_obj, *args, **kwargs)
    kwargs = _apply_model_override(session, kwargs)
    session.set_meta(framework="openai", model=kwargs.get("model"))
    request = _build_request(kind, kwargs)

    def executor() -> Any:
        return _dump(orig(self_obj, *args, **kwargs))

    result = session.engine.intercept(
        "llm", request, boundary="llm", executor=executor, usage_extractor=_extract_usage
    )
    return rehydrate(result) if isinstance(result, dict) else result


async def _aroute(
    orig: Callable[..., Any],
    self_obj: Any,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    *,
    kind: str,
    rehydrate: Callable[[Any], Any],
) -> Any:
    session = active_session()
    if session is None:
        return await orig(self_obj, *args, **kwargs)
    if kwargs.get("stream"):
        _guard_stream(session)
        return await orig(self_obj, *args, **kwargs)
    kwargs = _apply_model_override(session, kwargs)
    session.set_meta(framework="openai", model=kwargs.get("model"))
    request = _build_request(kind, kwargs)

    async def executor() -> Any:
        return _dump(await orig(self_obj, *args, **kwargs))

    result = await session.engine.aintercept(
        "llm", request, boundary="llm", executor=executor, usage_extractor=_extract_usage
    )
    return rehydrate(result) if isinstance(result, dict) else result


def _apply_model_override(session: Any, kwargs: dict[str, Any]) -> dict[str, Any]:
    """Apply ``model_override`` from config for replay-with-different-model runs.

    This genuinely changes the model sent to the API (a real re-execution, not
    deterministic replay), consistent with the honest framing in the docs.
    """

    override = getattr(session.config, "model_override", None)
    if override and "model" in kwargs and kwargs["model"] != override:
        return {**kwargs, "model": override}
    return kwargs


class OpenAIAdapter(Adapter):
    name = "openai"

    def __init__(self) -> None:
        self._patch = RefCountedPatch()

    def available(self) -> bool:
        try:
            import openai  # noqa: F401
        except Exception:
            return False
        return True

    def install(self, session: Any) -> None:
        self._patch.acquire(self._do_install)

    def uninstall(self) -> None:
        self._patch.release()

    def _do_install(self) -> list[Callable[[], None]]:
        restores: list[Callable[[], None]] = []
        restores += self._patch_target(
            "openai.resources.chat.completions",
            ["Completions", "AsyncCompletions"],
            kind="chat.completions",
            rehydrate=_rehydrate_chat,
        )
        restores += self._patch_target(
            "openai.resources.responses",
            ["Responses", "AsyncResponses"],
            kind="responses",
            rehydrate=_rehydrate_response,
        )
        restores += self._patch_target(
            "openai.resources.embeddings",
            ["Embeddings", "AsyncEmbeddings"],
            kind="embeddings",
            rehydrate=_rehydrate_embeddings,
        )
        return restores

    def _patch_target(
        self,
        module_path: str,
        class_names: list[str],
        *,
        kind: str,
        rehydrate: Callable[[Any], Any],
    ) -> list[Callable[[], None]]:
        restores: list[Callable[[], None]] = []
        try:
            module = __import__(module_path, fromlist=class_names)
        except Exception:
            return restores
        for class_name in class_names:
            cls = getattr(module, class_name, None)
            if cls is None or not hasattr(cls, "create"):
                continue
            original = cls.create
            is_async = class_name.startswith("Async")
            if is_async:

                @functools.wraps(original)  # type: ignore
                async def wrapper(  # type: ignore
                    self_obj: Any,
                    *args: Any,
                    __orig: Callable[..., Any] = original,
                    __kind: str = kind,
                    __rehydrate: Callable[[Any], Any] = rehydrate,
                    **kwargs: Any,
                ) -> Any:
                    return await _aroute(
                        __orig, self_obj, args, kwargs, kind=__kind, rehydrate=__rehydrate
                    )

            else:

                @functools.wraps(original)  # type: ignore
                def wrapper(  # type: ignore
                    self_obj: Any,
                    *args: Any,
                    __orig: Callable[..., Any] = original,
                    __kind: str = kind,
                    __rehydrate: Callable[[Any], Any] = rehydrate,
                    **kwargs: Any,
                ) -> Any:
                    return _route(
                        __orig, self_obj, args, kwargs, kind=__kind, rehydrate=__rehydrate
                    )

            cls.create = wrapper  # type: ignore[method-assign]
            restores.append(_restorer(cls, "create", original))
        return restores


def _restorer(cls: Any, name: str, original: Any) -> Callable[[], None]:
    def restore() -> None:
        setattr(cls, name, original)

    return restore
