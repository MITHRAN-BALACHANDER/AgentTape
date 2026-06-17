# Custom Adapters

Writing adapters to intercept unsupported libraries.

---

## What is it?

An **adapter** is a piece of code that hooks into a third-party library (like the Anthropic SDK or the Stripe SDK) to automatically capture its network requests and responses into the AgentTape engine.

---

## Why it exists

While you can always use `@agenttape.tool` to wrap a function that calls an API, writing an adapter allows AgentTape to intercept the library *automatically*. Users won't have to change their application code; they just use the SDK normally inside a `use_cassette` block.

---

## How it Works

An adapter is essentially a Python monkey-patch that intercepts a specific function call.

To write an adapter, you need to understand the internal API of the library you want to intercept. You find the lowest-level function where the network request is made (or where the request data is fully formed), patch it to record the data, and then patch it to return the recorded data during replay.

### The Adapter Interface

AgentTape adapters are not currently exposed via a public, stable API plugin system. They must be added directly to the AgentTape codebase in the `src/agenttape/adapters/` directory.

An adapter must implement a specific registration function that AgentTape calls when it initializes.

```python

import unittest.mock
from agenttape.engine import engine

def register() -> None:
    import my_api_sdk
    original_call = my_api_sdk.Client.make_request
    def interceptor(self, *args, **kwargs):
        request_data = {"args": args, "kwargs": kwargs}
        if engine.should_replay("http", request_data):
            recorded_response = engine.get_replay("http", request_data)
            return _deserialize_response(recorded_response)
        real_response = original_call(self, *args, **kwargs)
        response_data = _serialize_response(real_response)
        engine.record("http", request_data, response_data)

        return real_response
    patcher = unittest.mock.patch("my_api_sdk.Client.make_request", new=interceptor)
    patcher.start()
```

### Serialization

The hardest part of writing an adapter is writing `_serialize_response` and `_deserialize_response`.

The `request_data` and `response_data` you pass to the AgentTape engine **must be purely serializable Python primitives** (dicts, lists, strings, ints, floats).

If the SDK returns a complex object (like a `MyApiResponse` class), you must unpack that class into a dictionary for `record()`, and then reconstruct the class from the dictionary during replay so the application code doesn't notice the difference.

---

## Contributing Adapters

If you write an adapter for a popular LLM provider (Anthropic, Gemini) or a common agent framework (LangChain, LlamaIndex), please open a Pull Request!

The AgentTape core team maintains the official adapters to ensure they stay up to date when the underlying SDKs change.

---

## Summary

*   Adapters automatically intercept third-party SDKs.
*   They monkey-patch the SDK's internal network methods.
*   They must translate complex SDK objects into serializable dicts for the AgentTape engine.
*   You are encouraged to contribute new adapters to the main repository.

---

**Next Steps**: Understand the core design principles in [Internals](internals.md).