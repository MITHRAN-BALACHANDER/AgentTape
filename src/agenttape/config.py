"""``agenttape.toml`` discovery and configuration.

Configuration is optional — every setting has a sensible default so AgentTape works
with no config file at all. When present, ``agenttape.toml`` is discovered by
walking up from the current directory (like ``pyproject.toml``).

TOML parsing uses the stdlib :mod:`tomllib` on Python 3.11+; on 3.10 it falls back
to a tiny built-in parser for the small config subset AgentTape uses, keeping the
core dependency-free.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

from .canonical import DEFAULT_VOLATILE_FIELDS
from .errors import ConfigError
from .redaction import RedactionConfig

CONFIG_FILENAME = "agenttape.toml"
VALID_MODES = ("none", "once", "new_episodes", "all", "record")


@dataclass
class Config:
    """Resolved AgentTape configuration."""

    cassette_dir: Path = Path("cassettes")
    default_mode: str = "none"
    default_matchers: tuple[str, ...] = ("ignore_volatile",)
    freeze: tuple[str, ...] = ("clock", "uuid", "random")
    ignore_volatile_fields: tuple[str, ...] = DEFAULT_VOLATILE_FIELDS
    assets_threshold_bytes: int = 4096
    model_override: str | None = None
    format: str = "yaml"
    env_snapshot: tuple[str, ...] = ()
    redact: RedactionConfig = field(default_factory=RedactionConfig)
    source_path: Path | None = None

    @classmethod
    def load(cls, start: Path | None = None) -> Config:
        """Discover and load configuration, returning defaults if none found."""

        path = find_config(start or Path.cwd())
        if path is None:
            return cls()
        return cls.from_file(path)

    @classmethod
    def from_file(cls, path: Path) -> Config:
        data = _load_toml(path)
        base_dir = path.parent
        return cls.from_mapping(data, base_dir=base_dir, source_path=path)

    @classmethod
    def from_mapping(
        cls,
        data: dict[str, Any],
        *,
        base_dir: Path | None = None,
        source_path: Path | None = None,
    ) -> Config:
        base_dir = base_dir or Path.cwd()
        cfg = cls(source_path=source_path)

        cassette_dir = data.get("cassette_dir")
        if cassette_dir:
            cd = Path(cassette_dir)
            cfg.cassette_dir = cd if cd.is_absolute() else base_dir / cd
        else:
            cfg.cassette_dir = base_dir / "cassettes"

        mode = data.get("default_mode")
        if mode is not None:
            if mode not in VALID_MODES:
                raise ConfigError(f"default_mode={mode!r} is invalid; choose one of {VALID_MODES}.")
            cfg.default_mode = mode

        if "default_matchers" in data:
            cfg.default_matchers = tuple(data["default_matchers"])
        if "freeze" in data:
            cfg.freeze = tuple(data["freeze"])
        if "ignore_volatile_fields" in data:
            cfg.ignore_volatile_fields = tuple(data["ignore_volatile_fields"])
        if "assets_threshold_bytes" in data:
            cfg.assets_threshold_bytes = int(data["assets_threshold_bytes"])
        if data.get("model_override"):
            cfg.model_override = str(data["model_override"])
        if "format" in data:
            fmt = str(data["format"]).lower()
            if fmt not in ("yaml", "json"):
                raise ConfigError(f"format={fmt!r} must be 'yaml' or 'json'.")
            cfg.format = fmt
        if "env_snapshot" in data:
            cfg.env_snapshot = tuple(str(v) for v in data["env_snapshot"])

        redact_data = data.get("redact")
        if isinstance(redact_data, dict):
            cfg.redact = RedactionConfig.from_mapping(redact_data)
        return cfg


def find_config(start: Path) -> Path | None:
    """Walk up from ``start`` looking for ``agenttape.toml``."""

    start = start.resolve()
    for directory in (start, *start.parents):
        candidate = directory / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
    return None


# --------------------------------------------------------------------------- #
# TOML loading
# --------------------------------------------------------------------------- #


def _load_toml(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    try:
        import tomllib

        return cast("dict[str, Any]", tomllib.loads(raw.decode("utf-8")))
    except ModuleNotFoundError:
        pass
    try:
        import tomli

        return cast("dict[str, Any]", tomli.loads(raw.decode("utf-8")))
    except ModuleNotFoundError:
        pass
    return _MiniToml(raw.decode("utf-8")).parse()


class _MiniToml:
    """A tiny TOML subset parser (fallback for Python 3.10 without ``tomli``).

    Supports top-level keys, ``[table]`` headers, strings, integers, booleans and
    inline arrays of those — which is everything ``agenttape.toml`` needs.
    """

    def __init__(self, text: str) -> None:
        self._text = text

    def parse(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        current = result
        for raw_line in self._text.splitlines():
            line = _strip_toml_comment(raw_line).strip()
            if not line:
                continue
            if line.startswith("[") and line.endswith("]"):
                name = line[1:-1].strip()
                current = result.setdefault(name, {})
                continue
            if "=" not in line:
                raise ConfigError(f"Invalid TOML line: {raw_line!r}")
            key, _, value = line.partition("=")
            current[key.strip()] = _parse_toml_value(value.strip())
        return result


def _strip_toml_comment(line: str) -> str:
    in_str = False
    quote = ""
    for i, ch in enumerate(line):
        if in_str:
            if ch == quote:
                in_str = False
        elif ch in ("'", '"'):
            in_str = True
            quote = ch
        elif ch == "#":
            return line[:i]
    return line


def _parse_toml_value(value: str) -> Any:
    value = value.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_parse_toml_value(part.strip()) for part in _split_array(inner)]
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    if value in ("true", "false"):
        return value == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def _split_array(inner: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    in_str = False
    quote = ""
    buf: list[str] = []
    for ch in inner:
        if in_str:
            buf.append(ch)
            if ch == quote:
                in_str = False
        elif ch in ("'", '"'):
            in_str = True
            quote = ch
            buf.append(ch)
        elif ch in "[":
            depth += 1
            buf.append(ch)
        elif ch in "]":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if "".join(buf).strip():
        parts.append("".join(buf))
    return parts
