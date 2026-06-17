# CLI Reference

Command line tools for inspecting and managing cassettes.

---

## What is it?

AgentTape provides a command-line interface (CLI) to help you manage your cassettes without having to write Python scripts or manually read raw YAML files.

---

## Commands

### `agenttape init`

Scaffolds a new AgentTape configuration.

*   Creates a `cassettes/` directory.
*   Creates an `agenttape.toml` file with sensible defaults and comments explaining each option.

```bash
agenttape init
```

---

### `agenttape inspect`

Displays high-level metrics for a specific cassette.

*   Total duration of the recorded session.
*   Total token usage (if recorded by an LLM adapter).
*   A summary of the interactions contained within.

```bash
agenttape inspect cassettes/hello.yaml
```

---

### `agenttape diff`

Compares two cassettes and prints a unified diff.

This is primarily used when utilizing Partial Replay (`live={"llm"}`) to see how a new model or prompt changed the agent's behavior compared to the original recording.

```bash
agenttape diff cassettes/original.yaml cassettes/original.derived.yaml
```

---

### `agenttape timeline`

Prints a visual waterfall chart of the interactions in a cassette to your terminal.

This is an excellent debugging tool to quickly understand the execution order of a complex agent run.

```bash
agenttape timeline cassettes/complex_task.yaml
```

---

### `agenttape validate`

Checks a cassette for correctness.

*   Validates the YAML structure against the AgentTape schema.
*   Checks if any secrets defined in `agenttape.toml` have leaked into the file.

```bash
agenttape validate cassettes/hello.yaml
```

---

### `agenttape redact`

Retroactively redacts a secret from an existing cassette file.

If you accidentally record a session containing PII, you can use this command to perform a deep search-and-replace across the entire YAML structure.

```bash
agenttape redact cassettes/hello.yaml --secret "123-45-678"
```

---

### `agenttape view`

Generates a static HTML dashboard from a cassette and opens it in your browser.

This provides a UI for reading long LLM prompts and responses, which can be difficult to read in a raw YAML file in the terminal.

```bash
agenttape view cassettes/hello.yaml
```

---

### `agenttape export`

Exports the cassette data into an external format.

Currently supports exporting to OpenTelemetry (`otel`) format for ingestion into observability platforms.

```bash
agenttape export cassettes/hello.yaml --format otel > trace.json
```