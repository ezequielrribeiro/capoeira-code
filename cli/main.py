import difflib
import sys

import click

from .applier import ChangeApplier
from .instruction import load_instruction_set, render_project_profile
from .llm_client import DEFAULT_BASE_URL, DEFAULT_MODEL, DEFAULT_TIMEOUT, LLMClient, LLMRequestError
from .project import load_premises, resolve_config_dir, scan_file
from .prompts import (
    build_explain_prompt,
    build_generate_prompt,
    build_refactor_prompt,
    build_retry_prompt,
    build_run_prompt,
)
from .rag_client import RagClient, RagError, RagNotConfiguredError
from .reducers import get_reducer_for_path


def llm_options(func):
    """Opções compartilhadas de comunicação com o backend compatível com Ollama."""
    func = click.option(
        "--base-url",
        default=DEFAULT_BASE_URL,
        show_default=True,
        help="Base URL do backend compatível com Ollama (Ollama ou CapoeiraHost)",
    )(func)
    func = click.option(
        "--model",
        default=DEFAULT_MODEL,
        show_default=True,
        help="Perfil/modelo registrado no backend (ex.: gemini-pro, qwen2.5-coder)",
    )(func)
    func = click.option(
        "--timeout",
        default=DEFAULT_TIMEOUT,
        show_default=True,
        help="Timeout (s) por chamada ao backend",
    )(func)
    return func


def _read_code(file_path: str) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def _extract_skeleton(file_path: str, symbol: str | None) -> str:
    reducer = get_reducer_for_path(file_path)
    return reducer.extract_skeleton(_read_code(file_path), target_symbol=symbol or "")


def run_refactor(
    file_path: str,
    symbol: str,
    instruction: str,
    base_url: str,
    model: str,
    timeout: float,
    max_retries: int,
) -> bool:
    try:
        skeleton = _extract_skeleton(file_path, symbol)
    except ValueError as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        return False

    prompt = build_refactor_prompt(file_path, symbol, instruction, skeleton)
    client = LLMClient(base_url=base_url, model=model, timeout=timeout)

    current_prompt = prompt
    for attempt in range(1, max_retries + 1):
        try:
            raw_response = client.chat(current_prompt)
        except LLMRequestError as e:
            click.echo(click.style(str(e), fg="red"), err=True)
            return False

        result = ChangeApplier.apply_payload(raw_response)
        if result.ok:
            click.echo(click.style(f"Refatoração concluída! {result.message}", fg="green"))
            return True

        click.echo(
            click.style(f"[Tentativa {attempt}/{max_retries}] {result.error}", fg="yellow"),
            err=True,
        )
        # RNF-04: nada foi modificado; pede autocorreção ao LLM.
        current_prompt = build_retry_prompt(prompt, result.error)

    click.echo(click.style("Falha ao aplicar alterações após todas as tentativas.", fg="red"), err=True)
    return False


def run_generate(
    file_path: str,
    instruction: str,
    symbol: str | None,
    context_file: str | None,
    base_url: str,
    model: str,
    timeout: float,
    max_retries: int,
) -> bool:
    context = None
    if context_file:
        try:
            context = _extract_skeleton(context_file, symbol)
        except ValueError as e:
            click.echo(click.style(f"Contexto inválido: {e}", fg="red"), err=True)
            return False

    if symbol and not context_file:
        try:
            get_reducer_for_path(file_path)
        except ValueError as e:
            click.echo(click.style(f"{e} (desejava criar um novo arquivo? omita --symbol)", fg="red"), err=True)
            return False

    prompt = build_generate_prompt(file_path, instruction, symbol, context)
    client = LLMClient(base_url=base_url, model=model, timeout=timeout)

    current_prompt = prompt
    for attempt in range(1, max_retries + 1):
        try:
            raw_response = client.chat(current_prompt)
        except LLMRequestError as e:
            click.echo(click.style(str(e), fg="red"), err=True)
            return False

        result = ChangeApplier.apply_payload(raw_response, expected_file_path=file_path)
        if result.ok:
            click.echo(click.style(f"Artefato gerado! {result.message}", fg="green"))
            return True

        click.echo(
            click.style(f"[Tentativa {attempt}/{max_retries}] {result.error}", fg="yellow"),
            err=True,
        )
        current_prompt = build_retry_prompt(prompt, result.error)

    click.echo(click.style("Falha ao gerar o artefato após todas as tentativas.", fg="red"), err=True)
    return False


