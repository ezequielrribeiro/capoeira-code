import json
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from cli.tui import tools

FIXTURE_PHP = Path(__file__).parent / "fixtures" / "legacy_calculator.php"


def _run(proc):
    return SimpleNamespace(returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr)


def test_read_file_gera_resposta_ok(tmp_path):
    arquivo = tmp_path / "a.txt"
    arquivo.write_text("linha1\nlinha2\nlinha3\n", encoding="utf-8")
    result = tools.read_file("a.txt", str(tmp_path))
    assert result.ok is True
    assert "linha1" in result.output


def test_read_file_com_intervalo_de_linhas(tmp_path):
    arquivo = tmp_path / "a.txt"
    arquivo.write_text("\n".join(f"l{i}" for i in range(1, 11)), encoding="utf-8")
    result = tools.read_file("a.txt", str(tmp_path), [2, 4])
    assert result.output == "l2\nl3\nl4"


def test_read_file_inexistente(tmp_path):
    result = tools.read_file("nope.txt", str(tmp_path))
    assert result.ok is False


def test_list_dir(tmp_path):
    (tmp_path / "x.php").write_text("", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    result = tools.list_dir(".", str(tmp_path))
    assert result.ok is True
    assert "x.php" in result.output
    assert "sub" in result.output


def test_truncamento_de_saida(tmp_path):
    arquivo = tmp_path / "grande.txt"
    arquivo.write_text("y" * 20000, encoding="utf-8")
    result = tools.read_file("grande.txt", str(tmp_path))
    assert len(result.output) <= tools.OUTPUT_LIMIT + 80
    assert "truncada" in result.output


def test_run_shell_executa(monkeypatch):
    capturado = {}

    def fake_run(cmd, **kwargs):
        capturado["cmd"] = cmd
        capturado["cwd"] = kwargs.get("cwd")
        return SimpleNamespace(returncode=0, stdout="saida shell\n", stderr="")

    monkeypatch.setattr("cli.tui.tools.subprocess.run", fake_run)
    result = tools.run_shell("dir", r"C:\proj")
    assert result.ok is True
    assert "saida shell" in result.output
    assert capturado["cwd"] == r"C:\proj"


def test_run_python_executa(monkeypatch):
    capturado = {}

    def fake_run(cmd, **kwargs):
        capturado["cmd"] = cmd
        return SimpleNamespace(returncode=0, stdout="py ok\n", stderr="")

    monkeypatch.setattr("cli.tui.tools.subprocess.run", fake_run)
    result = tools.run_python("print('hi')", ".", python="python", timeout=5)
    assert result.ok is True
    assert capturado["cmd"][0] == "python"
    assert "py ok" in result.output


def test_write_file_cria_e_substitui(tmp_path):
    alvo = tmp_path / "novo.php"
    result = tools.write_file(
        {"path": "novo.php", "action": "create_file", "code_content": "<?php echo 1;", "explanation": "cria"},
        str(tmp_path),
    )
    assert result.ok is True
    assert alvo.read_text(encoding="utf-8") == "<?php echo 1;"

    copia = Path(tmp_path) / "copia.php"
    shutil.copy(FIXTURE_PHP, copia)
    result = tools.write_file(
        {
            "path": "copia.php",
            "action": "replace_symbol",
            "target_symbol": "soma",
            "code_content": "public function soma($a, $b) { return $a + $b + 1; }",
            "explanation": "edita",
        },
        str(tmp_path),
    )
    assert result.ok is True
    assert "return $a + $b + 1;" in copia.read_text(encoding="utf-8")


def test_apply_step_desconhecido_falha():
    result = tools.apply_step({"tool": "teleporte"}, ".")
    assert result.ok is False