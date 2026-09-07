"""Scanner de dependências e de impacto sistema <-> banco.

Usa os reducers existentes (extract_dependencies) e heurísticas de SQL para
montar o "pedigree" do sistema legado: como os arquivos se referenciam, qual o
papel de cada um (controller/model/view/migration) e quais tabelas cada um toca.
"""

import os
import re
from pathlib import Path

from ..reducers import get_reducer_for_path
from .premises import Premises

_SQL_TABLE_RE = re.compile(
    r"\b(?:FROM|INTO|UPDATE|TABLE|JOIN)\s+"
    r"(?:`)([A-Za-z0-9_]+)(?:`|(?=\s))"
    r"|(?:\b(?:FROM|INTO|UPDATE|TABLE|JOIN)\s+)([A-Za-z_][A-Za-z0-9_]*)",
    re.IGNORECASE,
)

_CREATE_TABLE_RE = re.compile(
    r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
    r"(?:`([^`]+)`|([A-Za-z_][A-Za-z0-9_]*))",
    re.IGNORECASE,
)


def _relative(path: str) -> str:
    return os.path.normpath(path).replace(os.sep, "/").lower()


def classify_module(file_path: str, structure: dict[str, str] | None = None) -> str:
    """Classifica um arquivo no papel do sistema (controller/model/view/...).

    Casa por segmento de caminho (funciona com caminhos absolutos ou relativos):
    um prefixo como 'app/controllers' bate em qualquer posição do caminho.
    """
    structure = structure or {}
    rel = "/" + _relative(file_path) + "/"
    for role, prefix in structure.items():
        pref = _relative(prefix)
        if pref and f"/{pref}/" in rel:
            return role
    return "outro"


def extract_sql_tables(content: str) -> list[str]:
    """Tabelas referenciadas em queries SQL (FROM/INTO/UPDATE/TABLE/JOIN)."""
    result = []
    for match in _SQL_TABLE_RE.finditer(content):
        table = match.group(1) or match.group(2)
        if table and table not in result:
            result.append(table)
    return result


def parse_schema_table_names(schema_sql: str) -> list[str]:
    """Nomes de tabelas definidos num dump/schema SQL (CREATE TABLE)."""
    result = []
    for match in _CREATE_TABLE_RE.finditer(schema_sql):
        table = match.group(1) or match.group(2)
        if table and table not in result:
            result.append(table)
    return result


def scan_file(file_path: str, premises: Premises | None = None) -> dict:
    """Perfil de um arquivo: classificação, dependências e tabelas tocadas."""
    premises = premises or EMPTY_SCAN_PREMISES
    abs_path = os.path.abspath(file_path)
    with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    deps: list[str] = []
    try:
        reducer = get_reducer_for_path(abs_path)
        deps = reducer.extract_dependencies(content)
    except ValueError:
        pass  # extensão sem reducer (ex.: .sql) - monta só por heurística

    structure = premises.stack.structure if premises.stack else {}
    return {
        "file": abs_path,
        "classification": classify_module(abs_path, structure),
        "dependencies": sorted(set(deps)),
        "sql_tables": extract_sql_tables(content),
    }


EMPTY_SCAN_PREMISES = Premises(name="scanner")


def scan_project(root: str | Path, premises: Premises | None = None) -> list[dict]:
    """Varre o projeto suportado (`.php`) e monta o perfil de cada arquivo."""
    premises = premises or EMPTY_SCAN_PREMISES
    root = Path(root)
    files = []
    for path in root.rglob("*"):
        if path.is_file() and path.suffix.lower() == ".php":
            try:
                get_reducer_for_path(str(path))
            except ValueError:
                continue
            files.append(scan_file(str(path), premises))
    return files


def schema_tables(schema_file: str) -> list[str]:
    """Tabelas disponíveis no schema/banco (para cruzar com o uso no código)."""
    with open(schema_file, "r", encoding="utf-8", errors="replace") as f:
        return parse_schema_table_names(f.read())