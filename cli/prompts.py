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
Responda APENAS com um JSON válido (bloco de código JSON) que siga estritamente este esquema:
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

Responda APENAS com o JSON corrigido (bloco de código JSON), sem nenhum texto adicional.

---
{original_prompt}
"""


# Contrato de resposta do motor `run`: uma ação única OU um lote multi-arquivo.
RUN_RESPONSE_CONTRACT = """Responda APENAS com um JSON válido (bloco de código JSON), em português, escolhendo UMA das formas:

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
# Modo agente (TUI interativa): contrato de ferramentas (tool calling do host)
# ---------------------------------------------------------------------------
TOOLS_CONTRACT = """Você é o motor CapoeiraCode em MODO AGENTE interativo de desenvolvimento.

O backend é o CapoeiraHost e usa tool calling SIMULADO via contrato textual: quando for
necessário chamar uma ferramenta, emita EXATAMENTE uma linha por chamada neste formato (sem
blocos de código, sem JSON e sem marcação markdown):

[TOOL_CALL] nome_da_ferramenta | chave1=valor1 | chave2=valor2

Regras do formato:
- Uma linha por chamada; pode haver texto antes e depois das linhas.
- Valores são SEMPRE de uma linha física: NUNCA use Enter real dentro de chave=valor — a
  chamada termina no caractere | ou na quebra de linha.
- O caractere | separa argumentos FORA de aspas simples; dentro de um valor aspeado
  ('...') ele é literal — use sem medo em comandos com pipe: cmd='php -l app | tail -5'.
- Conteúdo de arquivo/código (`code_content` de write_file e `code` de run_python) deve
  ser enviado em **base64** (bloco contínuo, sem quebras de linha, apenas A-Z a-z 0-9 + / =)
  — evita problemas de conversão no transporte. O agente decodifica antes de gravar/executar.
- Use aspas simples para valores com espaço: chave='valor com espaço'. Dentro de aspas,
  escape a aspa e a barra invertida como \' e \\.
- Números e booleanos vão direto (2, true); estruturas como listas vão como [1, 120].
- Para chamadas paralelas, emita uma linha por chamada.
- Se não for chamar ferramenta, responda com texto puro — isso também encerra o turno.

Semântica das ferramentas:
- read_file: lê um arquivo do projeto (opcionalmente um intervalo de linhas 1-based).
  Ex.: [TOOL_CALL] read_file | path=app/views/vagas.php | lines=[1, 120]
- list_dir: lista um diretório do projeto. Ex.: [TOOL_CALL] list_dir | path=app
- run_shell: executa um comando shell no diretório do projeto (ex.: lint, testes, git).
- run_python: executa trechos de Python no diretório do projeto (ex.: inspecionar schema).
  Ex.: [TOOL_CALL] run_python | code=aW1wb3J0IG9zCnByaW50KG9zLmxpc3RkaXIoJy4nKSk=
- write_file: modifica o projeto. action ∈ create_file | replace_symbol | patch_diff;
  target_symbol obrigatório em replace_symbol; patch_diff usa unified diff.
  Ex.: [TOOL_CALL] write_file | path='nova.php' | action='create_file' | target_symbol='' | code_content=PD9waHAKJG1zZyA9ICJvaSI7CmVjaG8gJG1zZzsKPz4=
- ask_user: faz uma pergunta ao usuário (use quando faltar informação essencial).
- done: encerra o turno de desenvolvimento. Inclua um resumo objetivo do que foi feito.

Regras:
- Prefira ler arquivos antes de alterá-los; altere o MÍNIMO necessário.
- Caminhos relativos partem da raiz do projeto.
- Agrupe alterações relacionadas em write_file sequenciais; nunca desative os padrões
  de segurança do projeto (escaping, acesso a banco via camadas).
- Não invente conteúdo de arquivo que não leu; use as ferramentas.
- Se precisar da mesma informação repetidamente, não a re-leia: use o contexto da última
  resposta da ferramenta.
- Sempre finalize o turno com a ferramenta "done" (com um resumo) quando a tarefa estiver
  concluída."""


TOOLS_DECLARATION = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Lê um arquivo do projeto (opcionalmente um intervalo de linhas 1-based).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Caminho relativo ou absoluto do arquivo."},
                    "lines": {"type": "array", "items": {"type": "integer"}, "description": "[inicio, fim] 1-based."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "Lista um diretório do projeto.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Diretório a listar."}},
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": "Executa um comando shell no diretório do projeto (ex.: lint, testes, git).",
            "parameters": {
                "type": "object",
                "properties": {"cmd": {"type": "string", "description": "Comando shell a executar."}},
                "required": ["cmd"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_python",
            "description": "Executa trechos de Python no diretório do projeto (ex.: inspecionar schema).",
            "parameters": {
                "type": "object",
                "properties": {"code": {"type": "string", "description": "Código Python em base64 (A-Za-z0-9+/=, sem quebras de linha). Escolha o python do projeto quando houver."}},
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Modifica o projeto de forma atômica.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Caminho relativo ou absoluto do arquivo."},
                    "action": {"type": "string", "enum": ["create_file", "replace_symbol", "patch_diff"]},
                    "target_symbol": {"type": "string", "description": "Obrigatório em replace_symbol."},
                    "code_content": {"type": "string", "description": "Conteúdo completo/definição/unified diff em base64 (A-Za-z0-9+/=, sem quebras de linha)."},
                    "explanation": {"type": "string", "description": "Resumo de 1 linha da alteração."},
                },
                "required": ["path", "action", "code_content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": "Faz uma pergunta ao usuário quando faltar informação essencial.",
            "parameters": {
                "type": "object",
                "properties": {"question": {"type": "string"}},
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "done",
            "description": "Encerra o turno de desenvolvimento com um resumo do que foi feito.",
            "parameters": {
                "type": "object",
                "properties": {"message": {"type": "string"}},
                "required": ["message"],
            },
        },
    },
]


def build_agent_system_prompt(
    profile: str,
    specs: str = "",
    skills: str = "",
    artifacts: str = "",
    blueprints: str = "",
) -> str:
    """System prompt do agente (TUI): perfil + specs + skills + blueprints + artefatos + contrato."""
    sections = [f"## PERFIL DO PROJETO\n{profile.strip() or '(sem projeto configurado)'}"]
    if specs:
        sections.append(f"## ESPECIFICAÇÕES / PADRÕES DO SISTEMA\n{specs}")
    if skills:
        sections.append(f"## PROCEDIMENTOS (SKILLS)\n{skills}")
    if blueprints:
        sections.append(f"## BLUEPRINTS / EXEMPLOS DE ESTRUTURA\n{blueprints}")
    if artifacts:
        sections.append(f"## ARTEFATOS DO PROJETO (scan local)\n{artifacts}")
    sections.append(f"## CONTRATO DE RESPOSTA (ferramentas)\n{TOOLS_CONTRACT}")
    return "\n\n".join(sections)