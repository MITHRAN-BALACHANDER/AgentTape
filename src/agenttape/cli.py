"""The ``agenttape`` command-line interface.

Commands: init · record · replay · inspect · timeline · diff · redact · validate ·
export · view · rm. Everything operates on local files only — no network, no server.
"""

from __future__ import annotations

import argparse
import importlib
import shutil
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import __version__
from . import cassette as cassette_io
from .assets import assets_dir_for
from .config import Config
from .redaction import Redactor


def _force_utf8() -> None:
    # Cassettes and renderings use Unicode (waterfalls, arrows, ✓). On Windows the
    # console defaults to cp1252 and would raise UnicodeEncodeError; reconfigure to
    # UTF-8 with replacement so output never crashes.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:
            pass


def main(argv: Sequence[str] | None = None) -> int:
    _force_utf8()
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 1
    try:
        return int(args.func(args) or 0)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # surface a clean message, full trace only with -v
        if getattr(args, "verbose", False):
            raise
        print(f"error: {exc}", file=sys.stderr)
        return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agenttape", description="Deterministic record/replay for AI agents."
    )
    parser.add_argument("--version", action="version", version=f"agenttape {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="show full tracebacks")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("init", help="scaffold agenttape.toml and the cassette dir")
    p.add_argument("--dir", default=".", help="project directory (default: .)")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("record", help="run an agent entrypoint (module:function) in record mode")
    p.add_argument("entrypoint", help="entrypoint as module:function")
    p.add_argument("cassette", help="cassette name")
    p.add_argument("--mode", default="record", help="record mode (default: record)")
    p.set_defaults(func=cmd_record)

    p = sub.add_parser("replay", help="replay a cassette and print the reconstructed timeline")
    p.add_argument("cassette")
    p.set_defaults(func=cmd_replay)

    p = sub.add_parser("inspect", help="pretty-print interactions, latency, tokens, cost")
    p.add_argument("cassette")
    p.add_argument("--full", action="store_true", help="do not truncate payloads")
    p.set_defaults(func=cmd_inspect)

    p = sub.add_parser("timeline", help="render the run as an ASCII waterfall")
    p.add_argument("cassette")
    p.set_defaults(func=cmd_timeline)

    p = sub.add_parser("diff", help="structured diff of two cassettes")
    p.add_argument("a")
    p.add_argument("b")
    p.add_argument(
        "--type",
        choices=["run", "prompt", "state", "output", "all"],
        default="run",
        help="which diff to show (default: run)",
    )
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("redact", help="re-run redaction over an existing cassette")
    p.add_argument("cassette")
    p.set_defaults(func=cmd_redact)

    p = sub.add_parser("validate", help="schema + determinism + leaked-secret lint")
    p.add_argument("cassette")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("export", help="export a cassette to json or otel")
    p.add_argument("cassette")
    p.add_argument("--format", choices=["json", "otel"], default="json")
    p.add_argument("-o", "--output", help="write to a file instead of stdout")
    p.set_defaults(func=cmd_export)

    p = sub.add_parser("view", help="generate a self-contained static HTML viewer")
    p.add_argument("cassette")
    p.add_argument("second", nargs="?", help="optional second cassette for a diff view")
    p.add_argument("-o", "--output", help="output HTML path")
    p.set_defaults(func=cmd_view)

    p = sub.add_parser("rm", help="delete a cassette and its assets")
    p.add_argument("cassette")
    p.add_argument("-f", "--force", action="store_true")
    p.set_defaults(func=cmd_rm)

    return parser


# --------------------------------------------------------------------------- #
# Path resolution
# --------------------------------------------------------------------------- #


def _config() -> Config:
    return Config.load()


def _resolve(arg: str, config: Config | None = None) -> Path:
    p = Path(arg)
    if p.exists():
        return p
    config = config or _config()
    resolved = cassette_io.resolve_path(arg, config.cassette_dir, config.format)
    if resolved.exists():
        return resolved
    raise FileNotFoundError(
        f"cassette not found: {arg} (looked in {config.cassette_dir}). "
        f"Record it first or check cassette_dir."
    )


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #


def cmd_init(args: Any) -> int:
    base = Path(args.dir).resolve()
    toml_path = base / "agenttape.toml"
    cassettes = base / "cassettes"
    cassettes.mkdir(parents=True, exist_ok=True)
    if toml_path.exists():
        print(f"agenttape.toml already exists at {toml_path}")
    else:
        toml_path.write_text(_DEFAULT_TOML, encoding="utf-8")
        print(f"created {toml_path}")
    print(f"cassette dir: {cassettes}")
    return 0


def cmd_record(args: Any) -> int:
    from .recorder import use_cassette

    sys.path.insert(0, str(Path.cwd()))
    module_name, _, func_name = args.entrypoint.partition(":")
    if not func_name:
        raise ValueError("entrypoint must be 'module:function'")
    module = importlib.import_module(module_name)
    fn = getattr(module, func_name)
    with use_cassette(args.cassette, mode=args.mode):
        result = fn()
    print(f"recorded {args.cassette} (mode={args.mode})")
    if result is not None:
        print(f"entrypoint returned: {result!r}")
    return 0


def cmd_replay(args: Any) -> int:
    from .timeline import render_timeline

    path = _resolve(args.cassette)
    cassette = cassette_io.read_cassette(path)
    print(render_timeline(cassette, str(path)))
    print("\nReconstructed (no external calls were made):")
    for interaction in cassette.interactions:
        name = interaction.boundary or interaction.kind
        outcome = "error" if interaction.error else "ok"
        print(f"  #{interaction.index} {interaction.kind}:{name} -> {outcome}")
    return 0


def cmd_inspect(args: Any) -> int:
    from .timeline import render_inspect

    path = _resolve(args.cassette)
    cassette = cassette_io.read_cassette(path)
    print(render_inspect(cassette, str(path), full=args.full))
    return 0


def cmd_timeline(args: Any) -> int:
    from .timeline import render_timeline

    path = _resolve(args.cassette)
    cassette = cassette_io.read_cassette(path)
    print(render_timeline(cassette, str(path)))
    return 0


def cmd_diff(args: Any) -> int:
    from .diff import output_diff, prompt_diff, run_diff, state_diff

    a = cassette_io.read_cassette(_resolve(args.a))
    b = cassette_io.read_cassette(_resolve(args.b))
    want = args.type
    if want in ("run", "all"):
        print(run_diff(a, b).render())
    if want in ("prompt", "all"):
        print("\n" + prompt_diff(a, b))
    if want in ("state", "all"):
        print("\n" + state_diff(a, b).render())
    if want in ("output", "all"):
        print("\n" + output_diff(a, b).render())
    return 0


def cmd_redact(args: Any) -> int:
    path = _resolve(args.cassette)
    config = _config()
    cassette = cassette_io.read_cassette(path)
    cassette_io.write_cassette(
        cassette,
        path,
        redactor=Redactor(config.redact),
        assets_threshold=config.assets_threshold_bytes,
    )
    print(f"re-redacted {path}")
    return 0


def cmd_validate(args: Any) -> int:
    from .validate import validate_cassette

    path = _resolve(args.cassette)
    report = validate_cassette(path)
    print(report.render())
    return 0 if report.ok else 1


def cmd_export(args: Any) -> int:
    from .export import to_json, to_otel_json

    path = _resolve(args.cassette)
    cassette = cassette_io.read_cassette(path)
    text = to_otel_json(cassette) if args.format == "otel" else to_json(cassette)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"wrote {args.output}")
    else:
        print(text)
    return 0


