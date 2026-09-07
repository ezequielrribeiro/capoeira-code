import json

from cli.project.premises import EMPTY_PREMISES, Premises
from cli.tui.scan_artifacts import artifacts_summary, generate_artifacts
from cli.tui.session import Session


def _projeto(tmp_path):
    proj = tmp_path / "app"
    (proj / "controllers").mkdir(parents=True)
    (proj / "controllers" / "CasaController.php").write_text(
        "<?php\nfunction listar() {\n    return 'ok';\n}\n", encoding="utf-8"
    )
    (proj / "models").mkdir(parents=True)
    (proj / "models" / "Casa.php").write_text(
        "<?php\nclass Casa { public function get($id) { return $id; } }\n", encoding="utf-8"
    )
    (proj / "LEIA.txt").write_text("anotação", encoding="utf-8")
    return proj


def test_generate_artifacts_cria_tree_deps_asts(tmp_path):
    proj = _projeto(tmp_path)
    session = Session(config_dir=tmp_path, project_path=str(proj))
    premises = Premises(name="app", stack={"structure": {"controllers": "controllers"}})

    result = generate_artifacts(session, premises)

    tree = (session.workspace / "tree.txt").read_text(encoding="utf-8")
    assert "controllers/" in tree
    assert "CasaController.php" in tree

    deps = json.loads((session.workspace / "dependencies.json").read_text(encoding="utf-8"))
    assert isinstance(deps, list)
    assert len(deps) == 2
    classif = {d["file"].endswith("CasaController.php"): d for d in deps}
    controller = classif[True] if True in classif else None
    assert controller is not None
    assert controller["classification"] == "controllers"

    ast = session.asts / "controllers" / "CasaController.php"
    assert ast.exists()
    assert result["ast_files"] >= 2
    assert result["num_files"] == 2


def test_artifacts_summary_enxuto():
    result = {"tree": "app/\n  x.php", "num_files": 3, "ast_files": 2, "dependencies": []}
    out = artifacts_summary(result)
    assert "Arquivos indexados: 3" in out
    assert "app/" in out
    assert "x.php" in out