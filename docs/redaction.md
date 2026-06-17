# Redaction

Preventing API keys and PII from leaking into Git.

---

## What is it?

When AgentTape records an interaction, it captures the raw HTTP headers, prompts, and tool arguments. These often contain sensitive information like authorization tokens, passwords, or Personally Identifiable Information (PII).

Redaction is the process of scrubbing this sensitive data before the cassette is saved to disk.

---

## Why it exists

Cassettes are designed to be committed to version control. If you commit an active OpenAI API key or a user's real email address to a public GitHub repository, it is a massive security risk.

AgentTape provides built-in mechanisms to automatically redact this data so your cassettes are safe to share.

---

## How it Works

Redaction is configured globally in your `agenttape.toml` file.

```toml
[redact]
headers = ["Authorization", "X-Api-Key", "Cookie"]
secrets = ["sk-proj-12345", "super_secret_password"]
replacement = "<REDACTED>"
```

### Header Redaction

When an HTTP adapter (like the `openai` adapter) records a request, AgentTape checks the headers against the `redact.headers` list. If it finds a match, it replaces the entire value with the `replacement` string.

### Secret Redaction

The `secrets` list is more powerful. AgentTape performs a deep search-and-replace across the entire cassette payload. It checks headers, request bodies, LLM prompts, tool arguments, and JSON responses. If it finds any of the exact strings listed in `secrets`, it replaces them.

---

## Dynamic Secrets

Hardcoding secrets in `agenttape.toml` is a bad idea because then the config file itself is a security risk.

Instead, you can tell AgentTape to redact whatever values are currently stored in specific environment variables.

```toml
[redact]
env_secrets = ["OPENAI_API_KEY", "STRIPE_SECRET_KEY"]
```

If your `OPENAI_API_KEY` is `sk-123`, AgentTape will search the cassette for `sk-123` and replace it with `<REDACTED>`.

---

## CLI Redaction

If you accidentally record a cassette without configuring redaction first, or if you discover PII in an existing cassette, you can use the CLI to redact it retroactively.

```bash
agenttape redact cassettes/hello.yaml --secret "john@example.com"
```

---

## Summary

*   Cassettes are committed to Git, so they must be scrubbed of secrets.
*   Configure redaction in `agenttape.toml`.
*   You can redact specific HTTP headers or perform global string replacements.
*   Use `env_secrets` to avoid hardcoding secrets in your config file.

---

**Next Steps**: See how to use these concepts to test real-world applications in [Testing AI Apps](testing-ai-apps.md).