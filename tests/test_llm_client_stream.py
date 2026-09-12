import http.server
import threading
import urllib.parse

import pytest

from cli.llm_client import ChatReply, LLMClient


class StreamHandler(http.server.BaseHTTPRequestHandler):
    """Responde /api/chat em texto puro (chunks de linha), como o host."""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf8")
        self.server.last_body = urllib.parse.parse_qs(raw, keep_blank_values=True)

        stream_true = (self.server.last_body.get("stream") or ["false"])[0] == "true"
        if stream_true:
            user_content = (self.server.last_body.get("content") or [""])[-1]
            if user_content == "quero_tool_call":
                lines = b"[TOOL_CALL] done | message=fim\n"
            else:
                lines = b"ola\n mundo\n!\n"
        else:
            lines = b"nao-stream\n"

        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(lines)))
        self.end_headers()
        self.wfile.write(lines)

    def log_message(self, *args):
        pass


@pytest.fixture()
def stream_server():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), StreamHandler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv
    srv.shutdown()
    srv.server_close()
    t.join(timeout=2)


def _client(stream_server):
    return LLMClient(base_url=f"http://127.0.0.1:{stream_server.server_address[1]}", model="x", timeout=5)


def test_chat_stream_acumula_e_chama_on_chunk(stream_server):
    client = _client(stream_server)
    chunks = []

    def on_chunk(part):
        chunks.append(part)

    out = client.chat_messages([{"role": "user", "content": "oi"}], stream=True, on_chunk=on_chunk)
    assert out == ChatReply(content="ola\n mundo\n!\n")
    assert chunks == ["ola\n", " mundo\n", "!\n"]
    assert stream_server.last_body["stream"] == ["true"]


def test_chat_stream_entrega_linha_tool_call(stream_server):
    client = _client(stream_server)
    out = client.chat_messages(
        [{"role": "user", "content": "quero_tool_call"}],
        stream=True,
    )
    assert out.content == "[TOOL_CALL] done | message=fim\n"


def test_chat_stream_sem_on_chunk_retorna_conteudo(stream_server):
    client = _client(stream_server)
    out = client.chat_messages([{"role": "user", "content": "oi"}], stream=True)
    assert out == ChatReply(content="ola\n mundo\n!\n")


def test_chat_nao_stream_mantem_comportamento(stream_server):
    client = _client(stream_server)
    out = client.chat_messages([{"role": "user", "content": "oi"}])
    assert out == ChatReply(content="nao-stream\n")
    assert stream_server.last_body["stream"] == ["false"]