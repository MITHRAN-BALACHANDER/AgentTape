# Cassette format specification

Cassettes default to **YAML** (most diff-friendly) with **JSON** also supported. A
cassette is an ordered list of interactions plus run metadata. The format is
**hand-editable**: edit a recorded response, save, replay, and the agent behaves
differently — with no API call.

## Top level

```yaml
version: '1'                      # schema version
created_at: '2026-06-16T12:00:00' # ISO timestamp (real, not frozen)
run_id: 4e852c18-...              # uuid for this run
meta:                             # framework, sdk, model, freeze settings, tags
  agenttape_version: 0.1.0
  framework: openai
  model: gpt-4o-mini
  freeze:
    features: [clock, uuid, random]
    base_time: 1781596500.91
    base_iso: '2026-06-16T07:55:00+00:00'
    random_seed: 0
    uuids: ['98f0...']
interactions: [...]
```

## An interaction

```yaml
- index: 0                # position in the run
  kind: llm               # llm | tool | retrieval | memory_read | memory_write | http
  boundary: llm           # named boundary (tool name, or "llm") — used by mixed replay
  request:                # canonicalised request
    model: gpt-4o-mini
    messages:
      - role: user
        content: Say hi
  response:               # recorded response (OR `error:` for a raised exception)
    choices:
      - message: {role: assistant, content: Hi there}
  match_key: 'sha256:...' # deterministic match key
  latency_ms: 581.0
  usage:                  # tokens/cost when known
    total_tokens: 13
  tags: []
```

A failed boundary records `error` instead of `response`:

```yaml
- index: 0
  kind: tool
  boundary: charge_card
  request: {name: charge_card, args: {amount: 4200}}
  error: {type: TimeoutError, module: builtins, message: "timed out"}
```

## Assets sidecar

Payloads larger than `assets_threshold_bytes` (default 4096) are written to a
sibling `<cassette>.assets/` directory, named by content hash, and referenced inline
so the YAML stays small and diffable:

```yaml
big_document:
  __agenttape_asset__: 'sha256:ab12…'
  encoding: utf-8
  size: 40213
  preview: 'The quick brown fox…'
```

On load, references are resolved transparently back to their content.

## Redaction

Secrets and PII are redacted **at record time**, before anything is written, so they
never touch disk. `Authorization` headers, `api_key`/`token`/`password` fields, API
key patterns and emails are replaced with `***REDACTED***`. See
[Redaction & secrets](redaction.md).

## Matching

An incoming request is reduced to a canonical form (volatile fields dropped, keys
sorted) and hashed with sha256 to produce the `match_key`. Matching is **keyed**,
falling back to **call order** on collision. Matchers: `exact`, `ignore_volatile`
(default), `ordered`, and `custom(callable)`.

## Versioning

The `version` field gates compatibility. Loading an unsupported version raises
`SchemaVersionError` with a migration hint. Run `agenttape validate <cassette>` to
check schema, determinism and leaked-secret lint.
