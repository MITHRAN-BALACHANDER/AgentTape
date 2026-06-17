---
title: CLI Reference
---

# CLI Reference

**The `agenttape` command manages and inspects cassettes — all on local files, no network, no server.**

```bash
agenttape <command> [args] [options]
agenttape --version
agenttape -v <command> ...   # -v / --verbose: show full tracebacks
```

| Command | Does |
| --- | --- |
| [`init`](#init) | Scaffold `agenttape.toml` + a `cassettes/` directory |
| [`record`](#record) | Run an entrypoint and record it |
| [`replay`](#replay) | Replay a cassette and print the reconstructed timeline |
| [`inspect`](#inspect) | Pretty-print interactions, latency, tokens, cost |
| [`timeline`](#timeline) | Render the run as an ASCII waterfall |
| [`diff`](#diff) | Structured diff of two cassettes |
| [`redact`](#redact) | Re-run redaction over a cassette |
| [`validate`](#validate) | Schema + determinism + leaked-secret lint |
| [`export`](#export) | Export to JSON or OpenTelemetry |
| [`view`](#view) | Generate a self-contained HTML viewer |
| [`rm`](#rm) | Delete a cassette and its assets |

!!! tip "Resolving cassette arguments"
    Most commands accept either a path (`cassettes/x.yaml`) or a bare name (`x`) — bare names are resolved against your configured `cassette_dir`.

---

## `init`

Scaffold a project: writes a commented `agenttape.toml` (if absent) and creates the `cassettes/` directory.

```bash
agenttape init [--dir DIR]
```

| Option | Default | Description |
| --- | --- | --- |
| `--dir` | `.` | Project directory to scaffold |

---

## `record`

Import a `module:function` entrypoint and run it inside a recording session.

```bash
agenttape record my_app.agents:run_demo checkout [--mode MODE]
```

| Argument / Option | Default | Description |
| --- | --- | --- |
| `entrypoint` | — | `module:function` to call (no args) |
| `cassette` | — | Cassette name to write |
| `--mode` | `record` | Recording mode |

---

## `replay`

Replay a cassette and print its reconstructed timeline. Confirms what would be served — **no external calls are made**.

```bash
agenttape replay checkout
```

---

## `inspect`

Pretty-print a cassette: metadata, each interaction's request/response, and totals (latency, tokens, cost).

```bash
agenttape inspect cassettes/weather.yaml [--full]
```

| Option | Description |
| --- | --- |
| `--full` | Don't truncate large payloads |

```text
Cassette: cassettes/weather.yaml
version=1 run_id=de5dc0ac-…
meta: {"agenttape_version": "0.1.5", "mode": "record"}
freeze: clock, random, uuid

#0 [tool] get_weather  (0.0ms)
  request:  {"name": "get_weather", "args": {"city": "London"}}
  response: {"temp": 15, "condition": "rainy"}

------------------------------------------------------------
1 interactions · 0.0ms · 0+0=0 tokens · cost n/a
```

---

## `timeline`

Render the run as an ASCII waterfall — great for seeing execution order and where time went.

```bash
agenttape timeline cassettes/weather.yaml
```

```text
Timeline: cassettes/weather.yaml
run de5dc0ac · 1 interactions

User
  → Tool      get_weather            |████████████████████████████████████████|      0.0ms
Done

Σ latency 0.0ms · tokens 0 · cost n/a
```

---

## `diff`

Structured diff of two cassettes. Indispensable with [Partial Replay](mixed-replay.md) for comparing a derived run against its original.

```bash
agenttape diff cassettes/checkout.yaml cassettes/checkout.derived.yaml [--type TYPE]
```

| Option | Choices | Default | Shows |
| --- | --- | --- | --- |
| `--type` | `run`, `prompt`, `state`, `output`, `all` | `run` | Which view of the diff to render |

---

## `redact`

Re-apply your **current** `agenttape.toml` redaction rules to an existing cassette, in place. Use it after recording a cassette before a new rule was configured.

```bash
agenttape redact cassettes/login.yaml
```

!!! note "No `--secret` flag"
    `redact` applies the configured rules — it doesn't take an arbitrary secret string. Add the secret's pattern to `[redact].regexes` or its field name to `[redact].denylist`, then run `redact`. See [Redaction](redaction.md).

---

## `validate`

Lint a cassette: validate the schema, flag determinism risks, and scan for leaked secrets. Exit code is non-zero on errors — wire it into CI or a pre-commit hook.

```bash
agenttape validate cassettes/login.yaml
```

```text
Validating cassettes/login.yaml
  ✓ valid — no issues found
```

---

## `export`

Export a cassette to another format.

```bash
agenttape export cassettes/checkout.yaml --format otel -o trace.json
```

| Option | Choices | Default | Description |
| --- | --- | --- | --- |
| `--format` | `json`, `otel` | `json` | Output format (`otel` = OpenTelemetry trace) |
| `-o`, `--output` | — | stdout | Write to a file instead of stdout |

---

## `view`

Generate a self-contained static HTML viewer — easier than reading long prompts in raw YAML. Pass a second cassette to render a side-by-side diff view.

```bash
agenttape view cassettes/checkout.yaml [second] [-o OUTPUT]
```

| Argument / Option | Default | Description |
| --- | --- | --- |
| `second` | — | Optional second cassette for a diff view |
| `-o`, `--output` | `<cassette>.html` | Output HTML path |

---

## `rm`

Delete a cassette and its sidecar assets (and any `.derived` companion).

```bash
agenttape rm cassettes/old.yaml [-f]
```

| Option | Description |
| --- | --- |
| `-f`, `--force` | Skip the confirmation prompt |

---

## Summary

- `init` scaffolds; `record`/`replay` capture and reconstruct.
- `inspect`, `timeline`, `diff`, `view` help you understand a run.
- `redact` and `validate` keep cassettes secret-free; `export` feeds observability tools.
- All commands are local-only — no network, no server.

[Next: Configuration Reference →](configuration-ref.md){ .md-button .md-button--primary }
