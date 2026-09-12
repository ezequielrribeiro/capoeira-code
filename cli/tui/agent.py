"""Loop do agente: envia contexto, interpreta tool calls e executa ferramentas."""

import base64
import binascii
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
    """Executa um turno interativo até `done`, limite de turnos ou interrupção.

    Stateless: cada requisição envia o **histórico completo** (sistema + últimas
    `MAX_CONTEXT_MESSAGES`) e o host abre uma conversa nova por request — sem
    reutilizar um chat aberto na aba.
    """

    def __init__(self, session: Session, options: AgentOptions, client):
        self.session = session
        self.options = options
        self.client = client
        self.gate = PermissionGate(options.mode)
        self.messages = session.load_messages()
        self._fallback_seq = 0

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

    def _add_tool(self, name: str, content: str, tool_call_id: str | None = None) -> None:
        msg = {"role": "tool", "tool_name": name, "content": content}
        if tool_call_id:
            msg["tool_call_id"] = tool_call_id
        self.messages.append(msg)
        self.session.record("tool", content, tool_name=name, tool_call_id=tool_call_id)

    def reset_messages(self) -> list[dict]:
        """Recarrega o histórico da sessão após o `/reset` da TUI."""
        self.messages = self.session.load_messages()
        return self.messages

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

            # Protocolo textual do CapoeiraHost: a resposta é texto puro, com
            # linhas `[TOOL_CALL] nome | chave=valor` para chamadas de ferramenta
            # (uma por linha) ou prosa final (encerra o turno).
            raw = reply.content or ""
            steps = _parse_tool_call_lines(raw)
            if steps:
                lines = _extract_tool_call_lines(raw) or []
                self._add("assistant", "\n".join(lines))
                for index, step in enumerate(steps):
                    ended = self._run_step(step, ask_user, ask_permission, tool_call_id=f"call_{index}")
                    if ended is not None:
                        return ended
                continue

            message = _unwrap_text(raw) or "Concluído."
            self._add("user", f"[sistema] Turno encerrado. {message}".strip())
            return {"done": True, "message": message}

        self._add("user", "[sistema] Limite de turnos atingido sem 'done'. Encerrado.")
        return {"done": False, "message": f"Limite de {opts.max_turns} turnos atingido."}

    def _run_step(self, step: dict, ask_user, ask_permission, tool_call_id: str | None = None):
        """Executa um passo de ferramenta e devolve o resultado (role:"tool").

        Retorna dict se o turno encerrou, senão None. Todo resultado carrega um
        `tool_call_id` (nativo `call_N` ou gerado para linhas `[TOOL_CALL]`) — o
        transcript do host renderiza `[TOOL_RESULT] (id) ...`.
        """
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

        if step.get("_truncated"):
            output = (
                f"[FERRAMENTA {tool}] {description}\n"
                "ERRO: argumento truncado no contrato textual do host (valor com aspas não "
                "fechadas). Reenvie a chamada em UMA linha, sem Enter real no conteúdo."
            )
            if tool_call_id is None:
                self._fallback_seq += 1
                tool_call_id = f"call_{self._fallback_seq}"
            self._add_tool(tool, output, tool_call_id=tool_call_id)
            return None

        if tool in ("write_file", "run_python"):
            key = "code_content" if tool == "write_file" else "code"
            raw = str(step.get(key) or "").strip()
            if not raw:
                output = (
                    f"[FERRAMENTA {tool}] {description}\n"
                    f"ERRO: {key} vazio. Reenvie a chamada com o {key} em base64 válido."
                )
                if tool_call_id is None:
                    self._fallback_seq += 1
                    tool_call_id = f"call_{self._fallback_seq}"
                self._add_tool(tool, output, tool_call_id=tool_call_id)
                return None
            decoded = _decode_b64(raw)
            if decoded is None:
                output = (
                    f"[FERRAMENTA {tool}] {description}\n"
                    f"ERRO: {key} não é base64 válido. Reenvie o conteúdo codificado em base64 "
                    "(A-Za-z0-9+/=, bloco contínuo, sem quebras de linha)."
                )
                if tool_call_id is None:
                    self._fallback_seq += 1
                    tool_call_id = f"call_{self._fallback_seq}"
                self._add_tool(tool, output, tool_call_id=tool_call_id)
                return None
            step[key] = decoded

        result = apply_step(step, self.options.cwd, python=self.options.python, timeout=self.options.timeout)
        output = f"[FERRAMENTA {tool}] {description}\n{result.output if result.ok else f'ERRO: {result.output}'}"
        if tool_call_id is None:
            self._fallback_seq += 1
            tool_call_id = f"call_{self._fallback_seq}"
        self._add_tool(tool, output, tool_call_id=tool_call_id)
        return None


_TOOL_CALL_LINE = re.compile(r"(?m)^[ \t]*\[TOOL_CALL\][ \t]+(.*)$")


def _extract_tool_call_lines(raw: str) -> list[str]:
    """Retorna as linhas `[TOOL_CALL]` originais do texto do host.

    Uma linha é candidata se começar (com opcional indentação) em `[TOOL_CALL]`.
    A validação de conteúdo (nome/args) acontece em `_parse_tool_call_lines`.
    """
    return [m.group(0).strip() for m in _TOOL_CALL_LINE.finditer(raw or "")]


