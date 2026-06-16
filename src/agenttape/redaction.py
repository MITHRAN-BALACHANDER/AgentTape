"""Record-time redaction of secrets and PII.

Redaction runs *before* a cassette is written to disk, so secrets never touch the
filesystem. It works in two layers:

1. **Denylisted keys** — any mapping key whose (case-insensitive) name matches the
   denylist has its entire value replaced with the placeholder. This covers
   ``Authorization`` headers, ``api_key`` fields, ``password``, ``token`` and so on.
2. **Regex value rules** — every string value is scanned and any substring matching
   a configured pattern (API keys, bearer tokens, emails, …) is replaced.

Both are configurable through ``agenttape.toml`` (``redact.denylist`` /
``redact.regexes``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

PLACEHOLDER = "***REDACTED***"

# Header / field names whose values are always fully redacted (case-insensitive).
DEFAULT_DENYLIST_KEYS: tuple[str, ...] = (
    "authorization",
    "proxy-authorization",
    "api_key",
    "api-key",
    "apikey",
    "x-api-key",
    "openai-api-key",
    "anthropic-api-key",
    "secret",
    "client_secret",
    "password",
    "passwd",
    "token",
    "access_token",
    "refresh_token",
    "id_token",
    "session_token",
    "private_key",
    "secret_key",
    "set-cookie",
    "cookie",
    "x-auth-token",
    "aws_secret_access_key",
)

# Value patterns redacted wherever they appear inside any string.
DEFAULT_VALUE_REGEXES: tuple[str, ...] = (
    r"sk-[A-Za-z0-9_\-]{16,}",  # OpenAI-style secret keys
    r"sk-proj-[A-Za-z0-9_\-]{16,}",  # OpenAI project keys
    r"xox[baprs]-[A-Za-z0-9-]{10,}",  # Slack tokens
    r"gh[pos]_[A-Za-z0-9]{20,}",  # GitHub tokens
    r"AKIA[0-9A-Z]{16}",  # AWS access key id
    r"AIza[0-9A-Za-z_\-]{20,}",  # Google API key
    r"Bearer\s+[A-Za-z0-9._\-]+",  # Bearer tokens
    r"-----BEGIN[A-Z ]+PRIVATE KEY-----[\s\S]+?-----END[A-Z ]+PRIVATE KEY-----",
)

# Optional PII patterns (enabled by default; emails are the common case).
EMAIL_REGEX = r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"


@dataclass
class RedactionConfig:
    """Configuration for the redactor."""

    placeholder: str = PLACEHOLDER
    denylist_keys: tuple[str, ...] = DEFAULT_DENYLIST_KEYS
    value_regexes: tuple[str, ...] = DEFAULT_VALUE_REGEXES
    redact_emails: bool = True
    extra_regexes: tuple[str, ...] = ()
    extra_denylist_keys: tuple[str, ...] = ()
    enabled: bool = True

    @classmethod
    def from_mapping(cls, data: dict[str, Any] | None) -> RedactionConfig:
        if not data:
            return cls()
        extra_keys = tuple(str(k).lower() for k in data.get("denylist", []) or [])
        extra_regexes = tuple(str(r) for r in data.get("regexes", []) or [])
        return cls(
            placeholder=str(data.get("placeholder", PLACEHOLDER)),
            redact_emails=bool(data.get("redact_emails", True)),
            extra_denylist_keys=extra_keys,
            extra_regexes=extra_regexes,
            enabled=bool(data.get("enabled", True)),
        )


class Redactor:
    """Applies redaction recursively to arbitrary JSON-like structures."""

    def __init__(self, config: RedactionConfig | None = None) -> None:
        self.config = config or RedactionConfig()
        self._denylist = {
            k.lower() for k in (*self.config.denylist_keys, *self.config.extra_denylist_keys)
        }
        patterns: list[str] = [*self.config.value_regexes, *self.config.extra_regexes]
        if self.config.redact_emails:
            patterns.append(EMAIL_REGEX)
        # Compile a single alternation for efficiency; longest-match preference via order.
        self._compiled: list[re.Pattern[str]] = []
        for pat in patterns:
            try:
                self._compiled.append(re.compile(pat))
            except re.error:
                # An invalid user-supplied pattern should never break recording.
                continue

    # -- public API -------------------------------------------------------- #

    def redact(self, obj: Any) -> Any:
        """Return a redacted deep copy of ``obj``."""

        if not self.config.enabled:
            return obj
        return self._walk(obj, key=None)

    def redact_string(self, text: str) -> str:
        for pattern in self._compiled:
            text = pattern.sub(self.config.placeholder, text)
        return text

    def is_denylisted(self, key: str) -> bool:
        return key.lower() in self._denylist

    # -- internals --------------------------------------------------------- #

    def _walk(self, obj: Any, key: str | None) -> Any:
        if isinstance(obj, dict):
            result: dict[Any, Any] = {}
            for k, v in obj.items():
                if isinstance(k, str) and self.is_denylisted(k):
                    result[k] = self.config.placeholder
                else:
                    result[k] = self._walk(v, key=k if isinstance(k, str) else None)
            return result
        if isinstance(obj, list):
            return [self._walk(item, key=key) for item in obj]
        if isinstance(obj, tuple):
            return [self._walk(item, key=key) for item in obj]
        if isinstance(obj, str):
            return self.redact_string(obj)
        return obj
