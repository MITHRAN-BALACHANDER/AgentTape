# Cassettes

The plain-text files that store your agent's interactions.

---

## What is it?

A **cassette** is a serialized log of every interaction that occurred while AgentTape was active.

They are stored as YAML files, making them easily readable, diffable, and editable by humans. When AgentTape is in replay mode, it uses these cassettes as its sole source of truth.

---

## Why it exists

If tests were recorded into an opaque binary format, you wouldn't know what was changing when an API updated.

Because AgentTape uses YAML, cassettes become part of your Git repository. When your agent's behavior changes, the cassette changes, and you can see exactly *why* in a GitHub pull request.

---

## Anatomy of a Cassette

A cassette file consists of two main sections: `meta` and `interactions`.

```yaml
meta:
  version: 1
  recorded_at: "2024-05-10T12:00:00Z"
  duration_ms: 1250
  freeze:
    clock: 1715342400.0
    uuid:
      - "550e8400-e29b-41d4-a716-446655440000"

interactions:
  - kind: llm
    start_ms: 0
    duration_ms: 800
    request:
      model: gpt-4o-mini
      messages:
        - role: user
          content: What is the weather?
    response:
      content: I need to use the weather tool to find out.
      tool_calls:
        - id: call_123
          function:
            name: get_weather
            arguments: '{"location": "London"}'

  - kind: tool
    boundary: get_weather
    start_ms: 850
    duration_ms: 400
    request:
      args: ["London"]
      kwargs: {}
    response:
      output: {"temp": 15, "condition": "rainy"}
```

### The `meta` block
This block contains global information about the recording session.
*   **`recorded_at`**: When the session was recorded.
*   **`duration_ms`**: Total time taken.
*   **`freeze`**: The deterministic seeds (clock, random, uuid) used during the recording, ensuring replay behaves identically.

### The `interactions` block
This is an ordered list of every boundary crossing that occurred.
*   **`kind`**: What type of interaction this is (`llm`, `tool`, `http`, `retrieval`, etc).
*   **`request`**: The inputs sent to the boundary (prompts, HTTP headers, function arguments).
*   **`response`**: The outputs returned by the boundary.
*   **`boundary`** (optional): For tools or custom boundaries, the name of the function called.

---

## Hand-Editing Cassettes

Because cassettes are YAML, you can edit them directly. This is a powerful debugging technique.

Imagine you want to test how your code handles a network timeout or a malformed JSON response from an LLM. Instead of trying to "prompt engineer" the model to make a mistake, you can simply edit the YAML file.

1.  Record a successful interaction.
2.  Open the cassette YAML file.
3.  Change the `response.content` to be `{"invalid": "json"`.
4.  Run your test in `mode="none"`.

Your code will immediately receive the malformed JSON, and you can test your error handling logic without ever hitting the network.

---

## Summary

*   Cassettes are human-readable YAML files.
*   They contain metadata and an ordered list of interactions.
*   They are checked into Git so you can review changes over time.
*   You can hand-edit them to test edge cases without API calls.

---

**Next Steps**: See how AgentTape handles Python functions in [Tools](tools.md).