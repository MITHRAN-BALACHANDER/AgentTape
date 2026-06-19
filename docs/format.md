---
title: Cassette Format
---

# Cassette Format

**The exact schema of a cassette file — for building tools that read them and for hand-editing them safely. Schema `version` is `"1"`.**

---

## Root structure

A cassette has run metadata at the top level plus an ordered list of interactions.

```yaml
version: '1'                  # schema version
created_at: '2026-06-17T12:00:00.000000'
run_id: bee71bc9-33b8-431b-8012-00a753783931
meta: { ... }                 # about the session
interactions: [ ... ]         # ordered boundary crossings
```

| Key | Type | Description |
| --- | --- | --- |
| `version` | `str` | Schema version (`"1"`). Check it for forward-compat. |
| `created_at` | `str` | ISO-8601 timestamp when the run started |
| `run_id` | `str` | Unique id for this run |
| `meta` | `map` | Session metadata (below) |
| `interactions` | `list` | Ordered `Interaction` objects (below) |

!!! note "Top-level, not nested"
    `version`, `created_at`, and `run_id` live at the **root**, beside `meta` — not inside it.

---

## The `meta` block

```yaml
meta:
  agenttape_version: 0.1.5
  mode: record
  freeze:
    features: [clock, random, uuid]
    base_time: 1781706140.86
    base_iso: '2026-06-17T12:00:00+00:00'
    random_seed: 0
    uuids: ["550e8400-e29b-41d4-a716-446655440000"]
    env: { MODEL_TIER: production }   # only if env_snapshot is set
  tags: [smoke]                        # only if you passed tags=
```

| Field | Description |
| --- | --- |
| `agenttape_version` | Version that recorded the cassette |
| `mode` | Mode used to record |
| `freeze` | Pinned determinism state, so replay reproduces it ([Determinism](determinism.md)) |
| `freeze.env` | Snapshotted env vars (present only if `env_snapshot` is configured) |
| `tags` | Labels passed via `tags=` |

---

## An `interaction`

```yaml
- index: 0
  kind: tool
  boundary: get_weather
  request: { name: get_weather, args: { city: London } }
  response: { temp: 15, condition: rainy }
  match_key: 'sha256:1ed923…'
  latency_ms: 88.0
  usage: null
  tags: []
```

| Field | Type | Description |
| --- | --- | --- |
| `index` | `int` | 0-based position in the run |
| `kind` | `str` | `llm`, `tool`, `retrieval`, `memory_read`, `memory_write`, `http` |
| `boundary` | `str` | The specific name (tool function name, or `"llm"`, or the HTTP host) |
| `request` | `map` | Inputs to the boundary — used for matching |
| `response` | `any` | The output (**omitted** when `error` is present) |
| `error` | `map` | A serialized exception (**omitted** when `response` is present) |
| `match_key` | `str` | `sha256:` hash of the canonical request |
| `latency_ms` | `float` | Real duration of the call |
| `usage` | `map` | Token/usage metadata (LLM calls) |
| `tags` | `list` | Optional labels |
| `metadata` | `map` | Optional extra data |

---

## Request & response shapes by `kind`

The shape of `request`/`response` depends on `kind`.

=== "tool / retrieval / memory"

    Arguments are bound to parameter names (not positional):

    ```yaml
    - kind: tool
      boundary: my_function
      request:
        name: my_function
        args: { user_id: "user_123", force_refresh: true }
      response: { status: active }
    ```

=== "llm"

    The request is the model + messages + params; the response is the provider's full dumped object. Token usage is the interaction-level `usage` field.

    ```yaml
    - kind: llm
      boundary: llm
      request:
        endpoint: chat.completions
        model: gpt-5.5
        messages:
          - { role: user, content: Hello }
      response:
        choices:
          - message: { role: assistant, content: Hi there! }
      usage: { prompt_tokens: 9, completion_tokens: 3, total_tokens: 12 }
    ```

=== "http"

    Captured by the raw httpx/requests fallback. Bodies are structured (`json`/`form`/`text`/`body_b64`); secret and volatile headers are dropped.

    ```yaml
    - kind: http
      boundary: api.example.com
      request:
        method: GET
        url: https://api.example.com/v1/data
        headers: { Accept: application/json }
      response:
        status_code: 200
        headers: { Content-Type: application/json }
        json: { ok: true }
    ```

=== "error (any kind)"

    When a boundary raised, `response` is replaced by `error`. On replay AgentTape re-raises it — as the real exception type when the class is importable.

    ```yaml
    - kind: tool
      boundary: charge_card
      request: { name: charge_card, args: { amount: 4200 } }
      error:
        type: TimeoutError
        module: builtins
        message: "payment gateway timed out"
    ```

---

## Editing guidelines

Hand-editing is a supported workflow ([Working Offline](working-offline.md#faking-errors)). Follow these rules so you don't break matching:

!!! tip "Safe to edit"
    - **`response`** — change `content`, output values, status codes, etc. to simulate edge cases.
    - **`error`** — add or change a serialized exception to test failure paths.
    - **`usage`, `latency_ms`, `tags`** — purely informational.

!!! warning "Edit with care"
    - **`request` fields** change the `match_key`, so the recording won't match your code's call — unless you change the code to match too.
    - **Order of `interactions`** matters when recordings share a match key (they're served in recorded order). Don't reorder unless your code's call order changed.

---

## Summary

- Root keys: `version`, `created_at`, `run_id`, `meta`, `interactions`.
- Each interaction has `kind`, `boundary`, `request`, and `response` **or** `error`, plus `match_key`/`latency_ms`/`usage`.
- Request/response shapes vary by `kind` (tool, llm, http, error).
- Edit responses and errors freely; changing requests breaks matching unless code changes too.

[Back to the Introduction →](index.md){ .md-button }
