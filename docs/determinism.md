# Determinism

Freezing time, randomness, and unique IDs.

---

## What is it?

Agents often rely on non-deterministic functions. They might inject the current time into a system prompt ("Today is Tuesday..."), generate UUIDs for request tracing, or use `random` to sample choices.

If these values change between the record phase and the replay phase, the Replay Engine will fail because the prompts no longer match.

AgentTape solves this with its **freeze layer**, which pins these non-deterministic sources to their recorded values.

---

## Why it exists

Without the freeze layer, you would have to write custom matchers to ignore every timestamp in every prompt, or you'd have to rewrite your application code to mock out `time.time()` manually during tests.

AgentTape handles this automatically, guaranteeing that your agent executes with the exact same environmental state during replay as it did during recording.

---

## How it Works

When AgentTape starts a session, you can pass a list of subsystems to freeze. By default, it freezes `clock`, `uuid`, and `random`.

```python
# Default behavior:
with agenttape.use_cassette("agent", freeze=["clock", "uuid", "random"]):
    # ...

# Disable all freezing:
with agenttape.use_cassette("agent", freeze=[]):
    # ...
```

### 1. `clock`
AgentTape patches `time.time`, `time.monotonic`, and `datetime.now`/`utcnow`/`today`.
When recording, it saves the start time to the cassette's `meta.freeze` block.
When replaying, it forces all clock functions to start from that exact saved time. (Latency measurements using `time.perf_counter` remain unaffected).

### 2. `uuid`
AgentTape intercepts `uuid.uuid4()`.
During recording, it saves the sequence of generated UUIDs into the cassette.
During replay, it yields that exact sequence of UUIDs back to your application.

### 3. `random`
AgentTape seeds Python's built-in `random` module (and `numpy`'s RNG, if installed) deterministically based on the cassette's metadata.

---

## Environment Variables

Sometimes agents depend on environment variables (like a `FEATURE_FLAG` or `MODEL_TIER`). If these change, your agent might behave differently, causing replay to fail confusingly.

You can tell AgentTape to snapshot specific environment variables.

```toml
# agenttape.toml
env_snapshot = ["MODEL_TIER", "FEATURE_FLAGS"]
```

During recording, AgentTape saves the values of these variables to the cassette. During replay, if the current environment doesn't match the saved snapshot, AgentTape emits a `DeterminismDriftWarning` to alert you that your environment is misconfigured.

---

## Important Considerations

**Real API timestamps**: If you freeze the clock during recording, real API calls made by your application will also use that frozen time. If an external API requires a live, cryptographically signed timestamp (like AWS SigV4), freezing the clock will cause the real API call to fail during recording.

In these cases, you must exclude `clock` from the `freeze` list for that specific cassette:

```python
with agenttape.use_cassette("aws_agent", freeze=["uuid", "random"]):
    pass
```

---

## Summary

*   Agents use time, UUIDs, and randomness, which break replay matching.
*   AgentTape automatically freezes these subsystems by default.
*   The frozen states are saved in the cassette metadata.
*   You can disable specific freezes if they interfere with real API authentication during recording.

---

**Next Steps**: Learn how to unfreeze specific boundaries to test new code against old recordings in [Partial Replay](mixed-replay.md).