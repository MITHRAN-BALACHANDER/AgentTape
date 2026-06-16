"""Adapter registry and bulk install/uninstall.

The registry is populated at import time with the built-in adapters. A
:class:`~agenttape.recorder.Session` installs every *available* adapter on enter
and uninstalls them on exit.
"""

from __future__ import annotations

from typing import Any

from .base import Adapter, RefCountedPatch
from .http import HttpxAdapter, RequestsAdapter
from .langgraph import LangGraphAdapter
from .openai import OpenAIAdapter

_REGISTRY: list[Adapter] = []


def register(adapter: Adapter) -> None:
    """Register an adapter so sessions will install it when its library is present."""

    _REGISTRY.append(adapter)


def registry() -> list[Adapter]:
    return list(_REGISTRY)


def install_all(session: Any) -> list[Adapter]:
    installed: list[Adapter] = []
    for adapter in _REGISTRY:
        try:
            if adapter.available():
                adapter.install(session)
                installed.append(adapter)
        except Exception:  # pragma: no cover - never let an adapter break a session
            continue
    return installed


def uninstall_all(adapters: list[Adapter]) -> None:
    for adapter in reversed(adapters):
        try:
            adapter.uninstall()
        except Exception:  # pragma: no cover
            continue


# Built-in adapters. Order matters only for cosmetic install order.
register(OpenAIAdapter())
register(LangGraphAdapter())
register(HttpxAdapter())
register(RequestsAdapter())


__all__ = [
    "Adapter",
    "HttpxAdapter",
    "LangGraphAdapter",
    "OpenAIAdapter",
    "RefCountedPatch",
    "RequestsAdapter",
    "install_all",
    "register",
    "registry",
    "uninstall_all",
]
