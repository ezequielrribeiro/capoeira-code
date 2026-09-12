"""Workspace e histórico de sessões por projeto no diretório de config do CapoeiraCode.

Layout com múltiplas sessões por projeto:

    configs/<slug>/workspace/...            # artefatos de scan (compartilhados por projeto)
    configs/<slug>/sessions/<nome>/session.jsonl   # histórico de UMA sessão

O layout legado (uma sessão por projeto: `configs/<slug>/session.jsonl`) é migrado para
`configs/<slug>/sessions/default/session.jsonl` na primeira operação.
"""

import json
import os
import re
import shutil
from pathlib import Path

from ..project.premises import resolve_config_dir

DEFAULT_SESSION = "default"


def slugify(project_path: str) -> str:
    """Slug estável para o nome do projeto (baseado no nome do diretório)."""
    name = Path(project_path).resolve().name or "projeto"
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", name).strip("-.").lower()
    return slug or "projeto"


def name_slug(name: str) -> str:
    """Slug para nome de sessão (dado pelo usuário, NÃO é caminho)."""
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", name or "").strip("-.").lower()
    return slug or DEFAULT_SESSION


def workspace_dir(config_dir: Path, project_path: str) -> Path:
    return Path(config_dir) / "configs" / slugify(project_path)


class Session:
    """Gerencia workspace (compartilhado) e histórico de UMA sessão por projeto.

    Passa de uma sessão única para **N sessões**: cada `Session` aponta para
    `configs/<slug>/sessions/<nome>/session.jsonl`, enquanto os artefatos de scan
    ficam em `configs/<slug>/workspace/` (compartilhados entre sessões).
    """

    def __init__(
        self,
        config_dir: Path | None = None,
        project_path: str | None = None,
        name: str | None = None,
    ):
        self.project_path = str(Path(project_path or os.getcwd()).resolve())
        self.project_dir = workspace_dir(config_dir or resolve_config_dir(), self.project_path)
        self.name = name_slug(name) if name else DEFAULT_SESSION
        self.dir = self.project_dir / "sessions" / self.name
        self.workspace = self.project_dir / "workspace"
        self.history_file = self.dir / "session.jsonl"
        self.premises_file = self.project_dir / "premises.yaml"
        self.asts = self.workspace / "asts"

    # ------------------------------------------------------------------
    # Estrutura
    # ------------------------------------------------------------------
    def ensure(self) -> None:
        """Cria os diretórios da sessão (e migra o legado, se houver)."""
        self._migrate_legacy()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.asts.mkdir(parents=True, exist_ok=True)

    def _migrate_legacy(self) -> None:
        """`configs/<slug>/session.jsonl` (uma sessão por projeto) → sessions/default/."""
        if self.name != DEFAULT_SESSION:
            return
        legacy = self.project_dir / "session.jsonl"
        target = self.dir / "session.jsonl"
        if legacy.is_file() and not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            legacy.replace(target)

    def reset(self) -> None:
        """Apaga o histórico da sessão ATUAL e recria os diretórios.

        Os artefatos de scan (workspace/asts) são compartilhados entre sessões e
        não são apagados.
        """
        self._migrate_legacy()
        if self.dir.is_dir():
            shutil.rmtree(self.dir, ignore_errors=True)
        if self.premises_file.is_file():
            self.premises_file.unlink()
        self.ensure()

    @staticmethod
    def list_sessions(config_dir: Path, project_path: str) -> list[str]:
        """Nomes das sessões salvas do projeto (com histórico) + o legado 'default'."""
        pdir = workspace_dir(config_dir or resolve_config_dir(), project_path)
        names: set[str] = set()
        sessions_dir = pdir / "sessions"
        if sessions_dir.is_dir():
            for child in sessions_dir.iterdir():
                if child.is_dir() and (child / "session.jsonl").is_file():
                    names.add(child.name)
        if (pdir / "session.jsonl").is_file():
            names.add(DEFAULT_SESSION)
        return sorted(names)

    # ------------------------------------------------------------------
    # Histórico da conversa (jsonl: {role, content, ts})
    # ------------------------------------------------------------------
    def record(self, role: str, content: str, tool_name: str | None = None, tool_call_id: str | None = None) -> None:
        self._migrate_legacy()
        self.dir.mkdir(parents=True, exist_ok=True)
        entry = {"role": role, "content": content, "ts": None}
        if tool_name is not None:
            entry["tool_name"] = tool_name
        if tool_call_id is not None:
            entry["tool_call_id"] = tool_call_id
        with open(self.history_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def load_messages(self) -> list[dict]:
        """Mensagens persistidas na ordem: role user|assistant|tool."""
        self._migrate_legacy()
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
                if data.get("role") in ("user", "assistant", "tool"):
                    msg = {"role": data["role"], "content": data["content"]}
                    if data.get("tool_name"):
                        msg["tool_name"] = data["tool_name"]
                    if data.get("tool_call_id"):
                        msg["tool_call_id"] = data["tool_call_id"]
                    messages.append(msg)
        return messages

    @property
    def has_history(self) -> bool:
        self._migrate_legacy()
        return self.history_file.is_file() and bool(self.load_messages())

    def summarize(self) -> str:
        return (
            f"Projeto: {self.project_path}\n"
            f"Sessão: {self.name} ({self.dir})\n"
            f"Workspace: {self.workspace}"
        )