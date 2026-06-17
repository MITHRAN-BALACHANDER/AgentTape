# Replay Engine

How AgentTape matches live requests against recorded cassettes.

---

## What is it?

The Replay Engine is the core component of AgentTape. When running in replay mode, it receives every intercepted request (an LLM call, a tool execution, etc.) and decides which recorded interaction to return.

It does this by using a set of rules called **Matchers**.

---

## How it Works

When AgentTape records a session, it saves interactions sequentially into a list.

During replay, when a request is intercepted:
1.  The Replay Engine looks at the *next available* unplayed interaction in the cassette.
2.  It compares the live request against the recorded request using its Matchers.
3.  If all Matchers agree they are identical, it returns the recorded response.
4.  If they don't match, it raises an `UnmatchedInteractionError` and prints a detailed diff.

### Sequential Matching

AgentTape matches sequentially, not globally. If you ask an LLM for the weather in London, and then ask for the weather in Paris, the cassette expects the London call first, and the Paris call second. If your code changes the order, AgentTape will fail.

This strictness ensures your agent's exact execution path is preserved.

---

## Matchers

Matchers are the rules that compare requests.

By default, AgentTape is extremely strict. However, some things naturally change between runs (like timestamps in a prompt, or random trace IDs in a header). AgentTape uses the `ignore_volatile` matcher by default to handle these edge cases without losing strictness.

### `ignore_volatile` (Default)
This matcher ignores specific, known fields that change often but don't affect the core logic of the request.
*   **Examples**: `Date` headers, `X-Amz-Date`, `User-Agent`.
*   If everything else matches, but the `Date` header is different, this matcher allows the replay to succeed.

### `exact`
Requires a byte-for-byte identical match between the live request and the recorded request. Useful for cryptographically strict tests.

---

## When Matches Fail

When a match fails, AgentTape refuses to proceed. It does not skip ahead to find a match, and it does not fall back to the network (unless you are using `mode="new_episodes"`).

Instead, it prints a diff to the console showing exactly why it failed.

```diff
UnmatchedInteractionError: run drifted from recorded snapshot

--- Recorded
+++ Actual
@@ -1,4 +1,4 @@
 request:
   messages:
     - role: user
-      content: Name a color.
+      content: Name a bright color.
```

This diff tells you exactly what changed in your code, making it trivial to figure out if it was an intentional change (meaning you need to re-record) or an accidental regression.

---

## Summary

*   The Replay Engine matches requests sequentially.
*   It uses Matchers to compare requests.
*   It ignores volatile fields by default (like timestamps).
*   If a match fails, it stops execution and prints a diff.

---

**Next Steps**: Learn how to eliminate non-determinism entirely in [Determinism](determinism.md).