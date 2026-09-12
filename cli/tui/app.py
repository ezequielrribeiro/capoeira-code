"""TUI textual interativa (prompt_toolkit + rich) estilo OpenCode."""

import os
import shutil

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import InMemoryHistory
from rich.console import Console

from ..llm_client import DEFAULT_BASE_URL, DEFAULT_MODEL, DEFAULT_TIMEOUT, LLMClient
from ..instruction.loader import load_instruction_set
from ..project.premises import EMPTY_PREMISES, load_premises, resolve_config_dir
from ..project.scanner import scan_file
from ..rag_client import RagClient, RagError, RagNotConfiguredError
from .agent import AgentOptions, AgentRun
from .bootstrap import bootstrap_instruction
from .scan_artifacts import artifacts_summary, generate_artifacts, is_empty_project
from .session import DEFAULT_SESSION, Session, slugify

_HELP = """/help            - esta ajuda
/model M        - troca o modelo (ex.: gemini-pro, qwen2.5-coder)
/base-url URL   - troca a base URL do CapoeiraHost (ex.: http://127.0.0.1:8765)
/premises       - recarrega premissas e specs/skills/prompts do config
/rescan         - regenera os artefatos de scan do projeto
/reset          - apaga o histórico da sessão ATUAL e rescan
/sessions       - lista as sessões salvas do projeto
/use NOME       - cria/troca para a sessão NOME (históricos independentes)
/delete NOME    - apaga a sessão NOME (com confirmação)
/bootstrap       - cria um sistema do zero (pergunta stack/banco; gera .sql)
/max-turns N    - limite de turnos do agente (padrão 20)
/readonly       - alterna modo somente-leitura (bloqueia execução/escrita)
/ask <pergunta> [--doc-type T]  - consulta o local-rag-system (contexto/docs)
/deps <arquivo> - lista módulo, dependências e tabelas SQL de um arquivo
/quit           - sai da TUI
"""

_COMMANDS = [
    "/help", "/model", "/base-url", "/premises", "/rescan", "/reset",
    "/sessions", "/use", "/delete", "/bootstrap", "/max-turns", "/readonly",
    "/ask", "/deps", "/quit", "/exit",
]


class _UICtx:
    """Contexto mutável da TUI: permite que os comandos de sessão troquem a
    sessão/agente ativos em runtime (o loop local não pode ser reatribuído)."""

    def __init__(self, session: Session, agent: AgentRun):
        self.session = session
        self.agent = agent


def run_tui(
    project_path: str | None = None,
    project: str | None = None,
    readonly: bool = False,
    model: str | None = None,
    base_url: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    session_name: str | None = None,
) -> None:
    console = Console()
    config_dir = resolve_config_dir()
    session = Session(config_dir, project_path or os.getcwd(), name=session_name)
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
    ui = _UICtx(session, agent)

    console.print("[bold]CapoeiraCode[/bold] — modo agente interativo")
    console.print(ui.session.summarize())
    console.print(
        f"Backend: CapoeiraHost ({client.base_url}) | Modelo: {client.model} | Projeto: {ui.session.project_path}"
    )
    if is_empty_project(artifacts, ui.session.project_path):
        console.print(
            "[yellow]Diretório parece vazio (projeto do zero). "
            "Digite /bootstrap ou descreva o sistema a criar.[/yellow]"
        )
    console.print("Digite um prompt e pressione Enter. /help para comandos.")

    completer = WordCompleter(_COMMANDS, ignore_case=True)
    prompt_session = PromptSession(history=InMemoryHistory(), completer=completer)

    def on_chunk(part: str) -> None:
        console.print(part, end="", highlight=False)

    def ask_user(question: str) -> str:
        return prompt_session.prompt(f"[pergunta] {question}\n> ")

    def ask_permission(description: str) -> str:
        choice = prompt_session.prompt(
            f"[permissão] Executar '{description}'? (y=sim, n=não, a=sempre na sessão) "
        )
        return choice.strip().lower()[:1] or "n"

    options.on_chunk = on_chunk

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
            if text.lower() in ("/bootstrap", "/bootstrap "):
                console.print("[dim]bootstrap... (Ctrl+C interrompe)[/dim]")
                try:
                    result = ui.agent.run(
                        bootstrap_instruction(instr_set),
                        ask_user=ask_user,
                        ask_permission=ask_permission,
                    )
                except KeyboardInterrupt:
                    console.print()
                    console.print("[yellow]\nBootstrap interrompido.[/yellow]")
                    continue
                console.print()
                if result.get("done") and result.get("message"):
                    console.print(f"[green]{result['message']}[/green]")
                continue
            if not _handle_slash(
                text, console, ui, premises, instr_set, artifacts, client, options,
            ):
                break
            continue

        console.print("[dim]agente em execução... (Ctrl+C interrompe)[/dim]")
        try:
            result = ui.agent.run(text, ask_user=ask_user, ask_permission=ask_permission)
        except KeyboardInterrupt:
            console.print()
            console.print("[yellow]\nInterrompido pelo usuário. O contexto segue na próxima linha.[/yellow]")
            continue
        console.print()
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


def _ask_query(premises, query: str, doc_type: str | None = None) -> str:
    """Consulta o local-rag-system (subprocess) e devolve o texto de contexto."""
    try:
        client = RagClient(premises)
    except RagNotConfiguredError as e:
        return str(e)
    try:
        return client.ask(query, doc_type)
    except RagError as e:
        return f"ERRO: {e}"


