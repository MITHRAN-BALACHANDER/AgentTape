"""The diff engine — run / prompt / state / output diffs.

Every diff is available both as an importable structured object (for assertions in
tests) and as rendered text (for the CLI). Two cassettes are aligned step-by-step
with :class:`difflib.SequenceMatcher` over per-step signatures so inserted/removed
steps are detected, not just in-place changes.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field
from typing import Any

from .engine import diff_fields
from .errors import FieldDiff
from .metrics import cassette_usage, final_output
from .schema import Cassette, Interaction

# --------------------------------------------------------------------------- #
# Run diff
# --------------------------------------------------------------------------- #


@dataclass
class StepChange:
    status: str  # "added" | "removed" | "changed" | "unchanged"
    index_a: int | None
    index_b: int | None
    kind: str
    boundary: str
    request_diffs: list[FieldDiff] = field(default_factory=list)
    response_diffs: list[FieldDiff] = field(default_factory=list)

    def render(self) -> str:
        sym = {"added": "+", "removed": "-", "changed": "~", "unchanged": " "}[self.status]
        head = f"{sym} [{self.kind}:{self.boundary}]"
        if self.status == "unchanged":
            return head
        lines = [head]
        for label, diffs in (("request", self.request_diffs), ("response", self.response_diffs)):
            for d in diffs:
                lines.append(f"    {label}.{d.path}: {d.expected!r} -> {d.received!r}")
        return "\n".join(lines)


@dataclass
class RunDiff:
    steps: list[StepChange]
    model_a: str | None
    model_b: str | None
    tokens_a: int
    tokens_b: int
    cost_a: float | None
    cost_b: float | None
    latency_a: float
    latency_b: float
    output_changed: bool
    tool_names_a: list[str]
    tool_names_b: list[str]

    @property
    def changed(self) -> bool:
        return any(s.status != "unchanged" for s in self.steps) or self.output_changed

    def render(self) -> str:
        lines = ["Run diff", "========"]
        lines.append(f"model:   {self.model_a}  ->  {self.model_b}")
        lines.append(f"tokens:  {self.tokens_a}  ->  {self.tokens_b}")
        lines.append(
            f"cost:    {_fmt_cost(self.cost_a)}  ->  {_fmt_cost(self.cost_b)}"
        )
        lines.append(
            f"latency: {self.latency_a:.1f}ms  ->  {self.latency_b:.1f}ms"
        )
        added = sorted(set(self.tool_names_b) - set(self.tool_names_a))
        removed = sorted(set(self.tool_names_a) - set(self.tool_names_b))
        if added:
            lines.append(f"tools added:   {', '.join(added)}")
        if removed:
            lines.append(f"tools removed: {', '.join(removed)}")
        lines.append("")
        lines.append("Steps:")
        for step in self.steps:
            lines.append(step.render())
        lines.append("")
        lines.append(f"final output changed: {self.output_changed}")
        return "\n".join(lines)


def _signature(interaction: Interaction) -> str:
    return f"{interaction.kind}:{interaction.boundary or interaction.kind}"


def _total_latency(cassette: Cassette) -> float:
    return sum((i.latency_ms or 0.0) for i in cassette.interactions)


def _tool_names(cassette: Cassette) -> list[str]:
    return [
        i.boundary or i.kind
        for i in cassette.interactions
        if i.kind in ("tool", "retrieval")
    ]


def run_diff(a: Cassette, b: Cassette) -> RunDiff:
    """Compare two cassettes step-by-step plus model/token/cost/latency/output."""

    sig_a = [_signature(i) for i in a.interactions]
    sig_b = [_signature(i) for i in b.interactions]
    matcher = difflib.SequenceMatcher(a=sig_a, b=sig_b, autojunk=False)
    steps: list[StepChange] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for off in range(i2 - i1):
                ia, ib = i1 + off, j1 + off
                steps.append(_pair_step(a.interactions[ia], b.interactions[ib], ia, ib))
        elif tag == "replace":
            for off in range(i2 - i1):
                ia = i1 + off
                steps.append(_removed_step(a.interactions[ia], ia))
            for off in range(j2 - j1):
                ib = j1 + off
                steps.append(_added_step(b.interactions[ib], ib))
        elif tag == "delete":
            for ia in range(i1, i2):
                steps.append(_removed_step(a.interactions[ia], ia))
        elif tag == "insert":
            for ib in range(j1, j2):
                steps.append(_added_step(b.interactions[ib], ib))

    usage_a = cassette_usage(a)
    usage_b = cassette_usage(b)
    return RunDiff(
        steps=steps,
        model_a=a.meta.get("model") if a.meta else None,
        model_b=b.meta.get("model") if b.meta else None,
        tokens_a=usage_a.total_tokens,
        tokens_b=usage_b.total_tokens,
        cost_a=usage_a.cost_usd,
        cost_b=usage_b.cost_usd,
        latency_a=_total_latency(a),
        latency_b=_total_latency(b),
        output_changed=final_output(a) != final_output(b),
        tool_names_a=_tool_names(a),
        tool_names_b=_tool_names(b),
    )


def _pair_step(ia: Interaction, ib: Interaction, idx_a: int, idx_b: int) -> StepChange:
    req_diffs = diff_fields(ia.request, ib.request)
    resp_diffs = diff_fields(ia.response, ib.response)
    status = "unchanged" if not req_diffs and not resp_diffs else "changed"
    return StepChange(
        status=status,
        index_a=idx_a,
        index_b=idx_b,
        kind=ib.kind,
        boundary=ib.boundary or ib.kind,
        request_diffs=req_diffs,
        response_diffs=resp_diffs,
    )


def _added_step(ib: Interaction, idx_b: int) -> StepChange:
    return StepChange("added", None, idx_b, ib.kind, ib.boundary or ib.kind)


def _removed_step(ia: Interaction, idx_a: int) -> StepChange:
    return StepChange("removed", idx_a, None, ia.kind, ia.boundary or ia.kind)


# --------------------------------------------------------------------------- #
# Prompt diff
# --------------------------------------------------------------------------- #


def extract_prompts(cassette: Cassette) -> str:
    """Concatenate system/user prompts across all llm interactions, in order."""

    chunks: list[str] = []
    for i, interaction in enumerate(cassette.interactions):
        if interaction.kind != "llm":
            continue
        messages = (interaction.request or {}).get("messages")
        if not isinstance(messages, list):
            continue
        chunks.append(f"# llm call {i}")
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role", "?")
            content = msg.get("content", "")
            chunks.append(f"[{role}] {_as_text(content)}")
    return "\n".join(chunks)


def prompt_diff(a: Cassette, b: Cassette, *, context: int = 3) -> str:
    """Return a git-style unified diff of prompts between two cassettes."""

    lines_a = extract_prompts(a).splitlines(keepends=True)
    lines_b = extract_prompts(b).splitlines(keepends=True)
    diff = difflib.unified_diff(
        lines_a, lines_b, fromfile="a/prompts", tofile="b/prompts", n=context
    )
    text = "".join(diff)
    return text if text else "(no prompt differences)"


# --------------------------------------------------------------------------- #
# State / memory diff
# --------------------------------------------------------------------------- #


@dataclass
class StateDiff:
    added: dict[str, Any] = field(default_factory=dict)
    removed: dict[str, Any] = field(default_factory=dict)
    changed: dict[str, tuple[Any, Any]] = field(default_factory=dict)

    @property
    def empty(self) -> bool:
        return not (self.added or self.removed or self.changed)

    def render(self) -> str:
        if self.empty:
            return "(no state/memory differences)"
        lines = ["State/memory diff", "================="]
        for key, value in sorted(self.added.items()):
            lines.append(f"+ {key}: {_short(value)}")
        for key, value in sorted(self.removed.items()):
            lines.append(f"- {key}: {_short(value)}")
        for key, (old, new) in sorted(self.changed.items()):
            lines.append(f"~ {key}: {_short(old)} -> {_short(new)}")
        return "\n".join(lines)


def _collect_state(cassette: Cassette) -> dict[str, Any]:
    """Merge all memory_write snapshots into a final key/value state."""

    state: dict[str, Any] = {}
    for interaction in cassette.interactions:
        if interaction.kind != "memory_write":
            continue
        snapshot = interaction.response
        if isinstance(snapshot, dict):
            state.update(snapshot)
        else:
            name = interaction.boundary or f"write_{interaction.index}"
            state[name] = snapshot
    return state


def state_diff(a: Cassette, b: Cassette) -> StateDiff:
    """Compare ``memory_write`` snapshots between two runs (keys add/remove/change)."""

    state_a = _collect_state(a)
    state_b = _collect_state(b)
    result = StateDiff()
    for key in state_b.keys() - state_a.keys():
        result.added[key] = state_b[key]
    for key in state_a.keys() - state_b.keys():
        result.removed[key] = state_a[key]
    for key in state_a.keys() & state_b.keys():
        if state_a[key] != state_b[key]:
            result.changed[key] = (state_a[key], state_b[key])
    return result


# --------------------------------------------------------------------------- #
# Output diff
# --------------------------------------------------------------------------- #


@dataclass
class OutputDiff:
    output_a: Any
    output_b: Any
    field_diffs: list[FieldDiff]

    @property
    def changed(self) -> bool:
        return self.output_a != self.output_b

    def render(self) -> str:
        if not self.changed:
            return "(final outputs are identical)"
        lines = ["Output diff", "==========="]
        if self.field_diffs:
            for d in self.field_diffs:
                lines.append(f"  {d.path}: {d.expected!r} -> {d.received!r}")
        else:
            lines.append(f"  a: {_short(self.output_a)}")
            lines.append(f"  b: {_short(self.output_b)}")
        return "\n".join(lines)


def output_diff(a: Cassette, b: Cassette) -> OutputDiff:
    out_a = final_output(a)
    out_b = final_output(b)
    return OutputDiff(out_a, out_b, diff_fields(out_a, out_b))


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _as_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, dict):
                parts.append(str(part.get("text", part.get("content", part))))
            else:
                parts.append(str(part))
        return " ".join(parts)
    return json.dumps(content, default=str)


def _short(value: Any, limit: int = 80) -> str:
    text = json.dumps(value, default=str) if not isinstance(value, str) else value
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _fmt_cost(cost: float | None) -> str:
    return "n/a" if cost is None else f"${cost:.6f}"
