"""The internal event vocabulary every adapter maps onto.

Adapters translate framework-native callbacks into these event names so the rest of
AgentTape (engine, timeline, viewer, exporters) is framework-agnostic.
"""

from __future__ import annotations

RUN_STARTED = "RUN_STARTED"
RUN_FINISHED = "RUN_FINISHED"
LLM_REQUEST = "LLM_REQUEST"
LLM_RESPONSE = "LLM_RESPONSE"
TOOL_START = "TOOL_START"
TOOL_END = "TOOL_END"
RETRIEVAL = "RETRIEVAL"
MEMORY_READ = "MEMORY_READ"
MEMORY_WRITE = "MEMORY_WRITE"
PLANNER = "PLANNER"
SYSTEM_PROMPT = "SYSTEM_PROMPT"
USER_MESSAGE = "USER_MESSAGE"
ERROR = "ERROR"
RETRY = "RETRY"
HUMAN_APPROVAL = "HUMAN_APPROVAL"

EVENTS = frozenset(
    {
        RUN_STARTED,
        RUN_FINISHED,
        LLM_REQUEST,
        LLM_RESPONSE,
        TOOL_START,
        TOOL_END,
        RETRIEVAL,
        MEMORY_READ,
        MEMORY_WRITE,
        PLANNER,
        SYSTEM_PROMPT,
        USER_MESSAGE,
        ERROR,
        RETRY,
        HUMAN_APPROVAL,
    }
)

# Maps internal events to cassette interaction kinds where applicable.
EVENT_TO_KIND = {
    LLM_REQUEST: "llm",
    LLM_RESPONSE: "llm",
    TOOL_START: "tool",
    TOOL_END: "tool",
    RETRIEVAL: "retrieval",
    MEMORY_READ: "memory_read",
    MEMORY_WRITE: "memory_write",
}
