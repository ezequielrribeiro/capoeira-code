"""Loop do agente: envia contexto, interpreta `steps` e executa ferramentas."""

import json
import re
from dataclasses import dataclass

from ..llm_client import LLMRequestError
from ..prompts import build_agent_system_prompt
from ..instruction.loader import render_project_profile
from .permissions import PermissionGate
from .session import Session
from .tools import apply_step

MAX_CONTEXT_MESSAGES = 40
INVALID_FORMAT_NOTE = (
    "[sistema] Sua resposta não veio no formato esperado. Responda SEMPRE com um "
    'JSON contendo "steps": [ {tool, ...}, ... ], finalizando com um passo "done".'
)


@dataclass
class AgentOptions:
    premises: object
    instruction_set: object
    artifacts_summary: str = ""
    cwd: str = "."
    python: str | None = None
    timeout: float = 120.0
    max_turns: int = 20
    mode: str = "ask"


class AgentRun:
    """Executa um turno interativo até `done`, limite de turnos ou interrupção."""

    def __init__(self, session: Session, options: AgentOptions, client):
        self.session = session
        self.options = options
        self.client = client
        self.gate = PermissionGate(options.mode)
        self.messages = session.load_messages()

    # ------------------------------------------------------------------
    # Prompt / chat
    # ------------------------------------------------------------------
    def _system_prompt(self) -> str:
        opts = self.options
        profile = render_project_profile(opts.premises)
        specs = opts.instruction_set.specs_combined if opts.instruction_set else ""
        skills = opts.instruction_set.skills_combined if opts.instruction_set else ""
        return build_agent_system_prompt(profile, specs=specs, skills=skills, artifacts=opts.artifacts_summary)

    def _build_prompt_messages(self) -> list[dict]:
        history = self.messages[-MAX_CONTEXT_MESSAGES:]
        return [{"role": "system", "content": self._system_prompt()}] + history

    def _chat_once(self) -> str:
        return self.client.chat_messages(self._build_prompt_messages())

    # ------------------------------------------------------------------
    # Registro
    # ------------------------------------------------------------------
    def _add(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})
        self.session.record(role, content)

    # ------------------------------------------------------------------
    # Execução do turno
    # ------------------------------------------------------------------
    def run(self, user_prompt: str, ask_user, ask_permission) -> dict:
        self._add("user", user_prompt)
        opts = self.options

        for turn in range(1, opts.max_turns + 1):
            try:
                raw = self._chat_once()
            except LLMRequestError as e:
                self._add("user", f"[sistema] Erro de comunicação com o backend: {e}")
                return {"done": False, "message": str(e)}

            self._add("assistant", raw)
            steps = _parse_steps(raw)
            if steps is None:
                self._add("user", INVALID_FORMAT_NOTE)
                continue

            for step in steps:
                tool = step.get("tool", "")
                if tool == "done":
                    message = step.get("message", "")
                    self._add("user", f"[sistema] Turno encerrado. {message}".strip())
                    return {"done": True, "message": message}

                if tool == "ask_user":
                    question = step.get("question", "?")
                    answer = ask_user(question)
                    self._add("user", f"[RESPOSTA DO USUÁRIO]\n{answer}")
                    continue

                description = _describe(step)
                if not self.gate.allow(tool, description, ask_permission):
                    self._add("user", f"[FERRAMENTA NÃO AUTORIZADA] {tool}: {description}")
                    continue

                result = apply_step(step, opts.cwd, python=opts.python, timeout=opts.timeout)
                self._add(
                    "user",
                    f"[FERRAMENTA {tool}] {description}\n{result.output if result.ok else f'ERRO: {result.output}'}",
                )

        self._add("user", "[sistema] Limite de turnos atingido sem 'done'. Encerrado.")
        return {"done": False, "message": f"Limite de {opts.max_turns} turnos atingido."}


def _parse_steps(raw: str) -> list[dict] | None:
    if not raw or not raw.strip():
        return None
    text = raw.strip()
    if "```" in text:
        match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
    start = text.find("{")
    if start == -1:
        return None
    try:
        data, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if isinstance(data.get("steps"), list):
        return [s for s in data["steps"] if isinstance(s, dict)]
    if isinstance(data.get("tool"), str):
        return [data]
    return None


def _describe(step: dict) -> str:
    tool = step.get("tool", "?")
    path = step.get("path") or step.get("cmd") or step.get("question") or ""
    action = f" [{step['action']}]" if step.get("action") else ""
    return f"{tool}{action} {path}".strip()