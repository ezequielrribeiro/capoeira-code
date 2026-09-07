from types import SimpleNamespace

import pytest

from cli.project.premises import Premises, RagPremises
from cli.rag_client import RagClient, RagError, RagNotConfiguredError


def _premises(tmp_path):
    return Premises(name="g", rag=RagPremises(working_dir=str(tmp_path)))


def test_sem_rag_config_lanca_erro_claro(tmp_path):
    with pytest.raises(RagNotConfiguredError):
        RagClient(Premises(name="g"))


def test_ask_executa_subprocess_no_working_dir(tmp_path, monkeypatch):
    prem = _premises(tmp_path)
    client = RagClient(prem)
    capturado = {}

    def fake_run(cmd, **kwargs):
        capturado["cmd"] = cmd
        capturado["cwd"] = kwargs.get("cwd")
        return SimpleNamespace(returncode=0, stdout="CONTEXTO_RAG\n", stderr="")

    monkeypatch.setattr("cli.rag_client.subprocess.run", fake_run)
    assert client.ask("como funciona o login?") == "CONTEXTO_RAG"
    assert capturado["cmd"][:4] == ["python", "main.py", "query", "como funciona o login?"]
    assert capturado["cwd"] == str(tmp_path)


def test_ask_mapeia_doc_type(tmp_path, monkeypatch):
    prem = _premises(tmp_path)
    client = RagClient(prem)
    capturado = {}

    def fake_run(cmd, **kwargs):
        capturado["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr("cli.rag_client.subprocess.run", fake_run)
    client.ask("bug no cadastro", "support")
    assert "--doc-type" in capturado["cmd"]
    assert capturado["cmd"][-2:] == ["--doc-type", "support"]


def test_ask_falha_no_processo(tmp_path, monkeypatch):
    client = RagClient(_premises(tmp_path))

    def fake_run(cmd, **kwargs):
        return SimpleNamespace(returncode=2, stdout="", stderr="boom rag")

    monkeypatch.setattr("cli.rag_client.subprocess.run", fake_run)
    with pytest.raises(RagError) as e:
        client.ask("x")
    assert "exit=2" in str(e.value)


def test_ask_executavel_inexistente(tmp_path, monkeypatch):
    client = RagClient(_premises(tmp_path))

    def fake_run(cmd, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr("cli.rag_client.subprocess.run", fake_run)
    with pytest.raises(RagError):
        client.ask("x")