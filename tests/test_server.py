import asyncio
import json

import pytest
import websockets

from cli.server import CapoeiraServer


def _run(coro):
    return asyncio.run(coro)


def _port(ws_server) -> int:
    return ws_server.sockets[0].getsockname()[1]


def test_rejeita_origin_nao_autorizada():
    async def main():
        server = CapoeiraServer(port=0)
        async with await server.start() as ws_server:
            uri = f"ws://127.0.0.1:{_port(ws_server)}"
            async with websockets.connect(uri, origin="https://evil.example.com") as ws:
                with pytest.raises(websockets.exceptions.ConnectionClosedError) as exc_info:
                    await ws.recv()
                return exc_info.value.rcvd.code == 1008

    assert _run(main()) is True


def test_sem_extensao_conectada_levanta_connection_error():
    async def main():
        server = CapoeiraServer(port=0)
        with pytest.raises(ConnectionError):
            await server.send_prompt_and_wait("qualquer")

    _run(main())


def test_fluxo_send_prompt_response_correlaciona_por_id():
    async def main():
        server = CapoeiraServer(port=0)
        async with await server.start() as ws_server:
            uri = f"ws://127.0.0.1:{_port(ws_server)}"
            async with websockets.connect(uri, origin="chrome-extension://abcdef") as ws:
                await server.wait_for_extension(timeout=5)

                async def extensao_fake():
                    msg = json.loads(await ws.recv())
                    assert msg["version"] == "1.0"
                    assert msg["action"] == "SEND_PROMPT"
                    assert msg["payload"]["provider"] == "claude"
                    assert msg["payload"]["prompt"] == "refatore isso"
                    assert msg["payload"]["systemPrompt"]
                    await ws.send(
                        json.dumps(
                            {
                                "version": "1.0",
                                "id": msg["id"],
                                "action": "RESPONSE",
                                "status": "SUCCESS",
                                "payload": {"rawResponse": '{"file_path": "x"}'},
                            }
                        )
                    )

                raw_response, _ = await asyncio.gather(
                    server.send_prompt_and_wait("refatore isso", provider="claude", timeout=5),
                    extensao_fake(),
                )
                return raw_response

    assert _run(main()) == '{"file_path": "x"}'


def test_resposta_sem_id_resolve_unico_pendente():
    async def main():
        server = CapoeiraServer(port=0)
        async with await server.start() as ws_server:
            uri = f"ws://127.0.0.1:{_port(ws_server)}"
            async with websockets.connect(uri, origin="chrome-extension://abcdef") as ws:
                await server.wait_for_extension(timeout=5)

                async def extensao_sem_id():
                    await ws.recv()
                    await ws.send(
                        json.dumps(
                            {
                                "action": "RESPONSE",
                                "status": "SUCCESS",
                                "payload": {"rawResponse": "sem-id"},
                            }
                        )
                    )

                raw_response, _ = await asyncio.gather(
                    server.send_prompt_and_wait("prompt", timeout=5),
                    extensao_sem_id(),
                )
                return raw_response

    assert _run(main()) == "sem-id"


def test_timeout_aguardando_resposta():
    async def main():
        server = CapoeiraServer(port=0)
        async with await server.start() as ws_server:
            uri = f"ws://127.0.0.1:{_port(ws_server)}"
            async with websockets.connect(uri, origin="chrome-extension://abcdef") as ws:
                await server.wait_for_extension(timeout=5)
                with pytest.raises(TimeoutError):
                    await server.send_prompt_and_wait("prompt", timeout=0.2)

    _run(main())
