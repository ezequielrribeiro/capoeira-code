"""Workspace de sessão por projeto no diretório de config do CapoeiraCode."""

import json
import os
import re
from pathlib import Path

from ..project.premises import resolve_config_dir


def slugify(project_path: str) -> str:
    """Slug estável para o nome do projeto (baseado no nome do diretório)."""
    name = Path(project_path).resolve().name or "projeto"
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", name).strip("-.").lower()
    return slug or "projeto"


def workspace_dir(config_dir: Path, project_path: str) -> Path:
    return Path(config_dir) / "configs" / slugify(project_path)


class Session:
    """Gerencia workspace + histórico (session.jsonl) de UMA sessão ativa por projeto."""

    def __init__(self, config_dir: Path | None = None, project_path: str | None = None):
        self.project_path = str(Path(project_path or os.getcwd()).resolve())
        self.dir = workspace_dir(config_dir or resolve_config_dir(), self.project_path)
        self.workspace = self.dir / "workspace"
        self.history_file = self.dir / "session.jsonl"
        self.premises_file = self.dir / "premises.yaml"
        self.asts = self.workspace / "asts"

    # ------------------------------------------------------------------
    # Estrutura
    # ------------------------------------------------------------------
    def ensure(self) -> None:
        """Cria os diretórios do workspace, se necessário."""
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.asts.mkdir(parents=True, exist_ok=True)

    def reset(self) -> None:
        """Limpa a sessão atual (apaga histórico e artefatos) e recria as pastas."""
        for path in (self.history_file, self.premises_file):
            if path.is_file():
                path.unlink()
        for child in list(self.dir.rglob("*")):
            if child.is_dir() and child != self.dir:
                import shutil

                shutil.rmtree(child, ignore_errors=True)
        for child in list(self.dir.iterdir()):
            if child.is_file():
                child.unlink()
        self.ensure()

    # ------------------------------------------------------------------
    # Histórico da conversa (jsonl: {role, content, ts})
    # ------------------------------------------------------------------
    def record(self, role: str, content: str) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        entry = {"role": role, "content": content, "ts": None}
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def load_messages(self) -> list[dict]:
        """Mensagens persistidas na ordem: [{'role': 'user'|'assistant', 'content': ...}]."""
        if not self.history_file.is_file():
            return []
        messages = []
        with open(self.history_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if data.get("role") in ("user", "assistant"):
                    messages.append({"role": data["role"], "content": data["content"]})
        return messages

    @property
    def has_history(self) -> bool:
        return self.history_file.is_file() and bool(self.load_messages())

    def summarize(self) -> str:
        return (
            f"Projeto: {self.project_path}\n"
            f"Sessão: {self.dir}\n"
            f"Workspace: {self.workspace}"
        )