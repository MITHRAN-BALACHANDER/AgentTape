# Determinism guide

Agents embed nondeterminism — timestamps in prompts, `uuid4()` request ids,
`random`-driven sampling. Left unchecked these make recordings differ run-to-run and
break replay matching. AgentTape's **freeze layer** pins them to recorded values.

## What gets frozen

| Feature | What it does |
|---------|--------------|
| `clock` | Patches `time.time`, `time.monotonic`, `datetime.now/utcnow/today` to a recorded base time. |
| `uuid` | Records the `uuid4()` sequence and replays it in order (deterministic fallback beyond what was recorded). |
| `random` | Seeds `random` (and `numpy` RNG state if present) deterministically. |
| env snapshot | Records a whitelist of env vars and warns on drift at replay. |

Freezing is **opt-in per cassette** and **on by default in `mode="none"`**:

```python
with agenttape.use_cassette("agent", freeze=["clock", "uuid", "random"]):
    ...
with agenttape.use_cassette("agent", freeze=[]):   # disable all freezing
    ...
```

The recorded base values live in `cassette.meta.freeze`, so replay reproduces them
byte-for-byte across machines and CI runners.

## Record-time freezing

When `clock` is enabled, the clock is frozen during **recording** too — so the agent
observes the *same* value it will see on replay. Latency is unaffected because it is
measured with `time.perf_counter`, which is never patched.

!!! note
    Freezing the clock during recording means real API calls also see the frozen
    time. If a request signs with a live timestamp, exclude `clock` from `freeze`.

## Environment drift

```toml
# agenttape.toml
env_snapshot = ["MODEL_TIER", "FEATURE_FLAGS"]
```

If a snapshotted variable changes between record and replay, AgentTape emits a
`DeterminismDriftWarning` rather than failing silently.

## Acceptance: identical recordings across machines

A clock/UUID-dependent agent produces identical *replays* on any machine because the
frozen values come from the committed cassette — not the local clock or RNG.
