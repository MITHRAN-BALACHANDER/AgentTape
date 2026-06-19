---
title: Python API Reference
---

# Python API Reference

**Every public name in the `agenttape` package, with signatures, arguments, and examples.**

All names are importable directly from the top level: `agenttape.use_cassette`, `agenttape.tool`, `agenttape.UnmatchedInteractionError`, and so on. Imports are lazy — `import agenttape` is cheap and side-effect-free.

---

## Sessions

### `use_cassette`

```python
agenttape.use_cassette(name, *, mode=None, live=None, frozen=None,
                       matchers=None, freeze=None, record=False,
                       config=None, cassette_dir=None, format=None,
                       tags=None) -> Session
```

The primary entry point. Returns a `Session` you use as a (sync or async) context manager.

| Argument | Type | Default | Description |
| --- | --- | --- | --- |
| `name` | `str \| Path` | — | Cassette name; saved as `name.yaml` in `cassette_dir` |
| `mode` | `str` | config `default_mode` (`none`) | `none`, `once`, `new_episodes`, `all`, `record` |
| `live` | `set[str]` | `None` | Boundaries to run for real ([Partial Replay](mixed-replay.md)) |
| `frozen` | `set[str]` | `None` | Boundaries to force-replay; mutually exclusive with `live` |
| `matchers` | `list` | config `default_matchers` | Matcher names/instances/callables ([Replay Engine](replay-engine.md)) |
| `freeze` | `list[str]` | config `freeze` | Subsystems to pin: `clock`, `uuid`, `random` |
| `record` | `bool` | `False` | Shorthand: `True` ⇒ `mode="record"` |
| `config` | `Config` | auto-discovered | Override the loaded configuration |
| `cassette_dir` | `str \| Path` | config `cassette_dir` | Where to read/write the cassette |
| `format` | `str` | config `format` (`yaml`) | `yaml` or `json` |
| `tags` | `list[str]` | `None` | Labels stored in `meta.tags` |

```python
import agenttape

with agenttape.use_cassette("checkout", mode="none"):
    run_agent()

# Async works too
async with agenttape.use_cassette("checkout"):
    await run_agent_async()
```

!!! note
    Arguments here override `agenttape.toml`. `live` and `frozen` cannot both be set.

---

### `Session`

```python
class agenttape.Session
```

The object returned by `use_cassette`. You rarely construct it directly. It's a context manager (sync **and** async) that, on enter, turns on the freeze layer, becomes the active session, and installs all available adapters; on exit, it uninstalls them, restores the freeze layer, and writes the cassette if the mode calls for it.

Useful attributes: `.path` (the resolved cassette path), `.mode`, `.engine`.

---

### `active_session`

```python
agenttape.active_session() -> Session | None
```

Returns the innermost active `Session`, or `None` outside any session. Adapters and boundary decorators use it to find the current engine. Useful when writing a [custom adapter](adapters.md).

---

## Decorators

### `@replay`

```python
@agenttape.replay(cassette, **kwargs)
```

Wraps a function so it runs inside a session. Defaults to `mode="none"` (offline replay). Accepts the same keyword arguments as `use_cassette`. Works on sync and `async def` functions.

```python
@agenttape.replay("hello")
def test_agent():
    assert "hi" in run_agent().lower()
```

### `@record`

```python
@agenttape.record(cassette, **kwargs)
```

Identical to `@replay` but defaults to `mode="record"`. Handy for capture scripts.

---

## Boundary decorators

### `@tool`, `@retrieval`, `@memory_read`, `@memory_write`

```python
@agenttape.tool
@agenttape.tool(name="custom_name")
```

Mark a function as a recorded boundary. During recording it executes normally and its arguments/return value are captured. During replay it returns the saved output and **never executes**. Outside a session it behaves like the original function.

The four decorators are identical except for the `kind` they record:

| Decorator | `kind` |
| --- | --- |
| `@tool` | `tool` |
| `@retrieval` | `retrieval` |
| `@memory_read` | `memory_read` |
| `@memory_write` | `memory_write` |

| Argument | Type | Description |
| --- | --- | --- |
| `name` | `str` | Override the recorded boundary name (defaults to the function name) |

```python
@agenttape.tool
def charge_card(amount: int) -> dict:
    return payment_api.charge(amount)

@agenttape.retrieval(name="kb_search")
async def search(query: str) -> list[str]:
    ...
```

