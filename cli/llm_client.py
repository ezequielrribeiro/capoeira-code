import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

DEFAULT_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_MODEL = "gemini-pro"
DEFAULT_TIMEOUT = 180.0

SYSTEM_PROMPT = "Você é o motor CapoeiraCode. Responda APENAS em formato JSON válido."


@dataclass
class ChatReply:
    """Resposta do backend (texto puro): prosa final e/ou linhas [TOOL_CALL]."""

    content: str = ""


def _textual_prop_type(prop: dict) -> str:
    """Mapeia um tipo do JSON Schema de ferramenta para o contrato textual do host."""
    ptype = prop.get("type")
    if ptype == "integer":
        return "int"
    if ptype == "number":
        return "float"
    if ptype == "boolean":
        return "bool"
    if ptype == "array":
        items_type = (prop.get("items") or {}).get("type")
        if items_type == "integer":
            return "int[]"
        if items_type == "number":
            return "float[]"
        return f"{items_type or 'string'}[]"
    return "string"


def serialize_tools(tools) -> str:
    """Serializa declarações de ferramentas (JSON schema) no contrato textual do host.

    Cada ferramenta vira uma linha `name=X | desc=... | arg:type` (uma por linha),
    como o campo `tools` de `/api/chat` espera.
    """
    lines: list[str] = []
    for tool in tools or []:
        fn = tool.get("function") if isinstance(tool, dict) else None
        if not isinstance(fn, dict):
            continue
        name = fn.get("name", "")
        if not name:
            continue
        parts = [f"name={name}"]
        desc = (fn.get("description") or "").replace("\n", " ").strip()
        if desc:
            parts.append(f"desc={desc}")
        for key, prop in ((fn.get("parameters") or {}).get("properties") or {}).items():
            parts.append(f"{key}:{_textual_prop_type(prop)}")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


class LLMClient:
    """Cliente HTTP do CapoeiraHost (protocolo textual, API `POST /api/chat`).

    O CapoeiraHost (`http://127.0.0.1:8765`, default) é o único backend e usa
    `application/x-www-form-urlencoded` com resposta `text/plain` (fora do padrão
    Ollama). Stateless: cada requisição é autocontida (histórico completo) e o host
    cria uma conversa nova por request.
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT,
        system_prompt: str = SYSTEM_PROMPT,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.system_prompt = system_prompt

    def chat(self, prompt: str) -> str:
        """Envia um turno user e retorna o texto da resposta do modelo."""
        return self.chat_messages(
            [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ]
        ).content

    def chat_messages(
        self,
        messages: list[dict],
        stream: bool = False,
        on_chunk=None,
        tools=None,
    ) -> ChatReply:
        """Envia uma conversa (form-urlencoded) e retorna um `ChatReply` (texto).

        `messages` é o histórico completo (stateless): pares `role`/`content` na
        ordem; `role=tool` leva `tool_call_id`. Com `tools`, declara as ferramentas
        no contrato textual (tool calling simulado do host). Com `stream=True`, lê a
        resposta em texto puro e chama `on_chunk(texto)` por fragmento.
        """
        fields: list[tuple[str, str]] = [("model", self.model)]
        for message in messages:
            role = message.get("role", "")
            if not role:
                continue
            fields.append(("role", role))
            fields.append(("content", str(message.get("content") or "")))
            if role == "tool" and message.get("tool_call_id"):
                fields.append(("tool_call_id", str(message["tool_call_id"])))
        if tools is not None:
            fields.append(("tools", serialize_tools(tools)))
        fields.append(("stream", "true" if stream else "false"))

        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=urllib.parse.urlencode(fields).encode("utf8"),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                if stream:
                    return self._read_stream(resp, on_chunk)
                return ChatReply(content=resp.read().decode("utf8"))
        except urllib.error.HTTPError as e:
            raise LLMRequestError(self._http_error_message(e)) from e
        except urllib.error.URLError as e:
            raise LLMRequestError(f"Não foi possível conectar em {self.base_url}: {e.reason}") from e

    @staticmethod
    def _read_stream(resp, on_chunk) -> ChatReply:
        """Lê a resposta streaming (texto puro em chunks) e acumula o conteúdo."""
        parts: list[str] = []
        for raw_line in resp:
            line = raw_line.decode("utf8", errors="replace")
            if not line:
                continue
            parts.append(line)
            if on_chunk is not None:
                on_chunk(line)
        return ChatReply(content="".join(parts))

    @staticmethod
    def _http_error_message(error: urllib.error.HTTPError) -> str:
        status = error.code
        body = error.read().decode("utf8", errors="replace").strip()
        base = f"Erro {status} do backend LLM em {error.url}"
        if body:
            base += f": {body}"
        return base


class LLMRequestError(Exception):
    """Falha na comunicação (conexão, status HTTP ou resposta inválida)."""