---
title: Quickstart
---

# Quickstart

**Everything you need to wire AgentTape into an existing project, on one page.**

If you've never seen AgentTape before, start with [Your First Recording](your-first-recording.md) instead — it explains each step. This page is the copy-paste reference.

---

## 1. Install

```bash
pip install "agenttape[openai]"   # swap or omit the extra as needed
```

---

## 2. Record and replay with a context manager

```python
import agenttape
from openai import OpenAI

def run_agent():
    client = OpenAI()
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Say hi in 3 words"}],
    )
    return resp.choices[0].message.content

# Record once — hits the real API, writes cassettes/hello.yaml
with agenttape.use_cassette("hello", mode="record"):
    print(run_agent())

# Replay forever — zero network, deterministic, milliseconds
with agenttape.use_cassette("hello", mode="none"):
    print(run_agent())
```

---

## 3. Or decorate a test function

`@agenttape.replay` defaults to `mode="none"`, so the function runs offline.

```python
import agenttape

@agenttape.replay("hello")
def test_agent():
    assert "hi" in run_agent().lower()
```

There's a matching `@agenttape.record` decorator (defaults to `mode="record"`) for capture scripts. Both work on `async def` functions too.

---

## 4. Record your own tools

Wrap any side-effecting function with `@agenttape.tool`. It runs normally while recording and returns the saved output during replay — **it never executes for real on replay.**

```python
import agenttape

@agenttape.tool
def charge_card(amount: int) -> dict:
    return payment_api.charge(amount)   # real side effect, skipped on replay

with agenttape.use_cassette("checkout", mode="none"):
    charge_card(4200)   # returns the recorded result instantly, charges nobody
```

Semantic variants label interactions in the cassette but behave identically:

```python
@agenttape.retrieval     # vector-store / search lookups
@agenttape.memory_read   # agent long-term memory read
@agenttape.memory_write  # agent long-term memory write
```

[More on tools →](tools.md)

---

## 5. Use the pytest plugin

The plugin installs automatically with the package. Bind a test to a cassette with the marker; tests default to offline replay.

```python
import pytest

@pytest.mark.agenttape("weather_agent")
def test_weather(agenttape_cassette):
    result = run_agent()
    assert "sunny" in result.lower()
    agenttape_cassette.assert_tool_calls(["get_location", "get_weather"])
```

Record (or re-record) cassettes by adding a flag:

```bash
pytest                      # offline replay (mode=none) — the default
pytest --agenttape-record   # hit real services and (re)write cassettes
```

[Full testing guide →](testing-ai-apps.md)

---

## 6. Inspect cassettes from the CLI

```bash
agenttape inspect cassettes/hello.yaml    # interactions, latency, tokens
agenttape timeline cassettes/hello.yaml   # ASCII waterfall of the run
agenttape diff a.yaml b.yaml              # structured diff of two runs
agenttape view cassettes/hello.yaml       # self-contained HTML viewer
```

[Full CLI reference →](cli.md)

---

## Cheat sheet

| You want to… | Use |
| --- | --- |
| Record a block of code | `with use_cassette("name", mode="record"):` |
| Replay offline | `with use_cassette("name", mode="none"):` |
| Replay in a test | `@agenttape.replay("name")` |
| Mock a side-effecting function | `@agenttape.tool` |
| Bind a pytest test to a cassette | `@pytest.mark.agenttape("name")` |
| Re-record in pytest | `pytest --agenttape-record` |
| Run the LLM live, keep tools frozen | `use_cassette("name", live={"llm"})` |

---

## Next steps

- [Record vs Replay](record-vs-replay.md) — the mental model, in depth.
- [Cassette Modes](cassette-modes.md) — `none`, `once`, `new_episodes`, `all`/`record`.
- [Configuration](configuration.md) — set defaults in `agenttape.toml`.
