"""Cassette validation: schema checks + determinism lint + leaked-secret scan."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import cassette as cassette_io
from .canonical import DEFAULT_VOLATILE_FIELDS
from .redaction import DEFAULT_VALUE_REGEXES, EMAIL_REGEX
from .schema import KINDS, SUPPORTED_VERSIONS


@dataclass
class ValidationReport:
    path: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def render(self) -> str:
        lines = [f"Validating {self.path}"]
        if not self.errors and not self.warnings:
            lines.append("  ✓ valid — no issues found")
            return "\n".join(lines)
        for err in self.errors:
            lines.append(f"  ✗ ERROR: {err}")
        for warn in self.warnings:
            lines.append(f"  ⚠ WARN:  {warn}")
        verdict = "valid (with warnings)" if self.ok else "INVALID"
        lines.append(f"  → {verdict}")
        return "\n".join(lines)


_SECRET_PATTERNS = [re.compile(p) for p in (*DEFAULT_VALUE_REGEXES, EMAIL_REGEX)]
_VOLATILE = {f.lower() for f in DEFAULT_VOLATILE_FIELDS}


def validate_cassette(path: Path) -> ValidationReport:
    """Validate schema, scan for determinism risks and leaked secrets."""

    report = ValidationReport(path=str(path))

    try:
        raw = cassette_io.load_raw(path)
    except Exception as exc:
        report.errors.append(f"could not load cassette: {exc}")
        return report

    version = str(raw.get("version", ""))
    if version not in SUPPORTED_VERSIONS:
        report.errors.append(
            f"unsupported schema version {version!r} (supported: {sorted(SUPPORTED_VERSIONS)}). "
            f"Migration hint: re-record with `agenttape record` or `--agenttape-record`."
        )

    interactions = raw.get("interactions")
    if not isinstance(interactions, list):
        report.errors.append("'interactions' missing or not a list")
        interactions = []

    for i, interaction in enumerate(interactions):
        _validate_interaction(i, interaction, report)

    meta = raw.get("meta") or {}
    if "freeze" not in meta:
        report.warnings.append(
            "no freeze settings recorded; clock/uuid/random determinism is not "
            "guaranteed across runs. Record with freeze enabled."
        )

    _scan_secrets(raw, report, path)
    return report


def _validate_interaction(i: int, interaction: Any, report: ValidationReport) -> None:
    if not isinstance(interaction, dict):
        report.errors.append(f"interaction #{i} is not a mapping")
        return
    kind = interaction.get("kind")
    if kind not in KINDS:
        report.errors.append(f"interaction #{i} has unknown kind {kind!r}")
    if "request" not in interaction:
        report.warnings.append(f"interaction #{i} has no request")
    if "response" not in interaction and "error" not in interaction:
        report.errors.append(f"interaction #{i} has neither response nor error")
    if not interaction.get("match_key"):
        report.warnings.append(f"interaction #{i} has no match_key")
    _scan_volatile(i, interaction.get("request"), report)


def _scan_volatile(i: int, request: Any, report: ValidationReport, prefix: str = "") -> None:
    if isinstance(request, dict):
        for key, value in request.items():
            if str(key).lower() in _VOLATILE:
                report.warnings.append(
                    f"interaction #{i} request has volatile field {prefix}{key!r}; "
                    f"add it to ignore_volatile_fields to keep matching stable."
                )
            _scan_volatile(i, value, report, prefix=f"{prefix}{key}.")
    elif isinstance(request, list):
        for item in request:
            _scan_volatile(i, item, report, prefix=prefix)


def _scan_secrets(raw: dict[str, Any], report: ValidationReport, path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    seen: set[str] = set()
    for pattern in _SECRET_PATTERNS:
        for match in pattern.findall(text):
            snippet = match if isinstance(match, str) else match[0]
            if snippet in seen:
                continue
            seen.add(snippet)
            report.errors.append(
                f"possible leaked secret/PII matching /{pattern.pattern}/: "
                f"{snippet[:12]}…  Run `agenttape redact {path}` to scrub it."
            )
