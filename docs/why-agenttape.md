# Why AgentTape?

AgentTape provides the safety of mocks with the realism of end-to-end tests.

---

## What is it?

"Why use AgentTape?" is a question about testing philosophy. Testing AI agents with real services is expensive and slow. Testing them with manual mocks is brittle and unrealistic.

AgentTape provides a third option: **deterministic record and replay**. It lets you run real scenarios once, save the exact network traffic and tool outputs, and replay them forever without changing your code.

---

## Why it exists

When testing AI applications, you encounter three major problems:

1.  **Cost and Latency**: Hitting OpenAI, Anthropic, or other LLMs for every unit test is slow. It ruins the developer experience of a fast test suite and costs money on every CI run.
2.  **Non-determinism**: LLMs are naturally probabilistic. Even with temperature set to `0`, APIs can change, models can be updated, and answers can vary. Flaky tests are ignored tests.
3.  **Side Effects**: Agents don't just talk; they act. If your agent has a tool to `execute_sql_query`, `send_email`, or `charge_credit_card`, you absolutely cannot let it run those tools against real systems during a test suite.

If you don't use AgentTape, you have to write manual mocks. Mocks are problematic because they test your *assumptions* about an API, not the API itself. When the real API changes, your mocks will still pass, but your production code will break.

---

## Detailed Walkthrough

Let's look at the core principles that guide AgentTape's design.

### 1. Local-First
AgentTape requires no servers, no telemetry, and no network access during replay. Everything lives in plain text files in your repository. This means your tests can run on an airplane, and your CI never needs API keys.

### 2. Zero Side Effects
When running in replay mode, AgentTape guarantees that a recorded tool will never execute for real. This makes it completely safe to test agents that take destructive actions.

### 3. Git-Friendly
Cassettes are saved as plain YAML files. They are designed to be human-readable, reviewable in pull requests, and hand-editable. You can manually tweak an LLM's response in the YAML file to test how your agent handles edge cases or malformed JSON without needing to "prompt engineer" the LLM into making a mistake.

### 4. Fail Loud, Never Silent
If AgentTape is in replay mode and your agent tries to make a request that isn't in the cassette, AgentTape will immediately raise an error. It will not silently hit the network or run the tool.

---

## Best Practices

*   **Commit your cassettes**: Cassettes should be checked into Git alongside your tests. They are the source of truth for how your agent should behave.
*   **Use `pytest`**: If you use `pytest`, AgentTape has a built-in plugin that makes tests run in offline replay mode by default.

---

## Summary

*   Agent tests are slow, costly, and flaky when hitting real APIs.
*   Manual mocks are brittle and unrealistic.
*   AgentTape records real interactions once and replays them deterministically.
*   It ensures tests run offline, for free, with zero risk of side effects.

---

**Next Steps**: Now that you know why it exists, let's look at [Installation](installation.md).