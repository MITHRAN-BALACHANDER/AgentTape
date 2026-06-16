# Replay with changes (the honest version)

AgentTape is deliberate about the difference between **replaying a recording** (no
external calls) and **re-executing with a change** (real calls, new cassette). We
never blur the two — pure replay and re-execution are different verbs.

## Pure replay — zero external calls

```python
with agenttape.use_cassette("run", mode="none"):
    run_agent()   # reconstructed entirely from recorded bytes. No API. No cost.
```

Use `agenttape replay <cassette>` to step the reconstructed timeline.

## Replay with a prompt change

Edit the prompt, then re-run with **only the LLM live** so tools stay frozen:

```python
with agenttape.use_cassette("run", live={"llm"}):
    new_output = run_agent()   # the LLM REALLY runs (real call, real cost)
```

```bash
agenttape diff cassettes/run.yaml cassettes/run.derived.yaml --type output
```

## Replay with a different model

```toml
# agenttape.toml
model_override = "gpt-4o"
```

```python
with agenttape.use_cassette("run", live={"llm"}):
    run_agent()   # a real call to the new model — this is re-execution, not replay
```

!!! warning "We say this loudly on purpose"
    Swapping the model or prompt and re-running is **not** deterministic replay and
    **not** free. The `live` boundary genuinely executes and produces a **new**
    recording. Anyone who tells you they can "replay your agent with a different
    model for free and get a real answer" is misframing it. AgentTape will not.

## What stays guaranteed

Even during re-execution, every boundary **not** in `live` is served from the
cassette and cannot cause a real side effect. So you can safely re-run a checkout
agent with a new prompt without charging a single card.