def cmd_view(args: Any) -> int:
    from .viewer import write_html

    path = _resolve(args.cassette)
    cassette = cassette_io.read_cassette(path)
    second = cassette_io.read_cassette(_resolve(args.second)) if args.second else None
    out = args.output or str(path.with_suffix(".html"))
    write_html(cassette, out, title=path.stem, second=second)
    print(f"wrote {out}  (open with file://)")
    return 0


def cmd_rm(args: Any) -> int:
    path = _resolve(args.cassette)
    if not args.force:
        resp = input(f"delete {path} and its assets? [y/N] ").strip().lower()
        if resp not in ("y", "yes"):
            print("aborted")
            return 1
    path.unlink()
    assets = assets_dir_for(path)
    if assets.exists():
        shutil.rmtree(assets)
    derived = path.with_suffix("").with_name(path.stem + ".derived" + path.suffix)
    if derived.exists():
        derived.unlink()
    print(f"removed {path}")
    return 0


_DEFAULT_TOML = """# AgentTape configuration
cassette_dir = "cassettes"
default_mode = "none"            # offline + deterministic by default (CI-friendly)
default_matchers = ["ignore_volatile"]
freeze = ["clock", "uuid", "random"]
assets_threshold_bytes = 4096

# Fields dropped before computing the match key (volatile / non-semantic).
ignore_volatile_fields = ["timestamp", "request_id", "x-request-id", "date", "nonce"]

# Optionally pin a model for replay-with-different-model experiments.
# model_override = "gpt-4o"

[redact]
# Extra field names whose values are fully redacted (case-insensitive).
denylist = []
# Extra regexes redacted wherever they appear in string values.
regexes = []
redact_emails = true
"""


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
