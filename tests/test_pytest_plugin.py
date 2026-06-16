"""Tests for the pytest-agenttape plugin, exercised via pytester."""

from __future__ import annotations

import pytest

pytest_plugins = ["pytester"]


def _write_project(pytester: pytest.Pytester) -> None:
    pytester.makefile(".toml", agenttape='cassette_dir = "cassettes"\n')
    pytester.makepyfile(
        conftest="""
        import sys, pathlib
        src = pathlib.Path(__file__).parent
        """
    )


def test_marker_record_then_replay(pytester: pytest.Pytester) -> None:
    pytester.makepyfile(
        test_agent="""
        import pytest
        import agenttape

        spy = {"n": 0}

        @agenttape.tool
        def do(x):
            spy["n"] += 1
            return {"v": x * 2}

        @pytest.mark.agenttape("agentcass")
        def test_records(agenttape_cassette):
            assert do(3) == {"v": 6}
            assert agenttape_cassette.mode in ("none", "all")
        """
    )
    pytester.makefile(".toml", agenttape='cassette_dir = "cassettes"\n')
    # First, record.
    result = pytester.runpytest("--agenttape-record")
    result.assert_outcomes(passed=1)
    assert pytester.path.joinpath("cassettes", "agentcass.yaml").exists()
    # Then replay offline (default mode none).
    result2 = pytester.runpytest()
    result2.assert_outcomes(passed=1)


def test_snapshot_assertions(pytester: pytest.Pytester) -> None:
    pytester.makefile(".toml", agenttape='cassette_dir = "cassettes"\n')
    pytester.makepyfile(
        test_snap="""
        import pytest
        import agenttape

        @agenttape.tool
        def alpha(x):
            return x + 1

        @agenttape.tool
        def beta(x):
            return x * 10

        def agent():
            alpha(1)
            return beta(2)

        @pytest.mark.agenttape("snapcass")
        def test_snapshot(agenttape_cassette):
            result = agent()
            agenttape_cassette.assert_tool_calls(["alpha", "beta"])
            agenttape_cassette.assert_final_output(20)
        """
    )
    pytester.runpytest("--agenttape-record").assert_outcomes(passed=1)
    pytester.runpytest().assert_outcomes(passed=1)


def test_unmatched_fails_test(pytester: pytest.Pytester) -> None:
    pytester.makefile(".toml", agenttape='cassette_dir = "cassettes"\n')
    pytester.makepyfile(
        test_unmatched="""
        import pytest
        import agenttape

        @agenttape.tool
        def do(x):
            return x

        @pytest.mark.agenttape("umcass")
        def test_first(agenttape_cassette):
            do(1)
        """
    )
    pytester.runpytest("--agenttape-record").assert_outcomes(passed=1)
    # Now change the call so it no longer matches; replay must fail.
    pytester.makepyfile(
        test_unmatched="""
        import pytest
        import agenttape

        @agenttape.tool
        def do(x):
            return x

        @pytest.mark.agenttape("umcass")
        def test_first(agenttape_cassette):
            do(999)
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(failed=1)
    result.stdout.fnmatch_lines(["*UnmatchedInteractionError*"])


def test_autouse_without_fixture(pytester: pytest.Pytester) -> None:
    pytester.makefile(".toml", agenttape='cassette_dir = "cassettes"\n')
    pytester.makepyfile(
        test_auto="""
        import pytest
        import agenttape

        @agenttape.tool
        def do(x):
            return x

        @pytest.mark.agenttape("autocass")
        def test_no_fixture():
            assert do(5) == 5
        """
    )
    pytester.runpytest("--agenttape-record").assert_outcomes(passed=1)
    pytester.runpytest().assert_outcomes(passed=1)
