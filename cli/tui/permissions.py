"""Política de permissão para ferramentas do agente.

Padrão: leituras automáticas; escrita/execução pedem aprovação (sim/não/sempre).
`readonly` proíbe escrita e execução. `auto` aceita tudo (uso pessoal).
"""

MODE_ASK = "ask"
MODE_READONLY = "readonly"
MODE_AUTO = "auto"

READ_TOOLS = {"read_file", "list_dir"}
WRITE_TOOLS = {"write_file"}
EXEC_TOOLS = {"run_shell", "run_python"}


class PermissionGate:
    def __init__(self, mode: str = MODE_ASK):
        self.mode = mode
        self.always: dict[str, str] = {}

    @property
    def readonly(self) -> bool:
        return self.mode == MODE_READONLY

    def allow(self, tool: str, description: str, ask) -> bool:
        """Verifica permissão para executar `tool`. `ask` é callable -> 'y'|'n'|'a'."""
        if tool in READ_TOOLS:
            return True
        if tool in self.always and self.always[tool] == tool:
            return True
        if self.mode == MODE_AUTO:
            return True
        if self.mode == MODE_READONLY:
            return False
        # modo ask
        choice = ask(description)
        if choice == "a":
            self.always[tool] = tool
            return True
        return choice == "y"