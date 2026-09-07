"""Geração dos artefatos iniciais de sessão: árvore, dependências, ASTs."""

import json
import os
from pathlib import Path

from ..project.premises import Premises
from ..project.scanner import scan_project
from ..reducers import get_reducer_for_path
from .session import Session

_IGNORED_DIRS = {".git", ".venv", "__pycache__", "node_modules", "vendor", ".idea", ".vscode"}
_TREE_LIMIT = 300


def _tree_lines(root: Path, prefix: str = "") -> list[str]:
    try:
        entries = sorted(root.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except OSError:
        return []
    lines = []
    for entry in entries:
        name = entry.name
        if entry.is_dir():
            if name in _IGNORED_DIRS:
                continue
            lines.append(f"{prefix}{name}/")
            lines.extend(_tree_lines(entry, prefix + "    "))
        else:
            lines.append(f"{prefix}{name}")
    return lines


def render_tree(root: Path) -> str:
    lines = [f"{root.name}/"]
    lines.extend(_tree_lines(root, "    "))
    return "\n".join(lines[:_TREE_LIMIT]) + ("\n...(árvore truncada)" if len(lines) > _TREE_LIMIT else "")


def _write_asts(session: Session, premises: Premises) -> int:
    """Persiste esqueletos (AST) por arquivo suportado, espelhando caminhos relativos."""
    count = 0
    root = Path(session.project_path)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        try:
            reducer = get_reducer_for_path(str(path))
        except ValueError:
            continue
        try:
            code = path.read_text(encoding="utf-8", errors="replace")
            skeleton = reducer.extract_skeleton(code, target_symbol="")
        except OSError:
            continue
        target = session.asts / str(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(skeleton, encoding="utf-8")
        count += 1
    return count


def generate_artifacts(session: Session, premises: Premises) -> dict:
    """Gera/regenera os artefatos do workspace e retorna um resumo."""
    session.ensure()
    root = Path(session.project_path)

    (session.workspace / "tree.txt").write_text(
        render_tree(root) + "\n", encoding="utf-8"
    )

    files = scan_project(root, premises)
    (session.workspace / "dependencies.json").write_text(
        json.dumps(files, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    for old in session.asts.glob("*"):
        if old.is_file():
            old.unlink()
    ast_count = _write_asts(session, premises)

    return {
        "tree": render_tree(root),
        "num_files": len(files),
        "ast_files": ast_count,
        "dependencies": files,
    }


def artifacts_summary(result: dict, max_lines: int = 80) -> str:
    """Resumo enxuto dos artefatos para o prompt do agente."""
    tree = (result.get("tree") or "").splitlines()[:max_lines]
    num = result.get("num_files") or 0
    ast = result.get("ast_files") or 0
    summary = [
        f"Arquivos indexados: {num} | Esqueletos AST: {ast}",
        "Tree (primeiras linhas):",
    ]
    summary.extend(f"  {line}" for line in tree)
    return "\n".join(summary)