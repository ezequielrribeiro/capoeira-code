import json

# Esquema de resposta obrigatório injetado em todo prompt de mutação (spec §5).
RESPONSE_SCHEMA = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "file_path": {"type": "string"},
        "action": {"type": "string", "enum": ["replace_symbol", "create_file", "patch_diff"]},
        "target_symbol": {"type": "string"},
        "code_content": {"type": "string"},
        "explanation": {"type": "string", "description": "Resumo de 1 linha da alteração"},
    },
    "required": ["file_path", "action", "code_content"],
}


def _schema_text() -> str:
    return json.dumps(RESPONSE_SCHEMA, indent=2, ensure_ascii=False)


def build_refactor_prompt(file_path: str, symbol: str, instruction: str, skeleton: str) -> str:
    return f"""INSTRUÇÃO: {instruction}
SÍMBOLO ALVO: {symbol}
CAMINHO DO ARQUIVO: {file_path}

ESQUELETO DO CÓDIGO DO PROJETO:
{skeleton}

Responda APENAS com um JSON válido que siga estritamente este esquema:
{_schema_text()}

Use action "replace_symbol" com target_symbol "{symbol}" e coloque em "code_content"
o código completo e atualizado da definição do símbolo alvo (e apenas dele).
Use "file_path" exatamente igual a "{file_path}".
"""


def build_generate_prompt(file_path: str, instruction: str, symbol: str | None, context: str | None) -> str:
    target = symbol or ""
    action = "replace_symbol" if symbol else "create_file"
    contexto = f"\n\nCONTEXTO DO PROJETO (esqueleto de arquivo relacionado):\n{context}\n" if context else ""
    return f"""INSTRUÇÃO: {instruction}
CAMINHO DO ARQUIVO ALVO: {file_path}
{"SÍMBOLO ALVO: " + symbol if symbol else "AÇÃO: criar um novo arquivo/artefato"}
{contexto}
Responda APENAS com um JSON válido que siga estritamente este esquema:
{_schema_text()}

Use action "{action}" com "file_path" exatamente igual a "{file_path}"{" e target_symbol \"" + target + "\"" if symbol else ""}.
Em "code_content" coloque o conteúdo completo e correto a ser gravado.
"""


def build_explain_prompt(file_path: str, symbol: str | None, skeleton: str) -> str:
    alvo = f" Símbolo alvo: {symbol}." if symbol else ""
    return f"""Explique o código abaixo de forma concisa e técnica, em português.
Autor: CapoeiraCode, focado em manutenção de sistemas legados.
Arquivo: {file_path}{alvo}
Explique propósito, fluxo principal e pontos de atenção (acoplamento, efeitos
colaterais, riscos de refatoração). Não escreva código novo.

CÓDIGO (esqueleto, corpos fora do alvo omitidos):
{skeleton}
"""


def build_retry_prompt(original_prompt: str, error: str) -> str:
    return f"""A resposta anterior não pôde ser aplicada: {error}

Responda APENAS com o JSON corrigido, sem nenhum texto adicional.

---
{original_prompt}
"""


# Contrato de resposta do motor `run`: uma ação única OU um lote multi-arquivo.
RUN_RESPONSE_CONTRACT = """Responda APENAS com um JSON válido, em português, escolhendo UMA das formas:

1) Ação única (uma mudança):
{
  "file_path": "caminho/arquivo.php",
  "action": "create_file | replace_symbol | patch_diff",
  "target_symbol": "nome_do_simbolo",   // obrigatório se action = replace_symbol
  "code_content": "conteúdo completo ou unified diff",
  "explanation": "resumo de 1 linha"
}

2) Lote multi-arquivo (várias mudanças numa resposta — use quando tocar em 2+ arquivos):
{
  "files": [
    { "file_path": "...", "action": "create_file", "code_content": "...", "explanation": "..." },
    { "file_path": "...", "action": "replace_symbol", "target_symbol": "...", "code_content": "...", "explanation": "..." },
    { "file_path": "...", "action": "patch_diff", "code_content": "...", "explanation": "..." }
  ]
}

Regras:
- "file_path" sempre relativo ou absoluto (caminho real do arquivo no projeto).
- Sobre "code_content": conteúdo completo do arquivo (create_file), definição completa
  do símbolo (replace_symbol), ou unified diff com contexto (patch_diff).
- Não escreva código em "explanation"; resuma em 1 linha."""


