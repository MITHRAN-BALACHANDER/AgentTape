# Python API Reference

Complete documentation for the AgentTape public API.

---

## What is it?

This page documents the functions, classes, and decorators exposed by the `agenttape` Python package.

---

## Context Managers

### `agenttape.use_cassette(name, mode=None, live=None, frozen=None, freeze=None)`

The primary entry point for recording and replaying interactions.

**Arguments:**

*   **`name`** *(str)*: The name of the cassette. It will be saved as `name.yaml` in the configured `cassette_dir`.
*   **`mode`** *(str, optional)*: The cassette mode (`"none"`, `"once"`, `"new_episodes"`, `"all"`, `"record"`). Defaults to the global configuration.
*   **`live`** *(set[str], optional)*: A set of boundaries to unfreeze. E.g., `{"llm", "my_tool"}`.
*   **`frozen`** *(set[str], optional)*: A set of boundaries to force replay, even if the mode is `record`.
*   **`freeze`** *(list[str], optional)*: Which non-deterministic subsystems to mock. Defaults to `["clock", "uuid", "random"]`.

**Example:**

```python
with agenttape.use_cassette("checkout", mode="none"):
    run_agent()
```

---

## Decorators

### `@agenttape.replay(name, **kwargs)`

A decorator version of `use_cassette`. It accepts all the same arguments. By default, it sets `mode="none"`.

**Example:**

```python
@agenttape.replay("my_test")
def test_agent():
    pass
```

### `@agenttape.tool`

Marks a function as a semantic boundary that should be intercepted by AgentTape. The function will execute normally during recording and return saved outputs during replay.

### `@agenttape.retrieval`

Identical to `@agenttape.tool`, but labels the interaction as `kind: retrieval` in the cassette YAML.

### `@agenttape.memory_read` / `@agenttape.memory_write`

Identical to `@agenttape.tool`, but labels the interaction as `kind: memory_read` or `kind: memory_write`.

---

## pytest Fixtures

### `agenttape_cassette`

When using the `pytest` plugin (which is installed automatically), you can request this fixture in any test decorated with `@pytest.mark.agenttape`.

It yields a `CassetteHandle` object.

#### `CassetteHandle.assert_snapshot()`
Fails the test with a diff if the exact sequence of interactions differs from the recorded cassette.

#### `CassetteHandle.assert_tool_calls(expected_list)`
Asserts that the agent called the exact list of tools, in the exact order specified.

```python
@pytest.mark.agenttape("test_name")
def test_agent(agenttape_cassette):
    agenttape_cassette.assert_tool_calls(["get_weather"])
```

---

## Exceptions

### `agenttape.errors.UnmatchedInteractionError`

Raised during replay mode when a live request does not match the next recorded interaction in the cassette.

### `agenttape.errors.DeterminismDriftWarning`

A warning emitted when AgentTape detects that a recorded environment variable has changed during replay.

### `agenttape.errors.ConfigError`

Raised when `agenttape.toml` is invalid or contains unrecognized settings.