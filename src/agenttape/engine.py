"""The interception engine — matching, recording, replay and the side-effect guardrail.

The engine is framework-agnostic: adapters hand it ``(kind, request, boundary,
executor)`` and it decides whether to **replay** a recorded response or **execute**
the real boundary, according to the cassette mode and the mixed-replay ``live`` /
``frozen`` sets. It never silently runs a side effect: a non-live boundary with no
recording raises :class:`UnmatchedInteractionError`.
"""

from __future__ import annotations

import datetime as _dt
import enum
import time
import uuid as _uuid
from collections.abc import Callable, Iterable
from contextvars import ContextVar
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .canonical import canonicalize
from .errors import FieldDiff, UnmatchedInteractionError
from .matchers import Matcher, is_ordered, resolve_matchers
from .schema import Cassette, Interaction

Executor = Callable[[], Any]


@dataclass
class _RecordedSlot:
    interaction: Interaction
    consumed: bool = False


@dataclass
class ModeFlags:
    replay_existing: bool
    record_new: bool
    ignore_existing: bool

    @classmethod
    def for_mode(cls, mode: str, cassette_existed: bool) -> ModeFlags:
        if mode == "none":
            return cls(replay_existing=True, record_new=False, ignore_existing=False)
        if mode == "once":
            if cassette_existed:
                return cls(replay_existing=True, record_new=False, ignore_existing=False)
            return cls(replay_existing=False, record_new=True, ignore_existing=True)
        if mode == "new_episodes":
            return cls(replay_existing=True, record_new=True, ignore_existing=False)
        if mode in ("all", "record"):
            return cls(replay_existing=False, record_new=True, ignore_existing=True)
        raise ValueError(f"Unknown mode {mode!r}")


