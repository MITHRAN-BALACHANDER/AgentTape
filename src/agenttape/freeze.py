"""Determinism freeze layer: clock, RNG, UUID and environment snapshots.

Agents frequently embed nondeterminism — timestamps in prompts, ``uuid4()`` request
ids, ``random``-driven sampling. Left unchecked these make recordings differ from
run to run and break replay matching. The freeze layer pins them to recorded values.

Each feature is opt-in per cassette (``freeze=["clock", "uuid", "random"]``) and on
by default in ``mode="none"``. The recorded base values live in ``cassette.meta``
under ``freeze`` so replay reproduces them byte-for-byte across machines.

Concurrency: the global callables (``time.time``, ``datetime``, ``uuid.uuid4``) are
patched **once** via a reference-counted, lock-guarded installer, and the patched
functions **dispatch through the freeze controller active in the current context**
(a :class:`~contextvars.ContextVar`). This means two sessions running concurrently
on different threads — or many asyncio tasks under one session — no longer stomp on
each other's patches, and the real callables are never permanently lost. (``random``
seeding and the env snapshot are inherently process-global and remain so; a thread
that does not inherit the freeze context simply sees the real clock, which is safe.)
"""

from __future__ import annotations

import datetime as _dt
import os
import random
import sys
import threading
import time
import uuid
import warnings
from collections.abc import Callable
from contextvars import ContextVar
from typing import Any

from .errors import DeterminismDriftWarning

# The original callables/types we patch — captured once at import.
_REAL_TIME = time.time
_REAL_TIME_NS = time.time_ns
_REAL_DATETIME = _dt.datetime
_REAL_DATE = _dt.date
_REAL_UUID4 = uuid.uuid4

_FROZEN_NAMESPACE = uuid.UUID("a9f1c2d3-0000-4000-8000-000000000000")

# The freeze controller that applies in the current execution context, or None.
_ACTIVE: ContextVar[FreezeController | None] = ContextVar("agenttape_active_freeze", default=None)


