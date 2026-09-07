import json
import shutil
from pathlib import Path

import click.testing
import pytest

from cli.llm_client import LLMRequestError
from cli.main import cli

FIXTURE_PHP = Path(__file__).parent / "fixtures" / "legacy_calculator.php"
FIXTURE_JS = Path(__file__).parent / "fixtures" / "dashboard.js"


class FakeLLMClient:
    """Substitui cli.main.LLMClient; respostas ficam em armazenamento cls.responses."""

    responses: list = []

    def __init__(self, base_url, model, timeout):
        self.base_url = base_url
        self.model = model

    def chat(self, prompt):
        if not self.responses:
            raise LLMRequestError("fim dos stubs (não deveria haver mais chamadas)")
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


@pytest.fixture(autouse=True)
def _substitui_llm_client(monkeypatch):
    FakeLLMClient.responses = []
    monkeypatch.setattr("cli.main.LLMClient", FakeLLMClient)


def _invoke(*args):
    runner = click.testing.CliRunner()
    return runner.invoke(cli, args)


def _payload_replace(file_path, **kwargs):
    base = {
        "file_path": str(file_path),
        "action": "replace_symbol",
        "target_symbol": "soma",
        "code_content": "public function soma($a, $b) { return $a + $b; }",
        "explanation": "teste",
    }
    base.update(kwargs)
    return json.dumps(base)


def test_refactor_sucesso_aplica_mudanca(tmp_path, monkeypatch):
    alvo = tmp_path / "legacy_calculator.php"
    shutil.copy(FIXTURE_PHP, alvo)
    FakeLLMClient.responses = [
        _payload_replace(alvo, code_content="public function soma($a, $b) { return $a + $b + 1; }")
    ]

    result = _invoke(
        "refactor",
        "--file", str(alvo),
        "--symbol", "soma",
        "--instruction", "adicione 1 no retorno",
        "--base-url", "http://127.0.0.1:8765",
        "--model", "gemini-pro",
    )
    assert result.exit_code == 0
    assert "Refatoração concluída" in result.output
    assert "return $a + $b + 1;" in alvo.read_text(encoding="utf-8")


def test_refactor_retry_rnf04_autocorrige(tmp_path):
    alvo = Path(tmp_path) / "legacy_calculator.php"
    shutil.copy(FIXTURE_PHP, alvo)
    FakeLLMClient.responses = [
        "texto sem json",
        _payload_replace(alvo, code_content="public function soma($a, $b) { return $a + $b + 1; }"),
    ]

    result = _invoke(
        "refactor",
        "--file", str(alvo),
        "--symbol", "soma",
        "--instruction", "adicione 1 no retorno",
        "--max-retries", "2",
    )
    assert result.exit_code == 0
    assert "[Tentativa 1/2]" in result.output
    assert "return $a + $b + 1;" in alvo.read_text(encoding="utf-8")


def test_refactor_erro_de_backend_falha(tmp_path):
    alvo = Path(tmp_path) / "legacy_calculator.php"
    shutil.copy(FIXTURE_PHP, alvo)
    FakeLLMClient.responses = [LLMRequestError("Erro 503 do backend: no provider connected")]

    result = _invoke(
        "refactor",
        "--file", str(alvo),
        "--symbol", "soma",
        "--instruction", "x",
    )
    assert result.exit_code == 1
    assert "Erro 503" in result.output


def test_generate_cria_arquivo_novo(tmp_path):
    alvo = tmp_path / "tests" / "test_calc.py"
    FakeLLMClient.responses = [
        json.dumps(
            {
                "file_path": str(alvo),
                "action": "create_file",
                "code_content": "def test_soma():\n    assert True\n",
                "explanation": "artefato de teste",
            }
        )
    ]

    result = _invoke(
        "generate",
        "--file", str(alvo),
        "--instruction", "gere um teste para soma",
    )
    assert result.exit_code == 0
    assert "Artefato gerado" in result.output
    assert "def test_soma()" in alvo.read_text(encoding="utf-8")


def test_generate_caminho_divergente_nao_escreve(tmp_path):
    alvo = tmp_path / "esperado.py"
    outro = tmp_path / "alucinado.py"
    FakeLLMClient.responses = [
        json.dumps(
            {
                "file_path": str(outro),
                "action": "create_file",
                "code_content": "x = 1",
                "explanation": "caminho errado",
            }
        )
    ]

    result = _invoke(
        "generate",
        "--file", str(alvo),
        "--instruction", "gere um módulo",
    )
    assert result.exit_code == 1
    assert "Caminho inesperado" in result.output
    assert not alvo.exists()
    assert not outro.exists()


def test_explain_imprime_resposta(tmp_path):
    alvo = Path(tmp_path) / "legacy_calculator.php"
    shutil.copy(FIXTURE_PHP, alvo)
    FakeLLMClient.responses = ["Explicação técnica do cálculo legado."]

    result = _invoke(
        "explain",
        "--file", str(alvo),
        "--symbol", "soma",
    )
    assert result.exit_code == 0
    assert "Explicação técnica do cálculo legado." in result.output


def test_deps_lista_imports_sem_llm():
    result = _invoke("deps", "--file", str(FIXTURE_JS))
    assert result.exit_code == 0
    assert "./render.js" in result.output
    assert "axios" in result.output