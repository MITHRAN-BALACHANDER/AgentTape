"""Asset sidecar handling for large payloads.

Big documents, images and base64 blobs would bloat a cassette and ruin its diffs.
Instead, any string/bytes value larger than a threshold is written to a sibling
``<cassette>.assets/`` directory, named by its content hash, and replaced inline
with a small reference. On load the references are resolved back to their content.

A reference looks like::

    {"__agenttape_asset__": "sha256:ab12…", "encoding": "utf-8", "size": 40213,
     "preview": "The quick brown fox…"}
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from .canonical import content_hash

ASSET_MARKER = "__agenttape_asset__"
DEFAULT_THRESHOLD_BYTES = 4096
_PREVIEW_LEN = 64


def is_asset_ref(obj: Any) -> bool:
    return isinstance(obj, dict) and ASSET_MARKER in obj


def externalize(obj: Any, assets_dir: Path, threshold: int = DEFAULT_THRESHOLD_BYTES) -> Any:
    """Return a copy of ``obj`` with large payloads replaced by asset references.

    Writes any externalized content into ``assets_dir`` (created on demand).
    """

    writes: dict[str, bytes] = {}
    result = _externalize(obj, threshold, writes)
    if writes:
        assets_dir.mkdir(parents=True, exist_ok=True)
        for name, data in writes.items():
            target = assets_dir / name
            if not target.exists():
                target.write_bytes(data)
    return result


def _externalize(obj: Any, threshold: int, writes: dict[str, bytes]) -> Any:
    if isinstance(obj, dict):
        return {k: _externalize(v, threshold, writes) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_externalize(v, threshold, writes) for v in obj]
    if isinstance(obj, str):
        encoded = obj.encode("utf-8")
        if len(encoded) > threshold:
            return _make_ref(encoded, "utf-8", obj[:_PREVIEW_LEN], writes)
        return obj
    if isinstance(obj, bytes):
        if len(obj) > threshold:
            preview = obj[:_PREVIEW_LEN].decode("utf-8", errors="replace")
            return _make_ref(obj, "base64", preview, writes)
        return base64.b64encode(obj).decode("ascii")
    return obj


def _make_ref(data: bytes, encoding: str, preview: str, writes: dict[str, bytes]) -> dict[str, Any]:
    digest = content_hash(data)
    name = digest.replace("sha256:", "sha256-")
    writes[name] = data
    return {
        ASSET_MARKER: digest,
        "encoding": encoding,
        "size": len(data),
        "preview": preview,
    }


def inline(obj: Any, assets_dir: Path) -> Any:
    """Return a copy of ``obj`` with asset references resolved to their content."""

    if is_asset_ref(obj):
        return _resolve_ref(obj, assets_dir)
    if isinstance(obj, dict):
        return {k: inline(v, assets_dir) for k, v in obj.items()}
    if isinstance(obj, list):
        return [inline(v, assets_dir) for v in obj]
    return obj


def _resolve_ref(ref: dict[str, Any], assets_dir: Path) -> Any:
    digest = str(ref[ASSET_MARKER])
    name = digest.replace("sha256:", "sha256-")
    path = assets_dir / name
    if not path.exists():
        # Asset missing: fall back to the preview so replay still produces *something*
        # recognisable rather than crashing. Validation flags this separately.
        return ref.get("preview", "")
    data = path.read_bytes()
    encoding = ref.get("encoding", "utf-8")
    if encoding == "base64":
        return data
    return data.decode("utf-8")


def assets_dir_for(cassette_path: Path) -> Path:
    """Return the sibling assets directory for a cassette path."""

    return cassette_path.with_suffix("").with_name(cassette_path.stem + ".assets")
