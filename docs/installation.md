---
title: Installation
---

# Installation

**Install the core engine with `pip install agenttape`. It has zero external dependencies — adapters are opt-in extras.**

---

## Requirements

- Python **3.10 – 3.13**
- `pip` (or [`uv`](https://github.com/astral-sh/uv), `poetry`, etc.)

That's it. The core engine is built entirely on the Python standard library, so installing AgentTape can't cause a version conflict with the libraries you're testing.

---

## Install

=== "pip"

    ```bash
    pip install agenttape
    ```

=== "uv"

    ```bash
    uv pip install agenttape
    ```

=== "poetry"

    ```bash
    poetry add agenttape
    ```

---

## Optional extras

AgentTape ships **adapters** that automatically intercept popular libraries, and an optional faster YAML backend. Install only what you need.

| Extra | Command | Adds |
| --- | --- | --- |
| OpenAI adapter | `pip install "agenttape[openai]"` | Auto-intercept the `openai` SDK |
| Robust YAML | `pip install "agenttape[yaml]"` | PyYAML (C-accelerated parsing for large cassettes) |
| Everything | `pip install "agenttape[all]"` | All adapters + enhancements |

!!! note "Adapters intercept; they don't require code changes"
    With `agenttape[openai]` installed, the OpenAI client is intercepted automatically inside any `use_cassette` block. You don't import or configure the adapter — it activates itself when the session starts. See [Recording APIs](recording-apis.md).

!!! tip "raw HTTP works without any extra"
    The `httpx` and `requests` fallback adapters are always on whenever those libraries are importable. Any SDK built on them is captured even without a dedicated adapter — see [Recording APIs](recording-apis.md).

---

## Verify

```bash
agenttape --version
```

You should see the installed version printed. The `agenttape` CLI is installed alongside the library and operates entirely on local files.

---

## Scaffold a project (optional)

Run `init` to drop a commented config file and a `cassettes/` directory into your project:

```bash
agenttape init
```

!!! success "What happened?"
    AgentTape created `agenttape.toml` (with sensible, documented defaults) and a `cassettes/` folder. Configuration is entirely optional — every setting has a default — but the file is a convenient place to set your cassette directory, redaction rules, and default mode. See [Configuration](configuration.md).

---

## Summary

- `pip install agenttape` — core engine, zero dependencies, Python 3.10–3.13.
- Add `[openai]` for automatic OpenAI interception, `[yaml]` for faster large-cassette parsing.
- `agenttape --version` confirms the install; `agenttape init` scaffolds a project.

[Record your first interaction →](your-first-recording.md){ .md-button .md-button--primary }
