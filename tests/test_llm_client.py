import http.server
import json
import threading

import pytest

from cli.llm_client import LLMClient, LLMRequestError


class OllamaStubHandler(http.server.BaseHTTPRequestHandler):
    response_status = 200
    response_body = '{"message": {"role": "assistant", "content": "ok"}}'

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length).decode("utf8"))
        self.server.last_request = body
        self.send_response(self.response_status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(self.response_body.encode("utf8"))

    def log_message(self, *args):
        pass


@pytest.fixture()
def stub_server():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), OllamaStubHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def _client(stub_server, model="gemini-pro"):
    OllamaStubHandler.response_status = 200
    OllamaStubHandler.response_body = '{"message": {"role": "assistant", "content": "ok"}}'
    port = stub_server.server_address[1]
    return LLMClient(base_url=f"http://127.0.0.1:{port}", model=model, timeout=5), OllamaStubHandler


def test_chat_retorna_conteudo_da_resposta(stub_server):
    client, _ = _client(stub_server, model="claude-sonnet")
    assert client.chat("refatore isso") == "ok"

    body = stub_server.last_request
    assert body["model"] == "claude-sonnet"
    assert body["stream"] is False
    roles = [m["role"] for m in body["messages"]]
    assert roles == ["system", "user"]
    assert "refatore isso" in body["messages"][1]["content"]


def test_chat_erro_status_404_traz_detalhe(stub_server):
    client, handler = _client(stub_server)
    handler.response_status = 404
    handler.response_body = '{"error": "model not found"}'
    with pytest.raises(LLMRequestError) as exc_info:
        client.chat("oi")
    message = str(exc_info.value)
    assert "Erro 404" in message
    assert "model not found" in message


def test_chat_erro_503_provider_offline(stub_server):
    client, handler = _client(stub_server)
    handler.response_status = 503
    handler.response_body = '{"error": "no provider connected"}'
    with pytest.raises(LLMRequestError):
        client.chat("oi")


def test_chat_resposta_sem_conteudo(stub_server):
    client, handler = _client(stub_server)
    handler.response_body = '{"model": "x", "done": true}'
    with pytest.raises(LLMRequestError) as exc_info:
        client.chat("oi")
    assert "sem conteúdo" in str(exc_info.value)


def test_chat_resposta_nao_json(stub_server):
    client, handler = _client(stub_server)
    handler.response_body = "<html>não sou JSON</html>"
    with pytest.raises(LLMRequestError) as exc_info:
        client.chat("oi")
    assert "não-JSON" in str(exc_info.value)


def test_conexao_recusada():
    client = LLMClient(base_url="http://127.0.0.1:1", timeout=1)
    with pytest.raises(LLMRequestError) as exc_info:
        client.chat("oi")
    assert "Não foi possível conectar" in str(exc_info.value)


def test_chat_messages_ler_tool_calls_nativos(stub_server):
    client, handler = _client(stub_server)
    handler.response_body = json.dumps(
        {
            "model": "x",
            "message": {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {"function": {"name": "write_file", "arguments": {"path": "a.php", "action": "create_file"}}},
                    {"function": {"name": "done", "arguments": {"message": "fim"}}},
                ],
            },
            "done": True,
        }
    )
    reply = client.chat_messages([{"role": "user", "content": "crie"}])
    assert reply.content == ""
    assert reply.has_tool_calls is True
    assert reply.tool_calls == [
        {"name": "write_file", "arguments": {"path": "a.php", "action": "create_file"}},
        {"name": "done", "arguments": {"message": "fim"}},
    ]


def test_chat_messages_tool_calls_formato_direto(stub_server):
    client, handler = _client(stub_server)
    handler.response_body = json.dumps(
        {
            "message": {
                "role": "assistant",
                "tool_calls": [{"name": "done", "arguments": {"message": "ok"}}],
            }
        }
    )
    reply = client.chat_messages([{"role": "user", "content": "x"}])
    assert reply.tool_calls == [{"name": "done", "arguments": {"message": "ok"}}]


def test_chat_messages_envia_tools_no_body(stub_server):
    client, handler = _client(stub_server)
    tools = [{"type": "function", "function": {"name": "done"}}]
    client.chat_messages([{"role": "user", "content": "oi"}], tools=tools)
    assert stub_server.last_request["tools"] == tools


def test_chat_messages_sem_tools_nao_envia_campo(stub_server):
    client, handler = _client(stub_server)
    client.chat_messages([{"role": "user", "content": "oi"}])
    assert "tools" not in stub_server.last_request