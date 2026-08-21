import json
import shutil
from pathlib import Path

import pytest

from cli.applier import ChangeApplier, apply_unified_diff

FIXTURE_PHP = Path(__file__).parent / "fixtures" / "legacy_calculator.php"


def _payload(**kwargs) -> str:
    base = {
        "file_path": "alvo.php",
        "action": "create_file",
        "code_content": "<?php echo 1;",
        "explanation": "teste",
    }
    base.update(kwargs)
    return json.dumps(base)


# ----------------------------------------------------------------------
# Parsing da resposta do LLM
# ----------------------------------------------------------------------
def test_parse_falha_em_resposta_sem_json():
    result = ChangeApplier.apply_payload("Desculpe, não consegui entender.")
    assert result.ok is False
    assert "JSON" in result.error


def test_parse_falha_em_json_incompleto():
    result = ChangeApplier.apply_payload('{"file_path": "x.php", "action": "create_file"')
    assert result.ok is False


def test_parse_falha_em_schema_incompleto():
    # falta code_content (obrigatório na spec)
    result = ChangeApplier.apply_payload('{"file_path": "x.php", "action": "create_file"}')
    assert result.ok is False


def test_parse_aceita_prosa_e_cerca_markdown(tmp_path):
    alvo = tmp_path / "novo.php"
    bruto = (
        "Claro! Aqui está o arquivo:\n"
        "```json\n"
        + _payload(file_path=str(alvo), code_content="<?php echo 42;")
        + "\n```\nEspero ter ajudado!"
    )
    result = ChangeApplier.apply_payload(bruto)
    assert result.ok is True
    assert alvo.read_text(encoding="utf-8") == "<?php echo 42;"


# ----------------------------------------------------------------------
# create_file
# ----------------------------------------------------------------------
def test_create_file_cria_diretorios_e_arquivo(tmp_path):
    alvo = tmp_path / "subdir" / "novo.php"
    result = ChangeApplier.apply_payload(
        _payload(file_path=str(alvo), code_content="<?php echo 'ok';")
    )
    assert result.ok is True
    assert alvo.read_text(encoding="utf-8") == "<?php echo 'ok';"


def test_create_file_json_invalido_nao_cria_arquivo(tmp_path):
    alvo = tmp_path / "novo.php"
    result = ChangeApplier.apply_payload("texto qualquer sem json")
    assert result.ok is False
    assert not alvo.exists()


# ----------------------------------------------------------------------
# replace_symbol
# ----------------------------------------------------------------------
@pytest.fixture()
def arquivo_php(tmp_path) -> Path:
    alvo = tmp_path / "legacy_calculator.php"
    shutil.copy(FIXTURE_PHP, alvo)
    return alvo


def test_replace_symbol_substitui_apenas_o_alvo(arquivo_php):
    original = arquivo_php.read_text(encoding="utf-8")
    novo_metodo = (
        "public function soma($a, $b)\n"
        "    {\n"
        "        // agora com validação\n"
        "        return max($a, $b) + min($a, $b);\n"
        "    }"
    )
    result = ChangeApplier.apply_payload(
        _payload(
            file_path=str(arquivo_php),
            action="replace_symbol",
            target_symbol="soma",
            code_content=novo_metodo,
        )
    )
    assert result.ok is True
    atualizado = arquivo_php.read_text(encoding="utf-8")
    assert "return max($a, $b) + min($a, $b);" in atualizado
    # o restante do arquivo permanece intacto
    assert "Logger::log($message);" in atualizado
    assert "function calc_helper" in atualizado
    assert len(atualizado) > len(novo_metodo)
    assert atualizado != original


def test_replace_symbol_simbolo_inexistente_nao_modifica_arquivo(arquivo_php):
    original = arquivo_php.read_text(encoding="utf-8")
    result = ChangeApplier.apply_payload(
        _payload(
            file_path=str(arquivo_php),
            action="replace_symbol",
            target_symbol="nao_existe",
            code_content="function nao_existe() {}",
        )
    )
    assert result.ok is False
    assert arquivo_php.read_text(encoding="utf-8") == original


def test_replace_symbol_codigo_quebrado_nao_modifica_arquivo(arquivo_php):
    original = arquivo_php.read_text(encoding="utf-8")
    result = ChangeApplier.apply_payload(
        _payload(
            file_path=str(arquivo_php),
            action="replace_symbol",
            target_symbol="soma",
            code_content="public function soma($a, $b) { { {",
        )
    )
    assert result.ok is False
    assert arquivo_php.read_text(encoding="utf-8") == original


def test_replace_symbol_sem_target_symbol_falha(arquivo_php):
    result = ChangeApplier.apply_payload(
        _payload(file_path=str(arquivo_php), action="replace_symbol", code_content="x")
    )
    assert result.ok is False
    assert "target_symbol" in result.error


# ----------------------------------------------------------------------
# patch_diff
# ----------------------------------------------------------------------
def test_apply_unified_diff_basico():
    original = "a\nb\nc\n"
    diff = "--- a/f.txt\n+++ b/f.txt\n@@ -1,3 +1,3 @@\n a\n-b\n+B\n c\n"
    assert apply_unified_diff(original, diff) == "a\nB\nc\n"


def test_apply_unified_diff_contexto_errado_falha():
    original = "a\nb\nc\n"
    diff = "@@ -1,3 +1,3 @@\n a\n-X\n+B\n c\n"
    with pytest.raises(ValueError):
        apply_unified_diff(original, diff)


def test_patch_diff_aplica_e_preserva_arquivo_em_erro(arquivo_php):
    original = arquivo_php.read_text(encoding="utf-8")
    diff = (
        "@@ -1,4 +1,4 @@\n"
        " <?php\n"
        " \n"
        '-require_once "vendor/autoload.php";\n'
        '+require_once "bootstrap.php";\n'
    )
    result = ChangeApplier.apply_payload(
        _payload(file_path=str(arquivo_php), action="patch_diff", code_content=diff)
    )
    assert result.ok is True
    assert 'require_once "bootstrap.php";' in arquivo_php.read_text(encoding="utf-8")

    diff_ruim = "@@ -1,2 +1,2 @@\n-CONTEUDO_QUE_NAO_EXISTE\n+qualquer\n"
    result = ChangeApplier.apply_payload(
        _payload(file_path=str(arquivo_php), action="patch_diff", code_content=diff_ruim)
    )
    assert result.ok is False
    assert arquivo_php.read_text(encoding="utf-8") != original  # já modificado pelo diff bom
    assert "CONTEUDO_QUE_NAO_EXISTE" not in arquivo_php.read_text(encoding="utf-8")
