"""Loop do agente: envia contexto, interpreta `steps` e executa ferramentas."""

import json
import re
from dataclasses import dataclass

from ..llm_client import ChatReply, LLMRequestError
from ..instruction.loader import render_project_profile
from ..prompts import TOOLS_DECLARATION, build_agent_system_prompt
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
    on_chunk=None


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
        instr = opts.instruction_set
        specs = instr.specs_combined if instr else ""
        skills = instr.skills_combined if instr else ""
        blueprints = instr.blueprints_combined if instr else ""
        return build_agent_system_prompt(
            profile,
            specs=specs,
            skills=skills,
            artifacts=opts.artifacts_summary,
            blueprints=blueprints,
        )

    def _build_prompt_messages(self) -> list[dict]:
        history = self.messages[-MAX_CONTEXT_MESSAGES:]
        return [{"role": "system", "content": self._system_prompt()}] + history

    def _chat_once(self) -> "ChatReply":
        msgs = self._build_prompt_messages()
        streaming = self.options.on_chunk is not None
        return self.client.chat_messages(
            msgs,
            stream=streaming,
            on_chunk=self.options.on_chunk,
            tools=TOOLS_DECLARATION,
        )

    # ------------------------------------------------------------------
    # Registro
    # ------------------------------------------------------------------
    def _add(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})
        self.session.record(role, content)

    def _add_tool(self, name: str, content: str) -> None:
        self.messages.append({"role": "tool", "tool_name": name, "content": content})
        self.session.record("tool", content, tool_name=name)

    # ------------------------------------------------------------------
    # Execução do turno
    # ------------------------------------------------------------------
    def run(self, user_prompt: str, ask_user, ask_permission) -> dict:
        self._add("user", user_prompt)
        opts = self.options

        for turn in range(1, opts.max_turns + 1):
            try:
                reply = self._chat_once()
            except LLMRequestError as e:
                self._add("user", f"[sistema] Erro de comunicação com o backend: {e}")
                return {"done": False, "message": str(e)}

            if reply.has_tool_calls:
                calls = reply.tool_calls or []
                if reply.content:
                    self._add("assistant", reply.content)
                else:
                    self.messages.append({"role": "assistant", "tool_calls": [c["name"] for c in calls]})
                    self.session.record(
                        "assistant",
                        json.dumps([(c.get("name"), c.get("arguments")) for c in calls], ensure_ascii=False),
                    )
                for call in calls:
                    step = _tool_call_to_step(call)
                    ended = self._run_step(step, ask_user, ask_permission, native=True)
                    if ended is not None:
                        return ended
                continue

            raw = reply.content
            if not raw:
                self._add("user", INVALID_FORMAT_NOTE)
                continue
            steps = _parse_steps(raw)
            if steps is None:
                self._add("user", INVALID_FORMAT_NOTE)
                continue

            for step in steps:
                ended = self._run_step(step, ask_user, ask_permission)
                if ended is not None:
                    return ended

        self._add("user", "[sistema] Limite de turnos atingido sem 'done'. Encerrado.")
        return {"done": False, "message": f"Limite de {opts.max_turns} turnos atingido."}

    def _run_step(self, step: dict, ask_user, ask_permission, native: bool = False):
        """Executa um passo (steps simulado ou tool_call nativo). Retorna dict se
        o turno encerrou, senão None. Com `native=True` o resultado vira mensagem
        `role:"tool"` (formato Ollama); no modo simulado permanece `role:"user"`."""
        tool = step.get("tool", "")
        if tool == "done":
            message = step.get("message", "")
            self._add("user", f"[sistema] Turno encerrado. {message}".strip())
            return {"done": True, "message": message}

        if tool == "ask_user":
            question = step.get("question", "?")
            answer = ask_user(question)
            self._add("user", f"[RESPOSTA DO USUÁRIO]\n{answer}")
            return None

        description = _describe(step)
        if not self.gate.allow(tool, description, ask_permission):
            self._add("user", f"[FERRAMENTA NÃO AUTORIZADA] {tool}: {description}")
            return None

        result = apply_step(step, self.options.cwd, python=self.options.python, timeout=self.options.timeout)
        output = f"[FERRAMENTA {tool}] {description}\n{result.output if result.ok else f'ERRO: {result.output}'}"
        if native:
            self._add_tool(tool, output)
        else:
            self._add("user", output)
        return None


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


def _tool_call_to_step(call: dict) -> dict:
    """Converte um tool_call nativo `{name, arguments}` no formato `{tool, ...}`."""
    name = _normalize_tool_name(call.get("name", ""))
    arguments = call.get("arguments") or {}
    step = {"tool": name}
    step.update({k: v for k, v in arguments.items() if v is not None})
    return step


def _normalize_tool_name(name: str) -> str:
    """Ajusta variações de nome do backend para os nomes internos das ferramentas."""
    mapping = {
        "list_dir": "list_dir",
        "list_directory": "list_dir",
        "read_file": "read_file",
        "read": "read_file",
        "run_shell": "run_shell",
        "run_command": "run_shell",
        "shell": "run_shell",
        "run_python": "run_python",
        "python": "run_python",
        "write_file": "write_file",
        "write": "write_file",
        "create_file": "write_file",
        "ask_user": "ask_user",
        "ask": "ask_user",
        "done": "done",
    }
    return mapping.get(name, name)