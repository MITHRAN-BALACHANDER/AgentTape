"""Session management and the public record/replay API surface.

A :class:`Session` ties together configuration, the loaded cassette, the freeze
layer, the engine and the installed adapters. The three documented entry points —
the :func:`use_cassette` context manager and the :func:`record` / :func:`replay`
decorators — are thin wrappers around it, exactly as specified.
"""

from __future__ import annotations

import functools
import inspect
import threading
from collections.abc import Awaitable, Callable, Iterable
from pathlib import Path
from typing import Any, TypeVar

from . import cassette as cassette_io
from .config import Config
from .engine import Engine
from .freeze import _REAL_DATETIME, _REAL_UUID4, FreezeController, default_features
from .matchers import MatcherSpec
from .redaction import Redactor
from .schema import SCHEMA_VERSION, Cassette

F = TypeVar("F", bound=Callable[..., Any])

# Active-session stack (thread-local) so adapters and the @tool decorator can find
# the current engine at call time without threading it through every call.
_local = threading.local()


def _stack() -> list[Session]:
    stack = getattr(_local, "stack", None)
    if stack is None:
        stack = []
        _local.stack = stack
    return stack


def active_session() -> Session | None:
    """Return the innermost active :class:`Session`, or ``None``."""

    stack = _stack()
    return stack[-1] if stack else None


class Session:
    """A single record/replay context bound to one cassette file."""

    def __init__(
        self,
        name: str | Path,
        *,
        mode: str | None = None,
        live: Iterable[str] | None = None,
        frozen: Iterable[str] | None = None,
        matchers: Iterable[MatcherSpec] | None = None,
        freeze: Iterable[str] | None = None,
        record: bool = False,
        config: Config | None = None,
        cassette_dir: str | Path | None = None,
        format: str | None = None,
        tags: Iterable[str] | None = None,
    ) -> None:
        self.config = config or Config.load()
        self.name = name
        self.mode = self._resolve_mode(mode, record)
        self.fmt = format or self.config.format
        self.tags = list(tags or [])

        cdir = Path(cassette_dir) if cassette_dir else self.config.cassette_dir
        self.path = cassette_io.resolve_path(name, cdir, self.fmt)
        self.cassette_existed = self.path.exists()

        self.redactor = Redactor(self.config.redact)
        self.assets_threshold = self.config.assets_threshold_bytes

        # Load any existing recording for matching.
        if self.cassette_existed and self.mode != "all":
            self.recorded = cassette_io.read_cassette(self.path)
        else:
            self.recorded = Cassette(version=SCHEMA_VERSION)

        matcher_specs = tuple(matchers) if matchers else self.config.default_matchers
        self.engine = Engine(
            recorded=self.recorded,
            mode=self.mode,
            cassette_existed=self.cassette_existed,
            matchers=matcher_specs,
            ignore_fields=self.config.ignore_volatile_fields,
            live=set(live) if live else None,
            frozen=set(frozen) if frozen else None,
            cassette_path=str(self.path),
        )

        # Explicit freeze= kwarg wins; otherwise use the configured/default features.
        if freeze is not None:
            features = set(freeze)
        else:
            features = default_features(self.config.freeze, self.mode)
        # Replay frozen values (patch the clock, replay recorded UUIDs) whenever we
        # are reading an existing recording rather than recording fresh.
        replay_clock = self.mode == "none" or (
            self.cassette_existed and self.mode in ("once", "new_episodes")
        )
        self.freeze = FreezeController(
            features,
            replay=replay_clock,
            state=self.recorded.meta.get("freeze") if self.recorded.meta else None,
            env_whitelist=self.config.env_snapshot,
        )

        self.meta: dict[str, Any] = {}
        self._adapters: list[Any] = []
        self.run_id = str(_REAL_UUID4())
        self.created_at = _REAL_DATETIME.now().isoformat()

    # -- mode resolution --------------------------------------------------- #

    def _resolve_mode(self, mode: str | None, record: bool) -> str:
        if mode is not None:
            return mode
        if record:
            return "record"
        return self.config.default_mode

    # -- lifecycle --------------------------------------------------------- #

    def __enter__(self) -> Session:
        from .adapters import install_all

        self.freeze.__enter__()
        _stack().append(self)
        self._adapters = install_all(self)
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        from .adapters import uninstall_all

        try:
            uninstall_all(self._adapters)
        finally:
            stack = _stack()
            if stack and stack[-1] is self:
                stack.pop()
            self.freeze.__exit__(exc_type, exc, tb)
            if exc_type is None:
                self._maybe_write()

    async def __aenter__(self) -> Session:
        return self.__enter__()

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.__exit__(exc_type, exc, tb)

    # -- writing ----------------------------------------------------------- #

    def _should_write(self) -> bool:
        if self.mode in ("record", "all"):
            return True
        if self.mode == "new_episodes":
            return self.engine.is_live_session() or bool(self.engine.executed)
        if self.mode == "once":
            return not self.cassette_existed
        # mode == "none": only when live boundaries produced a derived cassette.
        return self.engine.is_live_session()
    def output_path(self) -> Path:
        if self.mode == "none" and self.engine.is_live_session():
            return self.path.with_suffix("").with_name(
                self.path.stem + ".derived" + self.path.suffix
            )
        return self.path

    def _maybe_write(self) -> None:
        if not self._should_write():
            return
        out = Cassette(
            version=SCHEMA_VERSION,
            created_at=self.created_at,
            run_id=self.run_id,
            meta=self._build_meta(),
            interactions=self.engine.build_output(),
        )
        cassette_io.write_cassette(
            out,
            self.output_path(),
            fmt=self.fmt,
            redactor=self.redactor,
            assets_threshold=self.assets_threshold,
        )

    def _build_meta(self) -> dict[str, Any]:
        meta: dict[str, Any] = {
            "agenttape_version": _package_version(),
            "mode": self.mode,
        }
        meta.update(self.meta)
        freeze_meta = self.freeze.meta()
        if freeze_meta.get("features"):
            meta["freeze"] = freeze_meta
        if self.tags:
            meta["tags"] = self.tags
        return meta

    # -- adapter helpers --------------------------------------------------- #

    def set_meta(self, **kwargs: Any) -> None:
        self.meta.update({k: v for k, v in kwargs.items() if v is not None})


