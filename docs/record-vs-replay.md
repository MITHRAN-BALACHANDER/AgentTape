# Record vs Replay

Understand the difference between capturing interactions and simulating them.

---

## What is it?

AgentTape operates in two fundamental phases: **Record** and **Replay**. Understanding the difference between these two phases is critical to using the tool effectively and safely.

---

## The Record Phase

When AgentTape is recording, it acts as a **passthrough observer**.

It intercepts the call your code makes, forwards it to the real destination (e.g., the OpenAI API, or the execution of a Python function), waits for the real result, saves both the input and the result to a cassette file, and then returns the result to your code.

### When to Record

You should only record when:

1.  You are writing a brand new test.
2.  You intentionally changed your agent's code (e.g., updated the prompt, added a new tool, changed the model) and need to capture the new behavior.

### What Happens During Recording

*   Network requests hit real external servers.
*   API keys must be valid.
*   You will be billed for API usage.
*   Tools will execute their actual code.
*   **Side effects will happen** (databases will be written to, emails will be sent).

---

## The Replay Phase

When AgentTape is replaying, it acts as an **air-gapped simulator**.

It intercepts the call your code makes, compares it against the cassette file, and if it finds a match, immediately returns the saved result. It **never** forwards the call to the real destination.

### When to Replay

You should use replay:

1.  Running your test suite locally.
2.  Running tests in Continuous Integration (CI).
3.  Debugging an agent failure without paying for API calls.

### What Happens During Replay

*   Network requests are blocked.
*   API keys do not need to be valid (or even present).
*   API usage is completely free.
*   Tools are mocked.
*   **Zero side effects occur**.

---

## Strict Matching

In Replay mode, AgentTape is extremely strict. It will not guess.

If your code asks the LLM to generate a recipe for "Chocolate Cake", but the cassette only contains a recording for "Vanilla Cake", AgentTape will not hit the network. Instead, it will instantly raise an `UnmatchedInteractionError` and fail the test.

This strictness guarantees that your CI environment never accidentally executes a real side effect just because a test changed slightly.

---

## Summary

*   **Record**: Passthrough, requires network, real side effects, updates the YAML file.
*   **Replay**: Simulator, offline, zero side effects, reads the YAML file, strict matching.

---

**Next Steps**: Learn how to control these phases using [Cassette Modes](cassette-modes.md).