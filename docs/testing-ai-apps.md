# Testing AI Apps

A complete guide to using AgentTape with `pytest`.

---

## What is it?

Testing AI applications requires a shift in mindset. You are no longer just asserting that `2 + 2 = 4`. You are asserting that an agent follows a specific thought process, uses the correct tools, and produces a reasonable outcome.

This guide shows you how to structure an AI test suite using AgentTape and `pytest`.

---

## The pytest Plugin

AgentTape ships with a first-class `pytest` plugin. It is enabled automatically when you install AgentTape.

By default, the plugin forces all tests decorated with `@pytest.mark.agenttape` to run in `mode="none"`. This ensures your CI pipeline is always offline, fast, and free.

---

## Your First Test

Let's write a test for an agent that checks the weather.

```python
import pytest
from my_app import weather_agent

@pytest.mark.agenttape("weather_sunny_london")
def test_weather_agent_sunny(agenttape_cassette):
    result = weather_agent.run("What is the weather in London?")
    assert "sunny" in result.lower()
    agenttape_cassette.assert_tool_calls(["get_location", "get_weather"])
```

### What happened?
1. The `@pytest.mark.agenttape("name")` decorator tells AgentTape to use the `cassettes/weather_sunny_london.yaml` file.
2. The `agenttape_cassette` fixture is injected into the test. It provides access to the current session's metadata.
3. We assert that the final output contains "sunny".
4. We use the fixture's built-in assertion to verify the agent actually called the `get_location` and `get_weather` tools, and in that exact order.

---

## Recording Tests

When you write the test above for the first time, it will fail because the cassette file doesn't exist.

To record the cassette, run `pytest` with the record flag:

```bash
pytest --agenttape-record
```

This tells the plugin to run all marked tests in `mode="all"`, meaning it will hit the real network, execute real tools, and save the cassettes to disk.

Once the run is complete, remove the flag and run the tests normally:

```bash
pytest
```

The tests will now run instantly using the saved cassettes.

---

## Snapshot Testing

The `agenttape_cassette` fixture includes a powerful `assert_snapshot()` method.

This method compares the exact sequence of interactions in the current run against the sequence saved in the cassette. If the agent changes its behavior—for example, if it decides to call `get_weather` twice instead of once—the snapshot assertion will fail and print a diff.

```python
@pytest.mark.agenttape("weather_sunny_london")
def test_weather_agent_strict(agenttape_cassette):
    weather_agent.run("What is the weather in London?")
    agenttape_cassette.assert_snapshot()
```

This is the most robust way to ensure your agent doesn't silently regress as you update its prompts or update the underlying LLM model.

---

## Summary

*   Use `@pytest.mark.agenttape` to bind a test to a cassette.
*   Tests run offline by default.
*   Use `pytest --agenttape-record` to generate or update cassettes.
*   Use `agenttape_cassette.assert_tool_calls()` to verify agent behavior.
*   Use `agenttape_cassette.assert_snapshot()` to prevent regressions.

---

**Next Steps**: Learn how to intercept specific boundaries like [Recording APIs](recording-apis.md).