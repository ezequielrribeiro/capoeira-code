import json
from pathlib import Path
from types import SimpleNamespace

import click.testing
import pytest
import yaml

from cli.llm_client import LLMRequestError
from cli.main import cli

FIXTURE_PHP = Path(__file__).parent / "fixtures" / "legacy_calculator.php"


class FakeLLMClient:
    responses: list = []
    last_prompt: str = ""

    def __init__(self, base_url, model, timeout):
        self.base_url = base_url

    def chat(self, prompt):
        FakeLLMClient.last_prompt = prompt
        if not self.responses:
            raise LLMRequestError("fim dos stubs")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def _substitui_llm_client(monkeypatch, tmp_path):
    FakeLLMClient.responses = []
    monkeypatch.setattr("cli.main.LLMClient", FakeLLMClient)
    monkeypatch.setenv("CAPOEIRA_CONFIG_DIR", str(tmp_path))
    return FakeLLMClient


def _invoke(*args, **kwargs):
    runner = click.testing.CliRunner()
    return runner.invoke(cli, args, **kwargs)


def _batch(caminhos: list[Path], prefixo="x") -> str:
    files = [
        {"file_path": str(p), "action": "create_file", "code_content": f"<?php echo '{prefixo}';", "explanation": ""}
        for p in caminhos
    ]
    return json.dumps({"files": files})


def test_run_lote_multi_arquivo_aplica(tmp_path):
    a = tmp_path / "telas" / "Cadastro.php"
    b = tmp_path / "telas" / "Lista.php"
    FakeLLMClient.responses = [_batch([a, b])]
    result = _invoke("run", "crie telas de cadastro e lista")
    assert result.exit_code == 0
    assert "2 arquivo(s)" in result.output
    assert "<?php echo 'x';" in a.read_text(encoding="utf-8")
    assert "<?php echo 'x';" in b.read_text(encoding="utf-8")


def test_run_dry_run_recusa_aplica(tmp_path):
    alvo = tmp_path / "draft.php"
    FakeLLMClient.responses = [_batch([alvo])]
    result = _invoke("run", "crie um script", "--dry-run", input="n\n")
    assert result.exit_code == 0
    assert "RASCUNHO (dry-run)" in result.output
    assert "Nada aplicado." in result.output
    assert not alvo.exists()


def test_run_dry_run_aceita_aplica(tmp_path):
    alvo = tmp_path / "extra.php"
    FakeLLMClient.responses = [_batch([alvo])]
    result = _invoke("run", "crie um arquivo", "--dry-run", input="y\n")
    assert result.exit_code == 0
    assert alvo.exists()


def test_run_erro_de_backend_falha():
    FakeLLMClient.responses = [LLMRequestError("Erro 503: sem bridge")]
    result = _invoke("run", "qualquer coisa")
    assert result.exit_code == 1
    assert "Erro 503" in result.output


def test_run_projeto_inexistente_falha(tmp_path):
    result = _invoke("run", "tarefa", "--project", "nao-existe")
    assert result.exit_code == 1
    assert "não encontrado" in result.output


def test_ask_consulta_rag(tmp_path, monkeypatch):
    proj = tmp_path / "projects"
    proj.mkdir()
    (proj / "garagens.yaml").write_text(
        yaml.safe_dump({"name": "garagens", "rag": {"working_dir": "C:/falso/rag"}}), encoding="utf-8"
    )
    capturado = {}

    def fake_run(cmd, **kwargs):
        capturado["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout="CONTEXTO_DO_RAG\n", stderr="")

    monkeypatch.setattr("cli.rag_client.subprocess.run", fake_run)
    result = _invoke("ask", "como alterar senha?", "--project", "garagens", "--doc-type", "tech")
    assert result.exit_code == 0
    assert "CONTEXTO_DO_RAG" in result.output
    assert "--doc-type" in capturado["cmd"]


def test_run_erro_applier_retenta(tmp_path):
    alvo = tmp_path / "final.php"
    FakeLLMClient.responses = [
        "texto sem json",  # tentativa 1 falha
        _batch([alvo]),    # tentativa 2 corrigida
    ]
    result = _invoke("run", "crie um arquivo", "--max-retries", "2")
    assert result.exit_code == 0
    assert alvo.exists()
    assert "[Tentativa 1/2]" in result.output


def test_run_injeta_prompt_template_perfil_e_contexto(tmp_path, monkeypatch):
    proj = tmp_path / "projects"
    (tmp_path / "prompts").mkdir()
    proj.mkdir()
    (proj / "garagens.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "garagens",
                "stack": {"structure": {"controllers": "app/controllers"}},
                "specs": None,
                "skills": None,
                "prompts": None,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "prompts" / "new-screen.md").write_text("TEMPLO_DA_TELA: crie a tela no padrão.", encoding="utf-8")

    alvo = tmp_path / "out.html"
    FakeLLMClient.responses = [_batch([alvo])]
    result = _invoke(
        "run",
        "crie uma tela de cadastro",
        "--project", "garagens",
        "--prompt", "new-screen",
        "--file", str(FIXTURE_PHP),
    )
    assert result.exit_code == 0
    prompt = FakeLLMClient.last_prompt
    assert "TEMPLO_DA_TELA" in prompt
    assert "PERFIL DO PROJETO" in prompt
    assert "Projeto: garagens" in prompt
    assert "ESQUELETO" in prompt or "[Omitted by CapoeiraCode]" in prompt