class FreezeController:
    """Applies and restores determinism patches for a single cassette session."""

    def __init__(
        self,
        features: set[str],
        *,
        replay: bool,
        state: dict[str, Any] | None = None,
        env_whitelist: tuple[str, ...] = (),
        random_seed: int = 0,
    ) -> None:
        self.features = set(features)
        self.replay = replay
        self.state = dict(state or {})
        self.env_whitelist = env_whitelist
        self.random_seed = int(self.state.get("random_seed", random_seed))
        self._restores: list[Callable[[], None]] = []
        # UUID bookkeeping.
        self._recorded_uuids: list[str] = list(self.state.get("uuids", []))
        self._captured_uuids: list[str] = []
        self._uuid_index = 0
        # Clock bookkeeping.
        self._base_time: float = float(self.state.get("base_time", _REAL_TIME()))
        self._base_iso: str = str(
            self.state.get(
                "base_iso",
                _REAL_DATETIME.fromtimestamp(self._base_time, _dt.timezone.utc).isoformat(),
            )
        )
        # Env bookkeeping.
        self._env_snapshot: dict[str, str] = dict(self.state.get("env", {}))
        # Lifecycle bookkeeping.
        self._token: Any = None
        self._clock_installed = False
        self._uuid_installed = False

    # -- lifecycle --------------------------------------------------------- #

    def __enter__(self) -> FreezeController:
        if "clock" in self.features and not self.replay:
            # Recording: pin the clock to "now" and record that base. We still freeze
            # during record so the agent observes the *same* clock value it will see
            # on replay (cross-run determinism). Latency stays accurate because it is
            # measured with time.perf_counter, which is never patched.
            self._base_time = _REAL_TIME()
            self._base_iso = _REAL_DATETIME.fromtimestamp(
                self._base_time, _dt.timezone.utc
            ).isoformat()
        # Make this controller the one the patched globals dispatch through.
        self._token = _ACTIVE.set(self)
        if "clock" in self.features:
            _install_clock()
            self._clock_installed = True
        if "uuid" in self.features:
            _install_uuid()
            self._uuid_installed = True
        if "random" in self.features:
            self._freeze_random()
        if self.env_whitelist:
            self._handle_env()
        return self

    def __exit__(self, *exc: object) -> None:
        for restore in reversed(self._restores):
            try:
                restore()
            except Exception:  # pragma: no cover - defensive cleanup
                pass
        self._restores.clear()
        if self._uuid_installed:
            _uninstall_uuid()
            self._uuid_installed = False
        if self._clock_installed:
            _uninstall_clock()
            self._clock_installed = False
        if self._token is not None:
            try:
                _ACTIVE.reset(self._token)
            except (ValueError, LookupError):  # pragma: no cover - context mismatch
                _ACTIVE.set(None)
            self._token = None

    # -- serialization ----------------------------------------------------- #

    def meta(self) -> dict[str, Any]:
        """Return the freeze state to persist in ``cassette.meta['freeze']``."""

        data: dict[str, Any] = {"features": sorted(self.features)}
        if "clock" in self.features:
            data["base_time"] = self._base_time
            data["base_iso"] = self._base_iso
        if "random" in self.features:
            data["random_seed"] = self.random_seed
        if "uuid" in self.features:
            data["uuids"] = self._recorded_uuids if self.replay else self._captured_uuids
        if self.env_whitelist:
            data["env"] = self._env_snapshot if self.replay else _read_env(self.env_whitelist)
        return data

    # -- clock dispatch ---------------------------------------------------- #

    def _time(self) -> float:
        return self._base_time

    # -- uuid -------------------------------------------------------------- #

    def _next_uuid(self) -> uuid.UUID:
        if self.replay:
            if self._uuid_index < len(self._recorded_uuids):
                value = self._recorded_uuids[self._uuid_index]
            else:
                # Deterministic fallback for calls beyond what was recorded.
                value = str(uuid.uuid5(_FROZEN_NAMESPACE, str(self._uuid_index)))
            self._uuid_index += 1
            return uuid.UUID(value)
        value = str(_REAL_UUID4())
        self._captured_uuids.append(value)
        return uuid.UUID(value)

    # -- random ------------------------------------------------------------ #

    def _freeze_random(self) -> None:
        state = random.getstate()
        self._restores.append(lambda: random.setstate(state))
        random.seed(self.random_seed)
        self._freeze_numpy()

    def _freeze_numpy(self) -> None:
        if "numpy" not in sys.modules:
            return
        try:
            import numpy as np
        except Exception:  # pragma: no cover
            return
        prev = np.random.get_state()
        self._restores.append(lambda: np.random.set_state(prev))
        np.random.seed(self.random_seed)

    # -- env --------------------------------------------------------------- #

    def _handle_env(self) -> None:
        if self.replay and self._env_snapshot:
            current = _read_env(self.env_whitelist)
            for key, recorded in self._env_snapshot.items():
                now = current.get(key)
                if now != recorded:
                    warnings.warn(
                        f"Environment drift for {key!r}: recorded {recorded!r} but "
                        f"replay sees {now!r}. Determinism may be affected; align the "
                        f"environment or remove {key!r} from env_snapshot.",
                        DeterminismDriftWarning,
                        stacklevel=2,
                    )
        else:
            self._env_snapshot = _read_env(self.env_whitelist)


# --------------------------------------------------------------------------- #
# Global, reference-counted patch installers (context-dispatching)
# --------------------------------------------------------------------------- #

_INSTALL_LOCK = threading.RLock()
_clock_count = 0
_uuid_count = 0
_clock_restores: list[Callable[[], None]] = []
_uuid_restores: list[Callable[[], None]] = []


def _active_clock() -> FreezeController | None:
    fc = _ACTIVE.get()
    return fc if fc is not None and "clock" in fc.features else None


def _dispatch_time() -> float:
    fc = _active_clock()
    return fc._time() if fc is not None else _REAL_TIME()


def _dispatch_time_ns() -> int:
    fc = _active_clock()
    return int(fc._time() * 1e9) if fc is not None else _REAL_TIME_NS()


def _dispatch_uuid4() -> uuid.UUID:
    fc = _ACTIVE.get()
    if fc is not None and "uuid" in fc.features:
        return fc._next_uuid()
    return _REAL_UUID4()


class _FrozenDateTime(_REAL_DATETIME):
    """``datetime`` subclass whose ``now``/``utcnow``/``today`` follow the freeze."""

    @classmethod
    def now(cls, tz: Any = None) -> Any:
        fc = _active_clock()
        if fc is None:
            return _REAL_DATETIME.now(tz)
        moment = _REAL_DATETIME.fromtimestamp(fc._base_time, _dt.timezone.utc)
        return moment.astimezone(tz) if tz is not None else moment.replace(tzinfo=None)

    @classmethod
    def utcnow(cls) -> Any:
        fc = _active_clock()
        if fc is None:
            return _REAL_DATETIME.now(_dt.timezone.utc).replace(tzinfo=None)
        return _REAL_DATETIME.fromtimestamp(fc._base_time, _dt.timezone.utc).replace(tzinfo=None)

    @classmethod
    def today(cls) -> Any:
        fc = _active_clock()
        if fc is None:
            return _REAL_DATETIME.today()
        return _REAL_DATETIME.fromtimestamp(fc._base_time, _dt.timezone.utc).replace(tzinfo=None)


