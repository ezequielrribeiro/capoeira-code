from tree_sitter import Language, Parser
import tree_sitter_php as tsphp

from .base import BaseLanguageReducer

# Nós da gramática PHP (tree-sitter-php) verificados contra a saída real do parser.
_FUNCTIONS_QUERY = """
(method_declaration name: (name) @func_name body: (compound_statement) @func_body) @func_node
(function_definition name: (name) @func_name body: (compound_statement) @func_body) @func_node
"""

_DEPENDENCIES_QUERY = """
(require_expression (encapsed_string (string_content) @dep))
(require_once_expression (encapsed_string (string_content) @dep))
(include_expression (encapsed_string (string_content) @dep))
(include_once_expression (encapsed_string (string_content) @dep))
(namespace_use_declaration (namespace_use_clause (qualified_name) @dep))
"""


class PHPReducer(BaseLanguageReducer):
    """Redutor de contexto para PHP (métodos, funções e classes)."""

    _FUNCTIONS_QUERY = _FUNCTIONS_QUERY

    def __init__(self):
        self.language = Language(tsphp.language_php())
        self.parser = Parser(self.language)

    def extract_skeleton(self, code_content: str, target_symbol: str) -> str:
        return self._replace_bodies(code_content, self._collect_functions(code_content), target_symbol)

    def extract_dependencies(self, code_content: str) -> list[str]:
        return self._captures_text(code_content, _DEPENDENCIES_QUERY, "dep")
