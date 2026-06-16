# Cookbook

## Make an existing test offline

```python
# before: hits the real API every run
def test_agent():
    assert run_agent() == "ok"

# after: record once, replay forever
@agenttape.replay("agent_ok")
def test_agent():
    assert run_agent() == "ok"
```

```bash
pytest --agenttape-record   # one-time record
pytest                      # offline from now on
```

## Prove a tool has zero side effects in replay (with a spy)

```python
calls = {"n": 0}

@agenttape.tool
def write_row(row):
    calls["n"] += 1
    return db.insert(row)

with agenttape.use_cassette("dbtest", mode="record"):
    write_row({"id": 1})
assert calls["n"] == 1

with agenttape.use_cassette("dbtest", mode="none"):
    write_row({"id": 1})
assert calls["n"] == 1          # the DB was never touched in replay
```

## Test a failure path by hand-editing a cassette

Open `cassettes/agent.yaml`, change a recorded LLM response to a malformed value,
save, and re-run in `mode="none"`. Your agent's error handling is now tested with no
API call and full determinism.

## Async agents

```python
@agenttape.tool
async def fetch(url):
    return await client.get(url)

async def agent():
    return await fetch("https://api.example.com")

with agenttape.use_cassette("async", mode="none"):
    await agent()
```

## Snapshot the tool-call sequence

```python
@pytest.mark.agenttape("plan")
def test_plan(agenttape_cassette):
    run_planner()
    agenttape_cassette.assert_tool_calls(["search", "rank", "summarize"])
```

## Capture an SDK AgentTape has no adapter for

The `httpx` / `requests` fallback records any HTTP-based SDK automatically — just
wrap the call site in `use_cassette`. No adapter required.

## Compare two model runs

```bash
# record baseline, then re-run with model_override + live={"llm"}
agenttape diff cassettes/run.yaml cassettes/run.derived.yaml --type all
agenttape view cassettes/run.yaml cassettes/run.derived.yaml
```
