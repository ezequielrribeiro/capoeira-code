"""Redutores de contexto baseados em Tree-Sitter e registro por extensão de arquivo."""

from .base import BaseLanguageReducer, OMISSION_PLACEHOLDER, PYTHON_OMISSION_PLACEHOLDER
from .tree_sitter_js import JavaScriptReducer
from .tree_sitter_php import PHPReducer
from .tree_sitter_python import PythonReducer

_REDUCERS_BY_EXTENSION = {
    ".php": PHPReducer,
    ".js": JavaScriptReducer,
    ".mjs": JavaScriptReducer,
    ".cjs": JavaScriptReducer,
    ".py": PythonReducer,
}


def get_reducer_for_path(file_path: str) -> BaseLanguageReducer:
    """Retorna uma instância do reducer adequado à extensão do arquivo."""
    import os

    ext = os.path.splitext(file_path)[1].lower()
    reducer_cls = _REDUCERS_BY_EXTENSION.get(ext)
    if reducer_cls is None:
        suportadas = ", ".join(sorted(_REDUCERS_BY_EXTENSION))
        raise ValueError(f"Extensão '{ext}' sem reducer suportado. Suportadas: {suportadas}")
    return reducer_cls()


__all__ = [
    "BaseLanguageReducer",
    "JavaScriptReducer",
    "OMISSION_PLACEHOLDER",
    "PHPReducer",
    "PYTHON_OMISSION_PLACEHOLDER",
    "PythonReducer",
    "get_reducer_for_path",
]
