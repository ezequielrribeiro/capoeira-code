import json
import os
import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from .reducers import get_reducer_for_path


class CapoeiraResponse(BaseModel):
    """Contrato de resposta do LLM (spec secao 5) - acao unica (compat)."""

    file_path: str = Field(description="Caminho do arquivo a ser modificado")
    action: Literal["replace_symbol", "create_file", "patch_diff"] = Field(description="Ação a aplicar")
    target_symbol: str | None = Field(default=None, description="Símbolo alvo (obrigatório em replace_symbol)")
    code_content: str = Field(description="Novo código do símbolo/arquivo, ou unified diff")
    explanation: str = Field(default="", description="Resumo de 1 linha da alteração")


class CapoeiraBatch(BaseModel):
    """Resposta multi-arquivo: lista de ações aplicadas atomicamente em conjunto."""

    files: list[CapoeiraResponse] = Field(min_length=1, description="Uma ou mais ações atômicas")


@dataclass
class ApplyResult:
    ok: bool
    message: str = ""
    error: str = ""
    payload: CapoeiraResponse | None = field(default=None, repr=False)
    staged: dict[str, str] | None = field(default=None, repr=False)


class ChangeApplier:
    """Aplicador atomico do JSON retornado pelo LLM.

    RNF-04: qualquer falha (JSON inválido, schema, símbolo ausente, diff que
    não confere) resulta em ApplyResult(ok=False) SEM modificar arquivos.
    No formato multi-arquivo ('files': [...]), todas as ações são preparadas
    em memoria e so depois gravadas - ou grava tudo, ou não grava nada.
    """

    @staticmethod
    def apply_payload(raw_json_str: str, expected_file_path: str | None = None) -> ApplyResult:
        """Prepara (stage) e grava (commit) as ações. Atomicidade RNF-04."""
        result = ChangeApplier.stage_payload(raw_json_str, expected_file_path)
        if not result.ok or not result.staged:
            return result
        try:
            ChangeApplier.commit_staged(result.staged)
        except Exception as e:
            return ApplyResult(ok=False, error=f"Falha ao gravar as alterações: {e}")
        return result

    # ------------------------------------------------------------------
    # Staging: prepara tudo em memória sem tocar no disco
    # ------------------------------------------------------------------
    @staticmethod
    def stage_payload(raw_json_str: str, expected_file_path: str | None = None) -> ApplyResult:
        try:
            actions = ChangeApplier._parse_actions(raw_json_str)
        except ValueError as e:
            return ApplyResult(ok=False, error=str(e))

        staged: dict[str, str] = {}
        falha = ""
        try:
            if expected_file_path is not None:
                if len(actions) != 1 or actions[0].file_path != expected_file_path:
                    raise ValueError(
                        f"Caminho inesperado na resposta ({actions[0].file_path!r}); "
                        f"nada foi escrito. Esperado: {expected_file_path}"
                    )
            for action in actions:
                falha = action.file_path
                ChangeApplier._stage_action(action, staged)
        except Exception as e:
            rota = falha if falha else (actions[0].file_path if actions else "")
            return ApplyResult(ok=False, error=f"Falha ao validar '{rota}': {e}")

        solo = actions[0] if len(actions) == 1 else None
        return ApplyResult(
            ok=True,
            message=ChangeApplier._message(actions, staged),
            payload=solo,
            staged=staged,
        )

    @staticmethod
    def commit_staged(staged: dict[str, str]) -> None:
        """Grava todos os arquivos de uma vez (tmp + os.replace por arquivo)."""
        for path, content in staged.items():
            directory = os.path.dirname(os.path.abspath(path))
            os.makedirs(directory, exist_ok=True)
            ChangeApplier._atomic_write(path, content)

    @staticmethod
    def _stage_action(action: CapoeiraResponse, staged: dict[str, str]) -> None:
        path = action.file_path
        if action.action == "create_file":
            staged[path] = action.code_content
            return

        original = staged.get(path)
        if original is None:
            if not os.path.isfile(path):
                raise FileNotFoundError(f"Arquivo não encontrado: {path}")
            with open(path, "r", encoding="utf-8") as f:
                original = f.read()

        if action.action == "replace_symbol":
            if not action.target_symbol:
                raise ValueError("Ação 'replace_symbol' exige a propriedade 'target_symbol'.")
            reducer = get_reducer_for_path(path)
            symbol_range = reducer.find_symbol_range(original, action.target_symbol)
            if symbol_range is None:
                raise ValueError(f"Símbolo '{action.target_symbol}' não encontrado em {path}.")
            data = original.encode("utf8")
            start, end = symbol_range
            updated = (data[:start] + action.code_content.encode("utf8") + data[end:]).decode("utf8")
            if reducer.has_parse_errors(updated):
                raise ValueError("O código resultante tem erros de sintaxe; nada foi escrito.")
            staged[path] = updated
        else:  # patch_diff
            staged[path] = apply_unified_diff(original, action.code_content)

    # ------------------------------------------------------------------
    # Parsing da resposta do LLM (única ou batch)
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_actions(raw: str) -> list[CapoeiraResponse]:
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

        if isinstance(data, dict) and isinstance(data.get("files"), list):
            try:
                return CapoeiraBatch(**data).files
            except ValidationError as e:
                raise ValueError(f"Resposta batch fora do schema esperado: {e}") from e

        try:
            return [CapoeiraResponse(**data)]
        except ValidationError as e:
            raise ValueError(f"Resposta fora do schema esperado: {e}") from e

    @staticmethod
    def _message(actions: list[CapoeiraResponse], staged: dict[str, str]) -> str:
        total = len(actions)
        if total == 1:
            a = actions[0]
            return f"Alteração aplicada em {a.file_path}: {a.explanation}"
        resumos = ", ".join(a.explanation or a.action for a in actions[:3])
        extra = "" if total <= 3 else f" (+{total - 3} mais)"
        return f"Alterações aplicadas em {total} arquivo(s): {resumos}{extra}"

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