import yaml

from cli.project.premises import Premises, load_premises, resolve_config_dir


def _write_project(monkeypatch, tmp_path, data, name="garagens"):
    proj = tmp_path / "projects"
    proj.mkdir()
    (proj / f"{name}.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    monkeypatch.setenv("CAPOEIRA_CONFIG_DIR", str(tmp_path))


def test_resolve_config_dir_usa_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CAPOEIRA_CONFIG_DIR", str(tmp_path))
    assert resolve_config_dir() == tmp_path.resolve()


def test_load_premises_valida_schema(monkeypatch, tmp_path):
    _write_project(
        monkeypatch,
        tmp_path,
        {
            "name": "garagens",
            "description": "telas de garagens",
            "stack": {"language": "php", "structure": {"controllers": "app/controllers"}},
            "banco": {"schema_file": "database/schema.sql"},
            "rag": {"working_dir": "C:/rag"},
            "specs": ["padroes-telas"],
        },
    )
    p = load_premises(tmp_path, "garagens")
    assert p.name == "garagens"
    assert p.stack.language == "php"
    assert p.stack.structure["controllers"] == "app/controllers"
    assert p.banco.schema_file == "database/schema.sql"
    assert p.rag.working_dir == "C:/rag"
    assert p.specs == ["padroes-telas"]


def test_load_premises_arquivo_inexistente(monkeypatch, tmp_path):
    monkeypatch.setenv("CAPOEIRA_CONFIG_DIR", str(tmp_path))
    try:
        load_premises(tmp_path, "nao-existe")
    except FileNotFoundError:
        return
    raise AssertionError("deveria levantar FileNotFoundError")


def test_load_premises_falta_name(monkeypatch, tmp_path):
    _write_project(monkeypatch, tmp_path, {"stack": {}})
    try:
        load_premises(tmp_path, "garagens")
    except ValueError:
        return
    raise AssertionError("deveria levantar ValueError")


def test_validate_banco_avisa_faltas():
    p = Premises(name="x", banco={"dsn": "mysql://..."})
    assert p.validate_banco() == ""
    p2 = Premises(name="x", banco={})
    assert "schema_file" in p2.validate_banco()
    p3 = Premises(name="x")
    assert "banco" in p3.validate_banco()