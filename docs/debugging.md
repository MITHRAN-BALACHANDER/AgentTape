# Debugging

How to fix unmatched interactions and non-determinism.

---

## What is it?

When AgentTape is running in replay mode (`mode="none"`), it is extremely strict. If your live request doesn't match the recorded cassette exactly, AgentTape will throw an error.

This page explains how to debug the two most common errors.

---

## 1. UnmatchedInteractionError

This error occurs when your code makes a request that AgentTape cannot find in the cassette.

### Symptoms
AgentTape halts execution and prints a unified diff to the console.

```diff
agenttape.errors.UnmatchedInteractionError: run drifted from recorded snapshot

--- Recorded
+++ Actual
@@ -1,4 +1,4 @@
 request:
   messages:
     - role: user
-      content: What is the weather today?
+      content: What is the weather tomorrow?
```

### How to Fix

**1. Was the change intentional?**
If you intentionally changed the prompt (from "today" to "tomorrow"), the error is expected. The cassette is out of date.
*   **Fix**: Run the test with `pytest --agenttape-record` (or set `mode="record"`) to generate a new cassette.

**2. Was the change unintentional?**
If you didn't mean to change the agent's behavior, AgentTape just saved you from a regression!
*   **Fix**: Revert your code changes to make the prompt match the recording again.

**3. Is the change non-deterministic?**
If the diff shows a timestamp, a random UUID, or a constantly changing session ID, it means you have non-determinism in your prompt.
*   **Fix**: See the Determinism section below.

---

## 2. DeterminismDriftWarning

This warning occurs when AgentTape detects that a frozen system or environment variable has changed.

### Symptoms
AgentTape prints a warning indicating that the environment is different than when the cassette was recorded.

### How to Fix

**1. Environment Variables**
If you configured `env_snapshot = ["MODEL_NAME"]` in your `agenttape.toml`, and you recorded the cassette with `MODEL_NAME=gpt-4`, but are replaying with `MODEL_NAME=gpt-3.5`, AgentTape will warn you.
*   **Fix**: Ensure your test environment matches your recording environment, or re-record the cassette.

**2. Unfrozen Timestamp/UUID**
If you see timestamps or UUIDs causing `UnmatchedInteractionError`s, it means the `freeze` layer is not active or is not catching the specific function your agent uses to generate those values.
*   **Fix**: Ensure `freeze = ["clock", "uuid", "random"]` is set in your configuration. If you are generating unique IDs using a custom library, you may need to mock that specific function yourself using standard `unittest.mock.patch` alongside AgentTape.

---

## Using the CLI

AgentTape provides a CLI tool to inspect cassettes without having to read raw YAML.

### `inspect`
Shows high-level metrics for the cassette (duration, total tokens, number of interactions).

```bash
agenttape inspect cassettes/hello.yaml
```

### `diff`
Compares two cassettes. This is incredibly useful when using Partial Replay to see how a new model behaves compared to an old recording.

```bash
agenttape diff cassettes/checkout.yaml cassettes/checkout.derived.yaml
```

### `timeline`
Prints an ASCII waterfall chart showing exactly when each LLM call and tool execution happened during the recording.

```bash
agenttape timeline cassettes/hello.yaml
```

---

## Summary

*   Read the diffs provided by `UnmatchedInteractionError` carefully.
*   If the change was intentional, re-record.
*   If the change was unintentional, fix your code.
*   Use the CLI to inspect and diff cassettes to understand complex failures.

---

**Next Steps**: For advanced use cases, learn how to build [Custom Adapters](adapters.md).