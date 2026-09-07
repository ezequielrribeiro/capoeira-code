from pathlib import Path

from cli.instruction.loader import InstructionSet
from cli.project.premises import Premises
from cli.tui.bootstrap import BUILTIN_BOOTSTRAP_PROMPT, bootstrap_instruction
from cli.tui.scan_artifacts import generate_artifacts, is_empty_project
from cli.tui.session import Session


def test_is_empty_project_dir_vazio(tmp_path):
    result = generate_artifacts(Session(config_dir=tmp_path, project_path=str(tmp_path)), Premises(name="v"))
    assert is_empty_project(result, str(tmp_path)) is True


def test_is_empty_project_false_com_codigo(tmp_path):
    proj = tmp_path / "app"
    proj.mkdir()
    (proj / "x.php").write_text("<?php\n", encoding="utf-8")
    session = Session(config_dir=tmp_path, project_path=str(proj))
    result = generate_artifacts(session, Premises(name="app"))
    assert is_empty_project(result, str(proj)) is False


def test_is_empty_project_false_com_manifest(tmp_path):
    (tmp_path / "composer.json").write_text("{}", encoding="utf-8")
    session = Session(config_dir=tmp_path, project_path=str(tmp_path))
    result = generate_artifacts(session, Premises(name="m"))
    assert is_empty_project(result, str(tmp_path)) is False


def test_is_empty_project_dir_inexistente(tmp_path):
    assert is_empty_project({}, str(tmp_path / "nao-existe")) is True


def test_bootstrap_instruction_custom(tmp_path):
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "bootstrap.md").write_text("ROTEIRO_PERSONALIZADO", encoding="utf-8")
    instr = InstructionSet(specs={}, skills={}, prompts={"bootstrap": "ROTEIRO_PERSONALIZADO"})
    assert bootstrap_instruction(instr) == "ROTEIRO_PERSONALIZADO"


def test_bootstrap_instruction_fallback():
    instr = InstructionSet(specs={}, skills={}, prompts={})
    assert bootstrap_instruction(instr) == BUILTIN_BOOTSTRAP_PROMPT
    assert "schema.sql" in BUILTIN_BOOTSTRAP_PROMPT