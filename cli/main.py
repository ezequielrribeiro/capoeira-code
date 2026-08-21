import asyncio
import json
import sys

import click

from .applier import ChangeApplier
from .reducers import get_reducer_for_path
from .server import CapoeiraServer

# Esquema de resposta obrigatório injetado em todo prompt (spec secao 5).
RESPONSE_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "file_path": {"type": "string"},
        "action": {"type": "string", "enum": ["replace_symbol", "create_file", "patch_diff"]},
        "target_symbol": {"type": "string"},
        "code_content": {"type": "string"},
        "explanation": {"type": "string", "description": "Resumo de 1 linha da alteração"},
    },
    "required": ["file_path", "action", "code_content"],
}


def build_prompt(file_path: str, symbol: str, instruction: str, skeleton: str) -> str:
    schema_text = json.dumps(RESPONSE_SCHEMA, indent=2, ensure_ascii=False)
    return f"""INSTRUÇÃO: {instruction}
SÍMBOLO ALVO: {symbol}
CAMINHO DO ARQUIVO: {file_path}

ESQUELETO DO CÓDIGO DO PROJETO:
{skeleton}

Responda APENAS com um JSON válido que siga estritamente este esquema:
{schema_text}

Use action "replace_symbol" com target_symbol "{symbol}" e coloque em "code_content"
o código completo e atualizado da definição do símbolo alvo (e apenas dele).
"""


def build_retry_prompt(original_prompt: str, error: str) -> str:
    return f"""A resposta anterior não pôde ser aplicada: {error}

Responda APENAS com o JSON corrigido, sem nenhum texto adicional.

---
{original_prompt}
"""


async def run_refactor(
    file_path: str,
    symbol: str,
    instruction: str,
    provider: str,
    timeout: float,
    max_retries: int,
) -> bool:
    with open(file_path, "r", encoding="utf-8") as f:
        code = f.read()

    try:
        reducer = get_reducer_for_path(file_path)
    except ValueError as e:
        click.echo(click.style(str(e), fg="red"), err=True)
        return False

    skeleton = reducer.extract_skeleton(code, target_symbol=symbol)
    prompt = build_prompt(file_path, symbol, instruction, skeleton)

    server = CapoeiraServer()
    async with await server.start():
        click.echo(f"[CapoeiraCode] Bridge WebSocket em ws://{server.host}:{server.port}")
        click.echo("Aguardando a extensão conectar (abra a aba do LLM no navegador)...")
        try:
            await server.wait_for_extension()
        except KeyboardInterrupt:
            return False

        current_prompt = prompt
        for attempt in range(1, max_retries + 1):
            try:
                raw_response = await server.send_prompt_and_wait(
                    current_prompt, provider=provider, timeout=timeout
                )
            except (ConnectionError, TimeoutError) as e:
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


@click.group()
def cli():
    """CapoeiraCode CLI - Agente para desenvolvimento e refatoração em sistemas legados."""


@cli.command()
@click.option("--file", "file_path", required=True, help="Caminho do arquivo legado")
@click.option("--symbol", required=True, help="Nome do método/função alvo")
@click.option("--instruction", required=True, help="O que deve ser alterado/refatorado")
@click.option(
    "--provider",
    default="gemini",
    show_default=True,
    type=click.Choice(["gemini", "claude", "chatgpt", "copilot"]),
    help="Plataforma Web de LLM alvo",
)
@click.option("--timeout", default=180.0, show_default=True, help="Timeout (s) por resposta do LLM")
@click.option("--max-retries", default=3, show_default=True, help="Tentativas de autocorreção (RNF-04)")
def refactor(file_path: str, symbol: str, instruction: str, provider: str, timeout: float, max_retries: int):
    """Reduz o contexto do arquivo via AST e solicita a alteração ao LLM."""
    try:
        success = asyncio.run(
            run_refactor(file_path, symbol, instruction, provider, timeout, max_retries)
        )
    except FileNotFoundError:
        click.echo(click.style(f"Arquivo não encontrado: {file_path}", fg="red"), err=True)
        success = False
    except KeyboardInterrupt:
        click.echo("\nOperação cancelada pelo usuário.")
        success = False
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    cli()
