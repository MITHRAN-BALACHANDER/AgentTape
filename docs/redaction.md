# Redaction & secrets

AgentTape redacts secrets and PII **at record time**, before a cassette is written,
so secrets never touch disk.

## Two layers

1. **Denylisted keys** — any mapping key whose name matches the denylist (case
   insensitive) has its entire value replaced: `Authorization`, `api_key`,
   `password`, `token`, `set-cookie`, `client_secret`, and more.
2. **Value regexes** — every string is scanned for known secret/PII patterns:
   OpenAI/Slack/GitHub/AWS/Google keys, bearer tokens, PEM private keys and emails.

The placeholder is `***REDACTED***`.

## Configure

```toml
# agenttape.toml
[redact]
denylist = ["x-internal-secret"]   # extra field names to fully redact
regexes  = ['ACME-[0-9A-F]{20}']    # extra value patterns to scrub
redact_emails = true
```

## Matching stays stable

Redaction is applied before the cassette is written, and HTTP requests drop volatile
/ secret headers (`Authorization`, `Cookie`, `User-Agent`, …) from the matched
request. This means a redacted secret can never destabilise replay matching.

## Re-redact an existing cassette

If a cassette predates a denylist change, scrub it again:

```bash
agenttape redact cassettes/run.yaml
agenttape validate cassettes/run.yaml   # lints for any remaining leaked secrets
```

`agenttape validate` scans the serialised cassette for secret/PII patterns and fails
if any are found.
