# Recording APIs

How to capture and replay HTTP requests.

---

## What is it?

Agents communicate with LLM providers (OpenAI, Anthropic) and third-party services (Stripe, GitHub) via HTTP APIs. AgentTape needs to intercept these calls to record and replay them.

---

## Adapters

AgentTape uses **adapters** to hook into the HTTP clients used by your application.

### Built-in Adapters

If you install the corresponding extra, AgentTape will automatically intercept calls made by these libraries:

*   **`openai`**: `pip install "agenttape[openai]"`
*   *(More adapters coming soon)*

You do not need to change your application code to use these adapters. Simply wrapping your code in `use_cassette` is enough.

```python
import agenttape
from openai import OpenAI

# AgentTape automatically intercepts the OpenAI client.
with agenttape.use_cassette("api_test", mode="record"):
    client = OpenAI()
    client.chat.completions.create(...)
```

### The Universal HTTP Adapter

If your agent makes HTTP requests using the standard `requests` or `httpx` libraries, and there is no specific adapter for the service you are calling, AgentTape provides a generic HTTP adapter.

*(Note: The universal HTTP adapter is currently under development. For now, the recommended approach for unsupported APIs is to wrap the API call in a function and use the `@agenttape.tool` decorator).*

---

## Wrapping Unsupported APIs

If you are calling an API that AgentTape does not have an adapter for, you should wrap the call in a Python function and use the `@agenttape.tool` decorator.

This elevates the HTTP call from a low-level network event to a semantic boundary that AgentTape understands.

```python
import agenttape
import requests

# We don't have an adapter for the Github API, so we wrap it.
@agenttape.tool
def get_github_user(username: str) -> dict:
    resp = requests.get(f"https://api.github.com/users/{username}")
    resp.raise_for_status()
    return resp.json()

def run_agent():
    # The agent calls our wrapped function
    return get_github_user("octocat")
```

During recording, `requests.get` will execute normally. During replay, `requests.get` will never be called; AgentTape will intercept `get_github_user` and immediately return the saved dictionary.

---

## Best Practices

*   **Prefer Adapters**: If an adapter exists for the service you are using, install it. Adapters capture semantic metadata (like token usage and specific model parameters) that a generic HTTP interceptor would miss.
*   **Wrap the rest**: For everything else, use `@agenttape.tool`. It is safer and more robust than trying to intercept raw sockets.

---

## Summary

*   Adapters automatically intercept specific SDKs (like `openai`).
*   Install them using pip extras (`agenttape[openai]`).
*   For unsupported APIs, wrap the network call in a function decorated with `@agenttape.tool`.

---

**Next Steps**: See how this same principle applies to [Recording Databases](recording-databases.md).