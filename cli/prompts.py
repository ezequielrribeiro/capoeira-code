import json

# Esquema de resposta obrigatório injetado em todo prompt de mutação (spec §5).
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


def _schema_text() -> str:
    return json.dumps(RESPONSE_SCHEMA, indent=2, ensure_ascii=False)


def build_refactor_prompt(file_path: str, symbol: str, instruction: str, skeleton: str) -> str:
    return f"""INSTRUÇÃO: {instruction}
SÍMBOLO ALVO: {symbol}
CAMINHO DO ARQUIVO: {file_path}

ESQUELETO DO CÓDIGO DO PROJETO:
{skeleton}

Responda APENAS com um JSON válido que siga estritamente este esquema:
{_schema_text()}

Use action "replace_symbol" com target_symbol "{symbol}" e coloque em "code_content"
o código completo e atualizado da definição do símbolo alvo (e apenas dele).
Use "file_path" exatamente igual a "{file_path}".
"""


def build_generate_prompt(file_path: str, instruction: str, symbol: str | None, context: str | None) -> str:
    target = symbol or ""
    action = "replace_symbol" if symbol else "create_file"
    contexto = f"\n\nCONTEXTO DO PROJETO (esqueleto de arquivo relacionado):\n{context}\n" if context else ""
    return f"""INSTRUÇÃO: {instruction}
CAMINHO DO ARQUIVO ALVO: {file_path}
{"SÍMBOLO ALVO: " + symbol if symbol else "AÇÃO: criar um novo arquivo/artefato"}
{contexto}
Responda APENAS com um JSON válido que siga estritamente este esquema:
{_schema_text()}

Use action "{action}" com "file_path" exatamente igual a "{file_path}"{" e target_symbol \"" + target + "\"" if symbol else ""}.
Em "code_content" coloque o conteúdo completo e correto a ser gravado.
"""


def build_explain_prompt(file_path: str, symbol: str | None, skeleton: str) -> str:
    alvo = f" Símbolo alvo: {symbol}." if symbol else ""
    return f"""Explique o código abaixo de forma concisa e técnica, em português.
Autor: CapoeiraCode, focado em manutenção de sistemas legados.
Arquivo: {file_path}{alvo}
Explique propósito, fluxo principal e pontos de atenção (acoplamento, efeitos
colaterais, riscos de refatoração). Não escreva código novo.

CÓDIGO (esqueleto, corpos fora do alvo omitidos):
{skeleton}
"""


def build_retry_prompt(original_prompt: str, error: str) -> str:
    return f"""A resposta anterior não pôde ser aplicada: {error}

Responda APENAS com o JSON corrigido, sem nenhum texto adicional.

---
{original_prompt}
"""