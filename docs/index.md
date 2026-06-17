# AgentTape

**VCR.py for AI agents.** Record every external interaction your agent makes — LLM
calls *and* tool calls — into human-readable "cassettes", then replay them
deterministically so your agent tests run **offline, for free, with zero side
effects.**

## Why

Agent tests are slow, flaky, expensive and dangerous: they hit real LLM APIs (cost
+ nondeterminism) and real tools (a tool that charges a card or posts to Slack
*actually does it*). AgentTape records those interactions once and replays them
deterministically afterwards. Your CI runs with **no network access, no API keys,
and no risk of a real side effect.**

## The seven principles

1. **Local-first.** No servers, no network in replay, no telemetry.
2. **Deterministic.** Same inputs → same recorded outputs, byte-for-byte.
3. **Zero side effects in replay.** A replayed tool never executes for real.
4. **Almost-no-code integration.** At most a decorator or context manager.
5. **Git-friendly.** Cassettes are diffable, human-readable, hand-editable.
6. **Framework-agnostic core, thin adapters.** One internal schema.
7. **Fail loud, never silent.** Missing/mismatched recordings raise clearly.

## Install

```bash
pip install agenttape            # core (stdlib only — zero required deps)
pip install "agenttape[openai]"  # + OpenAI adapter
```

Continue to the [Quickstart](quickstart.md).

## What this is — and what it isn't

It **is** a deterministic record/replay layer for agent I/O that makes tests fast,
free, offline and side-effect-free.

It is **not** a way to "replay with a different prompt/model and get a deterministic
answer for free." Replay reconstructs *recorded* bytes; the moment you change an
input to a `live` boundary, that boundary **really executes** and produces a **new**
recording. We are explicit about this everywhere — see
[Replay with changes](replay-with-changes.md).