def run_explain(file_path: str, symbol: str | None, base_url: str, model: str, timeout: float) -> bool:
    try:
        skeleton = _extract_skeleton(file_path, symbol)
    except ValueError as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        return False

    prompt = build_explain_prompt(file_path, symbol, skeleton)
    client = LLMClient(base_url=base_url, model=model, timeout=timeout)
    try:
        explanation = client.chat(prompt)
    except LLMRequestError as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        return False

    click.echo(explanation.strip())
    return True


def run_deps(file_path: str) -> bool:
    try:
        reducer = get_reducer_for_path(file_path)
        deps = reducer.extract_dependencies(_read_code(file_path))
    except ValueError as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        return False

    if not deps:
        click.echo("Nenhuma dependência detectada.")
        return True
    click.echo("Dependências do arquivo:")
    for dep in deps:
        click.echo(f"  - {dep}")
    return True


def run_deps_project(file_path: str, project: str) -> bool:
    config_dir = resolve_config_dir()
    try:
        premises = load_premises(config_dir, project)
        perfil = scan_file(file_path, premises)
    except (FileNotFoundError, ValueError) as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        return False

    click.echo(f"Módulo: {perfil['classification']}")
    click.echo("Dependências do arquivo:")
    for dep in perfil["dependencies"] or [">< nenhuma"]:
        click.echo(f"  - {dep}")
    click.echo("Tabelas tocadas (SQL):")
    for t in perfil["sql_tables"] or [">< nenhuma"]:
        click.echo(f"  - {t}")
    return True


def _skeletons_for(paths: list[str]) -> str:
    blocos = []
    for path in paths:
        try:
            blocos.append(f"# {path}\n{_extract_skeleton(path, None)}")
        except (ValueError, FileNotFoundError):
            click.echo(click.style(f"Ignorando arquivo de contexto: {path}", fg="yellow"), err=True)
    return "\n\n".join(blocos)


def _render_diff(staged: dict[str, str]) -> None:
    for path, novo in staged.items():
        try:
            with open(path, "r", encoding="utf-8") as f:
                original = f.read()
        except FileNotFoundError:
            original = ""
        click.echo(click.style(f"\n=== {path} ({'+novo' if not original else 'modificado'}) ===", fg="cyan"))
        if not original:
            for line in novo.splitlines():
                click.echo(click.style(f"+ {line}", fg="green"))
            continue
        for line in difflib.unified_diff(original.splitlines(), novo.splitlines(), lineterm=""):
            if line.startswith("+") and not line.startswith("+++"):
                click.echo(click.style(line, fg="green"))
            elif line.startswith("-") and not line.startswith("---"):
                click.echo(click.style(line, fg="red"))
            elif line.startswith("@@"):
                click.echo(click.style(line, fg="cyan"))
            else:
                click.echo(line)


