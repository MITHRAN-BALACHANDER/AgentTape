# Your First Recording

Learn how to record an LLM interaction and replay it offline.

---

## What is it?

This guide will walk you through writing a simple script that calls the OpenAI API, recording the interaction with AgentTape, and replaying it.

---

## The Problem

Imagine we have a simple function that asks an LLM for a random color.

```python
from openai import OpenAI

def get_random_color():
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Name a random color. Reply with just one word."}]
    )
    return response.choices[0].message.content

print(get_random_color())
```

If we put this in a test, it will cost money every time it runs. It might return "Red" one time, and "Blue" the next. And if our CI server loses internet access, the test will fail.

---

## Recording the Interaction

We can fix this by wrapping the function call in an AgentTape `use_cassette` context manager.

```python
import agenttape
from openai import OpenAI

def get_random_color():
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Name a random color. Reply with just one word."}]
    )
    return response.choices[0].message.content
with agenttape.use_cassette("color_test", mode="record"):
    color = get_random_color()
    print(f"The LLM chose: {color}")
```

### What happened?

1.  AgentTape intercepted the `client.chat.completions.create` call.
2.  It forwarded the request to the real OpenAI API.
3.  It took the response (e.g., "Green") and saved both the prompt and the response into a new file at `cassettes/color_test.yaml`.
4.  It returned the response to our function.

---

## Replaying the Interaction

Now, let's change the mode to `none` (which means "replay only, no network").

```python
import agenttape
from openai import OpenAI

def get_random_color():
    client = OpenAI()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Name a random color. Reply with just one word."}]
    )
    return response.choices[0].message.content
with agenttape.use_cassette("color_test", mode="none"):
    color = get_random_color()
    print(f"The LLM chose: {color}")
```

### What happened?

1.  AgentTape intercepted the call.
2.  It looked at the `cassettes/color_test.yaml` file.
3.  It verified that the prompt matched the recorded prompt.
4.  It immediately returned the saved response ("Green") without making a network request.

If you run this script with `mode="none"`, it will execute in milliseconds. You can even turn off your Wi-Fi and it will still work perfectly.

---

## Inspecting the Cassette

AgentTape cassettes are just plain text. If you open `cassettes/color_test.yaml`, you will see something like this:

```yaml
interactions:
  - kind: llm
    request:
      model: gpt-4o-mini
      messages:
        - role: user
          content: Name a random color. Reply with just one word.
    response:
      content: Green
```

Because it's just text, you can edit it! Change "Green" to "Octarine" in the YAML file, run the replay script again, and watch your script output "The LLM chose: Octarine".

---

## Summary

*   Use `agenttape.use_cassette("name", mode="record")` to capture real API traffic.
*   Use `agenttape.use_cassette("name", mode="none")` to replay traffic offline.
*   Cassettes are saved as readable, editable YAML files in the `cassettes/` directory.

---

**Next Steps**: Move to the Getting Started section and see the [Quickstart](quickstart.md) for a concise reference.