import json
import shutil
from pathlib import Path

import click.testing
import pytest

from cli.main import cli
from cli.rag_client import RagClient

FIXTURE_PHP = Path(__file__).parent / "fixtures" / "legacy_calculator.php"


def _payload_batch(files: list[dict]) -> str:
    return json.dumps({"files": files})


def test_batch_cria_varios_arquivos(tmp_path):
    a = tmp_path / "a.php"
    b = tmp_path / "b.php"
    raw = _payload_batch(
        [
            {"file_path": str(a), "action": "create_file", "code_content": "<?php echo 'a';", "explanation": "tela a"},
            {"file_path": str(b), "action": "create_file", "code_content": "<?php echo 'b';", "explanation": "tela b"},
        ]
    )
    from cli.applier import ChangeApplier

    result = ChangeApplier.apply_payload(raw)
    assert result.ok is True
    assert "2 arquivo(s)" in result.message
    assert a.read_text(encoding="utf-8") == "<?php echo 'a';"
    assert b.read_text(encoding="utf-8") == "<?php echo 'b';"


def test_batch_falha_parcial_nao_grava_nada(tmp_path):
    alvo = tmp_path / "legacy_calculator.php"
    shutil.copy(FIXTURE_PHP, alvo)
    novo = tmp_path / "novo.php"
    original = alvo.read_text(encoding="utf-8")
    raw = _payload_batch(
        [
            {"file_path": str(novo), "action": "create_file", "code_content": "<?php novo", "explanation": "novo"},
            {
                "file_path": str(alvo),
                "action": "replace_symbol",
                "target_symbol": "nao_existe",
                "code_content": "function nao_existe() {}",
                "explanation": "falha proposital",
            },
        ]
    )
    from cli.applier import ChangeApplier

    result = ChangeApplier.apply_payload(raw)
    assert result.ok is False
    assert not novo.exists()
    assert alvo.read_text(encoding="utf-8") == original


def test_stage_nao_escreve_e_commit_escreve(tmp_path):
    a = tmp_path / "x.sql"
    raw = _payload_batch(
        [{"file_path": str(a), "action": "create_file", "code_content": "CREATE TABLE t (id INT);", "explanation": "migração"}]
    )
    from cli.applier import ChangeApplier

    result = ChangeApplier.stage_payload(raw)
    assert result.ok is True
    assert result.staged == {str(a): "CREATE TABLE t (id INT);"}
    assert not a.exists()
    ChangeApplier.commit_staged(result.staged)
    assert a.exists()


def test_expected_file_path_rejeita_batch(tmp_path):
    a = tmp_path / "a.php"
    raw = _payload_batch([{"file_path": str(a), "action": "create_file", "code_content": "x", "explanation": ""}])
    from cli.applier import ChangeApplier

    result = ChangeApplier.apply_payload(raw, expected_file_path=str(tmp_path / "outro.php"))
    assert result.ok is False
    assert not a.exists()
    assert "Caminho inesperado" in result.error


def test_formato_unico_continua_compativel(tmp_path):
    alvo = tmp_path / "novo.php"
    raw = json.dumps(
        {"file_path": str(alvo), "action": "create_file", "code_content": "<?php echo 1;", "explanation": "teste"}
    )
    from cli.applier import ChangeApplier

    result = ChangeApplier.apply_payload(raw)
    assert result.ok is True
    assert alvo.read_text(encoding="utf-8") == "<?php echo 1;"