"""Loader de instruções do CapoeiraCode (specs/skills/prompts declarativos)."""

from pathlib import Path

from ..project.premises import Premises

MD_EXT = ".md"


def _read_dir(dir_path: Path, selected: list[str] | None) -> dict[str, str]:
    """Lê *.md do diretório.

    Se `selected` for None (campo omitido), carrega todos os arquivos; se for
    uma lista (mesmo vazia), carrega somente os nomes informados.
    """
    if not dir_path.is_dir():
        return {}
    wanted = {s.lower() for s in selected} if selected is not None else None
    result: dict[str, str] = {}
    for path in sorted(dir_path.glob(f"*{MD_EXT}")):
        stem = path.stem.lower()
        if wanted is not None and stem not in wanted:
            continue
        result[stem] = path.read_text(encoding="utf-8")
    return result


class InstructionSet:
    """Conjunto carregado do diretório de config: specs, skills, prompts e blueprints."""

    def __init__(
        self,
        specs: dict[str, str],
        skills: dict[str, str],
        prompts: dict[str, str],
        blueprints: dict[str, str] | None = None,
    ):
        self.specs = specs
        self.skills = skills
        self.prompts = prompts
        self.blueprints = blueprints or {}

    @property
    def specs_combined(self) -> str:
        return "\n\n---\n\n".join(self.specs.values()).strip()

    @property
    def skills_combined(self) -> str:
        return "\n\n---\n\n".join(self.skills.values()).strip()

    @property
    def blueprints_combined(self) -> str:
        return "\n\n---\n\n".join(self.blueprints.values()).strip()

    def get_prompt(self, name: str | None) -> str:
        if not name:
            return ""
        key = name.lower()
        if key.endswith(".md"):
            key = key[: -len(".md")]
        return self.prompts.get(key, "")


def load_instruction_set(config_dir: Path, premises: Premises) -> InstructionSet:
    """Carrega specs/skills/prompts/blueprints do config_dir usando as seleções do yaml."""
    return InstructionSet(
        specs=_read_dir(config_dir / "specs", premises.specs),
        skills=_read_dir(config_dir / "skills", premises.skills),
        prompts=_read_dir(config_dir / "prompts", premises.prompts),
        blueprints=_read_dir(config_dir / "blueprints", premises.blueprints),
    )


def render_project_profile(premises: Premises) -> str:
    """Converte as premissas em um resumo textual injetável no prompt."""
    lines = [f"Projeto: {premises.name}"]
    if premises.description:
        lines.append(f"Descrição: {premises.description}")

    stack = premises.stack
    lines.append(f"Stack: {stack.language or 'php'}")
    if stack.project_root:
        lines.append(f"Raiz: {stack.project_root}")
    if stack.template_engine:
        lines.append(f"Template engine: {stack.template_engine}")
    if stack.structure:
        lines.append("Estrutura de pastas: " + ", ".join(f"{r}={p}" for r, p in stack.structure.items()))
    if stack.conventions:
        lines.append("Convenções:")
        lines.extend(f"  - {c}" for c in stack.conventions)

    if premises.frontend.css_classes:
        lines.append("Classes CSS em uso: " + ", ".join(premises.frontend.css_classes))
    if premises.frontend.components:
        lines.append("Componentes de UI: " + ", ".join(premises.frontend.components))

    if premises.banco:
        if premises.banco.dsn:
            lines.append(f"Banco (DSN): {premises.banco.dsn}")
        if premises.banco.schema_file:
            lines.append(f"Banco (schema): {premises.banco.schema_file}")
    return "\n".join(lines)