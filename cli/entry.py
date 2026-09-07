"""Entry point `capoeira`: PATH (ou cwd) abre a TUI; subcomandos seguem o Click."""

import os
import sys

from .llm_client import DEFAULT_BASE_URL, DEFAULT_MODEL, DEFAULT_TIMEOUT

SUBCOMMANDS = {"run", "refactor", "generate", "explain", "deps", "ask", "tui"}


def main(argv=None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)

    if args and (args[0] in SUBCOMMANDS or args[0].startswith("-")):
        from .main import cli

        cli()
        return

    path = args[0] if args else os.getcwd()
    kwargs = _parse_flags(path, args[1:])
    from .tui.app import run_tui

    run_tui(**kwargs)


def _parse_flags(path: str, rest: list[str]) -> dict:
    kwargs: dict = {"project_path": path, "base_url": DEFAULT_BASE_URL, "model": DEFAULT_MODEL, "timeout": DEFAULT_TIMEOUT}
    i = 0
    while i < len(rest):
        arg = rest[i]
        if arg == "--project" and i + 1 < len(rest):
            kwargs["project"] = rest[i + 1]
            i += 2
        elif arg == "--readonly":
            kwargs["readonly"] = True
            i += 1
        elif arg == "--model" and i + 1 < len(rest):
            kwargs["model"] = rest[i + 1]
            i += 2
        elif arg == "--base-url" and i + 1 < len(rest):
            kwargs["base_url"] = rest[i + 1]
            i += 2
        elif arg == "--timeout" and i + 1 < len(rest):
            try:
                kwargs["timeout"] = float(rest[i + 1])
            except ValueError:
                pass
            i += 2
        else:
            i += 1
    return kwargs