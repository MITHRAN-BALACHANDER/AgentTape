# Quickstart

## 30 seconds: record, then replay

```python
import agenttape
from openai import OpenAI

def run_agent():
    client = OpenAI()
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": "Say hi in 3 words"}],
    )
    return resp.choices[0].message.content

# Record once — hits the real API, writes cassettes/hello.yaml (secrets redacted).
with agenttape.use_cassette("hello", mode="record"):
    print(run_agent())

# Replay forever — zero network calls, milliseconds, free, deterministic.
with agenttape.use_cassette("hello", mode="none"):
    print(run_agent())   # identical output, served from the cassette
```

## As a decorator

```python
@agenttape.replay("hello")          # mode="none" by default → offline + deterministic
def test_agent():
    assert "hi" in run_agent().lower()
```

## Recording tools

Wrap any function that touches the outside world with `@agenttape.tool`. In replay
it is served from the cassette and **never executes for real**:

```python
@agenttape.tool
def charge_card(amount: int) -> dict:
    return payment_api.charge(amount)   # real side effect — only in record mode

with agenttape.use_cassette("checkout", mode="none"):
    charge_card(4200)   # returns the recorded result; no charge happens
```

Other boundary decorators: `@agenttape.retrieval`, `@agenttape.memory_read`,
`@agenttape.memory_write`. For frameworks that only expose callbacks, pass an
`agenttape.AgentTape()` instance as a listener.

## Cassette modes

| Mode | Behaviour |
|------|-----------|
| `none` | Replay only; error on any unmatched request. **Default in tests/CI.** |
| `once` | Record if the cassette is absent, replay if present. |
| `new_episodes` | Replay matches, record anything new. |
| `all` | Always record, ignore existing recordings. |
| `record` | Force record everything fresh. |

## Next

- [Mixed / partial replay](mixed-replay.md) — the killer feature.
- [pytest plugin](pytest.md) — offline tests by default.
- [CLI](cli.md) — inspect, diff, timeline, view.