class Engine:
    """Core record/replay decision engine for one cassette session."""

    def __init__(
        self,
        *,
        recorded: Cassette,
        mode: str,
        cassette_existed: bool,
        matchers: Iterable[Any] = ("ignore_volatile",),
        ignore_fields: tuple[str, ...] = (),
        live: set[str] | None = None,
        frozen: set[str] | None = None,
        cassette_path: str | None = None,
    ) -> None:
        if live and frozen:
            raise ValueError(
                "Pass either live={...} or frozen={...}, not both. "
                "live = run these for real; frozen = replay only these."
            )
        self.recorded = recorded
        self.mode = mode
        self.flags = ModeFlags.for_mode(mode, cassette_existed)
        self.matchers: list[Matcher] = resolve_matchers(tuple(matchers) or ("ignore_volatile",))
        self.ignore_fields = ignore_fields
        self.live = set(live) if live else None
        self.frozen = set(frozen) if frozen else None
        self.cassette_path = cassette_path

        # Interactions actually executed live this session (for record-back).
        self.executed: list[Interaction] = []
        # The full served timeline (replayed + executed), in call order.
        self.timeline: list[Interaction] = []
        # Re-entrancy guard. While an executor runs we are "inside" a boundary, so a
        # nested interception *in the same logical call* (e.g. the httpx fallback
        # firing during an OpenAI call the openai adapter already wrapped) must pass
        # through instead of double recording. This is tracked with a ContextVar so
        # that **concurrent** calls (asyncio tasks / threads) each carry an
        # independent depth: a sibling task awaiting *its own* executor must never be
        # mistaken for a nested call. A plain instance counter would conflate the two
        # and — during replay — silently execute a concurrent frozen boundary for
        # real, defeating the side-effect guardrail.
        self._depth: ContextVar[int] = ContextVar("agenttape_engine_depth", default=0)

        # Recorded slots indexed in recorded order per (kind, boundary), plus one key
        # index per configured matcher for the fallback chain.
        self._slots_by_kb: dict[tuple[str, str], list[_RecordedSlot]] = {}
        self._key_indexes: list[dict[tuple[str, str, str], list[_RecordedSlot]]] = []
        if not self.flags.ignore_existing:
            self._build_indexes()

    # -- public interception ---------------------------------------------- #

    def intercept(
        self,
        kind: str,
        request: dict[str, Any],
        *,
        boundary: str | None = None,
        executor: Executor | None = None,
        usage: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        usage_extractor: Callable[[Any], dict[str, Any] | None] | None = None,
    ) -> Any:
        """Replay or execute a boundary crossing and return its response.

        Raises :class:`UnmatchedInteractionError` if a non-live boundary has no
        recording (the side-effect guardrail).
        """

        boundary = boundary or kind
        if self._depth.get() > 0:
            # Nested inside *this* logical call's real execution: pass through.
            return executor() if executor is not None else None
        live = self._is_live(kind, boundary)
        match_key = self._key_for(request)

        if not live and self.flags.replay_existing:
            slot = self._find_match(kind, boundary, request)
            if slot is not None:
                slot.consumed = True
                self.timeline.append(slot.interaction)
                return self._reconstruct(slot.interaction)
            if not self.flags.record_new:
                raise self._unmatched(kind, boundary, request, match_key)

        # Either the boundary is live, we are ignoring existing recordings
        # (record/all), or it is a brand-new interaction in a recording mode.
        if executor is None:
            raise self._unmatched(kind, boundary, request, match_key)
        return self._execute_and_record(
            kind,
            request,
            boundary,
            executor,
            match_key,
            usage=usage,
            tags=tags,
            usage_extractor=usage_extractor,
        )

    async def aintercept(
        self,
        kind: str,
        request: dict[str, Any],
        *,
        boundary: str | None = None,
        executor: Callable[[], Any] | None = None,
        usage: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        usage_extractor: Callable[[Any], dict[str, Any] | None] | None = None,
    ) -> Any:
        """Async counterpart to :meth:`intercept` for coroutine boundaries."""

        boundary = boundary or kind
        if self._depth.get() > 0:
            return await executor() if executor is not None else None
        live = self._is_live(kind, boundary)
        match_key = self._key_for(request)

        if not live and self.flags.replay_existing:
            slot = self._find_match(kind, boundary, request)
            if slot is not None:
                slot.consumed = True
                self.timeline.append(slot.interaction)
                return self._reconstruct(slot.interaction)
            if not self.flags.record_new:
                raise self._unmatched(kind, boundary, request, match_key)

        if executor is None:
            raise self._unmatched(kind, boundary, request, match_key)
        return await self._aexecute_and_record(
            kind,
            request,
            boundary,
            executor,
            match_key,
            usage=usage,
            tags=tags,
            usage_extractor=usage_extractor,
        )

    async def _aexecute_and_record(
        self,
        kind: str,
        request: dict[str, Any],
        boundary: str,
        executor: Callable[[], Any],
        match_key: str,
        *,
        usage: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        usage_extractor: Callable[[Any], dict[str, Any] | None] | None = None,
    ) -> Any:
        start = time.perf_counter()
        token = self._depth.set(self._depth.get() + 1)
        try:
            response = await executor()
        except BaseException as exc:
            latency = (time.perf_counter() - start) * 1000.0
            self._append(
                Interaction(
                    index=0,
                    kind=kind,
                    request=request,
                    error=_serialize_exception(exc),
                    match_key=match_key,
                    latency_ms=round(latency, 3),
                    boundary=boundary,
                    tags=tags or [],
                )
            )
            raise
        finally:
            self._depth.reset(token)
        latency = (time.perf_counter() - start) * 1000.0
        if usage is None and usage_extractor is not None:
            usage = _safe_usage(usage_extractor, response)
        self._append(
            Interaction(
                index=0,
                kind=kind,
                request=request,
                response=_to_jsonable(response),
                match_key=match_key,
                latency_ms=round(latency, 3),
                usage=usage,
                boundary=boundary,
                tags=tags or [],
            )
        )
        return response

    # -- output ------------------------------------------------------------ #

    def is_live_session(self) -> bool:
        """True if any boundary executed live this session (a derived cassette)."""

        return bool(self.executed)

    def build_output(self) -> list[Interaction]:
        """Return the interaction list to persist, according to the mode."""

        if self.mode == "new_episodes":
            merged = list(self.recorded.interactions) + list(self.executed)
            return _reindex(merged)
        if self.mode in ("record", "all", "once"):
            # Fresh record (or once-absent): only what executed this session.
            return _reindex(list(self.executed))
        # mode == "none": derived cassette is the full served timeline.
        return _reindex(list(self.timeline))

    # -- live / frozen decision ------------------------------------------- #

    def _is_live(self, kind: str, boundary: str) -> bool:
        if self.frozen is not None:
            return not _token_match(kind, boundary, self.frozen)
        if self.live is not None:
            return _token_match(kind, boundary, self.live)
        return False

    # -- matching ---------------------------------------------------------- #

    def _key_for(self, request: dict[str, Any]) -> str:
        # Use the first matcher to produce the comparison key. Ordered matchers
        # return a constant sentinel so matching falls through to call order.
        matcher = self.matchers[0]
        return matcher.key(request, self.ignore_fields)

    def _build_indexes(self) -> None:
        slots: list[tuple[Interaction, str, _RecordedSlot]] = []
        for interaction in self.recorded.interactions:
            boundary = interaction.boundary or interaction.kind
            slot = _RecordedSlot(interaction)
            self._slots_by_kb.setdefault((interaction.kind, boundary), []).append(slot)
            slots.append((interaction, boundary, slot))
        # One key index per matcher, so the fallback chain can try each in turn.
        for matcher in self.matchers:
            index: dict[tuple[str, str, str], list[_RecordedSlot]] = {}
            if not is_ordered(matcher):
                for interaction, boundary, slot in slots:
                    key = matcher.key(interaction.request, self.ignore_fields)
                    index.setdefault((interaction.kind, boundary, key), []).append(slot)
                    # Also index by stored match_key so hand-written keys (and keys
                    # computed before redaction) still resolve.
                    if interaction.match_key and interaction.match_key != key:
                        index.setdefault(
                            (interaction.kind, boundary, interaction.match_key), []
                        ).append(slot)
            self._key_indexes.append(index)

    def _find_match(
        self, kind: str, boundary: str, request: dict[str, Any]
    ) -> _RecordedSlot | None:
        # Fallback chain: try each configured matcher in order; the first one that
        # resolves to an unconsumed recording wins. With a single matcher (the
        # default) this is exactly the previous keyed-or-ordered behaviour.
        for matcher, index in zip(self.matchers, self._key_indexes, strict=False):
            if is_ordered(matcher):
                slot = self._next_ordered(kind, boundary)
            else:
                key = matcher.key(request, self.ignore_fields)
                slot = _first_unconsumed(index.get((kind, boundary, key)))
            if slot is not None:
                return slot
        return None

    def _next_ordered(self, kind: str, boundary: str) -> _RecordedSlot | None:
        # Pure order: consume the next unconsumed of this (kind, boundary).
        for slot in self._slots_by_kb.get((kind, boundary), []):
            if not slot.consumed:
                return slot
        return None

    # -- execution + recording -------------------------------------------- #

    def _execute_and_record(
        self,
        kind: str,
        request: dict[str, Any],
        boundary: str,
        executor: Executor,
        match_key: str,
        *,
        usage: dict[str, Any] | None = None,
        tags: list[str] | None = None,
        usage_extractor: Callable[[Any], dict[str, Any] | None] | None = None,
    ) -> Any:
        start = time.perf_counter()  # perf_counter is never frozen
        token = self._depth.set(self._depth.get() + 1)
        try:
            response = executor()
        except BaseException as exc:
            latency = (time.perf_counter() - start) * 1000.0
            self._append(
                Interaction(
                    index=0,
                    kind=kind,
                    request=request,
                    error=_serialize_exception(exc),
                    match_key=match_key,
                    latency_ms=round(latency, 3),
                    boundary=boundary,
                    tags=tags or [],
                )
            )
            raise
        finally:
            self._depth.reset(token)
        latency = (time.perf_counter() - start) * 1000.0
        if usage is None and usage_extractor is not None:
            usage = _safe_usage(usage_extractor, response)
        self._append(
            Interaction(
                index=0,
                kind=kind,
                request=request,
                response=_to_jsonable(response),
                match_key=match_key,
                latency_ms=round(latency, 3),
                usage=usage,
                boundary=boundary,
                tags=tags or [],
            )
        )
        return response

    def _append(self, interaction: Interaction) -> None:
        # list.append is atomic under the GIL, so this is safe for the concurrent
        # (asyncio / threaded) recording paths.
        self.executed.append(interaction)
        self.timeline.append(interaction)

    def executes_for_real(self, kind: str, boundary: str | None = None) -> bool:
        """True if a fresh call to this boundary would run live rather than replay.

        Adapters use this to decide whether passing a call through to the real
        service (e.g. a streaming response, which cannot be recorded
        deterministically) is legitimate, or would silently break the offline-replay
        guarantee and must instead raise.
        """

        boundary = boundary or kind
        return self._is_live(kind, boundary) or self.flags.record_new

    # -- replay reconstruction -------------------------------------------- #

    def _reconstruct(self, interaction: Interaction) -> Any:
        if interaction.error is not None:
            _raise_recorded_error(interaction.error)
        return interaction.response

    # -- errors ------------------------------------------------------------ #

    def _unmatched(
        self, kind: str, boundary: str, request: dict[str, Any], match_key: str
    ) -> UnmatchedInteractionError:
        canonical = canonicalize(request, self.ignore_fields)
        closest, field_diffs = self._closest(kind, boundary, canonical)
        return UnmatchedInteractionError(
            kind=kind,
            canonical_request=canonical,
            cassette_path=self.cassette_path,
            closest=closest,
            field_diffs=field_diffs,
            mode=self.mode,
            boundary_name=boundary,
        )

    def _closest(self, kind: str, boundary: str, canonical: Any) -> tuple[Any, list[FieldDiff]]:
        best: Interaction | None = None
        best_diffs: list[FieldDiff] = []
        best_score = float("-inf")
        for interaction in self.recorded.interactions:
            b = interaction.boundary or interaction.kind
            if interaction.kind != kind or b != boundary:
                continue
            rec_canon = canonicalize(interaction.request, self.ignore_fields)
            diffs = diff_fields(rec_canon, canonical)
            score = -len(diffs)
            if score > best_score:
                best_score = score
                best = interaction
                best_diffs = diffs
        if best is None:
            return None, []
        return canonicalize(best.request, self.ignore_fields), best_diffs


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _token_match(kind: str, boundary: str, tokens: set[str]) -> bool:
    return "*" in tokens or boundary in tokens or kind in tokens


