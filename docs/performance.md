# Performance

Understanding the speed and memory footprint of AgentTape.

---

## What is it?

AgentTape is designed to be fast enough that it doesn't slow down your local development cycle, and memory-efficient enough that it can handle thousands of cassettes in a CI pipeline.

---

## Replay Speed

In `mode="none"`, AgentTape is a purely local CPU-bound process. It performs dictionary lookups, string comparisons, and YAML parsing.

A typical LLM call using the OpenAI SDK takes **1-5 seconds**.

The exact same call, intercepted and replayed by AgentTape, takes **< 5 milliseconds**.

Because network latency is completely eliminated, a test suite that normally takes 10 minutes to run against live APIs will often complete in under 5 seconds when replayed.

---

## The YAML Parser

Because AgentTape guarantees zero external dependencies by default, it uses a custom, built-in YAML parser (`agenttape.yaml_io`).

This parser is optimized for the specific shapes of AgentTape cassettes, but it is written in pure Python. For 99% of use cases, it is fast enough.

### Large Cassettes

If your agent fetches massive context documents (e.g., retrieving 10MB of text from a vector database), the cassette file will be large. The pure Python YAML parser can become a bottleneck when loading a 10MB file.

If you notice AgentTape taking a long time to start a session, you should install the optional `PyYAML` dependency.

```bash
pip install "agenttape[yaml]"
```

When `PyYAML` is installed, AgentTape automatically switches to using its C-extension backed parser (`yaml.CSafeLoader`), which is significantly faster for large files.

---

## Memory Footprint

AgentTape only loads a cassette into memory when a `Session` begins (e.g., when the `use_cassette` context manager is entered).

When the session ends, the memory is freed.

If you have a test suite with 1,000 tests, each using a different cassette, AgentTape will only ever have one cassette in memory at a time. This keeps the memory overhead of the `pytest` plugin extremely low, regardless of the size of your test suite.

---

## Summary

*   Replay mode is orders of magnitude faster than live execution because it eliminates network latency.
*   The default YAML parser is fast enough for most use cases.
*   Install `agenttape[yaml]` for C-extension speed if dealing with massive >5MB cassettes.
*   AgentTape streams cassettes one at a time, keeping memory usage low.

---

**Next Steps**: Learn how to build on top of AgentTape in [Extending AgentTape](extending.md).