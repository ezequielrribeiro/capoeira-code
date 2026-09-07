"""TUI textual interativa (prompt_toolkit + rich) estilo OpenCode."""

import os

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from rich.console import Console

from ..llm_client import DEFAULT_BASE_URL, DEFAULT_MODEL, DEFAULT_TIMEOUT, LLMClient
from ..instruction.loader import load_instruction_set
from ..project.premises import EMPTY_PREMISES, load_premises, resolve_config_dir
from .agent import AgentOptions, AgentRun
from .scan_artifacts import artifacts_summary, generate_artifacts
from .session import Session, slugify

_HELP = """/help            - esta ajuda
/model M        - troca o modelo (ex.: gemini-pro, qwen2.5-coder)
/base-url URL   - troca a base URL do backend (ex.: http://127.0.0.1:8765)
/premises       - recarrega premissas e specs/skills/prompts do config
/rescan         - regenera os artefatos de scan do projeto
/reset          - apaga a sessão/histórico e rescan
/readonly       - alterna modo somente-leitura (bloqueia execução/escrita)
/quit           - sai da TUI
"""


def run_tui(
    project_path: str | None = None,
    project: str | None = None,
    readonly: bool = False,
    model: str | None = None,
    base_url: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> None:
    console = Console()
    config_dir = resolve_config_dir()
    session = Session(config_dir, project_path or os.getcwd())
    session.ensure()

    premises_name = project or slugify(session.project_path)
    premises = _reload_premises(config_dir, premises_name, console, warn=True)

    instr_set = load_instruction_set(config_dir, premises)
    artifacts = generate_artifacts(session, premises)
    client = LLMClient(
        base_url=base_url or DEFAULT_BASE_URL,
        model=model or DEFAULT_MODEL,
        timeout=timeout,
    )

    options = AgentOptions(
        premises=premises,
        instruction_set=instr_set,
        artifacts_summary=artifacts_summary(artifacts),
        cwd=session.project_path,
        max_turns=20,
        mode="readonly" if readonly else "ask",
        python=getattr(getattr(premises, "rag", None), "python", None),
    )
    agent = AgentRun(session, options, client)

    console.print("[bold]CapoeiraCode[/bold] — modo agente interativo")
    console.print(session.summarize())
    console.print(
        f"Backend: {client.base_url} | Modelo: {client.model} | Projeto: {session.project_path}"
    )
    console.print("Digite um prompt e pressione Enter. /help para comandos.")

    prompt_session = PromptSession(history=InMemoryHistory())

    def ask_user(question: str) -> str:
        return prompt_session.prompt(f"[pergunta] {question}\n> ")

    def ask_permission(description: str) -> str:
        choice = prompt_session.prompt(
            f"[permissão] Executar '{description}'? (y=sim, n=não, a=sempre na sessão) "
        )
        return choice.strip().lower()[:1] or "n"

    while True:
        try:
            text = prompt_session.prompt("capoeira> ")
        except KeyboardInterrupt:
            continue
        except EOFError:
            break
        text = text.strip()
        if not text:
            continue

        if text.startswith("/"):
            if not _handle_slash(
                text, console, session, premises, instr_set, artifacts, client, options, agent,
            ):
                break
            continue

        console.print("[dim]agente em execução... (Ctrl+C interrompe)[/dim]")
        try:
            result = agent.run(text, ask_user=ask_user, ask_permission=ask_permission)
        except KeyboardInterrupt:
            console.print("[yellow]\nInterrompido pelo usuário. O contexto segue na próxima linha.[/yellow]")
            continue
        if result.get("done"):
            message = result.get("message") or ""
            if message:
                console.print(f"[green]{message}[/green]")
        else:
            console.print(f"[yellow]{result.get('message', '')}[/yellow]")

    console.print("\nAté logo!")


def _reload_premises(config_dir, name: str, console: Console, warn: bool = False):
    try:
        return load_premises(config_dir, name)
    except FileNotFoundError:
        if warn:
            console.print(
                f"[yellow]Premissas não encontradas (projects/{name}.yaml). "
                "Usando perfil genérico.[/yellow]"
            )
        return EMPTY_PREMISES


def _handle_slash(
    text: str,
    console: Console,
    session: Session,
    premises,
    instr_set,
    artifacts,
    client,
    options,
    agent,
) -> bool:
    """Trata um comando '/x'. Retorna True para continuar o loop, False para sair."""
    parts = text.split(None, 1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd in ("/quit", "/exit"):
        return False
    if cmd == "/help":
        console.print(_HELP)
    elif cmd == "/model" and arg:
        client.model = arg
        console.print(f"Modelo: {client.model}")
    elif cmd == "/base-url" and arg:
        client.base_url = arg.rstrip("/")
        console.print(f"Base URL: {client.base_url}")
    elif cmd == "/premises":
        config_dir = resolve_config_dir()
        name = premises.name or slugify(session.project_path)
        premises = _reload_premises(config_dir, name, console, warn=True)
        instr_set = load_instruction_set(config_dir, premises)
        options.premises = premises
        options.instruction_set = instr_set
        console.print("Premissas recarregadas.")
    elif cmd == "/rescan":
        artifacts = generate_artifacts(session, premises)
        options.artifacts_summary = artifacts_summary(artifacts)
        console.print(
            f"Scan refeito: {artifacts['num_files']} arquivos, {artifacts['ast_files']} ASTs."
        )
    elif cmd == "/reset":
        session.reset()
        artifacts = generate_artifacts(session, premises)
        options.artifacts_summary = artifacts_summary(artifacts)
        agent.messages = session.load_messages()
        console.print("Sessão reiniciada (histórico apagado) e scan refeito.")
    elif cmd == "/readonly":
        options.mode = "readonly" if options.mode != "readonly" else "ask"
        agent.gate.mode = options.mode
        state = "somente-leitura" if options.mode == "readonly" else "leitura+escrita (com aprovação)"
        console.print(f"Modo permissão: {state}")
    else:
        console.print("[red]Comando desconhecido.[/red] /help para a lista.")
    return True