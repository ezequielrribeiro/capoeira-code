import json
import urllib.error
import urllib.request

DEFAULT_BASE_URL = "http://127.0.0.1:8765"
DEFAULT_MODEL = "gemini-pro"
DEFAULT_TIMEOUT = 180.0

SYSTEM_PROMPT = "Você é o motor CapoeiraCode. Responda APENAS em formato JSON válido."


class LLMClient:
    """Cliente HTTP/JSON compatível com a API `/api/chat` do Ollama.

    Funciona com o Ollama nativo (`http://127.0.0.1:11434`) e com gateways
    Ollama-compatíveis como o CapoeiraHost (`http://127.0.0.1:8765`).
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
        body = {
            "model": self.model,
            "stream": False,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt},
            ],
        }
        return self.chat_messages(body["messages"])

    def chat_messages(
        self,
        messages: list[dict],
        stream: bool = False,
        on_chunk=None,
    ) -> str:
        """Envia uma conversa (roles system/user/assistant) e retorna a resposta.

        Com `stream=True` (NDJSON do Ollama), lê as respostas incrementalmente,
        acumula `message.content` e chama `on_chunk(texto)` para cada fragmento.
        """
        body = {
            "model": self.model,
            "stream": bool(stream),
            "messages": messages,
        }
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(body).encode("utf8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                if not stream:
                    raw = resp.read().decode("utf8")
                else:
                    return self._read_stream(resp, on_chunk)
        except urllib.error.HTTPError as e:
            raise LLMRequestError(self._http_error_message(e)) from e
        except urllib.error.URLError as e:
            raise LLMRequestError(f"Não foi possível conectar em {self.base_url}: {e.reason}") from e

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise LLMRequestError(f"Resposta não-JSON do backend: {e}") from e

        message = data.get("message") or {}
        content = message.get("content") or ""
        if not content:
            raise LLMRequestError("O backend retornou uma resposta sem conteúdo.")
        return content

    @staticmethod
    def _read_stream(resp, on_chunk) -> str:
        """Lê a resposta streaming (uma linha JSON NDJSON por chunk) e acumula."""
        parts: list[str] = []
        for raw_line in resp:
            line = raw_line.decode("utf8", errors="replace").strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            content = ((data.get("message") or {}).get("content")) or ""
            if content:
                parts.append(content)
                if on_chunk is not None:
                    on_chunk(content)
        return "".join(parts)

    @staticmethod
    def _http_error_message(error: urllib.error.HTTPError) -> str:
        status = error.code
        body = error.read().decode("utf8", errors="replace")
        detail = ""
        if body:
            try:
                detail = json.loads(body).get("error", "")
            except json.JSONDecodeError:
                detail = body.strip()
        base = f"Erro {status} do backend LLM em {error.url}"
        if detail:
            base += f": {detail}"
        return base


class LLMRequestError(Exception):
    """Falha na comunicação (conexão, status HTTP ou resposta inválida)."""