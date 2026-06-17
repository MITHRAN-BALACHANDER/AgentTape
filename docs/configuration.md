# Configuration

Global settings for AgentTape.

---

## What is it?

You don't have to pass configuration options to every single `use_cassette` call. AgentTape supports a global configuration file called `agenttape.toml`.

AgentTape will automatically search for this file in your current directory and all parent directories.

---

## Why it exists

If you have a large project, you likely want all your cassettes saved in a specific folder, you might want to redact certain API keys globally, or you might want to define custom matchers. `agenttape.toml` lets you define these project-wide defaults.

---

## Quick Example

Create an `agenttape.toml` file in the root of your project:

```toml
cassette_dir = "tests/fixtures/cassettes"
default_mode = "none"
[redact]
secrets = ["OPENAI_API_KEY", "STRIPE_SECRET_KEY"]
replacement = "<REDACTED>"
```

---

## Configuration Options

Here are the most common options. For a full list, see the [Configuration Reference](configuration-ref.md).

### `cassette_dir`
The directory where cassettes are stored.
*   **Default**: `cassettes`
*   **Example**: `cassette_dir = "tests/recordings"`

### `default_mode`
The cassette mode to use if not explicitly provided.
*   **Default**: `none`
*   **Example**: `default_mode = "once"`

### `freeze`
A list of non-deterministic elements to freeze during recording and replay. See [Determinism](determinism.md) for details.
*   **Default**: `["clock", "uuid", "random"]`
*   **Example**: `freeze = ["uuid"]`

### `env_snapshot`
A list of environment variables to record. If these change during replay, AgentTape will warn you.
*   **Default**: `[]`
*   **Example**: `env_snapshot = ["MODEL_NAME", "FEATURE_FLAGS"]`

### `redact`
Rules for removing sensitive information from cassettes before they are saved to disk. See [Redaction](redaction.md).

```toml
[redact]
headers = ["Authorization", "X-Api-Key"]
secrets = ["MY_APP_SECRET"]
```

---

## Summary

*   Configure AgentTape globally using `agenttape.toml`.
*   The file is auto-discovered.
*   Use it to set directories, default modes, redaction rules, and determinism settings.

---

**Next Steps**: Dive into the core data structure: [Cassettes](cassettes.md).