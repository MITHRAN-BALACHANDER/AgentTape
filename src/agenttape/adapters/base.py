"""Adapter base class and the documented extension interface.

An adapter translates a framework's native events into AgentTape's internal schema
by routing boundary crossings through the active session's engine. Adapters keep
their third-party imports lazy so the core stays dependency-free, and patch their
target libraries with **reference-counted** install/uninstall so nested sessions
share a single patch and route to whichever session is active at call time.

To add an adapter:

1. Subclass :class:`Adapter`.
2. Implement :meth:`available` (is the target library importable?), :meth:`install`
   and :meth:`uninstall`.
3. Register it via ``agenttape.adapters.register(MyAdapter())``.

Inside your patched callable, fetch ``agenttape.active_session()``; if it is
``None`` call the original (pass-through), otherwise call
``session.engine.intercept(kind, request, boundary=..., executor=...)``.
"""

from __future__ import annotations

from typing import Any


class Adapter:
    """Base class for framework adapters."""

    name: str = "adapter"

    def available(self) -> bool:
        """Return True if this adapter's target library is importable."""

        return False

    def install(self, session: Any) -> None:
        """Patch the target library to route through ``session``'s engine."""

    def uninstall(self) -> None:
        """Restore the target library to its original state."""


class RefCountedPatch:
    """Helper to install a patch once across nested sessions and restore on last exit."""

    def __init__(self) -> None:
        self._count = 0
        self._restores: list[Any] = []

    @property
    def active(self) -> bool:
        return self._count > 0

    def acquire(self, install_fn: Any) -> None:
        if self._count == 0:
            self._restores = install_fn() or []
        self._count += 1

    def release(self) -> None:
        if self._count == 0:
            return
        self._count -= 1
        if self._count == 0:
            for restore in reversed(self._restores):
                try:
                    restore()
                except Exception:  # pragma: no cover - defensive cleanup
                    pass
            self._restores = []