def run_run(
    instruction: str,
    project: str | None,
    prompt_name: str | None,
    skill_name: str | None,
    files: list[str],
    context_files: list[str],
    rag_query: str | None,
    rag_doc_type: str | None,
    dry_run: bool,
    base_url: str,
    model: str,
    timeout: float,
    max_retries: int,
) -> bool:
    config_dir = resolve_config_dir()
    try:
        premises = load_premises(config_dir, project or "")
    except (FileNotFoundError, ValueError) as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        return False

    instr_set = load_instruction_set(config_dir, premises)
    profile = render_project_profile(premises)
    specs = instr_set.specs_combined

    if skill_name:
        skill = instr_set.get_prompt(skill_name + ".md")
        skills = skill or instr_set.skills_combined
        if not skill:
            click.echo(click.style(f"Skill '{skill_name}' não encontrada; usando todas.", fg="yellow"), err=True)
    else:
        skills = instr_set.skills_combined

    prompt_template = instr_set.get_prompt((prompt_name or "") + ".md")
    if prompt_name and not prompt_template:
        click.echo(click.style(f"Template '{prompt_name}' não encontrado em prompts/.", fg="yellow"), err=True)

    context = _skeletons_for(list(files) + list(context_files))

    rag_context = ""
    if rag_query:
        try:
            rag_client = RagClient(premises)
            rag_context = rag_client.ask(rag_query, rag_doc_type)
        except (RagNotConfiguredError, RagError) as e:
            click.echo(click.style(str(e), fg="yellow"), err=True)

    prompt = build_run_prompt(
        instruction, profile, specs=specs, skills=skills,
        context_files=context, rag_context=rag_context, prompt_template=prompt_template,
    )
    client = LLMClient(base_url=base_url, model=model, timeout=timeout)

    current_prompt = prompt
    for attempt in range(1, max_retries + 1):
        try:
            raw_response = client.chat(current_prompt)
        except LLMRequestError as e:
            click.echo(click.style(str(e), fg="red"), err=True)
            return False

        result = ChangeApplier.stage_payload(raw_response)
        if not result.ok:
            click.echo(
                click.style(f"[Tentativa {attempt}/{max_retries}] {result.error}", fg="yellow"),
                err=True,
            )
            current_prompt = build_retry_prompt(prompt, result.error)
            continue

        if dry_run:
            click.echo(click.style("RASCUNHO (dry-run) — nada foi gravado.", fg="cyan"))
            _render_diff(result.staged)
            if click.confirm("\nAplicar as alterações?", default=False):
                try:
                    ChangeApplier.commit_staged(result.staged)
                except Exception as e:
                    click.echo(click.style(f"Falha ao gravar: {e}", fg="red"), err=True)
                    return False
                click.echo(click.style(f"Concluído! {result.message}", fg="green"))
            else:
                click.echo("Nada aplicado.")
            return True

        try:
            ChangeApplier.commit_staged(result.staged)
        except Exception as e:
            click.echo(click.style(f"Falha ao gravar: {e}", fg="red"), err=True)
            return False
        click.echo(click.style(f"Concluído! {result.message}", fg="green"))
        return True

    click.echo(click.style("Falha após todas as tentativas.", fg="red"), err=True)
    return False


def run_ask(query: str, doc_type: str | None, project: str | None) -> bool:
    config_dir = resolve_config_dir()
    try:
        premises = load_premises(config_dir, project or "")
        rag_client = RagClient(premises)
    except (FileNotFoundError, ValueError) as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        return False
    except RagNotConfiguredError as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        return False

    try:
        output = rag_client.ask(query, doc_type)
    except RagError as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        return False
    click.echo(output)
    return True


@click.group()
def cli():
    """CapoeiraCode CLI - Agente para desenvolvimento e refatoração em sistemas legados.

    Usa o modelo via backend compatível com a API do Ollama (Ollama nativo ou
    CapoeiraHost), desacoplando o CLI de navegador/extensão.
    """


@cli.command()
@click.option("--file", "file_path", required=True, help="Caminho do arquivo legado")
@click.option("--symbol", required=True, help="Nome do método/função alvo")
@click.option("--instruction", required=True, help="O que deve ser alterado/refatorado")
@click.option("--max-retries", default=3, show_default=True, help="Tentativas de autocorreção (RNF-04)")
@llm_options
def refactor(file_path, symbol, instruction, base_url, model, timeout, max_retries):
    """Reduz o contexto do arquivo via AST e solicita a alteração ao LLM."""
    try:
        success = run_refactor(file_path, symbol, instruction, base_url, model, timeout, max_retries)
    except FileNotFoundError:
        click.echo(click.style(f"Arquivo não encontrado: {file_path}", fg="red"), err=True)
        success = False
    except KeyboardInterrupt:
        click.echo("\nOperação cancelada pelo usuário.")
        success = False
    sys.exit(0 if success else 1)


@cli.command()
@click.option("--file", "file_path", required=True, help="Caminho do artefato a criar/gerar")
@click.option("--instruction", required=True, help="O que deve ser criado (ex.: testes, esqueleto, docs)")
@click.option("--symbol", default=None, help="Se informado, substitui um símbolo existente em vez de criar arquivo")
@click.option("--context", "context_file", default=None, help="Arquivo relacionado cujo esqueleto entra no prompt")
@click.option("--max-retries", default=3, show_default=True, help="Tentativas de autocorreção (RNF-04)")
@llm_options
def generate(file_path, instruction, symbol, context_file, base_url, model, timeout, max_retries):
    """Cria artefatos para auxiliar a codificação (testes, esqueleto de módulo, scaffolding, docs)."""
    try:
        success = run_generate(
            file_path, instruction, symbol, context_file, base_url, model, timeout, max_retries
        )
    except KeyboardInterrupt:
        click.echo("\nOperação cancelada pelo usuário.")
        success = False
    sys.exit(0 if success else 1)


