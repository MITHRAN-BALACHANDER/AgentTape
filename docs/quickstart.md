# Quickstart

A rapid reference for integrating AgentTape into your project.

---

## What is it?

This page provides the fastest path to getting AgentTape running in an existing codebase.

---

## 1. Install

```bash
pip install "agenttape[openai]"
```

*(Or replace `openai` with the adapter you need).*

---

## 2. Basic Usage (Context Manager)

Wrap the code you want to record or replay in a `use_cassette` block.

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
with agenttape.use_cassette("hello", mode="record"):
    print(run_agent())
with agenttape.use_cassette("hello", mode="none"):
    print(run_agent())
```

---

## 3. Basic Usage (Decorator)

You can also use AgentTape as a decorator. By default, the decorator uses `mode="none"`, which ensures your tests remain offline and deterministic.

```python
import agenttape

@agenttape.replay("hello")
def test_agent():
    assert "hi" in run_agent().lower()
```

---

## 4. Recording Tools

AgentTape doesn't just record LLM calls; it records the tools your agent uses.

Wrap any function that touches the outside world with `@agenttape.tool`. During a recording, it executes normally. During replay, it returns the saved output and **never executes for real**.

```python
import agenttape

@agenttape.tool
def charge_card(amount: int) -> dict:
    return payment_api.charge(amount) # Real side effect, skipped in replay!

with agenttape.use_cassette("checkout", mode="none"):
    charge_card(4200) # Returns recorded result instantly
```

Other decorators available for fine-grained semantic boundaries:
*   `@agenttape.retrieval`
*   `@agenttape.memory_read`
*   `@agenttape.memory_write`

---

## 5. Using pytest

If you use `pytest`, AgentTape provides a built-in plugin.

```python
import pytest

@pytest.mark.agenttape("weather_agent")
def test_weather(agenttape_cassette):
    assert run_agent() == "It's sunny."
```

By default, the plugin runs tests offline (`mode="none"`). To record new cassettes, run pytest with the record flag:

```bash
pytest --agenttape-record
```

---

## Summary

* Use `with agenttape.use_cassette()` for targeted recording.
* Use `@agenttape.replay()` to decorate test functions.
* Use `@agenttape.tool` to mock out side effects automatically.
* Use `@pytest.mark.agenttape` for seamless pytest integration.

---

**Next Steps**: Understand the mental model deeply in [Record vs Replay](record-vs-replay.md).