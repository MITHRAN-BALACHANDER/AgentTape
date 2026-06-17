# Extending AgentTape

How to build tools around the AgentTape ecosystem.

---

## What is it?

AgentTape is not just a testing tool; it is a standard format for recording agent interactions. Because cassettes are structured YAML files, you can build entirely separate tools that read, analyze, or visualize them.

---

## The Cassette Format

If you want to build a tool that reads AgentTape recordings (for example, a custom web dashboard, an analytics script, or an evaluation framework), you should read the raw YAML files directly.

You do not need to import the AgentTape Python library to read a cassette.

### Example: Token Usage Analyzer

Here is a simple script that parses a directory of cassettes to calculate total token usage across your test suite.

```python
import yaml
from pathlib import Path

total_tokens = 0

for file in Path("cassettes").glob("*.yaml"):
    with open(file) as f:
        cassette = yaml.safe_load(f)

    for interaction in cassette.get("interactions", []):
        if interaction.get("kind") == "llm":
            metrics = interaction.get("response", {}).get("metrics", {})
            total_tokens += metrics.get("total_tokens", 0)

print(f"Total tokens used across all tests: {total_tokens}")
```

---

## Integration with Evaluation Frameworks

Evaluation frameworks (like LangSmith, Braintrust, or local scripts) need to run agents against hundreds of examples.

If you run those evaluations against live APIs, it takes hours.

If you wrap the evaluation run in `agenttape.use_cassette("eval_dataset", mode="none")`, the evaluation will run instantly. This allows you to evaluate *deterministic logic* (like how your agent routes tasks or uses tools) over a massive dataset without paying for LLM calls.

---

## Exporting to OpenTelemetry

*(Experimental)*

AgentTape includes a CLI command to export cassettes into the OpenTelemetry (OTel) standard format.

```bash
agenttape export cassettes/hello.yaml --format otel > trace.json
```

This allows you to take an offline recording and import it into any standard observability platform (Datadog, Honeycomb, Jaeger) to visualize the agent's execution trace.

---

## Summary

*   Cassettes are an open data format.
*   You can parse them with standard YAML libraries in any language.
*   They are ideal for speeding up local evaluation loops.
*   They can be exported to OpenTelemetry for visualization.

---

**Next Steps**: Check the complete [Python API Reference](api.md).