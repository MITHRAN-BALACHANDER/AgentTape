"""Request canonicalization and deterministic hashing.

To decide whether an incoming request equals a recorded one, AgentTape reduces each
request to a stable canonical form and hashes it. Canonicalization:

* drops *volatile* fields (timestamps, request ids, nonces, …) by key name,
* recurses through nested mappings and sequences,
* and is rendered to JSON with sorted keys and compact separators so the hash is
  deterministic across machines and Python versions.

The resulting ``sha256:...`` string is the cassette ``match_key``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Conservative defaults: only fields that are almost always non-semantic.
DEFAULT_VOLATILE_FIELDS: tuple[str, ...] = (
    "timestamp",
    "created",
    "created_at",
    "request_id",
    "x-request-id",
    "x-amzn-requestid",
    "nonce",
    "trace_id",
    "traceparent",
    "date",
    "user-agent",
    "idempotency-key",
)


def canonicalize(
    obj: Any,
    ignore_fields: Iterable[str] = DEFAULT_VOLATILE_FIELDS,
    *,
    normalize_whitespace: bool = False,
) -> Any:
    """Return a canonical copy of ``obj`` with volatile fields removed.

    Args:
        obj: The request structure (JSON-like).
        ignore_fields: Field names (case-insensitive) to drop wherever they occur.
        normalize_whitespace: If true, strip leading/trailing whitespace on string
            scalars. Off by default because prompt whitespace can be semantically
            meaningful.
    """

    ignore = {f.lower() for f in ignore_fields}
    return _canon(obj, ignore, normalize_whitespace)


# Internal markers that must never participate in matching. ``raw_b64`` is the
# byte-faithful body copy the HTTP adapter stores for reconstruction only; including
# it in the hash would defeat the structural (whitespace/key-order tolerant) match.
_RESERVED_IGNORE = frozenset({"raw_b64"})


def _canon(obj: Any, ignore: set[str], strip_ws: bool) -> Any:
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            if isinstance(k, str) and (k.lower() in ignore or k in _RESERVED_IGNORE):
                continue
            if isinstance(k, str) and k.lower() == "url" and isinstance(v, str) and "://" in v:
                out[str(k)] = _canon_url(v, ignore)
                continue
            out[str(k)] = _canon(v, ignore, strip_ws)
        return out
    if isinstance(obj, (list, tuple)):
        return [_canon(item, ignore, strip_ws) for item in obj]
    if isinstance(obj, str) and strip_ws:
        return obj.strip()
    return obj


def _canon_url(url: str, ignore: set[str]) -> str:
    """Drop volatile query parameters from a URL so matching stays stable.

    SDKs routinely append a timestamp / nonce / cache-buster / request signature to
    the query string (``?timestamp=…``, presigned URLs). Those live inside the URL
    *string*, so the by-key volatile-field drop never reaches them and two otherwise
    identical calls hash differently. Here we parse the query and remove any
    parameter whose name is in the ignore set. When nothing is dropped the original
    string is returned verbatim (so ``exact`` matching is unaffected and the URL is
    not re-encoded).
    """

    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if not parts.query:
        return url
    all_pairs = parse_qsl(parts.query, keep_blank_values=True)
    kept = [(k, v) for k, v in all_pairs if k.lower() not in ignore]
    if len(kept) == len(all_pairs):
        return url
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), parts.fragment))


def stable_json(obj: Any) -> str:
    """Serialise ``obj`` to deterministic JSON (sorted keys, compact separators)."""

    return json.dumps(
        obj,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=_json_default,
    )


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (set, frozenset)):
        return sorted(obj, key=repr)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if hasattr(obj, "model_dump"):  # pydantic-style objects
        try:
            return obj.model_dump()
        except Exception:  # pragma: no cover - defensive
            pass
    if hasattr(obj, "__dict__"):
        return {k: v for k, v in vars(obj).items() if not k.startswith("_")}
    return str(obj)


def compute_match_key(
    obj: Any,
    ignore_fields: Iterable[str] = DEFAULT_VOLATILE_FIELDS,
    *,
    normalize_whitespace: bool = False,
) -> str:
    """Return the ``sha256:...`` match key for a request structure."""

    canon = canonicalize(obj, ignore_fields, normalize_whitespace=normalize_whitespace)
    digest = hashlib.sha256(stable_json(canon).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def content_hash(data: bytes) -> str:
    """Return a ``sha256:...`` hash for raw asset bytes."""

    return "sha256:" + hashlib.sha256(data).hexdigest()
