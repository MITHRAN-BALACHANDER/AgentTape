# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