def _reindex(interactions: list[Interaction]) -> list[Interaction]:
    out: list[Interaction] = []
    for i, interaction in enumerate(interactions):
        interaction.index = i
        out.append(interaction)
    return out


def _to_jsonable(obj: Any, _seen: frozenset[int] = frozenset()) -> Any:
    """Best-effort conversion of an arbitrary response to a serialisable structure.

    Binary stays ``bytes`` — the cassette I/O layer round-trips it losslessly via the
    assets sidecar (a small inline marker or an external blob), so it must *not* be
    lossily decoded here. Well-known non-JSON scalars (``datetime``, ``Decimal``,
    ``UUID``, ``Enum``, ``set``) are converted to a faithful, stable form rather than
    being dropped. Cyclic object graphs are broken with a placeholder instead of
    overflowing the stack.
    """

    # bool is a subclass of int; both pass through unchanged. bytes are preserved.
    if obj is None or isinstance(obj, (bool, int, float, str, bytes)):
        return obj
    if isinstance(obj, enum.Enum):
        return _to_jsonable(obj.value, _seen)
    if isinstance(obj, (_dt.datetime, _dt.date, _dt.time)):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, _uuid.UUID):
        return str(obj)
    if isinstance(obj, (set, frozenset)):
        return [_to_jsonable(v, _seen) for v in sorted(obj, key=repr)]
    oid = id(obj)
    if oid in _seen:
        return "<cycle>"
    seen = _seen | {oid}
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v, seen) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v, seen) for v in obj]
    if hasattr(obj, "model_dump"):
        try:
            return _to_jsonable(obj.model_dump(), seen)
        except Exception:  # pragma: no cover
            pass
    if hasattr(obj, "to_dict"):
        try:
            return _to_jsonable(obj.to_dict(), seen)
        except Exception:  # pragma: no cover
            pass
    if hasattr(obj, "__dict__"):
        return {
            str(k): _to_jsonable(v, seen) for k, v in vars(obj).items() if not k.startswith("_")
        }
    return str(obj)


