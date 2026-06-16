"""Export cassettes to JSON or OpenTelemetry spans.

The OTEL export produces an OTLP-style JSON document (resource + spans) without
requiring the OpenTelemetry SDK, keeping the core dependency-free. Each interaction
becomes a span; latency is mapped to span start/end and usage/cost to attributes.
"""

from __future__ import annotations

import json
from typing import Any

from .metrics import interaction_usage
from .schema import Cassette


def to_json(cassette: Cassette, *, indent: int = 2) -> str:
    return json.dumps(cassette.to_dict(), indent=indent, ensure_ascii=False, default=str)


def to_otel(cassette: Cassette) -> dict[str, Any]:
    """Return an OTLP-style trace document (resourceSpans/scopeSpans/spans)."""

    trace_id = _hex_id(cassette.run_id or "agenttape-run", 32)
    spans: list[dict[str, Any]] = []
    # Synthesise sequential nanosecond timestamps from recorded latencies.
    base_ns = int(_base_time(cassette) * 1e9)
    cursor = base_ns
    for interaction in cassette.interactions:
        dur_ns = int((interaction.latency_ms or 0.0) * 1e6)
        start = cursor
        end = cursor + dur_ns
        cursor = end
        usage = interaction_usage(interaction)
        attrs: dict[str, Any] = {
            "agenttape.kind": interaction.kind,
            "agenttape.boundary": interaction.boundary or interaction.kind,
            "agenttape.index": interaction.index,
        }
        if usage.total_tokens:
            attrs["llm.usage.total_tokens"] = usage.total_tokens
            attrs["llm.usage.prompt_tokens"] = usage.prompt_tokens
            attrs["llm.usage.completion_tokens"] = usage.completion_tokens
        if usage.cost_usd is not None:
            attrs["llm.usage.cost_usd"] = usage.cost_usd
        model = (interaction.request or {}).get("model")
        if model:
            attrs["llm.model"] = model
        spans.append(
            {
                "traceId": trace_id,
                "spanId": _hex_id(f"{cassette.run_id}-{interaction.index}", 16),
                "name": f"{interaction.kind}:{interaction.boundary or interaction.kind}",
                "kind": "SPAN_KIND_CLIENT",
                "startTimeUnixNano": str(start),
                "endTimeUnixNano": str(end),
                "attributes": [{"key": k, "value": _attr_value(v)} for k, v in attrs.items()],
                "status": {"code": "STATUS_CODE_ERROR" if interaction.error else "STATUS_CODE_OK"},
            }
        )

    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": "agenttape"}},
                        {
                            "key": "agenttape.run_id",
                            "value": {"stringValue": cassette.run_id or ""},
                        },
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "agenttape", "version": cassette.version},
                        "spans": spans,
                    }
                ],
            }
        ]
    }


def to_otel_json(cassette: Cassette, *, indent: int = 2) -> str:
    return json.dumps(to_otel(cassette), indent=indent, ensure_ascii=False)


def _attr_value(value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    return {"stringValue": str(value)}


def _base_time(cassette: Cassette) -> float:
    freeze = (cassette.meta or {}).get("freeze") or {}
    base = freeze.get("base_time")
    if isinstance(base, (int, float)):
        return float(base)
    return 0.0


def _hex_id(seed: str, length: int) -> str:
    import hashlib

    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:length]
