# Working Offline

Developing AI agents on an airplane.

---

## What is it?

Because AgentTape saves all external interactions to local YAML files, you can run your entire agent stack without an internet connection.

This guide explains how to leverage AgentTape for local, offline development.

---

## The Workflow

The standard offline workflow looks like this:

1.  **Online Phase**: Write the initial version of your agent. Run it once with `mode="record"` to capture the happy path.
2.  **Offline Phase**: Disconnect from the internet. Run your agent with `mode="none"`. Refactor your code, build out the UI, or write data processing logic.
3.  **Iteration Phase**: If you need the agent to take a new path, reconnect, record the new interaction, and disconnect again.

---

## Refactoring Business Logic

The most common use case for working offline is refactoring the code *around* your agent.

If you have a function that processes the JSON output of an LLM, you don't need to hit the OpenAI API every time you run your script to test your processing logic.

```python
import agenttape

def parse_llm_output(json_str: str):
    # Complex parsing logic you are working on
    pass

# Run this loop instantly, offline, for free.
with agenttape.use_cassette("complex_task", mode="none"):
    raw_response = agent.run("Do complex task")
    parsed = parse_llm_output(raw_response)
    print(parsed)
```

You can iterate on `parse_llm_output` hundreds of times a minute.

---

## UI Development

If you are building a frontend for your AI agent (like a chat interface), you can use AgentTape to serve immediate responses to the frontend without waiting 5 seconds for the LLM to reply.

Just wrap the backend endpoint in a `use_cassette` block. Your frontend will feel instantaneous during development.

---

## Faking Errors

When you are offline, you can use AgentTape to simulate network errors or API failures to test how your application handles them.

1.  Open the cassette YAML file.
2.  Find an HTTP interaction.
3.  Change the response status code to `500`.

```yaml
  - kind: http
    request: ...
    response:
      status: 500
      body: "Internal Server Error"
```

4. Run your application in `mode="none"`. The application will instantly receive a 500 error, allowing you to test your retry logic or error banners.

---

## Summary

*   AgentTape allows you to develop AI applications without internet access.
*   It provides instantaneous feedback loops for refactoring code.
*   You can hand-edit cassettes to simulate errors offline.

---

**Next Steps**: Learn how to diagnose issues when things go wrong in [Debugging](debugging.md).