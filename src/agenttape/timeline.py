"""ASCII timeline waterfall and human-readable inspection rendering."""

from __future__ import annotations

import json
from typing import Any

from .metrics import cassette_usage, interaction_usage
from .schema import Cassette, Interaction

_KIND_LANE = {
    "llm": "LLM",
    "tool": "Tool",
    "retrieval": "Retrieval",
    "memory_read": "Memory↓",
    "memory_write": "Memory↑",
    "http": "HTTP",
}


def render_timeline(cassette: Cassette, path: str | None = None, width: int = 40) -> str:
    """Render the run as an ASCII waterfall (User → Planner → Tool → LLM → …)."""

    lines: list[str] = []
    title = f"Timeline: {path}" if path else "Timeline"
    lines.append(title)
    lines.append(f"run {cassette.run_id or '?'} · {len(cassette.interactions)} interactions")
    lines.append("")

    latencies = [i.latency_ms or 0.0 for i in cassette.interactions]
    total = sum(latencies) or 1.0
    cursor = 0.0
    lines.append("User")
    for interaction, lat in zip(cassette.interactions, latencies):
        lane = _KIND_LANE.get(interaction.kind, interaction.kind)
        name = interaction.boundary or interaction.kind
        start_frac = cursor / total
        bar_len = max(1, int(round((lat / total) * width)))
        pad = int(round(start_frac * width))
        bar = " " * pad + "█" * bar_len
        bar = bar[:width].ljust(width)
        status = "✗" if interaction.error else "→"
        lines.append(f"  {status} {lane:<9} {name:<22} |{bar}| {lat:8.1f}ms")
        cursor += lat
    lines.append("Done")
    lines.append("")

    usage = cassette_usage(cassette)
    lines.append(
        f"Σ latency {total:.1f}ms · tokens {usage.total_tokens} "
        f"· cost {_fmt_cost(usage.cost_usd)}"
    )
    return "\n".join(lines)


def render_inspect(cassette: Cassette, path: str | None = None, *, full: bool = False) -> str:
    """Pretty-print interactions with latency, tokens and cost."""

    lines: list[str] = []
    if path:
        lines.append(f"Cassette: {path}")
    lines.append(f"version={cassette.version} run_id={cassette.run_id}")
    if cassette.meta:
        meta_view = {k: v for k, v in cassette.meta.items() if k != "freeze"}
        lines.append(f"meta: {json.dumps(meta_view, default=str)}")
        if "freeze" in cassette.meta:
            feats = cassette.meta["freeze"].get("features", [])
            lines.append(f"freeze: {', '.join(feats)}")
    lines.append("")

    for interaction in cassette.interactions:
        lines.append(_render_interaction(interaction, full=full))
        lines.append("")

    usage = cassette_usage(cassette)
    total_latency = sum((i.latency_ms or 0.0) for i in cassette.interactions)
    lines.append("-" * 60)
    lines.append(
        f"{len(cassette.interactions)} interactions · {total_latency:.1f}ms · "
        f"{usage.prompt_tokens}+{usage.completion_tokens}={usage.total_tokens} tokens · "
        f"cost {_fmt_cost(usage.cost_usd)}"
    )
    return "\n".join(lines)


def _render_interaction(interaction: Interaction, *, full: bool) -> str:
    head = f"#{interaction.index} [{interaction.kind}] {interaction.boundary or ''}".rstrip()
    meta_bits = []
    if interaction.latency_ms is not None:
        meta_bits.append(f"{interaction.latency_ms:.1f}ms")
    usage = interaction_usage(interaction)
    if usage.total_tokens:
        meta_bits.append(f"{usage.total_tokens} tok")
    if usage.cost_usd:
        meta_bits.append(_fmt_cost(usage.cost_usd))
    if meta_bits:
        head += "  (" + ", ".join(meta_bits) + ")"
    lines = [head]
    lines.append(f"  request:  {_summarize(interaction.request, full)}")
    if interaction.error is not None:
        lines.append(f"  error:    {interaction.error.get('type')}: {interaction.error.get('message')}")
    else:
        lines.append(f"  response: {_summarize(interaction.response, full)}")
    return "\n".join(lines)


def _summarize(value: Any, full: bool) -> str:
    text = json.dumps(value, default=str, ensure_ascii=False)
    if full or len(text) <= 200:
        return text
    return text[:199] + "…"


def _fmt_cost(cost: float | None) -> str:
    return "n/a" if cost is None else f"${cost:.6f}"
