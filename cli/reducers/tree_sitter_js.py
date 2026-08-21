from tree_sitter import Language, Parser
import tree_sitter_javascript as tsjs

from .base import BaseLanguageReducer

# Nós da gramática JavaScript (tree-sitter-javascript) verificados contra a saída real.
_FUNCTIONS_QUERY = """
(function_declaration name: (identifier) @func_name body: (statement_block) @func_body) @func_node
(generator_function_declaration name: (identifier) @func_name body: (statement_block) @func_body) @func_node
(method_definition name: (property_identifier) @func_name body: (statement_block) @func_body) @func_node
(lexical_declaration (variable_declarator name: (identifier) @func_name value: (arrow_function body: (statement_block) @func_body))) @func_node
(variable_declaration (variable_declarator name: (identifier) @func_name value: [(arrow_function body: (statement_block) @func_body) (function_expression body: (statement_block) @func_body)])) @func_node
"""

_DEPENDENCIES_QUERY = """
(import_statement source: (string (string_fragment) @dep))
(call_expression
  function: (identifier) @require_fn
  arguments: (arguments (string (string_fragment) @dep))
  (#eq? @require_fn "require"))
"""


class JavaScriptReducer(BaseLanguageReducer):
    """Redutor de contexto para JavaScript (funções, métodos, arrows e generators)."""

    _FUNCTIONS_QUERY = _FUNCTIONS_QUERY

    def __init__(self):
        self.language = Language(tsjs.language())
        self.parser = Parser(self.language)

    def extract_skeleton(self, code_content: str, target_symbol: str) -> str:
        return self._replace_bodies(code_content, self._collect_functions(code_content), target_symbol)

    def extract_dependencies(self, code_content: str) -> list[str]:
        return self._captures_text(code_content, _DEPENDENCIES_QUERY, "dep")
