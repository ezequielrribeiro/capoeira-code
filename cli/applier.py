import json
import os
import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from .reducers import get_reducer_for_path


class CapoeiraResponse(BaseModel):
    """Contrato de resposta do LLM (spec secao 5)."""

    file_path: str = Field(description="Caminho do arquivo a ser modificado")
    action: Literal["replace_symbol", "create_file", "patch_diff"] = Field(description="Ação a aplicar")
    target_symbol: str | None = Field(default=None, description="Símbolo alvo (obrigatório em replace_symbol)")
    code_content: str = Field(description="Novo código do símbolo/arquivo, ou unified diff")
    explanation: str = Field(default="", description="Resumo de 1 linha da alteração")


@dataclass
class ApplyResult:
    ok: bool
    message: str = ""
    error: str = ""
    payload: CapoeiraResponse | None = field(default=None, repr=False)


class ChangeApplier:
    """Aplicador atômico do JSON retornado pelo LLM.

    RNF-04: qualquer falha (JSON inválido, schema, símbolo ausente, diff que
    não confere) resulta em ApplyResult(ok=False) SEM modificar arquivos.
    """

    @staticmethod
    def apply_payload(raw_json_str: str) -> ApplyResult:
        try:
            payload = ChangeApplier._parse_payload(raw_json_str)
        except ValueError as e:
            return ApplyResult(ok=False, error=str(e))

        try:
            if payload.action == "create_file":
                ChangeApplier._apply_create_file(payload)
            elif payload.action == "replace_symbol":
                ChangeApplier._apply_replace_symbol(payload)
            elif payload.action == "patch_diff":
                ChangeApplier._apply_patch_diff(payload)
            else:  # defesa extra; o Literal do pydantic já barra
                return ApplyResult(ok=False, error=f"Ação desconhecida: {payload.action}")
        except Exception as e:
            return ApplyResult(ok=False, error=f"Falha ao aplicar '{payload.action}': {e}")

        return ApplyResult(
            ok=True,
            message=f"Alteração aplicada em {payload.file_path}: {payload.explanation}",
            payload=payload,
        )

    # ------------------------------------------------------------------
    # Parsing da resposta do LLM
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_payload(raw: str) -> CapoeiraResponse:
        if not raw or not raw.strip():
            raise ValueError("Resposta vazia do LLM.")

        text = raw.strip()
        if "```" in text:
            match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
            if match:
                text = match.group(1).strip()

        start = text.find("{")
        if start == -1:
            raise ValueError("Nenhum objeto JSON encontrado na resposta do LLM.")

        try:
            data, _ = json.JSONDecoder().raw_decode(text[start:])
        except json.JSONDecodeError as e:
            raise ValueError(f"JSON inválido na resposta do LLM: {e}") from e

        try:
            return CapoeiraResponse(**data)
        except ValidationError as e:
            raise ValueError(f"Resposta fora do schema esperado: {e}") from e

    # ------------------------------------------------------------------
    # Ações
    # ------------------------------------------------------------------
    @staticmethod
    def _apply_create_file(payload: CapoeiraResponse) -> None:
        directory = os.path.dirname(os.path.abspath(payload.file_path))
        os.makedirs(directory, exist_ok=True)
        ChangeApplier._atomic_write(payload.file_path, payload.code_content)

    @staticmethod
    def _apply_replace_symbol(payload: CapoeiraResponse) -> None:
        if not payload.target_symbol:
            raise ValueError("Ação 'replace_symbol' exige a propriedade 'target_symbol'.")
        if not os.path.isfile(payload.file_path):
            raise FileNotFoundError(f"Arquivo não encontrado: {payload.file_path}")

        reducer = get_reducer_for_path(payload.file_path)
        with open(payload.file_path, "r", encoding="utf-8") as f:
            original = f.read()

        symbol_range = reducer.find_symbol_range(original, payload.target_symbol)
        if symbol_range is None:
            raise ValueError(
                f"Símbolo '{payload.target_symbol}' não encontrado em {payload.file_path}."
            )

        data = original.encode("utf8")
        start, end = symbol_range
        updated = (data[:start] + payload.code_content.encode("utf8") + data[end:]).decode("utf8")

        if reducer.has_parse_errors(updated):
            raise ValueError("O código resultante tem erros de sintaxe; nada foi escrito.")

        ChangeApplier._atomic_write(payload.file_path, updated)

    @staticmethod
    def _apply_patch_diff(payload: CapoeiraResponse) -> None:
        if not os.path.isfile(payload.file_path):
            raise FileNotFoundError(f"Arquivo não encontrado: {payload.file_path}")
        with open(payload.file_path, "r", encoding="utf-8") as f:
            original = f.read()
        updated = apply_unified_diff(original, payload.code_content)
        ChangeApplier._atomic_write(payload.file_path, updated)

    # ------------------------------------------------------------------
    # Escrita atômica (tmp + os.replace): ou grava tudo, ou nada
    # ------------------------------------------------------------------
    @staticmethod
    def _atomic_write(file_path: str, content: str) -> None:
        tmp_path = os.path.abspath(file_path) + ".capoeira.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp_path, file_path)


def apply_unified_diff(original: str, diff: str) -> str:
    """Aplicador mínimo de unified diff, com checagem estrita de contexto.

    Suporta múltiplos hunks `@@ -a,b +c,d @@` e linhas ' ', '-' e '+'.
    Levanta ValueError se qualquer contexto/remoção não conferir — o chamador
    decide não escrever nada (RNF-04).
    """
    orig_lines = original.splitlines()
    diff_lines = diff.splitlines()

    out: list[str] = []
    src = 0
    i = 0
    hunks = 0

    while i < len(diff_lines) and not diff_lines[i].startswith("@@"):
        i += 1

    while i < len(diff_lines):
        header = re.match(r"@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", diff_lines[i])
        if not header:
            raise ValueError(f"Cabeçalho de hunk inválido: {diff_lines[i]!r}")
        hunks += 1
        old_start = int(header.group(1)) - 1
        if old_start < src:
            raise ValueError("Hunks sobrepostos ou fora de ordem.")
        out.extend(orig_lines[src:old_start])
        src = old_start
        i += 1

        while i < len(diff_lines) and not diff_lines[i].startswith("@@"):
            line = diff_lines[i]
            if line.startswith("\\"):  # "\ No newline at end of file"
                i += 1
                continue
            tag, text = (line[0], line[1:]) if line else (" ", "")
            if tag == " ":
                if src >= len(orig_lines) or orig_lines[src] != text:
                    raise ValueError(f"Contexto não confere na linha {src + 1}: {text!r}")
                out.append(orig_lines[src])
                src += 1
            elif tag == "-":
                if src >= len(orig_lines) or orig_lines[src] != text:
                    raise ValueError(f"Linha removida não confere na linha {src + 1}: {text!r}")
                src += 1
            elif tag == "+":
                out.append(text)
            else:
                raise ValueError(f"Linha de diff inválida: {line!r}")
            i += 1

    if hunks == 0:
        raise ValueError("Nenhum hunk '@@' encontrado no diff.")

    out.extend(orig_lines[src:])
    result = "\n".join(out)
    if original.endswith("\n"):
        result += "\n"
    return result