def _split_pipe_fields(text: str) -> list[str]:
    """Divide o texto em campos separados por `|` que NÃO estejam dentro de aspas
    simples (com escape `\'`). Um `|` dentro de `'...'` é literal — permite valores
    como `cmd='grep a || grep b'` e `code_content='...|...'` sem quebrar a chamada.
    """
    fields: list[str] = []
    buf: list[str] = []
    in_q = False
    esc = False
    for ch in text or "":
        if in_q:
            if esc:
                buf.append(ch)
                esc = False
            elif ch == "\\":
                buf.append(ch)
                esc = True
            elif ch == "'":
                in_q = False
                buf.append(ch)
            else:
                buf.append(ch)
            continue
        if ch == "'":
            in_q = True
            buf.append(ch)
        elif ch == "|":
            fields.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    fields.append("".join(buf).strip())
    return fields


def _parse_args(args_text: str) -> dict | None:
    """Converte `| chave1=valor1 | chave2=valor2` em dict.

    Separa campos com `_split_pipe_fields` (pipe dentro de aspas é literal) e
    tolera espaços ao redor do `=`. Se algum campo não for `chave=valor`, a linha
    é malformada e retorna `None`. Valores com aspas abertas e não fechadas
    (conteúdo cortado no meio) são sinalizados como `_truncated`.
    """
    args_text = (args_text or "").strip()
    if not args_text.startswith("|"):
        return {} if not args_text else None
    args: dict = {}
    truncated = False
    for field in _split_pipe_fields(args_text[1:]):
        field = field.strip()
        if not field:
            continue
        if "=" not in field:
            return None
        key, _, value = field.partition("=")
        key = key.strip()
        raw = value.strip()
        if raw.startswith("'") and not raw.endswith("'"):
            truncated = True
        args[key] = _parse_value(raw)
    if truncated:
        args["_truncated"] = True
    return args


def _parse_tool_call_lines(raw: str) -> list[dict] | None:
    """Converte o contrato `[TOOL_CALL] nome | chave=valor` do host em steps.

    Prosa ao redor é ignorada, linhas malformadas (nome vazio ou campo sem `=`)
    são descartadas e o nome é normalizado para o interno das ferramentas.
    """
    steps: list[dict] = []
    for line in _extract_tool_call_lines(raw or ""):
        match = _TOOL_CALL_LINE.match(line)
        if not match:
            continue
        rest = match.group(1).strip()
        parts = rest.split(None, 1)
        if not parts or not parts[0]:
            continue
        name = parts[0]
        args_text = parts[1] if len(parts) > 1 else ""
        args = _parse_args(args_text)
        if args is None:
            continue
        step = {"tool": _normalize_tool_name(name)}
        step.update({k: v for k, v in args.items() if v is not None})
        steps.append(step)
    return steps or None


def _parse_value(value: str):
    """Converte um valor do contrato textual (`chave=valor`) para o tipo interno.

    Strings com aspas simples ficam literais (com escapes `\\n` etc. decodificados via
    `_unescape`); números, booleanos e estruturas `[...]`/`{...}` são convertidos (o
    modelo pode valorar 2, true ou listas como `[1, 120]`, com ou sem aspas).
    """
    if len(value) >= 2 and value.startswith("'") and value.endswith("'"):
        value = value[1:-1]
    value = _unescape(value)
    if value in ("true", "True"):
        return True
    if value in ("false", "False"):
        return False
    if value in ("null", "None"):
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    if value[:1] in ("[", "{"):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass
    return value


_ESCAPES = {"n": "\n", "r": "\r", "t": "\t", "'": "'", '"': '"', "\\": "\\"}


def _unescape(value: str) -> str:
    """Decodifica sequências de escape conhecidas (`\\n`, `\\r`, `\\t`, `\\'`, `\\"`, `\\\\`).

    Sequências desconhecidas (`\\d`, etc.) ficam intactas; `\\\\n` vira a barra literal
    seguida de `n` (não vira quebra de linha).
    """
    return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), m.group(0)), value)


def _decode_b64(value: str) -> str | None:
    """Decodifica um valor base64 estrito (A-Za-z0-9+/=, sem quebras de linha) para texto.

    `None` se o valor for inválido/truncado (tamanho não múltiplo de 4, charset, padding
    ou bytes que não formam UTF-8) — nesse caso o agente NÃO grava/executa e o modelo
    reenvia.
    """
    if not value or len(value) % 4 != 0:
        return None
    try:
        raw = base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        return None
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _describe(step: dict) -> str:
    tool = step.get("tool", "?")
    path = step.get("path") or step.get("cmd") or step.get("question") or ""
    action = f" [{step['action']}]" if step.get("action") else ""
    return f"{tool}{action} {path}".strip()


def _unwrap_text(raw: str) -> str:
    """Desenvolve o contrato `{"text": "..."}` do CapoeiraHost (back-compat).

    O contrato v2.0 do host entrega prosa pura no fallback; versões antigas
    podiam entregar o JSON `{"text": "..."}` literal. Aceita ambos.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip("`").strip()
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return text
    if isinstance(payload, dict) and "text" in payload:
        return str(payload["text"])
    return text


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