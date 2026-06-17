"""Reading and writing cassette files (YAML default, JSON supported).

This module ties together the schema, redaction, the assets sidecar and the YAML
subset I/O. The write pipeline is intentionally ordered:

    cassette -> dict -> redact -> externalize large assets -> serialise -> disk

so that secrets are redacted *before* anything is written and large payloads land
in the sibling assets directory rather than the cassette body.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import yaml_io
from .assets import DEFAULT_THRESHOLD_BYTES, assets_dir_for, externalize, inline
from .errors import CassetteCorruptError, CassetteNotFoundError
from .redaction import Redactor
from .schema import Cassette

YAML_SUFFIXES = (".yaml", ".yml")
JSON_SUFFIXES = (".json",)


def detect_format(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in JSON_SUFFIXES:
        return "json"
    return "yaml"


def resolve_path(name_or_path: str | Path, cassette_dir: Path, fmt: str = "yaml") -> Path:
    """Resolve a cassette name (``"hello"``) or path to a concrete file path."""

    p = Path(name_or_path)
    if p.suffix.lower() in (*YAML_SUFFIXES, *JSON_SUFFIXES):
        # Explicit file path.
        return p if p.is_absolute() else (cassette_dir / p if not p.exists() else p)
    # Bare name: look for an existing file first, else default to the chosen format.
    for suffix in (*YAML_SUFFIXES, *JSON_SUFFIXES):
        candidate = cassette_dir / f"{p.name}{suffix}"
        if candidate.exists():
            return candidate
    default_suffix = ".json" if fmt == "json" else ".yaml"
    return cassette_dir / f"{p.name}{default_suffix}"


def write_cassette(
    cassette: Cassette,
    path: Path,
    *,
    fmt: str | None = None,
    redactor: Redactor | None = None,
    assets_threshold: int = DEFAULT_THRESHOLD_BYTES,
) -> Path:
    """Serialise ``cassette`` to ``path``, redacting and externalizing as needed."""

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fmt = fmt or detect_format(path)

    data: dict[str, Any] = cassette.to_dict()
    if redactor is not None:
        data = redactor.redact(data)

    assets_dir = assets_dir_for(path)
    data = externalize(data, assets_dir, threshold=assets_threshold)

    if fmt == "json":
        text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    else:
        text = yaml_io.dump(data)
    path.write_text(text, encoding="utf-8")
    return path


def read_cassette(path: Path) -> Cassette:
    """Load a cassette from ``path``, resolving asset references."""

    path = Path(path)
    if not path.exists():
        raise CassetteNotFoundError(
            f"Cassette not found: {path}. Record it first (mode='record' or "
            f"--agenttape-record) or check the cassette_dir setting."
        )
    text = path.read_text(encoding="utf-8")
    fmt = detect_format(path)
    try:
        data = json.loads(text) if fmt == "json" else yaml_io.load(text)
    except Exception as exc:
        raise CassetteCorruptError(
            f"Could not parse cassette {path}: {exc}. The file may be corrupt or "
            f"hand-edited into invalid {fmt.upper()}."
        ) from exc

    if data is None:
        raise CassetteCorruptError(f"Cassette {path} is empty.")
    if not isinstance(data, dict):
        raise CassetteCorruptError(
            f"Cassette {path} root must be a mapping, got {type(data).__name__}."
        )

    assets_dir = assets_dir_for(path)
    # strict: a missing asset must fail loudly on the replay path rather than
    # silently substituting the short preview for the real recorded payload.
    data = inline(data, assets_dir, strict=True)
    cassette = Cassette.from_dict(data)
    return cassette


def load_raw(path: Path) -> dict[str, Any]:
    """Load a cassette's raw dict form *without* resolving assets (for tooling)."""

    path = Path(path)
    text = path.read_text(encoding="utf-8")
    fmt = detect_format(path)
    data: Any = json.loads(text) if fmt == "json" else yaml_io.load(text)
    if not isinstance(data, dict):
        raise CassetteCorruptError(f"Cassette {path} root must be a mapping.")
    return data
