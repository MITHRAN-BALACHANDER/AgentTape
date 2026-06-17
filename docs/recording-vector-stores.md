# Recording Vector Stores

How to capture embeddings and semantic search.

---

## What is it?

Retrieval-Augmented Generation (RAG) agents rely heavily on vector databases (like Pinecone, Milvus, or local FAISS indexes) to fetch relevant context before answering a question.

Testing RAG agents is difficult because the contents of the vector database change over time, which changes the retrieved context, which changes the LLM's answer.

---

## Semantic Boundaries for Retrieval

Just like with standard databases, AgentTape does not intercept the low-level connection to Pinecone or FAISS. Instead, you wrap the retrieval function using the `@agenttape.retrieval` decorator.

```python
import agenttape
import pinecone

@agenttape.retrieval
def search_knowledge_base(query: str, top_k: int = 3) -> list[str]:
    embedding = get_embedding(query)
    index = pinecone.Index("my-index")
    results = index.query(vector=embedding, top_k=top_k, include_metadata=True)
    return [match['metadata']['text'] for match in results['matches']]
```

### Why use `@agenttape.retrieval`?

You could use `@agenttape.tool` here, and it would work perfectly.

However, `@agenttape.retrieval` is a semantic marker. It tells AgentTape (and anyone reading the YAML cassette) that this specific interaction was a document retrieval step, not an agent taking an action. This makes the cassettes easier to understand and filter later.

---

## The Value of Freezing Retrieval

When you record a session using the function above, AgentTape saves the `query` ("How do I reset my password?") and the list of retrieved text chunks into the cassette.

During replay, the agent receives the exact same text chunks it received months ago, even if the real Pinecone database has been completely wiped or updated.

This guarantees that if your test fails, it is because you broke the agent's reasoning logic, not because the underlying data changed.

---

## Partial Replay with RAG

RAG applications are the perfect use case for Partial Replay.

Often, you want to test if a new LLM model (like `gpt-4o`) is better at synthesizing information from retrieved documents than an older model.

You can run your agent with `live={"llm"}`.

```python
import agenttape
with agenttape.use_cassette("rag_test", live={"llm"}):
    answer = agent.run("How do I reset my password?")
```

In this mode, AgentTape will:
1.  Intercept the `search_knowledge_base` call and instantly return the saved documents.
2.  Allow the LLM call to hit the real OpenAI API with the new prompt/model.

This allows you to rapidly iterate on your synthesis prompts without paying to re-embed the query or hit the vector database.

---

## Summary

*   Use `@agenttape.retrieval` to wrap functions that query vector databases.
*   Ensure the function returns the raw text chunks (lists of strings or dicts).
*   Freezing retrieval ensures your tests are immune to underlying data changes.
*   Use Partial Replay to test new LLM models against frozen retrieval contexts.

---

**Next Steps**: Review the complete guide on [Recording Tools](recording-tools.md).