class _FrozenDate(_REAL_DATE):
    """``date`` subclass whose ``today`` follows the freeze."""

    @classmethod
    def today(cls) -> Any:
        fc = _active_clock()
        if fc is None:
            return _REAL_DATE.today()
        return _REAL_DATETIME.fromtimestamp(fc._base_time, _dt.timezone.utc).date()


def _install_clock() -> None:
    global _clock_count
    with _INSTALL_LOCK:
        if _clock_count == 0:
            _clock_restores.extend(_patch_clock_globals())
        _clock_count += 1


def _uninstall_clock() -> None:
    global _clock_count
    with _INSTALL_LOCK:
        if _clock_count == 0:
            return
        _clock_count -= 1
        if _clock_count == 0:
            _run_restores(_clock_restores)


def _install_uuid() -> None:
    global _uuid_count
    with _INSTALL_LOCK:
        if _uuid_count == 0:
            original = uuid.uuid4
            setattr(uuid, "uuid4", _dispatch_uuid4)  # noqa: B010 - dynamic patch target
            _uuid_restores.append(_restorer(uuid, "uuid4", original))
        _uuid_count += 1


def _uninstall_uuid() -> None:
    global _uuid_count
    with _INSTALL_LOCK:
        if _uuid_count == 0:
            return
        _uuid_count -= 1
        if _uuid_count == 0:
            _run_restores(_uuid_restores)


def _patch_clock_globals() -> list[Callable[[], None]]:
    restores: list[Callable[[], None]] = []

    def patch(target: Any, name: str, replacement: Any) -> None:
        original = getattr(target, name)
        setattr(target, name, replacement)
        restores.append(_restorer(target, name, original))

    patch(time, "time", _dispatch_time)
    patch(time, "time_ns", _dispatch_time_ns)
    # NB: time.monotonic / monotonic_ns are deliberately NOT frozen. Like
    # time.perf_counter they are *duration* clocks, and schedulers depend on them
    # advancing in real time — asyncio computes its timer deadlines from
    # loop.time() == time.monotonic(), so freezing it makes ``await asyncio.sleep``
    # (and any monotonic-based timeout) wait forever. Only the wall clock
    # (time.time / datetime) needs pinning for deterministic recorded timestamps.
    # Replace the real datetime/date classes in every already-imported module that
    # holds a direct reference (freezegun-lite). The frozen classes dispatch through
    # the active controller, so this single set of classes serves every session.
    #
    # Bind the comparison targets to locals and skip this module: the scan would
    # otherwise reassign our own ``_REAL_DATETIME`` / ``_REAL_DATE`` constants (they
    # *are* the real classes), which both breaks the ``is`` test for every module
    # visited afterwards and corrupts the constants the dispatch methods rely on.
    real_dt, real_date = _REAL_DATETIME, _REAL_DATE
    this_module = sys.modules.get(__name__)
    for module in list(sys.modules.values()):
        if module is None or module is this_module:
            continue
        try:
            members = list(vars(module).items())
        except TypeError:  # pragma: no cover - some modules disallow vars()
            continue
        for name, value in members:
            if value is real_dt:
                _try_swap(module, name, _FrozenDateTime, restores)
            elif value is real_date:
                _try_swap(module, name, _FrozenDate, restores)
    return restores


def _try_swap(module: Any, name: str, replacement: Any, restores: list[Callable[[], None]]) -> None:
    try:
        original = getattr(module, name)
        setattr(module, name, replacement)
        restores.append(_restorer(module, name, original))
    except Exception:  # pragma: no cover - read-only attrs
        return


def _run_restores(restores: list[Callable[[], None]]) -> None:
    for restore in reversed(restores):
        try:
            restore()
        except Exception:  # pragma: no cover - defensive cleanup
            pass
    restores.clear()


def _restorer(target: Any, name: str, original: Any) -> Callable[[], None]:
    def restore() -> None:
        setattr(target, name, original)

    return restore


def _read_env(whitelist: tuple[str, ...]) -> dict[str, str]:
    return {key: os.environ[key] for key in whitelist if key in os.environ}


def default_features(config_freeze: tuple[str, ...], mode: str) -> set[str]:
    """Determine which freeze features apply for a mode.

    Freezing is on by default in ``mode="none"`` (offline replay) and off otherwise
    unless explicitly configured.
    """

    if config_freeze:
        return set(config_freeze)
    if mode == "none":
        return {"clock", "uuid", "random"}
    return set()
