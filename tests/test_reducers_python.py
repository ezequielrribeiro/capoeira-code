from pathlib import Path

import pytest

from cli.reducers import OMISSION_PLACEHOLDER, PYTHON_OMISSION_PLACEHOLDER, PythonReducer

FIXTURE = Path(__file__).parent / "fixtures" / "legacy_service.py"


@pytest.fixture()
def code() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture()
def reducer() -> PythonReducer:
    return PythonReducer()


def test_skeleton_preserva_corpo_do_alvo(reducer, code):
    skeleton = reducer.extract_skeleton(code, "fetch")
    assert "data = rq.get(url)" in skeleton
    assert "return data.text" in skeleton


def test_skeleton_omite_corpos_fora_do_alvo(reducer, code):
    skeleton = reducer.extract_skeleton(code, "fetch")
    assert "value = os.getenv(key, \"\")" not in skeleton
    assert "return value * 2" not in skeleton
    assert skeleton.count(PYTHON_OMISSION_PLACEHOLDER) == 3


def test_placeholder_respeita_indentacao(reducer, code):
    skeleton = reducer.extract_skeleton(code, "fetch")
    # corpo de método de classe (coluna 8)
    assert "        " + PYTHON_OMISSION_PLACEHOLDER in skeleton


def test_placeholder_python_nao_usar_braces(reducer, code):
    skeleton = reducer.extract_skeleton(code, "fetch")
    assert OMISSION_PLACEHOLDER not in skeleton


def test_extract_dependencies(reducer, code):
    deps = reducer.extract_dependencies(code)
    assert "os" in deps
    assert "requests" in deps
    assert "pathlib" in deps


def test_find_symbol_range(reducer, code):
    symbol_range = reducer.find_symbol_range(code, "fetch")
    assert symbol_range is not None
    start, end = symbol_range
    trecho = code.encode("utf8")[start:end].decode("utf8")
    assert trecho.startswith("def fetch")
    assert trecho.rstrip().endswith("return data.text")


def test_find_symbol_range_async(reducer, code):
    symbol_range = reducer.find_symbol_range(code, "load")
    assert symbol_range is not None
    start, end = symbol_range
    trecho = code.encode("utf8")[start:end].decode("utf8")
    assert trecho.startswith("async def load")


def test_find_symbol_range_inexistente(reducer, code):
    assert reducer.find_symbol_range(code, "nao_existe") is None


def test_has_parse_errors(reducer, code):
    assert reducer.has_parse_errors(code) is False
    assert reducer.has_parse_errors("def quebrado(:") is True
