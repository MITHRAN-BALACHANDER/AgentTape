"""Request matching strategies.

A matcher reduces a request to a comparison key. The engine looks recorded
interactions up by ``(kind, key)``. When several recordings share a key (a genuine
duplicate, or a deliberate collision) they are served in recorded order — this is
the "keyed, falling back to order on collision" default.

Built-in matchers:

* ``exact`` — hash the request verbatim (no fields ignored).
* ``ignore_volatile`` — hash the request after dropping volatile fields (default).
* ``ordered`` — ignore content entirely; match the Nth call of a kind in sequence.
* ``semantic_stub`` — a documented hook point for embedding-based matching. The
  core never makes embedding calls, so by default it behaves like
  ``ignore_volatile``; supply your own via ``custom``.
* ``custom`` — wrap any ``Callable[[request], str]``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol, runtime_checkable

from .canonical import DEFAULT_VOLATILE_FIELDS, compute_match_key

ORDERED_SENTINEL = "__ordered__"


@runtime_checkable
class Matcher(Protocol):
    name: str

    def key(self, request: object, ignore_fields: Iterable[str]) -> str:
        """Return a comparison key for ``request``."""


class ExactMatcher:
    name = "exact"

    def key(self, request: object, ignore_fields: Iterable[str]) -> str:
        return compute_match_key(request, ignore_fields=())


class IgnoreVolatileMatcher:
    name = "ignore_volatile"

    def key(self, request: object, ignore_fields: Iterable[str]) -> str:
        return compute_match_key(request, ignore_fields=ignore_fields)


class OrderedMatcher:
    """Matches purely by call order; content is ignored for keying."""

    name = "ordered"

    def key(self, request: object, ignore_fields: Iterable[str]) -> str:
        return ORDERED_SENTINEL


class SemanticStubMatcher:
    """Hook point for semantic matching. Defaults to volatile-ignoring behaviour.

    The core deliberately performs **no** embedding calls (that would violate the
    local-first / offline guarantees). Provide a real implementation via
    ``custom(your_callable)``.
    """

    name = "semantic_stub"

    def key(self, request: object, ignore_fields: Iterable[str]) -> str:
        return compute_match_key(request, ignore_fields=ignore_fields)


class CustomMatcher:
    """Wrap a user callable ``request -> key``."""

    name = "custom"

    def __init__(self, fn: Callable[[object], str], name: str | None = None) -> None:
        self._fn = fn
        if name:
            self.name = name

    def key(self, request: object, ignore_fields: Iterable[str]) -> str:
        return self._fn(request)


_BUILTINS: dict[str, type[Matcher]] = {
    "exact": ExactMatcher,
    "ignore_volatile": IgnoreVolatileMatcher,
    "ordered": OrderedMatcher,
    "sequential": OrderedMatcher,
    "semantic_stub": SemanticStubMatcher,
}

MatcherSpec = str | Matcher | Callable[[object], str]


def resolve_matcher(spec: MatcherSpec) -> Matcher:
    """Resolve a matcher name, instance, or callable to a :class:`Matcher`."""

    if isinstance(spec, str):
        try:
            return _BUILTINS[spec]()
        except KeyError as exc:
            raise ValueError(
                f"Unknown matcher {spec!r}; available: {sorted(_BUILTINS)} or pass a callable."
            ) from exc
    if isinstance(spec, Matcher):
        return spec
    if callable(spec):
        return CustomMatcher(spec)
    raise TypeError(f"Cannot interpret matcher spec: {spec!r}")


def resolve_matchers(specs: Iterable[MatcherSpec]) -> list[Matcher]:
    return [resolve_matcher(s) for s in specs]


def is_ordered(matcher: Matcher) -> bool:
    return isinstance(matcher, OrderedMatcher)


__all__ = [
    "DEFAULT_VOLATILE_FIELDS",
    "ORDERED_SENTINEL",
    "CustomMatcher",
    "ExactMatcher",
    "IgnoreVolatileMatcher",
    "Matcher",
    "MatcherSpec",
    "OrderedMatcher",
    "SemanticStubMatcher",
    "is_ordered",
    "resolve_matcher",
    "resolve_matchers",
]
