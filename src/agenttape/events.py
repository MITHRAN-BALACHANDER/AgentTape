"""The internal event vocabulary the callback object maps onto.

The :class:`~agenttape.callbacks.AgentTape` callback translates framework-native
hooks into these event names so the rest of AgentTape (timeline, viewer, exporters)
sees a framework-agnostic stream. Only the events actually emitted today are
defined here; add new names alongside the emitter that produces them.
"""

from __future__ import annotations

RUN_STARTED = "RUN_STARTED"
RUN_FINISHED = "RUN_FINISHED"
LLM_REQUEST = "LLM_REQUEST"
TOOL_START = "TOOL_START"
RETRIEVAL = "RETRIEVAL"
