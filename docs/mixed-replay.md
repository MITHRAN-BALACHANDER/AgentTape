# Partial Replay

Run the LLM for real while keeping tools mocked.

---

## What is it?

Partial replay (also known as mixed replay) is AgentTape's killer feature. It allows you to selectively unfreeze specific parts of your agent—like the LLM—while keeping expensive or dangerous parts—like tools—frozen as recordings.

---

## Why it exists

Imagine you have a cassette of an agent executing a complex task: it searches a vector database, uses a calculator, and writes a row to PostgreSQL.

Now, you want to test if upgrading from `gpt-3.5` to `gpt-4o` makes the agent faster, or if a new system prompt improves its reasoning.

If you just run a normal replay, the test fails immediately because the new prompt doesn't match the old recorded prompt. If you delete the cassette and re-record `all`, you have to execute the real PostgreSQL write again, which is dangerous.

Partial replay solves this. It lets you say: **"Let the LLM run against the real OpenAI API, but if it tries to call a tool, feed it the results from the cassette."**

---

## Quick Example

You enable partial replay by passing a `live` set to `use_cassette`.

```python
import agenttape

# Only the LLM runs for real. Every tool is served from the cassette.
with agenttape.use_cassette("checkout", live={"llm"}):
    result = run_agent()
```

### What happens?

1.  The agent sends the new prompt to OpenAI. **(Real network call, costs money)**.
2.  OpenAI responds and decides to call the `charge_card` tool.
3.  AgentTape intercepts the tool call. Because `tool` is not in the `live` set, AgentTape looks in the `checkout.yaml` cassette.
4.  It returns the saved `charge_card` result. **(Zero side effects)**.

When the run finishes, AgentTape does not overwrite your original `checkout.yaml`. Instead, it writes a new file called `checkout.derived.yaml`.

You can then compare them to see exactly how your prompt change affected the agent's behavior:

```bash
agenttape diff cassettes/checkout.yaml cassettes/checkout.derived.yaml
```

---

## Defining Boundaries

The strings you pass to the `live` set match the `kind` or `boundary` of interactions in your cassette.

*   `"llm"`: Unfreezes all language model calls.
*   `"tool"`: Unfreezes all functions decorated with `@agenttape.tool`.
*   `"charge_card"`: Unfreezes only the specific tool named `charge_card`.

You can also pass a `frozen` set, which does the exact opposite: it forces specific boundaries to use the cassette, even if the global mode is `record`.

```python
# Record a new session, but DO NOT run the dangerous tool.
# It MUST use the saved response from the cassette.
with agenttape.use_cassette("checkout", mode="record", frozen={"charge_card"}):
    run_agent()
```

---

## Strict Adherence

If you run an LLM live, it might decide to call a tool that wasn't called in the original recording. Or it might call a tool with different arguments.

If this happens, AgentTape **fails immediately** with an `UnmatchedInteractionError`. Because the tool is not marked as `live`, AgentTape refuses to execute it for real. It will only return exact matches from the cassette.

This guarantees that a hallucinating LLM cannot accidentally wipe your database during a test run.

---

## Summary

*   Partial replay lets you test new prompts/models without triggering real side effects.
*   Use `live={"llm"}` to let LLMs hit the network while tools stay mocked.
*   AgentTape writes a `.derived.yaml` file so you can diff the results.
*   If a live LLM tries to do something new with a frozen tool, the test fails safely.

---

**Next Steps**: Learn how to ensure your cassettes don't leak secrets in [Redaction](redaction.md).