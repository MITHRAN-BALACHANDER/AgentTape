# Mixed / partial replay — "freeze all but one"

This is AgentTape's differentiator. Change **one** thing — a prompt, a model, a
single tool — and re-run while every **other** expensive or dangerous boundary stays
frozen from the recording.

## `live`: run these for real, replay the rest

```python
with agenttape.use_cassette("checkout", live={"llm"}):
    result = run_agent()   # new prompt → new LLM output; every tool stays frozen
```

* Boundaries named in `live` (by kind like `"llm"`/`"tool"`/`"http"`, by a specific
  tool name, or `"*"`) execute for real.
* Everything else is served from the cassette.
* The new live results are recorded into a **derived** cassette
  (`checkout.derived.yaml`) — the original is never mutated unless `mode="all"`.

## `frozen`: the inverse

```python
with agenttape.use_cassette("checkout", frozen={"charge_card"}):
    run_agent()   # only charge_card is replayed; everything else runs live
```

Pass either `live` or `frozen`, never both.

## The side-effect guardrail

Any boundary that is **not** live and has **no** recording raises
`UnmatchedInteractionError`. AgentTape will never silently run a real side effect:

```text
No recorded tool interaction matched this incoming request (charge_card).
Field differences (expected = recorded, received = incoming):
  - args.amount: expected 4200, received 9900
How to fix:
  * If this request is new and expected, re-record with mode='all'/'new_episodes'.
  * To run this boundary for real during replay, add it to the live={...} set.
```

## Typical workflow

```bash
# 1. record a baseline
python agent.py            # writes cassettes/checkout.yaml

# 2. change the prompt, re-run with only the LLM live
#    -> writes cassettes/checkout.derived.yaml, tools stay frozen

# 3. see exactly what changed
agenttape diff cassettes/checkout.yaml cassettes/checkout.derived.yaml
```
