---
hide:
  - navigation
  - toc
---

<div class="at-hero" markdown>

<span class="at-tag">VCR.py for AI agents</span>

# AgentTape

<p class="at-lead" markdown>
Record every external interaction your agent makes — LLM calls and tool calls — into
human-readable cassettes, then replay them deterministically so your agent tests run
offline, for free, with zero side effects.
</p>

<div class="at-cta" markdown>
[Get started](quickstart.md){ .md-button .md-button--primary }
[View on GitHub](https://github.com/MITHRAN-BALACHANDER/AgentTape){ .md-button }
</div>

</div>

## Why

Agent tests are slow, flaky, expensive and dangerous: they hit real LLM APIs (cost +
nondeterminism) and real tools (a tool that charges a card or posts to Slack actually
does it). AgentTape records those interactions once and replays them deterministically
afterwards. Your CI runs with no network access, no API keys, and no risk of a real
side effect.

## The seven principles

<div class="feature-grid" markdown>

<div class="feature-card" markdown>
### <span class="at-num">1</span> Local-first
No servers, no network in replay, no telemetry.
</div>

<div class="feature-card" markdown>
### <span class="at-num">2</span> Deterministic
Same inputs produce the same recorded outputs, byte-for-byte.
</div>

<div class="feature-card" markdown>
### <span class="at-num">3</span> Zero side effects in replay
A replayed tool never executes for real.
</div>

<div class="feature-card" markdown>
### <span class="at-num">4</span> Almost-no-code
At most a decorator or a context manager.
</div>

<div class="feature-card" markdown>
### <span class="at-num">5</span> Git-friendly
Cassettes are diffable, human-readable, hand-editable.
</div>

<div class="feature-card" markdown>
### <span class="at-num">6</span> Framework-agnostic core
Thin adapters translate to one internal schema.
</div>

<div class="feature-card" markdown>
### <span class="at-num">7</span> Fail loud, never silent
Missing or mismatched recordings raise clearly.
</div>

</div>

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
answer for free." Replay reconstructs *recorded* bytes; the moment you change an input
to a `live` boundary, that boundary **really executes** and produces a **new**
recording. We are explicit about this everywhere — see
[Replay with changes](replay-with-changes.md).
