from abc import ABC, abstractmethod

from tree_sitter import Query, QueryCursor

OMISSION_PLACEHOLDER = "// ... [Omitted by CapoeiraCode] ..."


class BaseLanguageReducer(ABC):
    """Interface base para os adaptadores de linguagem baseados em Tree-Sitter.

    Subclasses devem definir `self.language` e `self.parser` no __init__
    e implementar a propriedade `_FUNCTIONS_QUERY` com as capturas:
      @func_node  -> definição completa da função/método
      @func_name  -> nó do nome do símbolo
      @func_body  -> bloco de corpo a ser omitido
    """

    language = None
    parser = None

    @property
    @abstractmethod
    def _FUNCTIONS_QUERY(self) -> str:
        """Query Tree-Sitter (S-expression) que captura func_node/func_name/func_body."""

    @abstractmethod
    def extract_skeleton(self, code_content: str, target_symbol: str) -> str:
        """
        Retorna o código reduzido, omitindo corpos de funções/métodos irrelevantes
        e preservando o corpo do target_symbol.
        """

    @abstractmethod
    def extract_dependencies(self, code_content: str) -> list[str]:
        """Extrai nomes de arquivos ou módulos importados no arquivo atual."""

    # ------------------------------------------------------------------
    # Infraestrutura compartilhada entre os reducers
    # ------------------------------------------------------------------
    def _parse(self, code_content: str):
        data = code_content.encode("utf8")
        return self.parser.parse(data), data

    def _collect_functions(self, code_content: str) -> list[dict]:
        """Lista {node, name, body} para cada função/método, em ordem de aparição."""
        tree, data = self._parse(code_content)
        cursor = QueryCursor(Query(self.language, self._FUNCTIONS_QUERY))
        functions = []
        for _pattern_idx, captures in cursor.matches(tree.root_node):
            node = (captures.get("func_node") or [None])[0]
            name_node = (captures.get("func_name") or [None])[0]
            body_node = (captures.get("func_body") or [None])[0]
            if node is None or name_node is None:
                continue
            functions.append(
                {
                    "node": node,
                    "name": data[name_node.start_byte : name_node.end_byte].decode("utf8"),
                    "body": body_node,
                }
            )
        return functions

    def _replace_bodies(self, code_content: str, functions: list[dict], target_symbol: str) -> str:
        """Substitui corpos fora do alvo pelo placeholder, de baixo para cima."""
        modified = code_content.splitlines()
        ordered = sorted(functions, key=lambda f: f["body"].start_point[0] if f["body"] else -1, reverse=True)
        for func in ordered:
            body = func["body"]
            if body is None or func["name"] == target_symbol:
                continue
            start_row, start_col = body.start_point
            end_row, _ = body.end_point
            indent = " " * start_col
            placeholder = f"{indent}{{\n{indent}    {OMISSION_PLACEHOLDER}\n{indent}}}"
            modified[start_row : end_row + 1] = [placeholder]
        return "\n".join(modified)

    def _captures_text(self, code_content: str, query_scm: str, capture_name: str) -> list[str]:
        tree, data = self._parse(code_content)
        cursor = QueryCursor(Query(self.language, query_scm))
        result = []
        for node in cursor.captures(tree.root_node).get(capture_name, []):
            result.append(data[node.start_byte : node.end_byte].decode("utf8"))
        return result

    # ------------------------------------------------------------------
    # Operações usadas pelo applier (ação replace_symbol)
    # ------------------------------------------------------------------
    def find_symbol_range(self, code_content: str, target_symbol: str) -> tuple[int, int] | None:
        """Retorna (start_byte, end_byte) UTF-8 da definição completa do símbolo, ou None."""
        for func in self._collect_functions(code_content):
            if func["name"] == target_symbol:
                node = func["node"]
                return (node.start_byte, node.end_byte)
        return None

    def has_parse_errors(self, code_content: str) -> bool:
        """True se o Tree-Sitter reportou erro de sintaxe ao parsear o conteúdo."""
        tree, _ = self._parse(code_content)
        return tree.root_node.has_error
