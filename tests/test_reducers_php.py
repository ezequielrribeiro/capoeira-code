from pathlib import Path

import pytest

from cli.reducers import OMISSION_PLACEHOLDER, PHPReducer

FIXTURE = Path(__file__).parent / "fixtures" / "legacy_calculator.php"


@pytest.fixture()
def code() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture()
def reducer() -> PHPReducer:
    return PHPReducer()


def test_skeleton_preserva_corpo_do_alvo(reducer, code):
    skeleton = reducer.extract_skeleton(code, "soma")
    assert "$total = $a + $b;" in skeleton
    assert "return $total;" in skeleton


def test_skeleton_omite_corpos_fora_do_alvo(reducer, code):
    skeleton = reducer.extract_skeleton(code, "soma")
    assert "Logger::log" not in skeleton
    assert "return $value * 2;" not in skeleton
    assert skeleton.count(OMISSION_PLACEHOLDER) == 2


def test_placeholder_respeita_indentacao(reducer, code):
    skeleton = reducer.extract_skeleton(code, "soma")
    # corpo de método de classe (coluna 8) e função top-level (coluna 4)
    assert "        " + OMISSION_PLACEHOLDER in skeleton
    assert "\n    " + OMISSION_PLACEHOLDER in skeleton


def test_extract_dependencies(reducer, code):
    deps = reducer.extract_dependencies(code)
    assert "vendor/autoload.php" in deps
    assert "App\\Utils\\Logger" in deps


def test_find_symbol_range(reducer, code):
    symbol_range = reducer.find_symbol_range(code, "soma")
    assert symbol_range is not None
    start, end = symbol_range
    trecho = code.encode("utf8")[start:end].decode("utf8")
    assert trecho.startswith("public function soma")
    assert trecho.rstrip().endswith("}")


def test_find_symbol_range_inexistente(reducer, code):
    assert reducer.find_symbol_range(code, "nao_existe") is None


def test_has_parse_errors(reducer, code):
    assert reducer.has_parse_errors(code) is False
    assert reducer.has_parse_errors("<?php function quebrado( {") is True
