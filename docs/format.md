# Cassette Format

The structure of the YAML files.

---

## What is it?

This page details the exact schema of an AgentTape cassette file.

If you are building custom tools to parse cassettes, or if you need to hand-edit a cassette to fake a specific API response, this is the reference.

---

## The Root Structure

A cassette is a YAML document with exactly two top-level keys.

```yaml
meta: {}
interactions: []
```

---

## The `meta` block

Contains information about the session as a whole.

```yaml
meta:
  version: 1
  recorded_at: "2024-05-10T12:00:00.000000"
  duration_ms: 1250.5
  freeze:
    clock: 1715342400.0
    uuid:
      - "550e8400-e29b-41d4-a716-446655440000"
    random: 42
  env:
    MODEL_TIER: "production"
```

*   **`version`**: The schema version (currently `1`).
*   **`recorded_at`**: ISO 8601 timestamp of when the recording started.
*   **`duration_ms`**: Total execution time in milliseconds.
*   **`freeze`**: The deterministic seeds used by the Freeze layer.
*   **`env`**: The snapshotted environment variables (configured via `env_snapshot`).

---

## The `interactions` list

An ordered list of `Interaction` objects. Every HTTP call, LLM prompt, or tool execution is an interaction.

```yaml
interactions:
  - kind: llm
    boundary: openai.chat.completions.create
    start_ms: 10.5
    duration_ms: 800.0
    request: {}
    response: {}
```

*   **`kind`**: The type of interaction. Standard values are `llm`, `http`, `tool`, `retrieval`, `memory_read`, `memory_write`.
*   **`boundary`**: The specific name of the function or endpoint that was intercepted.
*   **`start_ms`**: The time this interaction started, relative to the session start.
*   **`duration_ms`**: How long the real interaction took.
*   **`request`**: The inputs to the boundary.
*   **`response`**: The outputs from the boundary.

---

## The `request` and `response` objects

The shape of the `request` and `response` objects depends entirely on the `kind` of interaction.

### Tool Requests

When a function is decorated with `@agenttape.tool`, AgentTape serializes its arguments into `args` and `kwargs`.

```yaml
  - kind: tool
    boundary: my_custom_function
    request:
      args: ["user_123"]
      kwargs:
        force_refresh: true
    response:
      output: {"status": "active"}
```

### LLM Requests

When an adapter intercepts an LLM call, it attempts to map the provider's specific API into a somewhat standardized shape, but the raw data is preserved.

```yaml
  - kind: llm
    boundary: openai
    request:
      model: gpt-4o-mini
      messages:
        - role: user
          content: Hello
    response:
      content: Hi there!
      tool_calls: []
      metrics:
        total_tokens: 15
```

### HTTP Requests

If the universal HTTP adapter intercepts a raw network call, it saves standard HTTP semantics.

```yaml
  - kind: http
    boundary: https://api.example.com/v1/data
    request:
      method: GET
      headers:
        Authorization: <REDACTED>
      body: ""
    response:
      status: 200
      headers:
        Content-Type: application/json
      body: '{"ok": true}'
```

---

## Editing Guidelines

*   You can edit `response.content` (for LLMs) or `response.output` (for tools) freely to simulate edge cases.
*   Do not edit `request` fields unless you also change the application code to match; otherwise, the Replay Engine will fail to match the interaction.
*   Do not reorder the items in the `interactions` list unless your application code has also been updated to execute in that new order.