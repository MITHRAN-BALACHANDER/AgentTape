"""The interception engine — matching, recording, replay and the side-effect guardrail.

The engine is framework-agnostic: adapters hand it ``(kind, request, boundary,
executor)`` and it decides whether to **replay** a recorded response or **execute**
the real boundary, according to the cassette mode and the mixed-replay ``live`` /
``frozen`` sets. It never silently runs a side effect: a non-live boundary with no
recording raises :class:`UnmatchedInteractionError`.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

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
        # Per-kind ordinal counter for ordered matching context.
        self._ordinal: dict[tuple[str, str], int] = {}

        self._index = self._build_index() if not self.flags.ignore_existing else {}

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
    ) -> Any:
        """Replay or execute a boundary crossing and return its response.

        Raises :class:`UnmatchedInteractionError` if a non-live boundary has no
        recording (the side-effect guardrail).
        """

        boundary = boundary or kind
        live = self._is_live(kind, boundary)
        match_key = self._key_for(request)

        if not live and self.flags.replay_existing:
            slot = self._find_match(kind, boundary, match_key)
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
            kind, request, boundary, executor, match_key, usage=usage, tags=tags
        )

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

    def _build_index(self) -> dict[tuple[str, str, str], list[_RecordedSlot]]:
        index: dict[tuple[str, str, str], list[_RecordedSlot]] = {}
        matcher = self.matchers[0] if self.matchers else None
        for interaction in self.recorded.interactions:
            boundary = interaction.boundary or interaction.kind
            if matcher is not None and not is_ordered(matcher):
                key = matcher.key(interaction.request, self.ignore_fields)
            else:
                key = interaction.match_key or matcher.key(interaction.request, self.ignore_fields) if matcher else interaction.match_key
            slot = _RecordedSlot(interaction)
            index.setdefault((interaction.kind, boundary, key), []).append(slot)
            # Also index by stored match_key so hand-written keys still resolve.
            if interaction.match_key and interaction.match_key != key:
                index.setdefault(
                    (interaction.kind, boundary, interaction.match_key), []
                ).append(slot)
        return index

    def _find_match(self, kind: str, boundary: str, key: str) -> _RecordedSlot | None:
        matcher = self.matchers[0]
        if is_ordered(matcher):
            # Pure order: consume the next unconsumed of this (kind, boundary).
            for slots in self._slots_for_kind(kind, boundary):
                for slot in slots:
                    if not slot.consumed:
                        return slot
            return None
        slots = self._index.get((kind, boundary, key))
        if slots:
            for slot in slots:
                if not slot.consumed:
                    return slot
        return None

    def _slots_for_kind(self, kind: str, boundary: str) -> Iterable[list[_RecordedSlot]]:
        for (k, b, _key), slots in self._index.items():
            if k == kind and b == boundary:
                yield slots

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
    ) -> Any:
        start = time.perf_counter()  # perf_counter is never frozen
        error: dict[str, Any] | None = None
        response: Any = None
        try:
            response = executor()
        except BaseException as exc:  # noqa: BLE001 - we record then re-raise
            error = _serialize_exception(exc)
            latency = (time.perf_counter() - start) * 1000.0
            interaction = Interaction(
                index=0,
                kind=kind,
                request=request,
                error=error,
                match_key=match_key,
                latency_ms=round(latency, 3),
                boundary=boundary,
                tags=tags or [],
            )
            self.executed.append(interaction)
            self.timeline.append(interaction)
            raise
        latency = (time.perf_counter() - start) * 1000.0
        interaction = Interaction(
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
        self.executed.append(interaction)
        self.timeline.append(interaction)
        return response

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

    def _closest(
        self, kind: str, boundary: str, canonical: Any
    ) -> tuple[Any, list[FieldDiff]]:
        best: Interaction | None = None
        best_diffs: list[FieldDiff] = []
        best_score = -1
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


def _to_jsonable(obj: Any) -> Any:
    """Best-effort conversion of an arbitrary response to a JSON-like structure."""

    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, dict):
        return {str(k): _to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_jsonable(v) for v in obj]
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if hasattr(obj, "model_dump"):
        try:
            return _to_jsonable(obj.model_dump())
        except Exception:  # pragma: no cover
            pass
    if hasattr(obj, "to_dict"):
        try:
            return _to_jsonable(obj.to_dict())
        except Exception:  # pragma: no cover
            pass
    if hasattr(obj, "__dict__"):
        return {
            str(k): _to_jsonable(v)
            for k, v in vars(obj).items()
            if not k.startswith("_")
        }
    return str(obj)


def _serialize_exception(exc: BaseException) -> dict[str, Any]:
    return {
        "type": type(exc).__name__,
        "module": type(exc).__module__,
        "message": str(exc),
        "repr": repr(exc),
    }


def _raise_recorded_error(error: dict[str, Any]) -> None:
    import builtins

    type_name = error.get("type", "ReplayedError")
    message = error.get("message", "")
    exc_cls: type[BaseException] = RuntimeError
    candidate = getattr(builtins, type_name, None)
    if isinstance(candidate, type) and issubclass(candidate, BaseException):
        exc_cls = candidate
    raise exc_cls(message)


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
