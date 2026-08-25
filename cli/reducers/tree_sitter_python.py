from tree_sitter import Language, Parser
import tree_sitter_python as tsp

from .base import BaseLanguageReducer, PYTHON_OMISSION_PLACEHOLDER

# Nós da gramática Python (tree-sitter-python) verificados contra a saída real do parser.
# Cobrem `def`, `async def` e métodos de classe (function_definition aninhados).
_FUNCTIONS_QUERY = """
(function_definition name: (identifier) @func_name body: (block) @func_body) @func_node
"""

_DEPENDENCIES_QUERY = """
(import_statement name: (dotted_name) @dep)
(import_statement name: (aliased_import name: (dotted_name) @dep))
(import_from_statement module_name: (dotted_name) @dep)
"""


class PythonReducer(BaseLanguageReducer):
    """Redutor de contexto para Python (funções, métodos async/sync e classes)."""

    _FUNCTIONS_QUERY = _FUNCTIONS_QUERY

    def __init__(self):
        self.language = Language(tsp.language())
        self.parser = Parser(self.language)

    def extract_skeleton(self, code_content: str, target_symbol: str) -> str:
        return self._replace_bodies(code_content, self._collect_functions(code_content), target_symbol)

    # Python usa indentação (não chaves), então a omissão de corpos usa um comentário
    # `# ...` no nível de indentação do bloco, em vez do placeholder `// ...` base.
    def _replace_bodies(self, code_content: str, functions: list[dict], target_symbol: str) -> str:
        modified = code_content.splitlines()
        ordered = sorted(functions, key=lambda f: f["body"].start_point[0] if f["body"] else -1, reverse=True)
        for func in ordered:
            body = func["body"]
            if body is None or func["name"] == target_symbol:
                continue
            indent = " " * body.start_point[1]
            placeholder = f"{indent}{PYTHON_OMISSION_PLACEHOLDER}"
            modified[body.start_point[0] : body.end_point[0] + 1] = [placeholder]
        return "\n".join(modified)

    def extract_dependencies(self, code_content: str) -> list[str]:
        return self._captures_text(code_content, _DEPENDENCIES_QUERY, "dep")
