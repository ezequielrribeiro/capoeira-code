import os
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, field_validator


class StackPremises(BaseModel):
    model_config = ConfigDict(extra="ignore")

    language: str = "php"
    project_root: str | None = None
    template_engine: str | None = None
    structure: dict[str, str] = {}
    conventions: list[str] = []


class BancoPremises(BaseModel):
    model_config = ConfigDict(extra="ignore")

    dsn: str | None = None
    schema_file: str | None = None

    @field_validator("dsn", "schema_file")
    @classmethod
    def _um_dos_dois(cls, v, info):
        # validação cruzada feita em Premises.validate_banco
        return v


class FrontendPremises(BaseModel):
    model_config = ConfigDict(extra="ignore")

    css_classes: list[str] = []
    components: list[str] = []


class RagPremises(BaseModel):
    model_config = ConfigDict(extra="ignore")

    working_dir: str
    python: str | None = None
    doc_types: dict[str, str] = {"user": "user", "tech": "tech", "support": "support"}


class Premises(BaseModel):
    """Arquivo de premissas de um projeto legado (projects/<nome>.yaml)."""

    model_config = ConfigDict(extra="ignore")

    name: str
    description: str = ""
    stack: StackPremises = StackPremises()
    banco: BancoPremises | None = None
    frontend: FrontendPremises = FrontendPremises()
    rag: RagPremises | None = None
    specs: list[str] | None = None
    skills: list[str] | None = None
    prompts: list[str] | None = None

    def validate_banco(self) -> str:
        """Retorna '' se banco ok, ou mensagem de orientação se algo faltar."""
        if not self.banco:
            return "Nenhuma configuração de banco em 'banco'. Informe 'dsn' ou 'schema_file'."
        if not self.banco.dsn and not self.banco.schema_file:
            return "'banco' sem 'dsn' nem 'schema_file'. Informe pelo menos um."
        return ""


EMPTY_PREMISES = Premises(name="generico")


def resolve_config_dir() -> Path:
    """Diretório de configuração do CapoeiraCode.

    Ordem: CAPOEIRA_CONFIG_DIR -> %APPDATA%/CapoeiraCode -> ~/.capoeira.
    """
    env = os.environ.get("CAPOEIRA_CONFIG_DIR")
    if env:
        return Path(env).resolve()
    appdata = os.environ.get("APPDATA")
    if appdata:
        cand = Path(appdata) / "CapoeiraCode"
        if cand.exists():
            return cand.resolve()
    return (Path.home() / ".capoeira").resolve()


def load_premises(config_dir: Path, project: str) -> Premises:
    """Carrega e valida projects/<project>.yaml dentro do diretório de config."""
    if not project:
        return EMPTY_PREMISES
    path = Path(config_dir) / "projects" / f"{project}.yaml"
    if not path.is_file():
        raise FileNotFoundError(
            f"Arquivo de premissas não encontrado: {path}. "
            "Crie-o ou use --project correto, ou defina CAPOEIRA_CONFIG_DIR."
        )
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"Premissas inválidas em {path}: esperado um mapeamento YAML.")
    try:
        return Premises(**data)
    except Exception as e:
        raise ValueError(f"Premissas inválidas em {path}: {e}") from e