---
title: Configuration Reference
---

# Configuration Reference

**Every valid key in `agenttape.toml`, its type, and its default.** Configuration is optional — every setting has a default. Place the file at your project root; it's discovered by walking up from the current directory.

For the conceptual overview, see [Configuration](configuration.md).

---

## Complete example

```toml title="agenttape.toml"
cassette_dir = "tests/cassettes"
default_mode = "none"
default_matchers = ["ignore_volatile"]
freeze = ["clock", "uuid", "random"]
ignore_volatile_fields = ["timestamp", "request_id", "x-request-id", "date", "nonce"]
assets_threshold_bytes = 4096
format = "yaml"
env_snapshot = ["MODEL_TIER", "FEATURE_FLAGS"]
# model_override = "gpt-4o"

[redact]
denylist = ["x-internal-token"]
regexes = ["cust_[a-z0-9]{12}"]
redact_emails = true
# placeholder = "***REDACTED***"
# enabled = true
```

---

## Top-level keys

### `cassette_dir`
- **Type:** `str` (path) · **Default:** `"cassettes"`
- Where cassettes are read and written. Relative paths resolve relative to the **`agenttape.toml` file's** location, not the current directory.

### `default_mode`
- **Type:** `str` · **Default:** `"none"`
- Fallback mode when `use_cassette` doesn't pass one. One of `none`, `once`, `new_episodes`, `all`, `record`. See [Cassette Modes](cassette-modes.md). An invalid value raises `ConfigError`.

### `default_matchers`
- **Type:** `list[str]` · **Default:** `["ignore_volatile"]`
- The matcher chain the [Replay Engine](replay-engine.md) uses. Built-ins: `ignore_volatile`, `exact`, `ordered` (alias `sequential`), `semantic_stub`.

### `format`
- **Type:** `str` · **Default:** `"yaml"`
- Serialization format: `"yaml"` or `"json"`. YAML is recommended for readability and Git diffs. An invalid value raises `ConfigError`.

### `assets_threshold_bytes`
- **Type:** `int` · **Default:** `4096`
- Payloads larger than this are written to a sibling assets directory instead of being inlined into the cassette, keeping the YAML readable.

### `model_override`
- **Type:** `str` · **Default:** *unset*
- Pins the model sent to the OpenAI adapter, for replay-with-a-different-model experiments. This **genuinely changes** the request (a real re-execution, not deterministic replay), so use it with [Partial Replay](mixed-replay.md).

---

## Determinism keys

### `freeze`
- **Type:** `list[str]` · **Default:** `["clock", "uuid", "random"]`
- Non-deterministic subsystems to pin during record and replay. See [Determinism](determinism.md).

### `env_snapshot`
- **Type:** `list[str]` · **Default:** `[]`
- Environment variable names to record into `meta.freeze.env`. If a value differs on replay, AgentTape emits a `DeterminismDriftWarning`.

---

## Matching keys

### `ignore_volatile_fields`
- **Type:** `list[str]` · **Default:** see below
- Field/header names (case-insensitive) the `ignore_volatile` matcher drops before hashing a request. Add your own dynamic fields here.

The built-in default list:

```python
["timestamp", "created", "created_at", "request_id", "x-request-id",
 "x-amzn-requestid", "nonce", "trace_id", "traceparent", "date",
 "user-agent", "idempotency-key"]
```

!!! note "Setting this replaces the default"
    Providing `ignore_volatile_fields` overrides the built-in list rather than extending it. Include the defaults you still want, plus your additions.

---

## Redaction: the `[redact]` table

These keys **add to** AgentTape's built-in redaction (denylisted keys + secret-pattern regexes + emails). See [Redaction](redaction.md).

```toml
[redact]
denylist = ["x-internal-token", "ssn"]
regexes = ["cust_[a-z0-9]{12}"]
redact_emails = true
placeholder = "***REDACTED***"
enabled = true
```

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `denylist` | `list[str]` | `[]` | Extra field/header names whose values are fully redacted (case-insensitive) |
| `regexes` | `list[str]` | `[]` | Extra value patterns to scrub anywhere in strings |
| `redact_emails` | `bool` | `true` | Redact email addresses |
| `placeholder` | `str` | `***REDACTED***` | Replacement text for redacted values |
| `enabled` | `bool` | `true` | Master switch for all redaction |

---

## How the file is loaded

- Parsed with stdlib `tomllib` (Python 3.11+); on 3.10, with `tomli` if present, otherwise a tiny built-in fallback parser — so config support adds **zero** dependencies.
- Discovered by walking up from the current directory, like `pyproject.toml`. The first `agenttape.toml` found wins.
- Per-call arguments to `use_cassette(...)` always override file values.

---

## Summary

- Top-level: `cassette_dir`, `default_mode`, `default_matchers`, `format`, `assets_threshold_bytes`, `model_override`.
- Determinism: `freeze`, `env_snapshot`.
- Matching: `ignore_volatile_fields` (replaces the default list when set).
- `[redact]`: `denylist`, `regexes`, `redact_emails`, `placeholder`, `enabled` — additive to the built-ins.

[Next: Cassette Format →](format.md){ .md-button .md-button--primary }
