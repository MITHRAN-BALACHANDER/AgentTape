"""``pytest-agenttape`` — first-class pytest integration.

Bind a test to a cassette with the marker and (optionally) request the fixture::

    @pytest.mark.agenttape("weather_agent")
    def test_weather(agenttape_cassette):
        assert run_agent() == "It's sunny."

By default tests run in ``mode="none"`` — offline, deterministic, fast and free, so
CI never touches the network. Regenerate cassettes with ``--agenttape-record``.
Unmatched interactions fail the test with a precise field-level diff (raised by the
engine as :class:`~agenttape.errors.UnmatchedInteractionError`).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .recorder import Session

# Submodules are imported lazily inside the hook/fixture bodies (not at module top
# level) so that pytest registering this entry-point plugin does not pull the engine
# in before pytest-cov starts measuring — which would otherwise leave the engine's
# import-time lines unmeasured under ``pytest --cov=agenttape``.

_SANITIZE = re.compile(r"[^A-Za-z0-9_.-]+")


def pytest_addoption(parser: Any) -> None:
    group = parser.getgroup("agenttape")
    group.addoption(
        "--agenttape-record",
        action="store_true",
        default=False,
        help="(re)record AgentTape cassettes against the real services.",
    )
    group.addoption(
        "--agenttape-mode",
        action="store",
        default=None,
        choices=["none", "once", "new_episodes", "all", "record"],
        help="override the AgentTape cassette mode for this run.",
    )


def pytest_configure(config: Any) -> None:
    config.addinivalue_line(
        "markers",
        "agenttape(cassette=None, **opts): bind this test to an AgentTape cassette.",
    )


def _resolve_mode(config: Any, marker_kwargs: dict[str, Any]) -> str:
    if config.getoption("--agenttape-record"):
        return "all"
    cli_mode = config.getoption("--agenttape-mode")
    if cli_mode:
        return str(cli_mode)
    return str(marker_kwargs.get("mode", "none"))


def _cassette_name(marker: Any, node_name: str) -> str:
    if marker.args:
        return str(marker.args[0])
    if "cassette" in marker.kwargs:
        return str(marker.kwargs["cassette"])
    return _SANITIZE.sub("_", node_name).strip("_")


class CassetteHandle:
    """Yielded by the ``agenttape_cassette`` fixture; offers snapshot assertions."""

    def __init__(self, session: Session) -> None:
        self.session = session

    @property
    def path(self) -> Path:
        return self.session.path

    @property
    def mode(self) -> str:
        return self.session.mode

    @property
    def tool_calls(self) -> list[str]:
        """Sequence of tool/retrieval boundary names exercised this run."""

        return [
            i.boundary or i.kind
            for i in self.session.engine.timeline
            if i.kind in ("tool", "retrieval")
        ]

    @property
    def interactions(self) -> list[Any]:
        return list(self.session.engine.timeline)

    @property
    def final_output(self) -> Any:
        from .metrics import final_output
        from .schema import Cassette

        c = Cassette(interactions=list(self.session.engine.timeline))
        return final_output(c)

    def assert_tool_calls(self, expected: list[str]) -> None:
        actual = self.tool_calls
        assert actual == expected, (
            f"tool-call snapshot mismatch:\n  expected: {expected}\n  actual:   {actual}"
        )

    def assert_final_output(self, expected: Any) -> None:
        actual = self.final_output
        assert actual == expected, (
            f"final-output snapshot mismatch:\n  expected: {expected!r}\n  actual:   {actual!r}"
        )

    def assert_snapshot(self) -> None:
        """Fail with a readable diff if this run drifts from the recorded cassette."""

        from .diff import run_diff
        from .schema import Cassette

        recorded = self.session.recorded
        current = Cassette(meta=recorded.meta, interactions=list(self.session.engine.timeline))
        diff = run_diff(recorded, current)
        assert not diff.changed, "run drifted from recorded snapshot:\n" + diff.render()


def _make_session(request: Any) -> Session | None:
    from .config import Config
    from .recorder import Session

    marker = request.node.get_closest_marker("agenttape")
    if marker is None:
        return None
    name = _cassette_name(marker, request.node.name)
    mode = _resolve_mode(request.config, marker.kwargs)
    config = Config.load()
    kwargs: dict[str, Any] = {"mode": mode, "config": config}
    for key in ("live", "frozen", "matchers", "freeze", "format"):
        if key in marker.kwargs:
            kwargs[key] = marker.kwargs[key]
    return Session(name, **kwargs)


def _open(request: Any) -> Iterator[CassetteHandle]:
    session = _make_session(request)
    if session is None:
        raise RuntimeError(
            "agenttape_cassette fixture requires the @pytest.mark.agenttape(...) marker."
        )
    session.__enter__()
    try:
        yield CassetteHandle(session)
    finally:
        session.__exit__(None, None, None)


def _pytest_fixture() -> Any:
    import pytest

    @pytest.fixture
    def agenttape_cassette(request: Any) -> Iterator[CassetteHandle]:
        """Open the cassette bound to the test's ``agenttape`` marker."""

        yield from _open(request)

    return agenttape_cassette


def _pytest_autouse_fixture() -> Any:
    import pytest

    @pytest.fixture(autouse=True)
    def _agenttape_auto(request: Any) -> Iterator[None]:
        # If the test has the marker but did not request the explicit fixture,
        # still activate a session around it.
        marker = request.node.get_closest_marker("agenttape")
        if marker is None or "agenttape_cassette" in request.fixturenames:
            yield
            return
        session = _make_session(request)
        assert session is not None
        session.__enter__()
        try:
            yield
        finally:
            session.__exit__(None, None, None)

    return _agenttape_auto


# Register fixtures at import time (pytest collects module-level fixtures).
agenttape_cassette = _pytest_fixture()
_agenttape_auto = _pytest_autouse_fixture()
