# Installation

Install AgentTape using pip.

---

## What is it?

This page covers how to install AgentTape and its optional dependencies. AgentTape's core engine is built entirely on the Python standard library, meaning it adds zero external dependencies to your project by default.

---

## How to Install

You can install the base package with `pip`.

```bash
pip install agenttape
```

### Adapters

AgentTape uses **adapters** to automatically intercept specific libraries, like the official `openai` Python client. If you want AgentTape to intercept these libraries, you should install the optional extras.

```bash
pip install "agenttape[openai]"
```

### Improved YAML parsing

By default, AgentTape uses a built-in YAML parser to keep dependencies at zero. However, for maximum robustness when parsing large or complex cassettes, you can install the optional `PyYAML` dependency.

```bash
pip install "agenttape[yaml]"
```

### Installing everything

If you want to install AgentTape with all available adapters and enhancements:

```bash
pip install "agenttape[all]"
```

---

## Verifying the Installation

To verify that AgentTape is installed correctly, you can run the CLI.

```bash
agenttape --version
```

---

## Summary

* Install the core engine with `pip install agenttape`.
* The core engine has zero external dependencies.
* Install framework adapters via optional extras, like `agenttape[openai]`.

---

**Next Steps**: Learn how to create [Your First Recording](your-first-recording.md).