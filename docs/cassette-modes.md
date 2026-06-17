# Cassette Modes

Control how AgentTape reads and writes cassettes.

---

## What is it?

Cassette modes tell AgentTape how strict it should be about using recorded data versus hitting the real network.

You set the mode when you start a session:

```python
with agenttape.use_cassette("my_test", mode="none"):
    # ...
```

---

## The Modes

AgentTape supports five modes.

### 1. `none` (Default)

**The safest mode. Perfect for CI and local tests.**

*   **Behavior**: Replay only.
*   **Rules**: If a request matches a recorded interaction, AgentTape returns it. If the request is new, or if the cassette file doesn't exist, AgentTape raises an error immediately.
*   **Network**: Completely disabled.

### 2. `once`

**The lazy recording mode.**

*   **Behavior**: Record if missing, replay if present.
*   **Rules**: If the cassette file does not exist, AgentTape will record everything and save the file. If the file already exists, AgentTape will switch to `none` mode and act strictly as a replayer.
*   **Network**: Enabled only on the very first run.

### 3. `new_episodes`

**The incremental recording mode.**

*   **Behavior**: Replay knowns, record unknowns.
*   **Rules**: If a request matches a recorded interaction, AgentTape returns it. If the request is new (e.g., your agent made a follow-up LLM call it didn't make before), AgentTape will hit the real network, append the new interaction to the cassette, and return the real result.
*   **Network**: Enabled only for unmatched requests.

### 4. `all`

**The overwrite mode.**

*   **Behavior**: Record everything, always.
*   **Rules**: AgentTape completely ignores any existing cassette file. It forwards every request to the real network, and rewrites the cassette file from scratch.
*   **Network**: Always enabled.

### 5. `record`

**An explicit alias for `all`.**

*   **Behavior**: Identical to `all`. Use this when you want to be semantically clear that you are actively recording a new session.

---

## Best Practices

*   **Use `none` in CI**. This is the only way to guarantee your test suite won't break due to a network outage or cause an accidental side effect.
*   **Use `once` or `new_episodes` when writing tests**. This allows you to build out a test suite incrementally without manually managing modes.
*   **Use `record` when updating prompts**. If you change a prompt, the old recording is invalid. Run your test locally with `mode="record"` once to capture the new behavior, then switch back to `none`.

---

## Summary

*   `none`: strict replay, no network.
*   `once`: record if file is missing, replay otherwise.
*   `new_episodes`: replay matches, record new requests.
*   `all` / `record`: ignore old file, record everything fresh.

---

**Next Steps**: Learn how to globally configure AgentTape in [Configuration](configuration.md).