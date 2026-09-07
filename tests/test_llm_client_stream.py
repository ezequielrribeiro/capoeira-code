import http.server
import json
import threading

import pytest

from cli.llm_client import LLMClient, LLMRequestError


class StreamHandler(http.server.BaseHTTPRequestHandler):
    """Responde ao /api/chat com NDJSON (stream) quando `stream:true` no corpo."""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length).decode("utf8"))
        self.server.last_body = body
        lines = []

        def chunk(txt):
            lines.append(json.dumps({"message": {"role": "assistant", "content": txt}, "done": False}))

        if body.get("stream") is True:
            chunk("ola")
            chunk(" mundo")
            chunk("!")
            lines.append(json.dumps({"done": True}))
        else:
            lines.append(
                json.dumps({"message": {"role": "assistant", "content": "nao-stream"}, "done": True})
            )

        payload = ("\n".join(lines) + "\n").encode("utf8")
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

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
    assert out == "ola mundo!"
    assert chunks == ["ola", " mundo", "!"]
    assert stream_server.last_body["stream"] is True


def test_chat_stream_sem_on_chunk_retorna_conteudo(stream_server):
    client = _client(stream_server)
    out = client.chat_messages([{"role": "user", "content": "oi"}], stream=True)
    assert out == "ola mundo!"


def test_chat_nao_stream_mantem_comportamento(stream_server):
    client = _client(stream_server)
    out = client.chat_messages([{"role": "user", "content": "oi"}])  # padrão: não-stream
    assert out == "nao-stream"