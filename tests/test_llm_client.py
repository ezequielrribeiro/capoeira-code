import http.server
import threading
import urllib.parse

import pytest

from cli.llm_client import LLMClient, LLMRequestError, serialize_tools


class StubHandler(http.server.BaseHTTPRequestHandler):
    response_status = 200
    response_body = "ok"

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf8")
        self.server.last_raw = raw
        self.server.last_request = urllib.parse.parse_qs(raw, keep_blank_values=True)
        self.send_response(self.response_status)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(self.response_body.encode("utf8"))

    def log_message(self, *args):
        pass


@pytest.fixture()
def stub_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), StubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def _client(stub_server, model="gemini-pro"):
    StubHandler.response_status = 200
    StubHandler.response_body = "ok"
    port = stub_server.server_address[1]
    return LLMClient(base_url=f"http://127.0.0.1:{port}", model=model, timeout=5), StubHandler


def test_chat_retorna_conteudo_da_resposta_texto(stub_server):
    client, handler = _client(stub_server, model="claude-sonnet")
    handler.response_body = "Viveu no fim do século XIX."
    assert client.chat("refatore isso") == "Viveu no fim do século XIX."

    body = stub_server.last_request
    assert body["model"] == ["claude-sonnet"]
    assert body["stream"] == ["false"]
    assert body["role"] == ["system", "user"]
    assert "refatore isso" in body["content"][1]
    assert "new_chat" not in body


def test_chat_messages_serializa_pares_role_content_e_tool_call_id(stub_server):
    client, handler = _client(stub_server)
    client.chat_messages(
        [
            {"role": "user", "content": "preciso criar"},
            {"role": "assistant", "content": "[TOOL_CALL] write_file | path=a.php"},
            {"role": "tool", "content": "[FERRAMENTA write_file] ok", "tool_call_id": "call_0"},
        ]
    )
    body = stub_server.last_request
    assert body["role"] == ["user", "assistant", "tool"]
    assert body["content"] == ["preciso criar", "[TOOL_CALL] write_file | path=a.php", "[FERRAMENTA write_file] ok"]
    assert body["tool_call_id"] == ["call_0"]


def test_chat_messages_envia_tools_textual(stub_server):
    client, handler = _client(stub_server)
    tools = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Lê um arquivo.",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}, "lines": {"type": "array", "items": {"type": "integer"}}},
                    "required": ["path"],
                },
            },
        }
    ]
    client.chat_messages([{"role": "user", "content": "oi"}], tools=tools)
    assert "new_chat" not in stub_server.last_request
    text = stub_server.last_request["tools"][0]
    assert "name=read_file" in text
    assert "desc=Lê um arquivo." in text
    assert "path:string" in text
    assert "lines:int[]" in text


def test_chat_messages_sem_tools_nao_envia_campo(stub_server):
    client, handler = _client(stub_server)
    client.chat_messages([{"role": "user", "content": "oi"}])
    assert "tools" not in stub_server.last_request


def test_serialize_tools_mapeia_tipos():
    tools = [
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Modifica um arquivo.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "action": {"type": "string"},
                        "enabled": {"type": "boolean"},
                    },
                    "required": ["path", "action"],
                },
            },
        }
    ]
    out = serialize_tools(tools)
    assert out.startswith("name=write_file | desc=Modifica um arquivo.")
    assert "path:string" in out
    assert "enabled:bool" in out


def test_chat_erro_status_404_texto(stub_server):
    client, handler = _client(stub_server)
    handler.response_status = 404
    handler.response_body = "model 'x' not found"
    with pytest.raises(LLMRequestError) as exc_info:
        client.chat("oi")
    message = str(exc_info.value)
    assert "Erro 404" in message
    assert "model 'x' not found" in message


def test_chat_erro_400_campo_model(stub_server):
    client, handler = _client(stub_server)
    handler.response_status = 400
    handler.response_body = "campo 'model' é obrigatório"
    with pytest.raises(LLMRequestError) as exc_info:
        client.chat("oi")
    assert "campo 'model' é obrigatório" in str(exc_info.value)


def test_chat_erro_503_provider_offline(stub_server):
    client, handler = _client(stub_server)
    handler.response_status = 503
    handler.response_body = "no bridge available for provider 'gemini'"
    with pytest.raises(LLMRequestError):
        client.chat("oi")


def test_conexao_recusada():
    client = LLMClient(base_url="http://127.0.0.1:1", timeout=1)
    with pytest.raises(LLMRequestError) as exc_info:
        client.chat("oi")
    assert "Não foi possível conectar" in str(exc_info.value)


def test_chat_retorno_vazio_sem_erro(stub_server):
    """Texto vazio é resposta válida (o cliente não invalida 'sem conteúdo')."""
    client, handler = _client(stub_server)
    handler.response_body = ""
    assert client.chat("oi") == ""