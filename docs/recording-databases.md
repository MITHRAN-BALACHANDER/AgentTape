# Recording Databases

How to safely mock SQL and NoSQL database interactions.

---

## What is it?

Agents often need to read from or write to databases. Testing these interactions is notoriously difficult: you either have to spin up a local test database (which is slow) or mock the database driver (which is brittle).

AgentTape allows you to record the inputs and outputs of your database queries, turning them into fast, offline mocks during replay.

---

## The Problem with Database Drivers

AgentTape does not attempt to intercept low-level database protocols (like the PostgreSQL wire protocol or MongoDB sockets).

Intercepting at the socket level is brittle because database drivers often maintain complex connection pools, binary formats, and streaming cursors that are nearly impossible to serialize cleanly into YAML.

---

## The Solution: Semantic Boundaries

Instead of mocking the database driver, you should mock the **boundary** between your application and the database. You do this using the `@agenttape.tool` decorator.

### Example: Reading from a Database

```python
import agenttape
import psycopg2

# 1. Define the boundary
@agenttape.tool
def fetch_user_record(user_id: int) -> dict:
    conn = psycopg2.connect("dbname=production")
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email FROM users WHERE id = %s", (user_id,))
    row = cursor.fetchone()
    return {"id": row[0], "name": row[1], "email": row[2]} if row else None

# 2. The agent uses the boundary
def agent_logic():
    user = fetch_user_record(42)
    # ... logic ...
```

During **recording**, AgentTape executes `fetch_user_record`, allowing it to connect to PostgreSQL and run the query. It saves the argument `42` and the returned dictionary to the cassette.

During **replay**, AgentTape intercepts `fetch_user_record(42)`. It never executes the inner code. It never imports `psycopg2`. It never tries to connect to a database. It simply returns the saved dictionary.

### Example: Writing to a Database

The exact same pattern applies to writes.

```python
@agenttape.tool
def update_user_status(user_id: int, status: str) -> bool:
    conn = psycopg2.connect("dbname=production")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET status = %s WHERE id = %s", (status, user_id))
    conn.commit()
    return True
```

In replay mode, `update_user_status` will return `True` without ever modifying the real database. This is what makes AgentTape safe for CI.

---

## Best Practices

*   **Serialize at the boundary**: Ensure the function you decorate returns simple, serializable Python objects (dicts, lists, strings, ints). Do not return active database cursors or ORM models. Convert them to dicts before returning.
*   **Keep boundaries focused**: Don't wrap a function that contains 50 lines of business logic and one database query. Extract the database query into a small helper function, and wrap the helper.

---

## Summary

*   AgentTape does not intercept low-level database drivers.
*   Use `@agenttape.tool` to define semantic boundaries around your database queries.
*   Ensure the decorated function returns serializable data (like dicts), not cursors.
*   This pattern makes tests fast, offline, and safe from destructive writes.

---

**Next Steps**: Apply this same logic to [Recording Vector Stores](recording-vector-stores.md).