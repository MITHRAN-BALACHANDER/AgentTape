# Configuration Reference

All valid keys for `agenttape.toml`.

---

## What is it?

This page lists every available configuration option you can place in your `agenttape.toml` file.

The file should be placed in the root of your repository (next to `pyproject.toml` or `package.json`). AgentTape will automatically discover it.

---

## Global Options

### `cassette_dir`
*   **Type**: `str` (Path)
*   **Default**: `"cassettes"`
*   **Description**: The directory where AgentTape will read and write YAML files. If a relative path is provided, it is resolved relative to the location of the `agenttape.toml` file.

### `default_mode`
*   **Type**: `str`
*   **Default**: `"none"`
*   **Description**: The fallback mode if none is specified in `use_cassette`. Must be one of `"none"`, `"once"`, `"new_episodes"`, `"all"`, or `"record"`.

### `format`
*   **Type**: `str`
*   **Default**: `"yaml"`
*   **Description**: The serialization format for cassettes. Supported values are `"yaml"` and `"json"`. YAML is strongly recommended for human readability and Git diffing.

---

## Determinism Options

### `freeze`
*   **Type**: `list[str]`
*   **Default**: `["clock", "uuid", "random"]`
*   **Description**: The non-deterministic subsystems to mock during recording and replay.

### `env_snapshot`
*   **Type**: `list[str]`
*   **Default**: `[]`
*   **Description**: A list of environment variable names to record into the cassette metadata. If these variables change during replay, AgentTape will emit a warning.

---

## Matching Options

### `default_matchers`
*   **Type**: `list[str]`
*   **Default**: `["ignore_volatile"]`
*   **Description**: The list of matchers the Replay Engine uses to compare requests.

### `ignore_volatile_fields`
*   **Type**: `list[str]`
*   **Default**: `["Date", "X-Amz-Date", "trace_id", "x-request-id", ...]` (See `canonical.py` for full list).
*   **Description**: The specific dictionary keys or HTTP headers that the `ignore_volatile` matcher should ignore when comparing requests. You can append your own custom dynamic headers here.

---

## Redaction Options

All redaction options must be placed under the `[redact]` table.

### `[redact]`

```toml
[redact]
headers = ["Authorization"]
secrets = ["sk-123"]
env_secrets = ["STRIPE_KEY"]
replacement = "[SCRUBBED]"
```

*   **`headers`** *(list[str])* - HTTP headers to completely redact.
*   **`secrets`** *(list[str])* - Literal strings to search for and replace anywhere in the cassette.
*   **`env_secrets`** *(list[str])* - Names of environment variables. AgentTape will read their current values and redact those strings from the cassette.
*   **`replacement`** *(str, default="<REDACTED>")* - The string inserted in place of redacted data.

---

## Performance Options

### `assets_threshold_bytes`
*   **Type**: `int`
*   **Default**: `4096`
*   **Description**: *Experimental.* If a tool returns a binary payload (like an image) larger than this threshold, AgentTape will save it as a separate file in an `assets/` directory rather than base64-encoding it directly into the YAML file, keeping the YAML readable.