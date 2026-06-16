"""Determinism freeze layer: clock, RNG, UUID and environment snapshots.

Agents frequently embed nondeterminism — timestamps in prompts, ``uuid4()`` request
ids, ``random``-driven sampling. Left unchecked these make recordings differ from
run to run and break replay matching. The freeze layer pins them to recorded values.

Each feature is opt-in per cassette (``freeze=["clock", "uuid", "random"]``) and on
by default in ``mode="none"``. The recorded base values live in ``cassette.meta``
under ``freeze`` so replay reproduces them byte-for-byte across machines.
"""

from __future__ import annotations

import datetime as _dt
import os
import random
import sys
import time
import uuid
import warnings
from collections.abc import Callable
from typing import Any

from .errors import DeterminismDriftWarning

# The original callables/types we patch — captured once at import.
_REAL_TIME = time.time
_REAL_MONOTONIC = time.monotonic
_REAL_TIME_NS = time.time_ns
_REAL_MONOTONIC_NS = time.monotonic_ns
_REAL_DATETIME = _dt.datetime
_REAL_DATE = _dt.date
_REAL_UUID4 = uuid.uuid4

_FROZEN_NAMESPACE = uuid.UUID("a9f1c2d3-0000-4000-8000-000000000000")


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
            self.state.get("base_iso", _REAL_DATETIME.fromtimestamp(self._base_time, _dt.timezone.utc).isoformat())
        )
        self._mono_counter = 0.0
        # Env bookkeeping.
        self._env_snapshot: dict[str, str] = dict(self.state.get("env", {}))

    # -- lifecycle --------------------------------------------------------- #

    def __enter__(self) -> FreezeController:
        if "clock" in self.features:
            self._freeze_clock()
        if "random" in self.features:
            self._freeze_random()
        if "uuid" in self.features:
            self._freeze_uuid()
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

    # -- clock ------------------------------------------------------------- #

    def _freeze_clock(self) -> None:
        if not self.replay:
            # Recording: pin the clock to "now" and record that base. We still freeze
            # during record so the agent observes the *same* clock value it will see
            # on replay (cross-run determinism). Latency stays accurate because it is
            # measured with time.perf_counter, which is never patched.
            self._base_time = _REAL_TIME()
            self._base_iso = _REAL_DATETIME.fromtimestamp(
                self._base_time, _dt.timezone.utc
            ).isoformat()

        base = self._base_time

        def fake_time() -> float:
            return base

        def fake_monotonic() -> float:
            self._mono_counter += 1e-6
            return base + self._mono_counter

        self._patch(time, "time", fake_time)
        self._patch(time, "monotonic", fake_monotonic)
        self._patch(time, "time_ns", lambda: int(base * 1e9))
        self._patch(time, "monotonic_ns", lambda: int((base + self._mono_counter) * 1e9))
        self._freeze_datetime(base)

    def _freeze_datetime(self, base: float) -> None:
        frozen_dt = _make_frozen_datetime(base)
        frozen_date = _make_frozen_date(base)

        # Replace in the datetime module and in every already-imported module that
        # holds a direct reference to the real classes (freezegun-lite).
        targets_dt: list[tuple[Any, str, Any]] = []
        for module in list(sys.modules.values()):
            if module is None:
                continue
            try:
                members = list(vars(module).items())
            except TypeError:  # pragma: no cover - some modules disallow vars()
                continue
            for name, value in members:
                if value is _REAL_DATETIME:
                    targets_dt.append((module, name, frozen_dt))
                elif value is _REAL_DATE:
                    targets_dt.append((module, name, frozen_date))
        for module, name, replacement in targets_dt:
            try:
                original = getattr(module, name)
                setattr(module, name, replacement)
                self._restores.append(_restorer(module, name, original))
            except Exception:  # pragma: no cover - read-only attrs
                continue

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

    # -- uuid -------------------------------------------------------------- #

    def _freeze_uuid(self) -> None:
        if self.replay:

            def replay_uuid4() -> uuid.UUID:
                if self._uuid_index < len(self._recorded_uuids):
                    value = self._recorded_uuids[self._uuid_index]
                else:
                    # Deterministic fallback for calls beyond what was recorded.
                    value = str(uuid.uuid5(_FROZEN_NAMESPACE, str(self._uuid_index)))
                self._uuid_index += 1
                return uuid.UUID(value)

            self._patch(uuid, "uuid4", replay_uuid4)
        else:

            def record_uuid4() -> uuid.UUID:
                value = _REAL_UUID4()
                self._captured_uuids.append(str(value))
                return value

            self._patch(uuid, "uuid4", record_uuid4)

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

    # -- helpers ----------------------------------------------------------- #

    def _patch(self, target: Any, name: str, replacement: Any) -> None:
        original = getattr(target, name)
        setattr(target, name, replacement)
        self._restores.append(_restorer(target, name, original))


def _restorer(target: Any, name: str, original: Any) -> Callable[[], None]:
    def restore() -> None:
        setattr(target, name, original)

    return restore


def _read_env(whitelist: tuple[str, ...]) -> dict[str, str]:
    return {key: os.environ[key] for key in whitelist if key in os.environ}


def _make_frozen_datetime(base: float) -> type:
    frozen_moment = _REAL_DATETIME.fromtimestamp(base, _dt.timezone.utc)

    class FrozenDateTime(_REAL_DATETIME):  # type: ignore[misc, valid-type]
        @classmethod
        def now(cls, tz: Any = None) -> Any:
            if tz is None:
                return frozen_moment.replace(tzinfo=None)
            return frozen_moment.astimezone(tz)

        @classmethod
        def utcnow(cls) -> Any:
            return frozen_moment.replace(tzinfo=None)

        @classmethod
        def today(cls) -> Any:
            return frozen_moment.replace(tzinfo=None)

    return FrozenDateTime


def _make_frozen_date(base: float) -> type:
    frozen_day = _REAL_DATETIME.fromtimestamp(base, _dt.timezone.utc).date()

    class FrozenDate(_REAL_DATE):  # type: ignore[misc, valid-type]
        @classmethod
        def today(cls) -> Any:
            return frozen_day

    return FrozenDate


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