!!! warning "Pass and return serializable primitives"
    Arguments and return values are serialized to YAML. Use `str`/`int`/`float`/`bool`/`list`/`dict`. Custom objects fall back to an unstable `str()` form and break matching. See [Tools](tools.md#the-golden-rule-serialize-at-the-boundary).

---

### `record_call`

```python
agenttape.record_call(kind, request, executor, *,
                      boundary=None, usage=None, tags=None) -> Any
```

The low-level hook behind the decorators. Routes a single boundary crossing through the active session with an explicit request payload. Outside a session it just calls `executor()`.

| Argument | Type | Description |
| --- | --- | --- |
| `kind` | `str` | `tool`, `retrieval`, `memory_read`, `memory_write`, `llm`, `http` |
| `request` | `dict` | JSON-like request used for matching |
| `executor` | `Callable[[], Any]` | Runs the real boundary; called on record/live |
| `boundary` | `str` | Boundary name (defaults to `kind`) |
| `usage` | `dict` | Optional usage metadata to store |
| `tags` | `list[str]` | Optional labels |

```python
result = agenttape.record_call(
    "tool",
    {"name": "weather", "args": {"city": "London"}},
    executor=lambda: weather_client.fetch("London"),
    boundary="weather",
)
```

---

## AgentTape callback object

```python
class agenttape.AgentTape(*, tag=None)
```

A duck-typed callback/listener for frameworks that expose hooks instead of a patchable client (LangChain, LlamaIndex, CrewAI). Pass an instance into the framework's callback slot and it records `llm`, `tool`, and `retrieval` boundaries into the active session.

```python
from langchain_openai import ChatOpenAI
import agenttape

with agenttape.use_cassette("chain", mode="record"):
    llm = ChatOpenAI(callbacks=[agenttape.AgentTape()])
    chain.invoke(..., config={"callbacks": [agenttape.AgentTape()]})
```

!!! note "Observational — record-only"
    A framework calls these hooks *after* the fact and can't let the handler substitute a return value. So the callback object is for **recording** and event normalization. Deterministic **replay** still relies on the transport adapters (OpenAI / httpx / requests), which can serve a recorded response in place of a real call.

---

## Data model

### `Cassette`

```python
@dataclass
class agenttape.Cassette:
    version: str = "1"
    created_at: str = ""
    run_id: str = ""
    meta: dict = {}
    interactions: list[Interaction] = []
```

The in-memory representation of a cassette file. `Cassette.from_dict(...)` / `.to_dict()` round-trip the YAML structure. See the [cassette format](format.md).

### `Interaction`

```python
@dataclass
class agenttape.Interaction:
    index: int
    kind: str
    request: dict
    response: Any = None
    error: dict | None = None
    match_key: str = ""
    latency_ms: float | None = None
    usage: dict | None = None
    tags: list[str] = []
    boundary: str | None = None
    metadata: dict = {}
```

One captured boundary crossing. `kind` must be one of `llm`, `tool`, `retrieval`, `memory_read`, `memory_write`, `http`.

### `Config`

```python
@dataclass
class agenttape.Config: ...
Config.load(start=None) -> Config
```

The resolved configuration. `Config.load()` discovers `agenttape.toml` by walking up from the current directory. Every field has a default. See the [Configuration Reference](configuration-ref.md).

---

## pytest integration

The plugin registers automatically. Full guide: [Testing AI Apps](testing-ai-apps.md).

### Marker

```python
@pytest.mark.agenttape(cassette=None, **opts)
```

Binds a test to a cassette. If `cassette` is omitted, the name is derived from the test node. Supported `opts`: `mode`, `live`, `frozen`, `matchers`, `freeze`, `format`.

### Fixture: `agenttape_cassette`

Yields a `CassetteHandle` for tests carrying the marker.

```python
class CassetteHandle:
    # properties
    path: Path
    mode: str
    tool_calls: list[str]      # tool/retrieval boundary names exercised
    interactions: list         # full timeline
    final_output: Any
    # assertions
    def assert_tool_calls(self, expected: list[str]) -> None: ...
    def assert_final_output(self, expected) -> None: ...
    def assert_snapshot(self) -> None: ...
```

| Method | Fails when… |
| --- | --- |
| `assert_tool_calls(list)` | The tool/retrieval boundary names (in order) differ |
| `assert_final_output(value)` | The final output differs |
| `assert_snapshot()` | The whole interaction sequence drifts from the cassette |

### Command-line flags

| Flag | Effect |
| --- | --- |
| `--agenttape-record` | Record marked tests (forces `mode="all"`) |
| `--agenttape-mode MODE` | Override the mode for this run |

---

## Errors

All inherit from `agenttape.AgentTapeError`.

| Exception | Raised when |
| --- | --- |
| `AgentTapeError` | Base class for all AgentTape errors |
| `UnmatchedInteractionError` | A request has no matching recording during replay. Carries the canonical request, closest recording, and field-level diffs. ([Debugging](debugging.md)) |
| `CassetteNotFoundError` | The cassette file is missing when accessed directly via `read_cassette()` (e.g. CLI internals). `use_cassette()` does **not** raise this — a missing file in `mode="none"` causes the first interaction to raise `UnmatchedInteractionError` instead. |
| `CassetteCorruptError` | A cassette can't be parsed or violates the schema |
| `SchemaVersionError` | A cassette uses an unsupported schema version |
| `ConfigError` | `agenttape.toml` is invalid (bad mode, bad format, …) |
| `StreamingReplayError` | A `stream=True` LLM call was made during offline replay |

```python
import agenttape

try:
    with agenttape.use_cassette("x", mode="none"):
        run_agent()
except agenttape.UnmatchedInteractionError as e:
    print(e)            # full diagnostic message
    print(e.field_diffs)  # list of field-level differences
```

---

## Warnings

Subclasses of `UserWarning` — non-fatal, surfaced via the `warnings` module.

| Warning | Emitted when |
| --- | --- |
| `DeterminismDriftWarning` | A whitelisted env var changed between record and replay ([Determinism](determinism.md)) |
| `StreamingNotRecordedWarning` | A streaming call ran live during recording and so wasn't captured |

```python
import warnings, agenttape

with warnings.catch_warnings():
    warnings.simplefilter("error", agenttape.DeterminismDriftWarning)  # treat as error
    with agenttape.use_cassette("x"):
        run_agent()
```

---

## Summary

- `use_cassette` / `@replay` / `@record` open a session; `@tool` & friends mark boundaries; `record_call` is the low-level hook.
- `AgentTape` is a record-only callback for hook-based frameworks.
- `Cassette`/`Interaction`/`Config` are the data model; the pytest plugin adds a marker and the `agenttape_cassette` fixture.
- Errors are actionable and specific; warnings flag drift and uncaptured streams.

[Next: CLI Reference →](cli.md){ .md-button .md-button--primary }
