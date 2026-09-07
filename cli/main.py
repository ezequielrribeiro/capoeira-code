import sys

import click

from .applier import ChangeApplier
from .llm_client import DEFAULT_BASE_URL, DEFAULT_MODEL, DEFAULT_TIMEOUT, LLMClient, LLMRequestError
from .prompts import (
    build_explain_prompt,
    build_generate_prompt,
    build_refactor_prompt,
    build_retry_prompt,
)
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
@click.option("--file", "file_path", required=True, help="Caminho do arquivo")
def deps(file_path):
    """Lista dependências (imports/requires) do arquivo - sem LLM."""
    try:
        success = run_deps(file_path)
    except FileNotFoundError:
        click.echo(click.style(f"Arquivo não encontrado: {file_path}", fg="red"), err=True)
        success = False
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    cli()