@cli.command()
@click.option("--file", "file_path", required=True, help="Caminho do arquivo legado")
@click.option("--symbol", default=None, help="Limita a explicação a um símbolo específico")
@llm_options
def explain(file_path, symbol, base_url, model, timeout):
    """Explica o esqueleto de um arquivo/símbolo via LLM (somente leitura)."""
    try:
        success = run_explain(file_path, symbol, base_url, model, timeout)
    except FileNotFoundError:
        click.echo(click.style(f"Arquivo não encontrado: {file_path}", fg="red"), err=True)
        success = False
    except KeyboardInterrupt:
        click.echo("\nOperação cancelada pelo usuário.")
        success = False
    sys.exit(0 if success else 1)


@cli.command()
@click.argument("instruction")
@click.option("--project", default=None, help="Nome do arquivo de premissas (projects/<nome>.yaml)")
@click.option("--prompt", "prompt_name", default=None, help="Template de fluxo em prompts/ (ex.: new-screen, bugfix)")
@click.option("--skill", "skill_name", default=None, help="Skill em skills/ a destacar no procedimento")
@click.option("--file", "files", multiple=True, help="Arquivo(s) de código do sistema para contexto (pode repetir)")
@click.option("--context", "context_files", multiple=True, help="Arquivo(s) adicionais de contexto (pode repetir)")
@click.option("--rag", "rag_query", default=None, help="Consulta ao local-rag-system para injetar contexto")
@click.option("--doc-type", "rag_doc_type", default=None, type=click.Choice(["user", "tech", "support"]))
@click.option("--dry-run", is_flag=True, help="Mostra o diff e pede confirmação antes de aplicar")
@click.option("--max-retries", default=3, show_default=True, help="Tentativas de autocorreção (RNF-04)")
@llm_options
def run(
    instruction,
    project,
    prompt_name,
    skill_name,
    files,
    context_files,
    rag_query,
    rag_doc_type,
    dry_run,
    base_url,
    model,
    timeout,
    max_retries,
):
    """Motor de instrução: você descreve o que quer e o LLM decide as ações.

    Responde em formato de ações (create_file / replace_symbol / patch_diff),
    incluindo lote multi-arquivo, aplicadas atomicamente (RNF-04).
    """
    try:
        success = run_run(
            instruction,
            project,
            prompt_name,
            skill_name,
            list(files),
            list(context_files),
            rag_query,
            rag_doc_type,
            dry_run,
            base_url,
            model,
            timeout,
            max_retries,
        )
    except KeyboardInterrupt:
        click.echo("\nOperação cancelada pelo usuário.")
        success = False
    sys.exit(0 if success else 1)


@cli.command("ask")
@click.argument("query")
@click.option("--project", default=None, help="Projeto cujas premissas apontam o RAG")
@click.option("--doc-type", default=None, type=click.Choice(["user", "tech", "support"]))
def ask(query, project, doc_type):
    """Consulta o local-rag-system (CLI via subprocess) e devolve o contexto."""
    try:
        success = run_ask(query, doc_type, project)
    except KeyboardInterrupt:
        click.echo("\nOperação cancelada pelo usuário.")
        success = False
    sys.exit(0 if success else 1)


@cli.command()
@click.option("--file", "file_path", required=True, help="Caminho do arquivo")
@click.option("--project", default=None, help="Nome das premissas para classificar o módulo e mostrar tabelas")
def deps(file_path, project):
    """Lista dependências (imports/requires) do arquivo - sem LLM."""
    try:
        if project:
            success = run_deps_project(file_path, project)
        else:
            success = run_deps(file_path)
    except FileNotFoundError:
        click.echo(click.style(f"Arquivo não encontrado: {file_path}", fg="red"), err=True)
        success = False
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    cli()