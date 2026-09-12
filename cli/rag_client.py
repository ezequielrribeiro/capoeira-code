import subprocess

from .project.premises import Premises

DEFAULT_PYTHON = "python"
DEFAULT_TIMEOUT = 180.0


class RagNotConfiguredError(Exception):
    """O projeto não tem `rag.working_dir` configurado nas premissas."""


class RagError(Exception):
    """Falha ao executar o local-rag-system (subprocess)."""


class RagClient:
    """Consulta o `local-rag-system` (CLI, via subprocess) para trazer contexto.

    O RAG é independente do backend do CapoeiraCode e roda no working_dir
    informado nas premissas (rag.working_dir).
    """

    def __init__(self, premises: Premises, timeout: float = DEFAULT_TIMEOUT):
        if not premises.rag or not premises.rag.working_dir:
            raise RagNotConfiguredError(
                "Projeto sem 'rag.working_dir' nas premissas. Configure o yaml do projeto."
            )
        self.premises = premises
        self.timeout = timeout

    def _build_command(self, query: str, doc_type: str | None) -> list[str]:
        rag = self.premises.rag
        cmd = [rag.python or DEFAULT_PYTHON, "main.py", "query", query]
        if doc_type:
            mapped = rag.doc_types.get(doc_type, doc_type)
            cmd += ["--doc-type", mapped]
        return cmd

    def ask(self, query: str, doc_type: str | None = None) -> str:
        """Executa uma consulta no RAG e retorna a saída (contexto) como texto."""
        cmd = self._build_command(query, doc_type)
        try:
            proc = subprocess.run(
                cmd,
                cwd=self.premises.rag.working_dir,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
            )
        except FileNotFoundError as e:
            raise RagError(f"Executável do RAG não encontrado ({cmd[0]}). Verifique rag.python.") from e
        except subprocess.TimeoutExpired as e:
            raise RagError(f"Timeout ao consultar o RAG ({self.timeout:.0f}s).") from e

        if proc.returncode != 0:
            raise RagError(
                f"local-rag-system falhou (exit={proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}"
            )
        out = proc.stdout.strip()
        if not out:
            raise RagError("RAG retornou sem conteúdo.")
        return out