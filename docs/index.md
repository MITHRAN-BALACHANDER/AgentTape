---
title: What is AgentTape?
---

# What is AgentTape?

**AgentTape records what your AI agent says and does, then replays it — so your tests run offline, for free, with zero side effects.**

<div class="grid cards" markdown>

-   :material-record-circle: __Record once__

    Run your agent against the real OpenAI API, database, and tools. AgentTape saves every call to a YAML file.

-   :material-play-circle: __Replay forever__

    Run the same code with the network turned off. AgentTape serves the saved responses in milliseconds.

</div>

---

## The one-minute version

AgentTape sits between your code and the outside world. It intercepts external calls — an OpenAI request, a database query, a custom Python tool — and saves the inputs and outputs to a local file called a **cassette**.

The next time your code runs, AgentTape blocks the real call and returns the saved response instead. Your application can't tell the difference. It thinks it's talking to live services.

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

!!! success "What happened?"
    The **first** block called OpenAI for real and saved the prompt and response into `cassettes/hello.yaml`. The **second** block intercepted the same call, matched the prompt against the cassette, and returned the saved response without touching the network.

---

## Why this matters

Tests for AI agents are usually slow, flaky, expensive, and dangerous:

| Problem | Without AgentTape | With AgentTape |
| --- | --- | --- |
| **Cost** | Every test run burns tokens | Replay is free |
| **Speed** | 1–5s per LLM call | < 5ms per call |
| **Flakiness** | Models drift; outputs vary | Byte-for-byte identical |
| **Side effects** | A tool really charges the card | Replayed tools never execute |
| **Offline** | No network, no tests | Runs on a plane |

The usual alternative is hand-written mocks. But mocks test your *assumptions* about an API, not the API itself — when the real service changes, your mocks keep passing while production breaks. AgentTape captures the **real** interaction once, then replays that.

[Read the full motivation →](why-agenttape.md){ .md-button }

---

## How it works

=== "Recording"

    ```mermaid
    flowchart LR
        A[Your code] --> B[AgentTape]
        B -->|forwards| C[Real world<br/>OpenAI · DB · Stripe]
        C -->|response| B
        B -->|saves| D[(Cassette<br/>YAML)]
        B -->|returns| A
    ```

    AgentTape forwards the call, waits for the real response, **saves both the request and response** to the cassette, then hands the response back to your code.

=== "Replaying"

    ```mermaid
    flowchart LR
        A[Your code] --> B[AgentTape]
        B -->|matches request| D[(Cassette<br/>YAML)]
        D -->|saved response| B
        B -->|returns| A
        C[Real world] -.->|never called| B
    ```

    AgentTape matches the request against the cassette and returns the saved response. The real world is **never** contacted. If no match is found, it raises an error rather than silently hitting the network.

---

## What AgentTape captures

AgentTape doesn't only record LLM calls. It records every **boundary** your agent crosses:

<div class="grid cards" markdown>

-   :material-brain: __LLM calls__

    OpenAI chat completions, responses, and embeddings — captured automatically by the built-in adapter.

-   :material-tools: __Tools__

    Any Python function you mark with `@agenttape.tool` — database writes, API calls, payments.

-   :material-web: __Raw HTTP__

    Any `httpx` or `requests` call, even to services AgentTape has no dedicated adapter for.

-   :material-database-search: __Retrieval & memory__

    Vector-store lookups and agent memory reads/writes, tagged for clarity.

</div>

---

## Core guarantees

!!! abstract "AgentTape's promises"
    - **Local-first** — no servers, no telemetry, no network during replay.
    - **Deterministic** — the same inputs always produce the same recorded output, byte-for-byte.
    - **Zero side effects** — a replayed tool *never* executes for real. Safe for CI.
    - **Fail loud, never silent** — an unmatched request raises an error instead of quietly calling the real service.
    - **Git-friendly** — cassettes are plain YAML you can read, diff, and hand-edit.
    - **Zero core dependencies** — the engine runs on the Python standard library alone.

---

## Where to go next

<div class="grid cards" markdown>

-   :material-rocket-launch: __[Your First Recording](your-first-recording.md)__

    A guided, five-minute walkthrough from zero to replaying offline.

-   :material-lightning-bolt: __[Quickstart](quickstart.md)__

    Already know the idea? Copy-paste your way into an existing project.

-   :material-school: __[Core Concepts](cassettes.md)__

    Understand cassettes, the replay engine, determinism, and partial replay.

-   :material-book-open-variant: __[Python API Reference](api.md)__

    Every function, decorator, and class, with signatures and examples.

</div>

---

## Summary

- AgentTape intercepts your agent's external calls — LLM **and** tool calls.
- It saves them to readable YAML **cassettes**, then replays them deterministically.
- Replay is offline, free, fast, and safe from side effects.
- Integration is one `with` block or one decorator — your agent code stays unchanged.
