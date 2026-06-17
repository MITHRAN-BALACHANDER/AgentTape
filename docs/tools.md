# Tools

Safely recording and mocking Python functions with side effects.

---

## What is it?

Tools are the functions your agent calls to interact with the world: executing a SQL query, fetching a webpage, or charging a credit card.

AgentTape provides decorators to explicitly mark these functions so their inputs and outputs are recorded and replayed, just like LLM network calls.

---

## Why it exists

While intercepting `openai` network calls is great for saving money, intercepting tools is **essential for safety**.

If your agent decides to call a tool that deletes a user from a database, you cannot allow that to happen during a test suite. By marking the tool, AgentTape ensures it only executes during a recording session. During replay, it is perfectly mocked.

---

## How it Works

You mark a function using the `@agenttape.tool` decorator.

```python
import agenttape
import requests

@agenttape.tool
def get_user_profile(user_id: int) -> dict:
    # This might take 2 seconds and hit a real API
    response = requests.get(f"https://api.example.com/users/{user_id}")
    return response.json()
```

### During Record
1. The agent calls `get_user_profile(42)`.
2. AgentTape intercepts the call.
3. The real function executes, hitting the network.
4. AgentTape saves the input `args=[42]` and the JSON output to the cassette.
5. The result is returned to the agent.

### During Replay
1. The agent calls `get_user_profile(42)`.
2. AgentTape intercepts the call.
3. AgentTape looks up `get_user_profile` in the cassette.
4. It verifies the arguments match `[42]`.
5. It returns the saved JSON output. **The real function is completely bypassed.**

---

## Semantic Boundaries

AgentTape provides several decorators depending on the *kind* of action the function performs. This metadata makes cassettes easier to read and allows for granular filtering later.

### `@agenttape.tool`
For general-purpose agent actions (e.g., calculator, weather API, slack post).

### `@agenttape.retrieval`
For functions that fetch documents from vector stores or search engines.

```python
@agenttape.retrieval
def search_docs(query: str) -> list[str]:
    # ... query vector DB ...
```

### `@agenttape.memory_read` and `@agenttape.memory_write`
For functions that interact with long-term agent memory.

---

## Best Practices

*   **Only wrap boundary functions**: Do not wrap pure business logic or internal helper functions. Only wrap functions that cross a boundary (network, disk, database).
*   **Keep inputs simple**: AgentTape needs to serialize the arguments of your tools to YAML. If you pass complex, custom objects into a tool, AgentTape may not be able to record them properly. Pass simple types (strings, ints, dicts, lists) whenever possible.

---

## Summary

*   Use `@agenttape.tool` to wrap functions that have side effects.
*   Tools execute normally during record mode.
*   Tools are bypassed entirely during replay mode, returning saved outputs.
*   Use semantic decorators (`retrieval`, `memory_read`) for better cassette organization.

---

**Next Steps**: Understand how AgentTape matches these requests in the [Replay Engine](replay-engine.md).