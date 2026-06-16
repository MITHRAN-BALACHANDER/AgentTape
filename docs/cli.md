# CLI

Everything operates on local files only — no network, no server.

```text
agenttape init                       scaffold agenttape.toml + cassettes/
agenttape record <module:func> <name>  run an entrypoint in record mode
agenttape replay <cassette>          print the reconstructed timeline (no calls)
agenttape inspect <cassette>         interactions, latency, tokens, cost
agenttape timeline <cassette>        ASCII waterfall of the run
agenttape diff <a> <b> [--type ...]  run/prompt/state/output diff
agenttape redact <cassette>          re-run redaction over a cassette
agenttape validate <cassette>        schema + determinism + leaked-secret lint
agenttape export <cassette> --format json|otel
agenttape view <cassette> [second]   self-contained static HTML (no server)
agenttape rm <cassette>              delete a cassette + its assets
```

## Examples

### Timeline

```text
$ agenttape timeline cassettes/demo
Timeline: cassettes/demo.yaml
run 7acf9ec4-… · 2 interactions

User
  → Tool      get_weather            |█                                       |    0.0ms
  → LLM       llm                    |████████████████████████████████████████|  165.1ms
Done

Σ latency 165.1ms · tokens 17 · cost $0.000005
```

### Diff

```text
$ agenttape diff cassettes/a cassettes/b --type all
Run diff
========
model:   gpt-4o-mini  ->  gpt-4o-mini
tokens:  17  ->  17
latency: 165.1ms  ->  0.9ms

Steps:
~ [llm:llm]
    request.messages[0].content: 'weather in Paris?' -> 'forecast for London?'
```

`--type` accepts `run` (default), `prompt`, `state`, `output`, or `all`.

### Export to OpenTelemetry

```bash
agenttape export cassettes/demo --format otel -o trace.json
```

Produces an OTLP-style document where each interaction is a span with token/cost
attributes.

### View

```bash
agenttape view cassettes/demo                 # single-cassette timeline
agenttape view cassettes/a cassettes/b        # two-cassette side-by-side diff
```

Generates a self-contained HTML file (inlined CSS/JS) that opens with `file://`.
Nothing is fetched; nothing leaves your machine.