def build_run_prompt(
    instruction: str,
    profile: str,
    specs: str = "",
    skills: str = "",
    context_files: str = "",
    rag_context: str = "",
    prompt_template: str = "",
) -> str:
    sections = []
    if prompt_template:
        sections.append(f"## DIRETRIZES DA TAREFA\n{prompt_template.strip()}")
    sections.append(f"## PERFIL DO PROJETO\n{profile.strip() or '(sem projeto configurado)'}")
    if specs:
        sections.append(f"## ESPECIFICAÇÕES / PADRÕES DO SISTEMA\n{specs}")
    if skills:
        sections.append(f"## PROCEDIMENTOS DISPONÍVEIS\n{skills}")
    if rag_context:
        sections.append(f"## CONTEXTO DA BASE DE CONHECIMENTO (RAG)\n{rag_context}")
    if context_files:
        sections.append(f"## CÓDIGO DE CONTEXTO (esqueleto)\n{context_files}")

    sections.append(f"## INSTRUÇÃO\n{instruction.strip()}")
    sections.append(f"## CONTRATO DE RESPOSTA\n{RUN_RESPONSE_CONTRACT}")
    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Modo agente (TUI interativa): contrato de ferramentas (steps)
# ---------------------------------------------------------------------------
TOOLS_CONTRACT = """Você é o motor CapoeiraCode em MODO AGENTE interativo de desenvolvimento.

Para cada turno, responda SEMPRE com um único JSON contendo uma lista de passos:

{
  "steps": [
    { "tool": "read_file",  "path": "app/views/vagas.php", "lines": [1, 120] },
    { "tool": "list_dir",   "path": "app" },
    { "tool": "run_shell",  "cmd": "php -l app/views/vagas.php" },
    { "tool": "run_python", "code": "import os; print(os.listdir('.'))" },
    { "tool": "write_file", "path": "app/models/Db.php", "action": "replace_symbol",
      "target_symbol": "conectar", "code_content": "..." },
    { "tool": "ask_user",   "question": "Qual o nome da tela?" },
    { "tool": "done",       "message": "Resumo do que foi feito" }
  ]
}

Semântica das ferramentas:
- read_file: lê um arquivo do projeto (opcionalmente um intervalo de linhas 1-based).
- list_dir: lista um diretório do projeto.
- run_shell: executa um comando shell no diretório do projeto (ex.: lint, testes, git).
- run_python: executa trechos de Python no diretório do projeto (ex.: inspecionar schema).
- write_file: modifica o projeto. action ∈ create_file | replace_symbol | patch_diff;
  target_symbol obrigatório em replace_symbol; patch_diff usa unified diff.
- ask_user: faz uma pergunta ao usuário (use quando faltar informação essencial).
- done: encerra o turno de desenvolvimento. Inclua um resumo objetivo do que foi feito.

Regras:
- "tool" é obrigatório em todo passo; ignore chaves extras.
- Prefira ler arquivos antes de alterá-los; altere o MÍNIMO necessário.
- Caminhos relativos partem da raiz do projeto.
- Agrupe alterações relacionadas em write_file sequenciais; nunca desative os padrões
  de segurança do projeto (escaping, acesso a banco via camadas).
- Não invente conteúdo de arquivo que não leu; use as ferramentas.
- Se precisar da mesma informação repetidamente, não a re-leia: use o contexto da última
  resposta da ferramenta.
- Sempre finalize o turno com um passo "done" quando a tarefa estiver concluída."""


def build_agent_system_prompt(
    profile: str,
    specs: str = "",
    skills: str = "",
    artifacts: str = "",
) -> str:
    """System prompt do agente (TUI): perfil + specs + skills + artefatos + contrato."""
    sections = [f"## PERFIL DO PROJETO\n{profile.strip() or '(sem projeto configurado)'}"]
    if specs:
        sections.append(f"## ESPECIFICAÇÕES / PADRÕES DO SISTEMA\n{specs}")
    if skills:
        sections.append(f"## PROCEDIMENTOS (SKILLS)\n{skills}")
    if artifacts:
        sections.append(f"## ARTEFATOS DO PROJETO (scan local)\n{artifacts}")
    sections.append(f"## CONTRATO DE RESPOSTA (ferramentas)\n{TOOLS_CONTRACT}")
    return "\n\n".join(sections)