# --------------------------------------------------------------------------- #
# Public entry points
# --------------------------------------------------------------------------- #


def use_cassette(name: str | Path, **kwargs: Any) -> Session:
    """Context manager / session factory for recording or replaying a cassette.

    Example::

        with agenttape.use_cassette("checkout", mode="once"):
            run_agent()
    """

    return Session(name, **kwargs)


def replay(cassette: str | Path, **kwargs: Any) -> Callable[[F], F]:
    """Decorator that replays ``cassette`` (``mode="none"`` by default — offline)."""

    kwargs.setdefault("mode", "none")
    return _decorator(cassette, kwargs)


def record(cassette: str | Path, **kwargs: Any) -> Callable[[F], F]:
    """Decorator that records ``cassette`` (``mode="record"`` by default)."""

    kwargs.setdefault("mode", "record")
    return _decorator(cassette, kwargs)


def _decorator(cassette: str | Path, kwargs: dict[str, Any]) -> Callable[[F], F]:
    def decorate(fn: F) -> F:
        if inspect.iscoroutinefunction(fn):

            @functools.wraps(fn)
            async def awrapper(*args: Any, **kw: Any) -> Any:
                async with Session(cassette, **kwargs):
                    return await fn(*args, **kw)

            return awrapper  # type: ignore[return-value]

        @functools.wraps(fn)
        def wrapper(*args: Any, **kw: Any) -> Any:
            with Session(cassette, **kwargs):
                return fn(*args, **kw)

        return wrapper  # type: ignore[return-value]

    return decorate


def _package_version() -> str:
    try:
        from importlib.metadata import version

        return version("agenttape")
    except Exception:  # pragma: no cover - dev tree without install
        return "0.0.0+dev"


__all__ = [
    "Session",
    "active_session",
    "record",
    "replay",
    "use_cassette",
]

# Re-export for convenience to callers that want the awaitable typing alias.
AsyncCallable = Callable[..., Awaitable[Any]]
