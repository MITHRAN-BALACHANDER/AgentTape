"""A tiny attribute-accessible mapping used to rehydrate replayed responses.

When a cassette is replayed offline, recorded responses come back as plain dicts.
Many SDKs (OpenAI, etc.) hand callers objects with attribute access
(``resp.choices[0].message.content``). :class:`Box` lets replayed dicts support
both ``obj.attr`` and ``obj["attr"]`` so user code behaves identically whether or
not the original SDK is installed.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any


class Box(dict):  # type: ignore[type-arg]
    """A dict that also supports attribute access, recursively."""

    def __getattr__(self, name: str) -> Any:
        try:
            return _wrap(self[name])
        except KeyError as exc:
            raise AttributeError(name) from exc

    def __setattr__(self, name: str, value: Any) -> None:
        self[name] = value

    def __iter__(self) -> Iterator[Any]:  # pragma: no cover - dict default suffices
        return super().__iter__()

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return {k: _unwrap(v) for k, v in self.items()}

    def to_dict(self) -> dict[str, Any]:
        return {k: _unwrap(v) for k, v in self.items()}


def _wrap(value: Any) -> Any:
    if isinstance(value, Box):
        return value
    if isinstance(value, dict):
        return Box(value)
    if isinstance(value, list):
        return [_wrap(v) for v in value]
    return value


def _unwrap(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _unwrap(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_unwrap(v) for v in value]
    return value


def box(data: Any) -> Any:
    """Recursively wrap ``data`` so dicts gain attribute access."""

    return _wrap(data)
