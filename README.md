# AgentTape

Deterministic record and replay for AI agents.

AgentTape captures every external interaction your agent makes—both LLM calls and tool executions—into human-readable "cassettes." It then replays them deterministically so your tests run **offline, for free, with zero side effects.**

[![CI](https://github.com/MITHRAN-BALACHANDER/AgentTape/actions/workflows/ci.yml/badge.svg)](https://github.com/MITHRAN-BALACHANDER/AgentTape/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/agenttape.svg)](https://pypi.org/project/agenttape/)
[![Downloads](https://static.pepy.tech/badge/agenttape)](https://pepy.tech/project/agenttape)
[![Python](https://img.shields.io/pypi/pyversions/agenttape.svg)](https://pypi.org/project/agenttape/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## What is it?

AgentTape is a testing and debugging tool for AI applications. It sits between your agent and the outside world.

When you run your agent in **record mode**, AgentTape saves every API call, prompt, and tool execution to a YAML file (a cassette).

When you run your agent in **replay mode**, AgentTape intercepts all network and tool calls and serves the exact responses saved in the cassette. Your code thinks it's talking to the real world, but it's completely offline.

## Why it exists

Agent tests are traditionally slow, flaky, expensive, and dangerous.

Every test run hits real LLM APIs (incurring latency, cost, and non-determinism) and executes real tools. If a tool charges a credit card, writes to a database, or posts to Slack—a test run will actually perform those actions.

Without AgentTape, you have to choose between writing fragile mocks or running expensive, slow end-to-end tests. AgentTape gives you the best of both worlds: the realism of end-to-end tests with the speed and safety of mocks.

## Quick Example

Here is the smallest possible working example.

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

# 1. Record (hits the real API once, writes to cassettes/hello.yaml)
with agenttape.use_cassette("hello", mode="record"):
    print(run_agent())

# 2. Replay (zero network calls, completely free, perfectly deterministic)
with agenttape.use_cassette("hello", mode="none"):
    print(run_agent()) # Outputs the exact same text, served from the cassette
```

**What happened?**
The first time you run this, AgentTape talks to OpenAI and saves the prompt and response. The second time, AgentTape blocks the network request and immediately returns the saved response.

## Key Features

- **Local-first**: No servers, no network required in replay, no telemetry.
- **Deterministic**: The same inputs always produce the exact same recorded outputs, byte-for-byte.
- **Zero side effects**: A replayed tool never executes for real. Safe for CI.
- **Almost-no-code integration**: Add a single decorator or `with` block to your existing code.
- **Git-friendly**: Cassettes are plain YAML. You can read, diff, and hand-edit them.
- **Zero core dependencies**: The engine is built entirely on the Python standard library.

## Installation

Install AgentTape using pip. The core package has no external dependencies.

```bash
pip install agenttape            # core (stdlib only)
pip install "agenttape[openai]"  # + OpenAI adapter
pip install "agenttape[yaml]"    # + PyYAML for extra-robust YAML loading
```

## Documentation

Ready to start building? Check out our documentation:

- [Introduction](https://MITHRAN-BALACHANDER.github.io/AgentTape/)
- [Quickstart](https://MITHRAN-BALACHANDER.github.io/AgentTape/quickstart)
- [Core Concepts](https://MITHRAN-BALACHANDER.github.io/AgentTape/cassettes)
- [Guides](https://MITHRAN-BALACHANDER.github.io/AgentTape/testing-ai-apps)

## License

MIT — see [LICENSE](LICENSE) for details.
