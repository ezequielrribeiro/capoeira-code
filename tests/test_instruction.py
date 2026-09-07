from pathlib import Path

from cli.instruction.loader import (
    InstructionSet,
    load_instruction_set,
    render_project_profile,
)
from cli.project.premises import Premises


def _make_config(tmp_path: Path) -> Path:
    (tmp_path / "specs").mkdir()
    (tmp_path / "skills").mkdir()
    (tmp_path / "prompts").mkdir()
    (tmp_path / "specs" / "01-padroes-telas.md").write_text("Toda tela usa layout.php", encoding="utf-8")
    (tmp_path / "specs" / "02-orm.md").write_text("ORM não usado", encoding="utf-8")
    (tmp_path / "skills" / "criar-tela.md").write_text("Procedimento criar-tela", encoding="utf-8")
    (tmp_path / "prompts" / "new-screen.md").write_text("Crie uma nova tela seguindo os padrões.", encoding="utf-8")
    return tmp_path


def test_load_seleciona_apenas_os_listados(tmp_path):
    cfg = _make_config(tmp_path)
    prem = Premises(name="g", specs=["01-padroes-telas"], skills=[], prompts=[])
    instr = load_instruction_set(cfg, prem)
    assert set(instr.specs) == {"01-padroes-telas"}
    assert "02-orm" not in instr.specs
    assert instr.get_prompt("new-screen") == ""


def test_load_sem_selecao_carrega_tudo(tmp_path):
    cfg = _make_config(tmp_path)
    prem = Premises(name="g")
    instr = load_instruction_set(cfg, prem)
    assert set(instr.specs) == {"01-padroes-telas", "02-orm"}
    assert set(instr.skills) == {"criar-tela"}
    assert "new-screen" in instr.prompts


def test_get_prompt_normaliza_maiusculas_e_sufixo(tmp_path):
    cfg = _make_config(tmp_path)
    prem = Premises(name="g")
    instr = load_instruction_set(cfg, prem)
    base = instr.get_prompt("new-screen")
    assert base
    assert instr.get_prompt("NEW-SCREEN") == base
    assert instr.get_prompt("new-screen.md") == base


def test_render_project_profile_inclui_convencoes():
    prem = Premises(
        name="garagens",
        description="sistema de garagens",
        stack={
            "language": "php",
            "structure": {"controllers": "app/controllers"},
            "conventions": ["camelCase para telas"],
        },
        frontend={"css_classes": ["btn", "card"]},
        banco={"schema_file": "schema.sql"},
    )
    out = render_project_profile(prem)
    assert "garagens" in out
    assert "camelCase para telas" in out
    assert "btn, card" in out


def test_combined_joins_documents():
    instr = InstructionSet(specs={"a": "aaa"}, skills={"s": "bbb"}, prompts={})
    assert "aaa" in instr.specs_combined
    assert "bbb" in instr.skills_combined