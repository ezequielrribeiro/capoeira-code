"""Executores de ferramentas do agente (leitura, shell/python, escrita via applier)."""

import json
import os
import subprocess
from dataclasses import dataclass

from ..applier import ChangeApplier

OUTPUT_LIMIT = 8000


@dataclass
class ToolResult:
    ok: bool
    output: str


def _truncate(text: str, limit: int = OUTPUT_LIMIT) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... (saída truncada em {limit} caracteres)"


def _resolve(path: str, cwd: str) -> str:
    p = os.path.abspath(path) if os.path.isabs(path) else os.path.abspath(os.path.join(cwd, path))
    return os.path.normpath(p)


def read_file(path: str, cwd: str, lines: list[int] | None = None) -> ToolResult:
    full = _resolve(path, cwd)
    if not os.path.isfile(full):
        return ToolResult(False, f"Arquivo não encontrado: {path}")
    try:
        with open(full, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError as e:
        return ToolResult(False, f"Falha ao ler {path}: {e}")
    if lines:
        start, end = lines
        content_lines = content.splitlines()
        start = max(1, start)
        end = min(len(content_lines), end) if end else len(content_lines)
        content = "\n".join(content_lines[start - 1 : end])
    return ToolResult(True, _truncate(content))


def list_dir(path: str, cwd: str) -> ToolResult:
    full = _resolve(path, cwd)
    if not os.path.isdir(full):
        return ToolResult(False, f"Diretório não encontrado: {path}")
    try:
        entries = sorted(os.listdir(full))
    except OSError as e:
        return ToolResult(False, f"Falha ao listar {path}: {e}")
    lines = []
    for name in entries:
        p = os.path.join(full, name)
        kind = "D" if os.path.isdir(p) else "F"
        size = os.path.getsize(p) if os.path.isfile(p) and os.access(p, os.R_OK) else 0
        lines.append(f"{kind} {size:>10} {name}")
    return ToolResult(True, _truncate("\n".join(lines) if lines else "(vazio)"))


def run_shell(cmd: str, cwd: str, timeout: float = 120.0) -> ToolResult:
    if not cmd or not cmd.strip():
        return ToolResult(False, "Comando vazio.")
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as e:
        return ToolResult(False, f"Comando não encontrado: {e}")
    except subprocess.TimeoutExpired:
        return ToolResult(False, f"Timeout após {timeout:.0f}s executando: {cmd}")
    output = proc.stdout or ""
    if proc.stderr:
        output += ("" if not output else "\n") + "[stderr]\n" + proc.stderr
    output = f"(exit={proc.returncode})\n{output}".strip()
    return ToolResult(True, _truncate(output))


def run_python(code: str, cwd: str, python: str | None = None, timeout: float = 120.0) -> ToolResult:
    if not code or not code.strip():
        return ToolResult(False, "Código vazio.")
    exe = python or "python"
    try:
        proc = subprocess.run(
            [exe, "-c", code],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as e:
        return ToolResult(False, f"Interpretador não encontrado ({exe}): {e}")
    except subprocess.TimeoutExpired:
        return ToolResult(False, f"Timeout após {timeout:.0f}s executando o trecho Python.")
    output = proc.stdout or ""
    if proc.stderr:
        output += ("" if not output else "\n") + "[stderr]\n" + proc.stderr
    output = f"(exit={proc.returncode})\n{output}".strip()
    return ToolResult(True, _truncate(output))


def write_file(step: dict, cwd: str) -> ToolResult:
    rel = step.get("path", "")
    action = step.get("action", "create_file")
    payload = {
        "file_path": _resolve(rel, cwd),
        "action": action,
        "target_symbol": step.get("target_symbol"),
        "code_content": step.get("code_content", ""),
        "explanation": step.get("explanation", "agente"),
    }
    result = ChangeApplier.apply_payload(json.dumps(payload), expected_file_path=payload["file_path"])
    if not result.ok:
        return ToolResult(False, result.error)
    return ToolResult(True, result.message)


def apply_step(step: dict, cwd: str, python: str | None = None, timeout: float = 120.0) -> ToolResult:
    """Executa um passo de ferramenta (sem checar permissões — a cargo do agente)."""
    tool = step.get("tool", "")
    try:
        if tool == "read_file":
            return read_file(step.get("path", ""), cwd, step.get("lines"))
        if tool == "list_dir":
            return list_dir(step.get("path", ""), cwd)
        if tool == "run_shell":
            return run_shell(step.get("cmd", ""), cwd, timeout)
        if tool == "run_python":
            return run_python(step.get("code", ""), cwd, python, timeout)
        if tool == "write_file":
            return write_file(step, cwd)
    except Exception as e:  # noqa: BLE001 - defesa do loop do agente
        return ToolResult(False, f"Erro ao executar {tool}: {e}")
    return ToolResult(False, f"Ferramenta desconhecida: {tool}")