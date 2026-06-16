# AgentTape

**VCR.py for AI agents.** Record every external interaction your agent makes — LLM
calls *and* tool calls — into human-readable "cassettes", then replay them
deterministically so your agent tests run **offline, for free, with zero side
effects.**

[![CI](https://github.com/MITHRAN-BALACHANDER/AgentTape/actions/workflows/ci.yml/badge.svg)](https://github.com/MITHRAN-BALACHANDER/AgentTape/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/agenttape.svg)](https://pypi.org/project/agenttape/)
[![Python](https://img.shields.io/pypi/pyversions/agenttape.svg)](https://pypi.org/project/agenttape/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## Why

Agent tests today are slow, flaky, expensive, and dangerous: they hit real LLM
APIs (cost + nondeterminism) and real tools (a tool that charges a card, writes a
row, or posts to Slack *actually does it*). AgentTape records those interactions
once and replays them deterministically afterwards. Your CI runs with **no network
access, no API keys, and no risk of a real side effect.**

* **Local-first** — no server, no telemetry, nothing leaves your machine.
* **Deterministic** — same inputs produce the same recorded outputs, byte-for-byte.
* **Zero side effects in replay** — a replayed tool *never* executes for real.
* **Almost-no-code** — add a decorator or a `with` block.
* **Git-friendly** — cassettes are YAML: diffable, reviewable, hand-editable.
* **Zero core dependencies** — the engine is pure standard library.

## Install

```bash
pip install agenttape            # core (stdlib only)
pip install "agenttape[openai]"  # + OpenAI adapter
pip install "agenttape[yaml]"    # + PyYAML for extra-robust YAML loading
```

## 30-second quickstart

Record once (real API call), then replay forever (no network):

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

# --- record (hits the real API once, writes cassettes/hello.yaml) ---
with agenttape.use_cassette("hello", mode="record"):
    print(run_agent())

# --- replay (zero network calls, milliseconds, free, deterministic) ---
with agenttape.use_cassette("hello", mode="none"):
    print(run_agent())   # identical output, served from the cassette
```

Or as a decorator:

```python
@agenttape.replay("hello")          # mode="none": offline + deterministic
def test_agent():
    assert "hi" in run_agent().lower()
```

## Mixed / partial replay — "freeze all but one"

Change *one* thing — a prompt, a model, a single tool — and re-run while every
**other** expensive or dangerous boundary stays frozen from the recording:

```python
# Only the LLM runs for real; every tool is served from the cassette.
# A *derived* cassette is written — the original is never mutated.
with agenttape.use_cassette("checkout", live={"llm"}):
    result = run_agent()   # new prompt → new LLM output, tools stay frozen

# See exactly what changed:
#   agenttape diff cassettes/checkout.yaml cassettes/checkout.derived.yaml
```

Any boundary that is **not** in `live` and has no recording raises
`UnmatchedInteractionError` — AgentTape will never silently run a real side effect.

## Hand-edit a response

Cassettes are just YAML. Open `cassettes/hello.yaml`, edit a recorded LLM
response, save, and re-run in `mode="none"` — your agent behaves differently with
**no API call at all.** Perfect for testing edge cases and failure paths.

## pytest plugin

Ships in the box. Tests run offline and deterministically by default:

```python
import pytest

@pytest.mark.agenttape("weather_agent")
def test_weather(agenttape_cassette):
    assert run_agent() == "It's sunny."
```

```bash
pytest                       # replay mode, offline, free (CI default)
pytest --agenttape-record    # (re)record cassettes against the real API
```

## CLI

```bash
agenttape init                       # scaffold agenttape.toml + cassettes/
agenttape inspect cassettes/hello    # tokens, latency, cost, per-step I/O
agenttape timeline cassettes/hello   # ASCII waterfall of the run
agenttape diff a.yaml b.yaml         # prompt / model / tool / cost / output diff
agenttape validate cassettes/hello   # schema + determinism + leaked-secret lint
agenttape view cassettes/hello       # self-contained static HTML, no server
agenttape redact cassettes/hello     # re-run secret/PII redaction
agenttape export cassettes/hello --format otel
```

## What this is — and what it isn't

**It is:**

* A deterministic record/replay layer for agent I/O (LLM + tools + raw HTTP).
* A way to make agent tests fast, free, offline and side-effect-free.
* A diff/inspection toolkit for understanding and reviewing agent runs.

**It isn't:**

* It is **not** a way to "replay with a different prompt/model and get a
  deterministic answer for free." Replay reconstructs *recorded* bytes. The moment
  you change an input to a boundary marked `live`, that boundary **really executes**
  (real API call, real cost) and produces a **new** recording. AgentTape is
  explicit about this everywhere — pure replay vs. re-execution are different verbs
  and we never blur them.
* It is **not** an evaluation framework, a prompt optimizer, or a tracing SaaS.

See the [determinism guide](docs/determinism.md) and the
[cassette format spec](docs/format.md) for details.

## License

MIT — see [LICENSE](LICENSE).
