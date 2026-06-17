# AgentTape

**Deterministic record & replay for AI agents.**

AgentTape captures every external interaction your agent makes — both LLM calls **and** tool executions — into human-readable YAML "cassettes," then replays them deterministically so your tests run **offline, for free, with zero side effects.**

[![CI](https://github.com/MITHRAN-BALACHANDER/AgentTape/actions/workflows/ci.yml/badge.svg)](https://github.com/MITHRAN-BALACHANDER/AgentTape/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/agenttape.svg)](https://pypi.org/project/agenttape/)
[![Downloads](https://static.pepy.tech/badge/agenttape)](https://pepy.tech/project/agenttape)
[![Python](https://img.shields.io/pypi/pyversions/agenttape.svg)](https://pypi.org/project/agenttape/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> **Full documentation:** https://MITHRAN-BALACHANDER.github.io/AgentTape/

---

## What it does

AgentTape sits between your agent and the outside world.

- **Record** — run your agent against the real OpenAI API, database, and tools. AgentTape saves every call to a YAML cassette.
- **Replay** — run the same code with the network off. AgentTape serves the saved responses in milliseconds. Your code can't tell the difference.

The usual alternative — hand-written mocks — tests your *assumptions* about a service, not the service itself. AgentTape records the **real** interaction once, then replays it.

## Why it exists

Agent tests are normally slow, flaky, expensive, and dangerous: every run hits live LLM APIs (latency, cost, non-determinism) and executes real tools. If a tool charges a card, writes to a database, or posts to Slack, a test run actually does it. AgentTape gives you the realism of end-to-end tests with the speed and safety of mocks.

## Quick example

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

# 1. Record — calls the real API once, writes cassettes/hello.yaml
with agenttape.use_cassette("hello", mode="record"):
    print(run_agent())

# 2. Replay — zero network, free, identical output every time
with agenttape.use_cassette("hello", mode="none"):
    print(run_agent())
```

The first block calls OpenAI and saves the prompt and response. The second block blocks the network and returns the saved response instantly.

## Record your own tools

Wrap any side-effecting function. It runs normally while recording and returns the saved output during replay — **it never executes for real on replay.**

```python
@agenttape.tool
def charge_card(amount: int) -> dict:
    return payment_api.charge(amount)   # real side effect, skipped on replay
```

## Key features

- **Local-first** — no servers, no telemetry, no network during replay.
- **Deterministic** — same inputs → same recorded output, byte-for-byte (time, UUIDs, and randomness are frozen).
- **Zero side effects** — a replayed tool never runs for real. Safe for CI.
- **Almost-no-code** — one `with` block or one decorator; your agent code is unchanged.
- **Git-friendly** — cassettes are plain YAML you can read, diff, and hand-edit.
- **Partial replay** — run the LLM live against a new prompt while tools stay frozen.
- **Zero core dependencies** — the engine runs on the Python standard library alone.

## Installation

```bash
pip install agenttape            # core (stdlib only, zero deps)
pip install "agenttape[openai]"  # + automatic OpenAI interception
pip install "agenttape[yaml]"    # + PyYAML for faster large-cassette parsing
pip install "agenttape[all]"     # everything
```

## pytest integration

```python
import pytest

@pytest.mark.agenttape("weather_agent")
def test_weather(agenttape_cassette):
    result = run_agent()
    assert "sunny" in result.lower()
    agenttape_cassette.assert_tool_calls(["get_location", "get_weather"])
```

```bash
pytest                      # offline replay (mode=none) — the default
pytest --agenttape-record   # (re)record against real services
```

## CLI

```bash
agenttape init                       # scaffold agenttape.toml + cassettes/
agenttape inspect cassettes/x.yaml   # interactions, latency, tokens
agenttape timeline cassettes/x.yaml  # ASCII waterfall
agenttape diff a.yaml b.yaml         # structured diff of two runs
agenttape view cassettes/x.yaml      # self-contained HTML viewer
```

## Documentation

| Start here | Go deeper |
| --- | --- |
| [What is AgentTape?](https://MITHRAN-BALACHANDER.github.io/AgentTape/) | [Core Concepts](https://MITHRAN-BALACHANDER.github.io/AgentTape/cassettes/) |
| [Your First Recording](https://MITHRAN-BALACHANDER.github.io/AgentTape/your-first-recording/) | [Testing AI Apps](https://MITHRAN-BALACHANDER.github.io/AgentTape/testing-ai-apps/) |
| [Quickstart](https://MITHRAN-BALACHANDER.github.io/AgentTape/quickstart/) | [Python API Reference](https://MITHRAN-BALACHANDER.github.io/AgentTape/api/) |

## License

MIT — see [LICENSE](LICENSE).
