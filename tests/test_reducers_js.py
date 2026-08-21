from pathlib import Path

import pytest

from cli.reducers import OMISSION_PLACEHOLDER, JavaScriptReducer

FIXTURE = Path(__file__).parent / "fixtures" / "dashboard.js"


@pytest.fixture()
def code() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture()
def reducer() -> JavaScriptReducer:
    return JavaScriptReducer()


def test_skeleton_preserva_corpo_do_alvo(reducer, code):
    skeleton = reducer.extract_skeleton(code, "loadDashboard")
    assert 'axios.get("/api/dashboard/" + user)' in skeleton


def test_skeleton_omite_metodo_e_arrow_fora_do_alvo(reducer, code):
    skeleton = reducer.extract_skeleton(code, "loadDashboard")
    assert "render(loadDashboard(this.user))" not in skeleton
    assert "title.toUpperCase()" not in skeleton
    assert skeleton.count(OMISSION_PLACEHOLDER) == 2


def test_alvo_pode_ser_arrow_function(reducer, code):
    skeleton = reducer.extract_skeleton(code, "formatTitle")
    assert "title.toUpperCase()" in skeleton
    assert 'axios.get("/api/dashboard/" + user)' not in skeleton


def test_extract_dependencies(reducer, code):
    deps = reducer.extract_dependencies(code)
    assert "./render.js" in deps
    assert "axios" in deps


def test_find_symbol_range_metodo_de_classe(reducer, code):
    symbol_range = reducer.find_symbol_range(code, "refresh")
    assert symbol_range is not None
    start, end = symbol_range
    trecho = code.encode("utf8")[start:end].decode("utf8")
    assert trecho.startswith("refresh()")
    assert trecho.rstrip().endswith("}")
