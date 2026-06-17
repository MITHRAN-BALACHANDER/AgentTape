---
title: Extending AgentTape
---

# Extending AgentTape

**Cassettes are an open YAML format. Anything that reads them — analytics, dashboards, eval harnesses, observability pipelines — can be built without importing AgentTape at all.**

---

## Cassettes are just data

To build on AgentTape, read the YAML directly. You don't need the library.

```python title="Total token usage across a test suite"
import yaml
from pathlib import Path

total = 0
for file in Path("cassettes").glob("*.yaml"):
    cassette = yaml.safe_load(file.read_text())
    for interaction in cassette.get("interactions", []):
        if interaction.get("kind") == "llm":
            usage = interaction.get("usage") or {}
            total += usage.get("total_tokens", 0)

print(f"Total tokens across all cassettes: {total}")
```

!!! note "Usage lives at the interaction level"
    Token usage is the interaction's top-level `usage` field (`{prompt_tokens, completion_tokens, total_tokens}`), not nested in the response. See the [cassette format](format.md).

---

## Speed up evaluation loops

Eval frameworks (LangSmith, Braintrust, home-grown scripts) run an agent over hundreds of examples. Against live APIs that's slow and expensive.

Wrap the eval run in a cassette and the *deterministic* parts — routing, tool selection, parsing — run instantly and free:

```python
import agenttape

with agenttape.use_cassette("eval_dataset", mode="none"):
    for example in dataset:
        result = agent.run(example.input)
        score(result, example.expected)
```

This is ideal for regression-testing agent **logic** over a large frozen dataset. To evaluate a *new* model against frozen tool outputs, combine it with [Partial Replay](mixed-replay.md) (`live={"llm"}`).

---

## Export to OpenTelemetry

Turn an offline recording into a standard trace for any observability backend (Datadog, Honeycomb, Jaeger):

```bash
agenttape export cassettes/checkout.yaml --format otel -o trace.json
```

The CLI also exports plain JSON (`--format json`) for tools that prefer it. See the [CLI reference](cli.md#export).

---

## Build a custom viewer

AgentTape ships a self-contained HTML viewer (`agenttape view`), but the format is simple enough to render however you like — a web dashboard, a Slack unfurl, a PR comment bot. The contract you depend on:

| You can rely on | Notes |
| --- | --- |
| `version` | Schema version (`"1"` today); check it for forward-compat |
| `interactions[].kind` | One of `llm`, `tool`, `retrieval`, `memory_read`, `memory_write`, `http` |
| `interactions[].request` / `response` / `error` | The captured payloads |
| `interactions[].usage` / `latency_ms` | Metrics, when present |

[Full schema →](format.md){ .md-button }

---

## Want to intercept a new library instead?

If your goal is to *capture* a new SDK rather than *read* recordings, you want a transport adapter, not an external tool. See [Custom Adapters](adapters.md).

---

## FAQ

??? question "Is the cassette format stable?"
    The schema is versioned (`version: "1"`). Read `version` and treat unknown future versions defensively. Within a major version, fields are additive.

??? question "Can I read cassettes in another language?"
    Yes — it's plain YAML/JSON. Any language with a YAML parser can consume them.

??? question "How do I total cost, not just tokens?"
    Cost depends on per-model pricing AgentTape doesn't hardcode. Read `usage` and `meta.model` (or the request's `model`) and apply your own price table.

---

## Summary

- Cassettes are open YAML — read them with any parser, no AgentTape import required.
- Wrap eval runs in a cassette to test agent logic over big datasets instantly and free.
- `agenttape export --format otel` turns a recording into a standard trace.
- To capture a new SDK instead, write a [custom adapter](adapters.md).

[Next: Python API Reference →](api.md){ .md-button .md-button--primary }
