# pytest plugin

`pytest-agenttape` ships in the box (registered automatically). Tests run **offline
and deterministically by default**, so CI never touches the network.

## Marker + fixture

```python
import pytest

@pytest.mark.agenttape("weather_agent")
def test_weather(agenttape_cassette):
    assert run_agent() == "It's sunny."
```

The marker binds the test to a cassette (name defaults to the test name). Requesting
the `agenttape_cassette` fixture gives you a handle for snapshot assertions; you can
also omit it and just use the marker.

## Recording vs replaying

```bash
pytest                       # mode="none": offline, deterministic, free (CI default)
pytest --agenttape-record    # (re)record cassettes against the real services
pytest --agenttape-mode=once # override the mode for this run
```

## Snapshot assertions

```python
@pytest.mark.agenttape("tool_sequence")
def test_sequence(agenttape_cassette):
    result = agent()
    agenttape_cassette.assert_tool_calls(["search", "summarize"])
    agenttape_cassette.assert_final_output("done")
    # or: drift detection against the recorded cassette
    agenttape_cassette.assert_snapshot()
```

## Mismatch diffs

When a replayed request doesn't match its recording, the test fails with a precise,
field-level diff (raised as `UnmatchedInteractionError`) telling you exactly what
changed and how to fix it — re-record, ignore a volatile field, or mark the boundary
`live`.

## Marker options

```python
@pytest.mark.agenttape("name", live={"llm"}, matchers=["ordered"], freeze=["uuid"])
```

`live`, `frozen`, `matchers`, `freeze` and `format` are all forwarded to the session.