# Simple, serialisable attributes worth preserving on replayed SDK errors so that
# ``except RateLimitError as e: e.status_code`` keeps working offline. Only JSON-simple
# values are captured (a real ``httpx.Response`` cannot be reconstructed faithfully).
_ERROR_ATTRS = ("status_code", "code", "param", "type", "request_id", "retry_after")


def _serialize_exception(exc: BaseException) -> dict[str, Any]:
    data: dict[str, Any] = {
        "type": type(exc).__name__,
        "module": type(exc).__module__,
        "message": str(exc),
        "repr": repr(exc),
    }
    attrs: dict[str, Any] = {}
    for name in _ERROR_ATTRS:
        value = getattr(exc, name, None)
        if isinstance(value, (bool, int, float, str)):
            attrs[name] = value
    if attrs:
        data["attrs"] = attrs
    return data


def _safe_usage(
    extractor: Callable[[Any], dict[str, Any] | None], response: Any
) -> dict[str, Any] | None:
    try:
        return extractor(response)
    except Exception:  # pragma: no cover - usage extraction must never break recording
        return None


def _first_unconsumed(slots: list[_RecordedSlot] | None) -> _RecordedSlot | None:
    if not slots:
        return None
    for slot in slots:
        if not slot.consumed:
            return slot
    return None


