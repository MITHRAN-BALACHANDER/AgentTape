# What is AgentTape?

AgentTape is a deterministic record and replay framework for testing and debugging AI agents.

---

## What is it?

AgentTape is a Python library that sits between your code and the outside world.

It intercepts external calls—like hitting the OpenAI API, querying a database, or triggering a custom Python tool—and saves the inputs and outputs to a local file called a **cassette**. The next time your code runs, AgentTape blocks the network request and instantly returns the saved response.

Your application code does not know it is being recorded or replayed. It thinks it's interacting with live services.

---

## Why it exists

Building AI applications introduces new testing challenges.

Traditional tests expect deterministic inputs and outputs. But AI models are non-deterministic, slow, and cost money per token. If your agent uses tools that write to a database or charge a credit card, you cannot safely run those tests in Continuous Integration (CI).

Without AgentTape, developers usually resort to writing brittle mocks for every API and tool, or they accept slow, flaky end-to-end tests that occasionally cause real-world side effects.

AgentTape solves this by giving you the realism of a real API call during recording, and the safety, speed, and determinism of a mock during replay.

---

## Quick Example

Here is a minimal example using AgentTape to record an OpenAI call.

```python
import agenttape
from openai import OpenAI

def ask_agent():
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "What is 2+2?"}]
    )
    return response.choices[0].message.content

# Run 1: Hits the real OpenAI API and writes the result to a YAML file.
with agenttape.use_cassette("math_agent", mode="record"):
    print(ask_agent())

# Run 2: Zero network calls. Returns the exact string from the YAML file.
with agenttape.use_cassette("math_agent", mode="none"):
    print(ask_agent())
```

**What happened?**
The first block executed a real API request and recorded it into a `cassettes/math_agent.yaml` file. The second block intercepted the `OpenAI` client, read from the `math_agent.yaml` file, and instantly returned the exact same response without touching the network.

---

## How it Works

AgentTape uses a combination of request interceptors (for HTTP/APIs) and decorators (for Python functions).

```text
User Code
    ↓
AgentTape (Interceptor / Decorator)
    ↓ (Mode: Record)
Real World (OpenAI / Database / Stripe)
    ↓
AgentTape (Saves to Cassette)
    ↓
User Code
```

In **replay mode**, the flow is shorter:

```text
User Code
    ↓
AgentTape (Matches input)
    ↓ (Mode: Replay)
Reads from Cassette
    ↓
User Code
```

AgentTape compares your current request (e.g., the LLM prompt and parameters) against the requests saved in the cassette. If it finds an exact match, it returns the saved output. If it doesn't, it fails loudly to prevent accidental side effects.

---

## Summary

* AgentTape intercepts LLM calls and tool executions.
* It saves them to local YAML files called cassettes.
* Replaying cassettes makes tests completely offline, free, and fast.
* It prevents dangerous side effects during test runs.

---

**Next Steps**: Continue to [Why AgentTape?](why-agenttape.md) to understand the core problems AgentTape solves in depth.
