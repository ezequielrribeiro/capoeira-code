import os
from pathlib import Path
from types import SimpleNamespace

from cli.project.premises import Premises, RagPremises
from cli.tui.app import _COMMANDS, _HELP, _ask_query, _deps_report, _split_ask


def _premises(tmp_path) -> Premises:
    return Premises(name="g", rag=RagPremises(working_dir=str(tmp_path)))


def test_ask_e_deps_documentados_no_help():
    assert "/ask" in _HELP
    assert "/deps" in _HELP
    assert "/ask" in _COMMANDS
    assert "/deps" in _COMMANDS


def test_split_ask_separa_doc_type():
    assert _split_ask("como login? --doc-type support") == ("como login?", "support")
    assert _split_ask("como login?") == ("como login?", None)


def test_ask_query_chama_rag(tmp_path, monkeypatch):
    chamadas = {}

    def fake_run(cmd, **kwargs):
        chamadas["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout="CONTEXTO_DO_RAG\n", stderr="")

    monkeypatch.setattr("cli.rag_client.subprocess.run", fake_run)
    out = _ask_query(_premises(tmp_path), "como o sistema cobra?", "support")
    assert out == "CONTEXTO_DO_RAG"
    assert "--doc-type" in chamadas["cmd"]


def test_ask_query_sem_rag_orienta():
    premises = Premises(name="g")
    out = _ask_query(premises, "pergunta")
    assert "rag.working_dir" in out


def test_deps_report_mostra_modulo_deps_tabelas(tmp_path):
    arquivo = tmp_path / "app" / "models" / "Garagens.php"
    arquivo.parent.mkdir(parents=True)
    arquivo.write_text(
        "<?php\n"
        'require_once "vendor/autoload.php";\n'
        "function lista() {\n"
        '    $sql = "SELECT * FROM garagens";\n'
        "    return $sql;\n"
        "}\n",
        encoding="utf-8",
    )
    premises = Premises(name="g", stack={"structure": {"models": "app/models"}})
    out = _deps_report(premises, str(arquivo))
    assert "Módulo: models" in out
    assert "vendor/autoload.php" in out
    assert "garagens" in out


def test_deps_report_arquivo_inexistente():
    out = _deps_report(Premises(name="g"), "C:/nao/existe.php")
    assert "não encontrado" in out