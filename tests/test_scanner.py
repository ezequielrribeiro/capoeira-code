import yaml

from cli.project.premises import Premises
from cli.project.scanner import (
    classify_module,
    extract_sql_tables,
    parse_schema_table_names,
    scan_file,
    schema_tables,
)


def test_classify_module_pelo_caminho():
    structure = {"controllers": "app/controllers", "models": "app/models", "css": "public/assets/css"}
    assert classify_module("C:/x/app/controllers/CasaController.php", structure) == "controllers"
    assert classify_module("app/models/Casa.php", structure) == "models"
    assert classify_module("public/assets/css/tela.css", structure) == "css"
    assert classify_module("scripts/qualquer.php", structure) == "outro"


def test_extract_sql_tables_heuristicas():
    codigo = """<?php
$sql = "SELECT * FROM garagens WHERE id = ?";
$sql2 = "INSERT INTO vagas (id) VALUES (?)";
$sql3 = "UPDATE garagens SET status = 1";
$sql4 = "SELECT g.*, v.* FROM garagens g JOIN vagas v ON v.garagem_id = g.id";
"""
    assert extract_sql_tables(codigo) == ["garagens", "vagas"]


def test_parse_schema_table_names():
    schema = """CREATE TABLE `garagens` (id INT);
CREATE TABLE IF NOT EXISTS vagas (id INT);
"""
    assert parse_schema_table_names(schema) == ["garagens", "vagas"]


def test_schema_tables_le_arquivo(tmp_path):
    arquivo = tmp_path / "schema.sql"
    arquivo.write_text("CREATE TABLE clientes (id INT);\nCREATE TABLE apartamentos (id INT);\n", encoding="utf-8")
    assert schema_tables(str(arquivo)) == ["clientes", "apartamentos"]


def test_scan_file_classifica_deps_e_tabelas(tmp_path):
    arquivo = tmp_path / "app" / "models" / "Garagens.php"
    arquivo.parent.mkdir(parents=True)
    arquivo.write_text(
        "<?php\n"
        'require_once "vendor/autoload.php";\n'
        "use App\\Utils\\Logger;\n"
        "function lista() {\n"
        '    $sql = "SELECT * FROM garagens";\n'
        "    return $sql;\n"
        "}\n",
        encoding="utf-8",
    )
    premises = Premises(
        name="g",
        stack={"structure": {"controllers": "app/controllers", "models": "app/models"}},
    )
    perfil = scan_file(str(arquivo), premises)
    assert perfil["classification"] == "models"
    assert perfil["dependencies"] == ["App\\Utils\\Logger", "vendor/autoload.php"]
    assert perfil["sql_tables"] == ["garagens"]


def test_scan_file_sem_premisas_classifica_outro(tmp_path):
    arquivo = tmp_path / "x.php"
    arquivo.write_text("<?php function f() { return 1; }\n", encoding="utf-8")
    perfil = scan_file(str(arquivo), Premises(name="g"))
    assert perfil["classification"] == "outro"
    assert perfil["sql_tables"] == []