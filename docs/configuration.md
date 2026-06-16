# Configuration — `agenttape.toml`

Configuration is optional; every setting has a sensible default. When present,
`agenttape.toml` is discovered by walking up from the current directory (like
`pyproject.toml`). Scaffold one with `agenttape init`.

```toml
# Where cassettes live (relative to this file).
cassette_dir = "cassettes"

# Default mode when none is passed. "none" = offline + deterministic (CI-friendly).
default_mode = "none"

# Matching strategy: exact | ignore_volatile | ordered
default_matchers = ["ignore_volatile"]

# Determinism features enabled by default.
freeze = ["clock", "uuid", "random"]

# Fields dropped before computing the match key (volatile / non-semantic).
ignore_volatile_fields = ["timestamp", "request_id", "x-request-id", "date", "nonce"]

# Payloads larger than this are externalised to <cassette>.assets/.
assets_threshold_bytes = 4096

# Cassette serialisation format: yaml | json
format = "yaml"

# Env vars to snapshot and warn on drift.
env_snapshot = ["MODEL_TIER"]

# Pin a model for replay-with-different-model experiments.
# model_override = "gpt-4o"

[redact]
denylist = []          # extra field names to fully redact
regexes  = []          # extra value patterns to scrub
redact_emails = true
```

## Keys

| Key | Default | Meaning |
|-----|---------|---------|
| `cassette_dir` | `cassettes` | Directory holding cassettes. |
| `default_mode` | `none` | Mode when not specified. |
| `default_matchers` | `["ignore_volatile"]` | Match strategy. |
| `freeze` | `["clock","uuid","random"]` | Determinism features. |
| `ignore_volatile_fields` | see above | Fields dropped from match keys. |
| `assets_threshold_bytes` | `4096` | Asset externalisation threshold. |
| `format` | `yaml` | `yaml` or `json`. |
| `env_snapshot` | `[]` | Env vars snapshotted for drift warnings. |
| `model_override` | unset | Force a model in `live={"llm"}` runs. |
| `redact.denylist` | `[]` | Extra redaction key names. |
| `redact.regexes` | `[]` | Extra redaction value patterns. |

TOML is parsed with the stdlib `tomllib` on Python 3.11+, falling back to a tiny
built-in parser on 3.10 — the core stays dependency-free.
