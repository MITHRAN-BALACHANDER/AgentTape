# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

AgentTape provides deterministic record/replay for AI agents: it records an agent's external interactions
(LLM calls *and* tool calls) into human-readable YAML "cassettes", then replays them
deterministically so tests run offline, free, and with zero side effects. It is a
pure-Python library + CLI + pytest plugin. The package lives under `src/agenttape/`.

## Commands

Environment management uses [`uv`](https://github.com/astral-sh/uv).

```bash
uv venv
uv pip install -e ".[dev]"        # dev extra: pytest, pytest-cov, ruff, mypy, PyYAML
```

The full quality bar (every PR must pass all four):

```bash
ruff check src tests              # lint
ruff format --check src tests     # formatting (run `ruff format src tests` to fix)
mypy                              # strict type-check — config pins files to src/agenttape only
pytest --cov=agenttape            # tests; core engine must stay ≥90% covered
```

Running tests:

```bash
pytest                                        # whole suite, quiet (addopts = -q)
pytest tests/test_engine.py                   # one file
pytest tests/test_engine.py::test_name        # one test
pytest -k "freeze and replay"                 # by keyword
pytest --cov=agenttape --cov-report=term-missing
```

To exercise the **zero-optional-deps** path (the stdlib YAML emitter/parser, no
PyYAML), set `AGENTTAPE_FORCE_STDLIB_YAML=1` before running tests. CI runs the core
test subset this way to guarantee the engine works with standard library only. On
PowerShell: `$env:AGENTTAPE_FORCE_STDLIB_YAML = "1"`.

The CLI entry point is `agenttape` (`agenttape.cli:main`): `init`, `record`,
`replay`, `inspect`, `timeline`, `diff`, `redact`, `validate`, `export`, `view`,
`rm`. All operate on local files only.

## Non-negotiable invariants

These constrain every change — violating them breaks the project's promise:

1. **The core engine has zero required runtime dependencies** (`dependencies = []`).
   Everything else (PyYAML, openai, httpx, langgraph, numpy, otel…) is an optional
   extra. Adapters and optional features must keep their third-party imports **lazy**
   (import inside functions, never at module top level in the core path).
2. **Never silently run a side effect.** A boundary that is not `live` and has no
   recording must raise `UnmatchedInteractionError` — replay never executes a real
   tool/API call.
3. **Deterministic, byte-for-byte.** Same inputs → same recorded output.
4. **Replay reconstructs recorded bytes; it is not "free re-execution with a new
   prompt."** The moment an input to a `live` boundary changes, that boundary
   *really executes* (real cost) and a **derived** cassette is written — the original
   is never mutated. Keep this distinction explicit in code and docs.
5. `mypy` runs in `strict` mode but only over `src/agenttape` (set in
   `[tool.mypy] files`). Tests and adapters relax `warn_unused_ignores`.

## Architecture

Everything funnels into one internal schema and one decision engine; adapters and
helpers are thin translators around them.

### The central objects

- **`schema.py` — `Cassette` / `Interaction`.** The single internal schema *every*
  adapter translates to, so the engine, CLI, diff, and viewer are all framework
  agnostic. `KINDS = {llm, tool, retrieval, memory_read, memory_write, http}`;
  `SCHEMA_VERSION = "1"`. An `Interaction` carries `kind`, `boundary`, `request`,
  `response`/`error`, `match_key`, `usage`, etc.

- **`recorder.py` — `Session`.** The orchestrator. One `Session` ties together a
  `Config`, the loaded `Cassette`, a `FreezeController`, an `Engine`, and the
  installed adapters. The three documented entry points — `use_cassette(...)` (context
  manager) and the `replay()` / `record()` decorators — are thin wrappers around
  `Session`. A **thread-local active-session stack** (`active_session()`) lets adapters
  and boundary decorators find the current engine at call time without threading it
  through every call. On `__enter__`: freeze layer on, push onto stack, install all
  available adapters. On `__exit__`: uninstall, pop, restore freeze, then
  `_maybe_write()`.

- **`engine.py` — `Engine`.** The record/replay decision core and the side-effect
  guardrail. Adapters/decorators call `engine.intercept(kind, request, boundary=,
  executor=)` (and `aintercept` for async). It decides **replay vs. execute** from the
  cassette `mode` (`ModeFlags`) and the mixed-replay `live`/`frozen` sets, then either
  reconstructs the recorded response or runs `executor()` and records the result.
  Key subtleties:
  - **Re-entrancy depth** (`self._depth`): while an executor runs we are "inside" a
    boundary, so a nested interception (e.g. the httpx fallback firing during an
    OpenAI call the openai adapter already wrapped) passes through instead of double
    recording. The outermost boundary is the one captured.
  - **`build_output()`** decides what gets persisted per mode; on `mode="none"` with a
    live boundary it returns the full served timeline (the derived cassette).
  - `UnmatchedInteractionError` is constructed with the closest recorded request and
    field-level diffs (`diff_fields`) for a precise error message.

### The three interception mechanisms

Requests reach the engine three ways — know which one a change belongs to:

1. **Transport adapters** (`adapters/`): patch a library's client so calls route
   through the engine. These are the only mechanism that can *replay* (substitute a
   recorded response). `OpenAIAdapter` (patches `chat.completions.create` /
   `responses.create`, sync+async) is the primary fully-built one; `HttpxAdapter` /
   `RequestsAdapter` are the always-on raw-HTTP fallback; `LangGraphAdapter` exists.
   The registry in `adapters/__init__.py` installs every *available* adapter per
   session. Adapters use **`RefCountedPatch`** so nested sessions share one patch and
   route to whichever session is active. To add one: subclass `Adapter`, implement
   `available()` / `install()` / `uninstall()`, register it, and inside the patched
   callable check `active_session()` (pass through if `None`).

2. **Boundary decorators** (`boundaries.py`): `@tool`, `@retrieval`, `@memory_read`,
   `@memory_write`, plus the low-level `record_call(...)`. The "almost-no-code" way to
   make any user function a recorded boundary; outside a session they behave like the
   original function. This is what guarantees a replayed tool (DB write, charge, Slack
   post) does nothing.

3. **`callbacks.py` — `AgentTape`**: a duck-typed callback/listener for frameworks
   (LangChain, LlamaIndex, CrewAI) that expose hooks rather than a patchable client.
   It is **observational / record-only** — a framework calls it after the fact and it
   cannot substitute a return value, so deterministic replay still relies on the
   transport adapters.

### Supporting layers

- **`freeze.py` — `FreezeController`.** Determinism layer: pins `clock`, `uuid`,
  `random` (and optional `numpy`, env snapshot). On by default in `mode="none"`. Base
  values are stored in `cassette.meta["freeze"]` so replay reproduces them across
  machines. Note: `time.perf_counter` is **never** frozen, so recorded `latency_ms`
  stays real. Datetime freezing is freezegun-lite — it swaps the real `datetime`/`date`
  classes in every already-imported module that holds a direct reference.

- **`matchers.py` + `canonical.py`.** A matcher reduces a request to a comparison key;
  the engine indexes recordings by `(kind, boundary, key)`. Default `ignore_volatile`
  drops volatile fields (timestamps, request ids) before hashing. `ordered` matches
  purely by call sequence. When keys collide, recordings are served in recorded order.

- **`cassette.py` + `yaml_io.py` + `assets.py` + `redaction.py`.** The I/O pipeline is
  ordered deliberately: `cassette → dict → redact → externalize large assets →
  serialise → disk`, so secrets are redacted *before* anything is written and large
  payloads go to a sibling assets dir. YAML is default (stdlib subset emitter when
  PyYAML is absent); JSON supported.

- **`config.py` — `Config`.** Optional `agenttape.toml`, discovered by walking up from
  cwd (like `pyproject.toml`). Every setting has a default, so no config is required.
  TOML parsing uses stdlib `tomllib` (3.11+), falling back to a tiny built-in
  `_MiniToml` parser on 3.10 to stay dependency-free.

- **`pytest_plugin.py`.** Registered via the `pytest11` entry point. Bind a test with
  `@pytest.mark.agenttape("name")` and optionally the `agenttape_cassette` fixture
  (which yields a `CassetteHandle` with snapshot assertions). Tests default to
  `mode="none"` (offline/deterministic); `--agenttape-record` forces `mode="all"` to
  re-record against real services, `--agenttape-mode` overrides per run.

- Tooling/output modules: `diff.py`, `timeline.py`, `metrics.py`, `validate.py`,
  `export.py` (json/otel), `viewer.py` (self-contained static HTML).

### Cassette modes

`none` (replay only — CI default), `once` (replay if present else record), `new_episodes`
(replay existing + record new), `all`/`record` (always record fresh). The mixed-replay
`live=` / `frozen=` sets implement "freeze all but one": pass `live={"llm"}` to run only
the LLM for real while every tool is served frozen. `live` and `frozen` are mutually
exclusive.

## Conventions

- Ruff line length 100; rule set `E,F,I,UP,B,C4,SIM,RUF` (see `pyproject.toml` for the
  intentional ignores). Run `ruff format` to fix formatting.
- Supports Python 3.10–3.13; the 3.10 path must avoid 3.11+-only stdlib (hence the
  `tomli`/`_MiniToml` fallback). CI matrix covers all four versions on Linux/macOS/Windows.
- Update `CHANGELOG.md` under `[Unreleased]` and add/adjust tests for any behaviour change.
