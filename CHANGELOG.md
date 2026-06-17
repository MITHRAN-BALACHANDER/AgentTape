# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **HTTP replay no longer corrupts compressed responses.** The raw httpx/requests
  fallback recorded the *decoded* body but kept the wire headers, so a
  `Content-Encoding: gzip` (or br/deflate) response was reconstructed with a gzip
  header over already-decompressed bytes — httpx raised `DecodingError` at
  construction, breaking both replay *and* recording (the fallback rewraps the
  response even when nested under the OpenAI adapter). `Content-Encoding`,
  `Content-Length` and `Transfer-Encoding` are now dropped from the recorded
  response so the framework reconstructs the body faithfully.
- **`time.monotonic` / `monotonic_ns` are no longer frozen.** Like `perf_counter`
  they are duration clocks that schedulers depend on; freezing `monotonic` made
  `await asyncio.sleep(...)` (and any monotonic-based timeout) wait forever under a
  recorded session, because asyncio derives its timer deadlines from it. Only the
  wall clock (`time.time` / `datetime`) is pinned now.
- **Binary tool/boundary results are preserved.** `_to_jsonable` lossily decoded
  `bytes` to a UTF-8 string with replacement characters, silently corrupting images,
  files and other binary payloads; bytes now round-trip losslessly via the assets
  sidecar. `datetime`/`date`/`Decimal`/`UUID`/`Enum`/`set` convert to a faithful,
  stable form (an `Enum` previously collapsed to `{}`), and cyclic object graphs are
  broken with a `"<cycle>"` placeholder instead of overflowing the stack.
- **Secrets in raw HTTP request/response *bodies* are now redacted.** JSON and
  form-urlencoded bodies are captured structurally, so the denylist sees nested keys
  (`password` in a login POST, `access_token` in a token response) instead of an
  opaque string the regex rules missed. Redacted bodies still replay, because the
  match key is computed pre-redaction.
- **Multipart uploads (file / audio endpoints) match on replay.** The random
  multipart boundary in the body and `Content-Type` is normalised to a fixed token,
  so repeated uploads resolve to the recording instead of raising
  `UnmatchedInteractionError`.
- **YAML round-trip is lossless for awkward multiline strings.** The stdlib emitter
  lost the extra newlines of a string ending in `\n\n+` and corrupted a block whose
  first line was indented; such strings now use a double-quoted scalar, and the
  block reader dedents by the least-indented line so interior/leading spaces survive.
- **Reconstructed HTTP responses carry the fields callers expect.** httpx responses
  restore `reason_phrase` / `http_version` and set `.elapsed` (which otherwise
  raises on access); requests responses set `.encoding`, `.raw`, `.elapsed` and
  `.history`.
- **Replayed SDK exceptions keep their simple attributes** (`status_code`, `code`,
  `retry_after`, …), so `except RateLimitError as e: e.status_code` works offline.
- **The active-session lookup is a `ContextVar`, not a thread-local.** Two cassettes
  opened concurrently in one event loop (`asyncio.gather`) no longer corrupt a shared
  stack and route interceptions to the wrong cassette.
- OpenAI responses are dumped with `model_dump(mode="json")` so enums/datetimes are
  recorded in their faithful JSON form and re-validate on replay; the `embeddings`
  endpoint is now intercepted alongside `chat.completions` and `responses`.
- `agenttape validate` scans externalized asset files (not just the cassette body)
  for leaked secrets, and `agenttape rm` also removes the derived cassette's assets
  sidecar.
- `pytest --cov=agenttape` now measures the engine correctly (90%+, matching CI's
  `coverage run`). The package `__init__` and the pytest entry-point plugin defer
  their heavy imports (PEP 562 lazy loading) so the engine no longer loads — and
  goes unmeasured — at plugin-registration time, before pytest-cov starts.
- `AgentTape` callback now records the real prompt / tool input / retriever query
  on the interaction (correlated by `run_id` from the matching `on_*_start`),
  instead of a `<via-callback>` placeholder.
- LangGraph adapter no longer wraps `Pregel.stream`: a streamed generator cannot be
  captured as a single deterministic `memory_write` without exhausting the caller's
  stream. `.invoke` is still checkpointed; LLM/tool calls inside `.stream` continue
  to record/replay through the transport adapters.

### Removed

- Unused event constants and the `EVENTS` / `EVENT_TO_KIND` tables from
  `agenttape.events` (only the five events the callback actually emits remain).

### Changed

- Bumped optional/dev/docs dependency floors to current stable major lines while
  preserving Python 3.10–3.13 support: `openai>=1.66` (matches `responses.create`),
  `langgraph>=1.0`, `langchain-core>=0.3`, `llama-index-core>=0.12`, `crewai>=1.0`,
  `pyautogen>=0.9`, `mcp>=1.9`, `httpx>=0.27`, `requests>=2.32.4` (security),
  `numpy>=1.26`, `opentelemetry-sdk>=1.30`, `pytest>=8.0`, `pytest-cov>=5.0`,
  `ruff>=0.6`, `mypy>=1.11`, `types-PyYAML>=6.0.12`, `mkdocs-material>=9.5`,
  `mkdocstrings[python]>=0.26`, `PyYAML>=6.0.1`.

### Added

- Python 3.14 to the CI test matrix and the PyPI classifiers.

## [0.1.0] - 2026-06-16

### Added

- Core interception engine: record / replay of LLM, tool, retrieval, memory and
  raw HTTP boundaries into ordered cassettes.
- Cassette format (YAML default, JSON supported) with assets sidecar for large
  payloads referenced by content hash. Pure-stdlib YAML reader/writer with
  optional PyYAML acceleration.
- Cassette modes: `none`, `once`, `new_episodes`, `all`, `record`.
- Request canonicalization + sha256 match keys; pluggable matchers (`exact`,
  `ignore_volatile`, `ordered`, `custom`).
- Mixed / partial replay (`live` / `frozen` sets) with side-effect guardrail and
  record-back into a derived cassette.
- Determinism freeze layer: clock, RNG, UUID freeze; env snapshot + drift warning.
- Record-time redaction of secrets/PII (denylist + regex rules + header redaction).
- Public API: `record` / `replay` decorators, `use_cassette` context manager, and
  an `AgentTape` callback/hook object.
- OpenAI adapter (chat + responses + tool calling) and an always-on
  `httpx` / `requests` fallback. LangGraph adapter and a documented extension
  interface for the rest.
- CLI: `init`, `record`, `replay`, `inspect`, `timeline`, `diff`, `redact`,
  `validate`, `export` (json/otel), `view`, `rm`.
- Diff engine: run / prompt / state-memory / output diffs (CLI + importable).
- `pytest-agenttape` plugin: marker, fixture, offline-by-default mode, record
  flag, mode flag, mismatch diffs, snapshot assertions.
- Self-contained static HTML viewer (single + two-cassette diff), no server.

[Unreleased]: https://github.com/MITHRAN-BALACHANDER/AgentTape/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/MITHRAN-BALACHANDER/AgentTape/releases/tag/v0.1.0