def _raise_recorded_error(error: dict[str, Any]) -> None:
    type_name = str(error.get("type", "ReplayedError"))
    module_name = str(error.get("module", "builtins"))
    message = error.get("message", "")
    exc_cls = _resolve_exception_class(module_name, type_name)
    exc = _instantiate_exception(exc_cls, message, type_name)
    attrs = error.get("attrs")
    if isinstance(attrs, dict):
        for name, value in attrs.items():
            try:
                setattr(exc, name, value)
            except Exception:  # pragma: no cover - read-only/slotted attributes
                pass
    raise exc


def _resolve_exception_class(module_name: str, type_name: str) -> type[BaseException]:
    """Resolve a recorded exception back to its real class when importable.

    Builtins are resolved first; otherwise the recorded module is imported (a local
    operation, never a network call) so a replayed ``openai.RateLimitError`` or a
    user-defined exception is raised as its true type — which is what ``except`` /
    ``pytest.raises`` clauses match on. Falls back to ``RuntimeError`` if the type
    cannot be located.
    """

    import builtins
    import importlib

    candidate = getattr(builtins, type_name, None)
    if isinstance(candidate, type) and issubclass(candidate, BaseException):
        return candidate
    if module_name and module_name not in ("builtins", "__builtin__"):
        try:
            module = importlib.import_module(module_name)
        except Exception:
            module = None
        if module is not None:
            candidate = getattr(module, type_name, None)
            if isinstance(candidate, type) and issubclass(candidate, BaseException):
                return candidate
    return RuntimeError


def _instantiate_exception(
    exc_cls: type[BaseException], message: Any, type_name: str
) -> BaseException:
    """Best-effort construction of ``exc_cls`` with ``message``.

    Some library exceptions require keyword-only constructor args (e.g. the OpenAI
    SDK errors need a ``response``); when the simple call fails we bypass ``__init__``
    so the replayed error still carries the correct *type* even if not every field is
    reconstructed. As a last resort a ``RuntimeError`` preserves the original name.
    """

    try:
        return exc_cls(message)
    except Exception:
        pass
    try:
        exc = exc_cls.__new__(exc_cls)
        BaseException.__init__(exc, message)
        return exc
    except Exception:  # pragma: no cover - exotic exception types
        return RuntimeError(f"{type_name}: {message}")


def diff_fields(expected: Any, received: Any, path: str = "") -> list[FieldDiff]:
    """Return leaf-level differences between two JSON-like structures."""

    diffs: list[FieldDiff] = []
    if isinstance(expected, dict) and isinstance(received, dict):
        for key in sorted(set(expected) | set(received)):
            child = f"{path}.{key}" if path else str(key)
            if key not in expected:
                diffs.append(FieldDiff(child, "<absent>", received[key]))
            elif key not in received:
                diffs.append(FieldDiff(child, expected[key], "<absent>"))
            else:
                diffs.extend(diff_fields(expected[key], received[key], child))
    elif isinstance(expected, list) and isinstance(received, list):
        for i in range(max(len(expected), len(received))):
            child = f"{path}[{i}]"
            if i >= len(expected):
                diffs.append(FieldDiff(child, "<absent>", received[i]))
            elif i >= len(received):
                diffs.append(FieldDiff(child, expected[i], "<absent>"))
            else:
                diffs.extend(diff_fields(expected[i], received[i], child))
    elif expected != received:
        diffs.append(FieldDiff(path or "<root>", expected, received))
    return diffs
