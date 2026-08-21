import asyncio
import json
import uuid

import websockets

SYSTEM_PROMPT = "Você é o motor CapoeiraCode. Responda APENAS em formato JSON válido."

# RNF-02: apenas origens de extensões de navegador e das páginas de LLM suportadas.
ALLOWED_ORIGIN_PREFIXES = ("chrome-extension://", "moz-extension://")
ALLOWED_PAGE_ORIGINS = frozenset(
    {
        "https://gemini.google.com",
        "https://claude.ai",
        "https://chatgpt.com",
        "https://chat.openai.com",
        "https://copilot.microsoft.com",
    }
)


def _origin_allowed(origin: str | None) -> bool:
    if not origin:
        return False
    if origin.startswith(ALLOWED_ORIGIN_PREFIXES):
        return True
    return origin in ALLOWED_PAGE_ORIGINS


class CapoeiraServer:
    """Servidor WebSocket local (ws://127.0.0.1:8765) que faz a ponte CLI <-> extensão."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self.active_socket = None
        self.connected = asyncio.Event()
        self._pending: dict[str, asyncio.Future] = {}

    # ------------------------------------------------------------------
    # Conexão
    # ------------------------------------------------------------------
    @staticmethod
    def _extract_origin(websocket) -> str | None:
        request = getattr(websocket, "request", None)
        if request is not None:  # websockets asyncio (novo)
            return request.headers.get("Origin")
        headers = getattr(websocket, "request_headers", None)  # websockets legacy
        return headers.get("Origin") if headers else None

    async def handler(self, websocket):
        origin = self._extract_origin(websocket)
        if not _origin_allowed(origin):
            print(f"\n[CapoeiraCode Bridge] Conexão REJEITADA (Origin: {origin!r}).")
            await websocket.close(code=1008, reason="Origin nao autorizada")
            return

        self.active_socket = websocket
        self.connected.set()
        print(f"\n[CapoeiraCode Bridge] Extensão conectada! (Origin: {origin})")
        try:
            async for message in websocket:
                self._handle_message(message)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            if self.active_socket is websocket:
                self.active_socket = None
                self.connected.clear()
            print("\n[CapoeiraCode Bridge] Conexão encerrada.")

    def _handle_message(self, message: str) -> None:
        try:
            data = json.loads(message)
        except json.JSONDecodeError:
            print("\n[CapoeiraCode Bridge] Mensagem não-JSON ignorada.")
            return

        if data.get("action") != "RESPONSE":
            return

        request_id = data.get("id")
        future = self._pending.get(request_id)
        if future is None and len(self._pending) == 1:
            # Tolerância: extensões antigas podem não ecoar o id.
            future = next(iter(self._pending.values()))
        if future is not None and not future.done():
            future.set_result(data.get("payload") or {})

    # ------------------------------------------------------------------
    # API usada pelo CLI
    # ------------------------------------------------------------------
    async def wait_for_extension(self, timeout: float | None = None) -> None:
        """Bloqueia até a extensão conectar (ou timeout, se informado)."""
        await asyncio.wait_for(self.connected.wait(), timeout)

    async def send_prompt_and_wait(
        self, prompt: str, provider: str = "gemini", timeout: float = 180.0
    ) -> str:
        if not self.active_socket:
            raise ConnectionError("Nenhuma extensão conectada via WebSocket.")

        request_id = str(uuid.uuid4())
        payload = {
            "version": "1.0",
            "id": request_id,
            "action": "SEND_PROMPT",
            "payload": {
                "provider": provider,
                "systemPrompt": SYSTEM_PROMPT,
                "prompt": prompt,
            },
        }

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        self._pending[request_id] = future
        try:
            await self.active_socket.send(json.dumps(payload))
            print("[CapoeiraCode CLI] Prompt enviado. Aguardando processamento...")
            response_payload = await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError as e:
            raise TimeoutError(
                f"Tempo limite de {timeout:.0f}s excedido aguardando a resposta do LLM."
            ) from e
        finally:
            self._pending.pop(request_id, None)

        return response_payload.get("rawResponse", "")

    async def start(self):
        return await websockets.serve(self.handler, self.host, self.port)
