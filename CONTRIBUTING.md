# Contributing to AgentTape

Thanks for your interest in AgentTape! This project is local-first and
community-driven. Contributions of all kinds are welcome.

## Development setup

We use [`uv`](https://github.com/astral-sh/uv) for environment management.

```bash
git clone https://github.com/MITHRAN-BALACHANDER/AgentTape
cd AgentTape
uv venv
uv pip install -e ".[dev]"
```

## The quality bar

Every PR must pass:

```bash
ruff check src tests          # lint
ruff format --check src tests # formatting
mypy                          # strict type-checking on the core
pytest --cov=agenttape        # tests, ≥90% coverage on the core engine
```

Run them all with:

```bash
ruff check src tests && mypy && pytest --cov=agenttape --cov-report=term-missing
```

## Principles (please read before contributing)

AgentTape has seven non-negotiable principles. Changes that violate them will not
be merged:

1. **Local-first.** No servers, no network in replay, no telemetry.
2. **Deterministic.** Same inputs → same recorded outputs, byte-for-byte.
3. **Zero side effects in replay.** A replayed tool must never execute for real.
4. **Almost-no-code integration.** At most a decorator or context manager.
5. **Git-friendly.** Cassettes stay diffable, human-readable, hand-editable.
6. **Framework-agnostic core, thin adapters.** One internal schema.
7. **Fail loud, never silent.** Missing/mismatched recordings raise clearly.

The **core engine has zero required runtime dependencies** (standard library
only). Anything else belongs behind an optional extra (`agenttape[openai]`, …).

## Writing an adapter

See [docs/adapters.md](docs/adapters.md). Adapters translate framework-native
events into AgentTape's internal event schema and live under
`src/agenttape/adapters/`. Keep their third-party imports lazy so the core stays
dependency-free.

## Commit / PR conventions

- Keep PRs focused; one concern per PR.
- Add or update tests for any behaviour change.
- Update `CHANGELOG.md` under `[Unreleased]`.
- Update docs for user-facing changes.

By contributing you agree your contributions are licensed under the MIT License.
