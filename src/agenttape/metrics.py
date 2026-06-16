"""Token and cost accounting derived from recorded ``usage`` fields.

Cost is best-effort: AgentTape ships a small, override-able price table for common
models. When a model is unknown the cost is reported as ``None`` rather than guessed.
Prices are USD per 1,000 tokens and are intentionally easy to edit/extend.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .schema import Cassette, Interaction

# USD per 1K tokens: (prompt, completion). Approximate; override as needed.
PRICE_TABLE: dict[str, tuple[float, float]] = {
    "gpt-4o": (0.0025, 0.01),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4-turbo": (0.01, 0.03),
    "gpt-4": (0.03, 0.06),
    "gpt-3.5-turbo": (0.0005, 0.0015),
    "o1": (0.015, 0.06),
    "o1-mini": (0.0011, 0.0044),
    "claude-opus-4": (0.015, 0.075),
    "claude-sonnet-4": (0.003, 0.015),
    "claude-3-5-sonnet": (0.003, 0.015),
    "claude-3-5-haiku": (0.0008, 0.004),
}


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost_usd: float | None = None

    def __add__(self, other: Usage) -> Usage:
        cost: float | None
        if self.cost_usd is None and other.cost_usd is None:
            cost = None
        else:
            cost = (self.cost_usd or 0.0) + (other.cost_usd or 0.0)
        return Usage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cost_usd=cost,
        )


def _price_for(model: str | None) -> tuple[float, float] | None:
    if not model:
        return None
    if model in PRICE_TABLE:
        return PRICE_TABLE[model]
    # Prefix match (e.g. "gpt-4o-2024-08-06" -> "gpt-4o").
    for key, price in sorted(PRICE_TABLE.items(), key=lambda kv: -len(kv[0])):
        if model.startswith(key):
            return price
    return None


def interaction_usage(interaction: Interaction, model: str | None = None) -> Usage:
    data = interaction.usage or {}
    prompt = int(data.get("prompt_tokens", 0) or 0)
    completion = int(data.get("completion_tokens", 0) or 0)
    total = int(data.get("total_tokens", prompt + completion) or 0)
    model = model or _model_of(interaction)
    price = _price_for(model)
    cost = None
    if price is not None:
        cost = (prompt / 1000.0) * price[0] + (completion / 1000.0) * price[1]
    return Usage(prompt, completion, total, cost)


def _model_of(interaction: Interaction) -> str | None:
    req = interaction.request or {}
    model = req.get("model")
    return str(model) if model else None


def cassette_usage(cassette: Cassette) -> Usage:
    total = Usage()
    default_model = cassette.meta.get("model") if cassette.meta else None
    for interaction in cassette.interactions:
        if interaction.kind == "llm":
            total = total + interaction_usage(interaction, _model_of(interaction) or default_model)
    return total


def final_output(cassette: Cassette) -> Any:
    """Return the final agent output (last interaction's response)."""

    for interaction in reversed(cassette.interactions):
        if interaction.error is None:
            return interaction.response
    return None