def _deps_report(premises, path: str) -> str:
    """Relatório local de módulo/dependências/tabelas de um arquivo (sem LLM)."""
    if not os.path.isfile(path):
        return f"Arquivo não encontrado: {path}"
    try:
        perfil = scan_file(path, premises)
    except ValueError as e:
        return f"ERRO: {e}"
    deps = perfil["dependencies"] or []
    tables = perfil["sql_tables"] or []
    lines = [f"Módulo: {perfil['classification']}", "Dependências:"]
    lines.extend(f"  - {d}" for d in deps) or lines.append("  (nenhuma)")
    lines.append("Tabelas SQL:")
    lines.extend(f"  - {t}" for t in tables) or lines.append("  (nenhuma)")
    return "\n".join(lines)


def _handle_slash(
    text: str,
    console: Console,
    ui: _UICtx,
    premises,
    instr_set,
    artifacts,
    client,
    options,
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
        name = premises.name or slugify(ui.session.project_path)
        premises = _reload_premises(config_dir, name, console, warn=True)
        instr_set = load_instruction_set(config_dir, premises)
        options.premises = premises
        options.instruction_set = instr_set
        console.print("Premissas recarregadas.")
    elif cmd == "/rescan":
        artifacts = generate_artifacts(ui.session, premises)
        options.artifacts_summary = artifacts_summary(artifacts)
        console.print(
            f"Scan refeito: {artifacts['num_files']} arquivos, {artifacts['ast_files']} ASTs."
        )
    elif cmd == "/reset":
        ui.session.reset()
        artifacts = generate_artifacts(ui.session, premises)
        options.artifacts_summary = artifacts_summary(artifacts)
        ui.agent.reset_messages()
        console.print(f"Sessão '{ui.session.name}' reiniciada (histórico apagado) e scan refeito.")
    elif cmd == "/sessions":
        config_dir = resolve_config_dir()
        names = Session.list_sessions(config_dir, ui.session.project_path)
        if not names:
            console.print("Nenhuma sessão salva ainda.")
        for n in names:
            marca = "  <- atual" if n == ui.session.name else ""
            ss = Session(config_dir, ui.session.project_path, name=n)
            estado = "tem histórico" if ss.has_history else "vazia"
            console.print(f"  {n} ({estado}){marca}")
    elif cmd == "/use" and arg:
        config_dir = resolve_config_dir()
        nova = Session(config_dir, ui.session.project_path, name=arg)
        if nova.name == ui.session.name:
            console.print(f"Já está na sessão '{ui.session.name}'.")
            return True
        nova.ensure()
        ui.session = nova
        ui.agent = AgentRun(nova, options, client)
        console.print(ui.session.summarize())
        console.print("[green]Sessão ativa trocada.[/green]")
    elif cmd == "/delete" and arg:
        config_dir = resolve_config_dir()
        alvo = Session(config_dir, ui.session.project_path, name=arg)
        if alvo.name == ui.session.name:
            console.print("[red]Não é possível apagar a sessão em uso.[/red]")
            return True
        if alvo.name == DEFAULT_SESSION and alvo.has_history:
            console.print("[red]Não é possível apagar a sessão 'default' com histórico.[/red]")
            return True
        if not alvo.dir.is_dir():
            console.print(f"[red]Sessão '{alvo.name}' não existe.[/red]")
            return True
        confirm = console.input(f"[permissão] Apagar a sessão '{alvo.name}'? (y=sim) ")
        if confirm.strip().lower()[:1] == "y":
            shutil.rmtree(alvo.dir, ignore_errors=True)
            console.print(f"Sessão '{alvo.name}' apagada.")
        else:
            console.print("Nada apagado.")
    elif cmd == "/bootstrap":
        console.print("[yellow]Use /bootstrap na linha de comando para iniciar.[/yellow]")
    elif cmd == "/max-turns" and arg:
        try:
            options.max_turns = max(1, int(arg))
            console.print(f"Máximo de turnos: {options.max_turns}")
        except ValueError:
            console.print("[red]Valor inválido para /max-turns.[/red]")
    elif cmd == "/readonly":
        options.mode = "readonly" if options.mode != "readonly" else "ask"
        ui.agent.gate.mode = options.mode
        state = "somente-leitura" if options.mode == "readonly" else "leitura+escrita (com aprovação)"
        console.print(f"Modo permissão: {state}")
    elif cmd == "/ask":
        query, doc_type = _split_ask(arg)
        if not query:
            console.print("[red]Uso: /ask <pergunta> [--doc-type user|tech|support][/red]")
        else:
            console.print(_ask_query(premises, query, doc_type))
    elif cmd == "/deps":
        if not arg:
            console.print("[red]Uso: /deps <arquivo>[/red]")
        else:
            path = arg if os.path.isabs(arg) else os.path.join(ui.session.project_path, arg)
            console.print(_deps_report(premises, os.path.normpath(path)))
    else:
        console.print("[red]Comando desconhecido.[/red] /help para a lista.")
    return True


def _split_ask(arg: str) -> tuple[str, str | None]:
    """Separa `/<pergunta> [--doc-type T]` -> (pergunta, doc_type)."""
    if "--doc-type" in arg:
        query, _, rest = arg.partition("--doc-type")
        doc_type = rest.strip().split()[0] if rest.strip() else None
        return query.strip(), doc_type
    return arg.strip(), None