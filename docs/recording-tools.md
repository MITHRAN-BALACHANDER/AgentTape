# Recording Tools

A comprehensive guide to capturing tool executions.

---

## What is it?

We've covered the basics of tools in the Core Concepts section. This guide provides advanced patterns for recording tools, handling complex objects, and using semantic decorators.

---

## The Golden Rule of Tools

AgentTape must be able to serialize the inputs and outputs of your tools to YAML.

If you pass a complex object (like a live database connection or a custom class instance) into a decorated tool, AgentTape will attempt to serialize it. If it cannot cleanly represent the object in YAML, it will fall back to a string representation (e.g., `<MyClass object at 0x1034>`).

During replay, the Replay Engine will compare the string `<MyClass object at 0x1034>` against `<MyClass object at 0x8892>` and the match will fail.

**Always pass and return simple, serializable primitives (strings, ints, lists, dicts) at the boundary.**

### Bad

```python
@agenttape.tool
def get_user_status(db_conn: DatabaseConnection, user: UserObject) -> None:
    # AgentTape cannot serialize db_conn or user reliably.
    pass
```

### Good

```python
@agenttape.tool
def get_user_status(user_id: int) -> str:
    # The database connection is handled *inside* the tool, or globally.
    # AgentTape only sees the integer and the string.
    db_conn = get_global_db()
    return db_conn.query_status(user_id)
```

---

## Tool Decorators

AgentTape provides specific decorators to organize your cassettes semantically. They all function identically under the hood; they only change the `kind` label in the YAML file.

### `@agenttape.tool`
The default decorator. Use this for general actions: sending emails, charging cards, using a calculator, making API calls.

### `@agenttape.retrieval`
Use this for functions that fetch documents for RAG applications. (See [Recording Vector Stores](recording-vector-stores.md)).

### `@agenttape.memory_read` and `@agenttape.memory_write`
Some agents have long-term memory systems (e.g., saving user preferences to a database between sessions). Use these decorators to explicitly mark when the agent is interacting with its memory state.

```python
@agenttape.memory_write
def save_preference(user_id: str, key: str, value: str):
    pass
```

---

## Tools and Partial Replay

When using Partial Replay (`live={"llm"}`), your tools remain frozen.

If your live LLM decides to call a tool with different arguments than it did during recording, AgentTape will instantly fail the test with an `UnmatchedInteractionError`.

For example, if the cassette expects `charge_card(amount=50)`, but the live LLM hallucinates and calls `charge_card(amount=500)`, AgentTape will **not** execute the tool. It blocks the call and fails the test. This is by design, ensuring partial replay never accidentally causes real-world damage.

---

## Summary

*   Always pass serializable data types into decorated functions.
*   Use semantic decorators (`retrieval`, `memory_read`) for better cassette organization.
*   Tools are always blocked during replay, even if the LLM is running live, unless explicitly unfrozen.

---

**Next Steps**: Learn how to use AgentTape to enable [Working Offline](working-offline.md).