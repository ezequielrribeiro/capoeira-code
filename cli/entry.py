"""Entry point `capoeira`: única interface é a TUI interativa.

`capoeira [PATH] [OPÇÕES]` abre o modo agente na raiz do projeto
(PATH padrão: diretório atual). Não há subcomandos/CLI one-shot.
"""

import os
import sys

from .llm_client import DEFAULT_BASE_URL, DEFAULT_MODEL, DEFAULT_TIMEOUT

USAGE = """Uso: capoeira [PATH] [OPÇÕES]

Inicia a interface interativa (TUI) na raiz do projeto (padrão: diretório atual).

OPÇÕES:
  --project NOME    premissas projects/<nome>.yaml do diretório de config
  --readonly        somente leitura (bloqueia execução/escrita)
  --model M         modelo/perfil do backend            (padrão: gemini-pro)
  --base-url URL    base URL compatível com Ollama      (padrão: http://127.0.0.1:8765)
  --timeout SEG     timeout por chamada ao backend      (padrão: 180)
  -h, --help        mostra esta ajuda
"""

_VALUE_FLAGS = {"--project", "--model", "--base-url", "--timeout"}


def main(argv=None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    path, flags = _split_path_and_flags(args)

    if any(flag in ("-h", "--help") for flag in flags):
        print(USAGE)
        return

    kwargs = _parse_flags(path or os.getcwd(), flags)
    from .tui.app import run_tui

    run_tui(**kwargs)


def _split_path_and_flags(args: list[str]) -> tuple[str | None, list[str]]:
    """Separa o primeiro token posicional (PATH) das opções (com seus valores)."""
    path = None
    flags: list[str] = []
    i = 0
    while i < len(args):
        token = args[i]
        if token.startswith("-"):
            flags.append(token)
            if token in _VALUE_FLAGS and i + 1 < len(args):
                flags.append(args[i + 1])
                i += 2
                continue
            i += 1
        else:
            if path is None:
                path = token
            i += 1
    return path, flags


def _parse_flags(path: str, flags: list[str]) -> dict:
    kwargs: dict = {
        "project_path": path,
        "base_url": DEFAULT_BASE_URL,
        "model": DEFAULT_MODEL,
        "timeout": DEFAULT_TIMEOUT,
        "readonly": False,
    }
    i = 0
    while i < len(flags):
        flag = flags[i]
        if flag == "--project" and i + 1 < len(flags):
            kwargs["project"] = flags[i + 1]
            i += 2
        elif flag == "--readonly":
            kwargs["readonly"] = True
            i += 1
        elif flag == "--model" and i + 1 < len(flags):
            kwargs["model"] = flags[i + 1]
            i += 2
        elif flag == "--base-url" and i + 1 < len(flags):
            kwargs["base_url"] = flags[i + 1]
            i += 2
        elif flag == "--timeout" and i + 1 < len(flags):
            try:
                kwargs["timeout"] = float(flags[i + 1])
            except ValueError:
                pass
            i += 2
        else:
            i += 1
    return kwargs