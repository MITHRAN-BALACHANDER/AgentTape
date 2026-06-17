# Internals

How AgentTape is built.

---

## What is it?

This page describes the internal architecture of the AgentTape core engine. It is intended for developers who want to contribute to the project or understand exactly how the record/replay mechanism works under the hood.

---

## Zero Dependencies

The most important architectural constraint of AgentTape is that the core engine must have **zero external runtime dependencies**.

It cannot rely on `requests`, `pydantic`, `pyyaml`, or even `typing_extensions`. It must run on a bare Python 3.10+ installation.

### Why?
AgentTape is a testing tool. If a user installs AgentTape into their environment, it should not cause version conflicts with the libraries they are actually trying to test. If AgentTape required `pydantic>=2.0`, it would break any project still using `pydantic 1.x`.

### How?
*   **YAML**: AgentTape includes a tiny, custom-written recursive block-YAML parser in `yaml_io.py`. It only supports the subset of YAML needed for cassettes. (Users can optionally install `PyYAML` for more robust parsing if they want).
*   **TOML**: AgentTape uses the standard library `tomllib` in Python 3.11+, and includes a tiny fallback parser for 3.10.
*   **Data Structures**: AgentTape uses standard `dataclasses` instead of `pydantic`.

---

## The Engine (`engine.py`)

The `Engine` class is the central nervous system.

When you use `with agenttape.use_cassette(...)`, you are creating a new `Session`, which initializes a new `Engine`.

The Engine is responsible for:
1.  Loading the cassette from disk into memory.
2.  Maintaining a pointer to the "current" interaction during replay.
3.  Receiving `intercept()` calls from adapters and decorators.
4.  Executing the matchers to decide if an intercept should replay or record.
5.  Appending new interactions to the in-memory timeline.
6.  Flushing the timeline back to disk when the session ends.

---

## The Matchers (`matchers.py`)

Matchers are pure functions. They take two dictionaries: the `recorded_request` and the `live_request`.

They return a boolean indicating if they match, and if they don't, a list of string paths indicating exactly which fields differed.

The default `ignore_volatile` matcher uses a hardcoded list (found in `canonical.py`) of keys to ignore during comparison, such as `Date`, `X-Amz-Date`, and `trace_id`.

---

## The Freeze Layer (`freeze.py`)

The freeze layer works by dynamically patching standard library modules using `unittest.mock.patch`.

*   **`clock`**: Patches `time.time()`. It maintains an internal offset counter. Every time `time.time()` is called during a recording, the counter increments slightly so time appears to move forward, but deterministically.
*   **`uuid`**: Patches `uuid.uuid4()`.
*   **`random`**: Calls `random.seed()` with a deterministic integer derived from the cassette metadata.

These patches are applied when the `Session` enters, and removed when the `Session` exits, ensuring no global state leaks between tests.

---

## Summary

*   AgentTape has zero core dependencies to prevent version conflicts.
*   It includes custom, minimal YAML and TOML parsers.
*   The `Engine` manages state, matching, and I/O.
*   The `Freeze` layer patches the standard library to guarantee determinism.

---

**Next Steps**: Read about how this architecture affects speed in [Performance](performance.md).