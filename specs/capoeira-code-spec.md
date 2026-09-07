# 📜 Software Specification & Implementation Architecture: CapoeiraCode

**Projeto:** CapoeiraCode  
**Versão:** `4.0.0`  
**Status:** `Approved — Iteração 5 (modo agente interativo/TUI com ferramentas) implementada e testada`  
**Data:** 8 de Setembro de 2026  

---

## 1. Visão Geral e Objetivos

### 1.1. Propósito
O **CapoeiraCode** é um agente CLI para manutenção, refatoração, criação de telas/artefatos
e **automação de rotina** em **sistemas legados** (foco inicial em PHP). Reduz o contexto do
código via AST (*Tree-Sitter*) e conversa com um **backend compatível com a API do Ollama** —
Ollama nativo ou o gateway local [CapoeiraHost](https://github.com/ezequielrribeiro/capoeira-host) —
via HTTP/JSON (`POST /api/chat`). Não há navegador, extensão nem ponte WebSocket.

A partir da v3.0.0 o CLI vira um **motor de instrução declarativo** (estilo OpenCode):
especs/skills/prompts vivem em arquivos no diretório de config, e o LLM **decide a ação**
sobre os arquivos do projeto (inclusive **lote multi-arquivo**), com base num perfil de
**premissas por projeto** e, opcionalmente, contexto de um RAG local.

Na v4.0.0 entra o **modo agente interativo (TUI)**: `capoeira [PATH]` abre uma interface
textual (prompt_toolkit + rich) que cria um **workspace de sessão** por projeto, gera
**artefatos de scan** (árvore, dependências, ASTs) e roda um **loop de desenvolvimento** em
que o LLM responde com **passos de ferramentas** (`read_file`, `list_dir`, `run_shell`,
`run_python`, `write_file`, `ask_user`, `done`) — leituras automáticas; escrita/execução
seguem política de permissão — até a conclusão da tarefa.

### 1.2. Problema de Negócio
Sistemas legados possuem bases extensas, acopladas e com pouca documentação. Rotinas como
"criar tela", "corrigir bug", "otimizar" e "ajustar front-end" exigem conhecer padrões do
projeto (estrutura de pastas, convenções, schema do banco) — conhecimento normalmente
espalhado e não automatizável com subcomandos rígidos.

### 1.3. Objetivos de Design
* **Economia Extrema de Tokens:** Redução de até 90% do contexto via AST (*Tree-Sitter*) e grafos de dependência locais.
* **Backend-Agnóstico (API Ollama):** `POST {base_url}/api/chat`, funcionando com Ollama nativo ou gateways Ollama-compatíveis (CapoeiraHost) — sem chave de API.
* **Motor de Instrução (estilo OpenCode):** o usuário fornece **instrução livre** + arquivos de `specs/skills/prompts`; um comando genérico (`run`) monta o prompt rico e o LLM decide as ações.
* **Premissas por projeto:** arquivo `projects/<nome>.yaml` descreve stack, estrutura, convenções, banco (schema) e RAG — reutilizável entre projetos/empresas.
* **Operação Atômica:** lote multi-arquivo todo-or-nothing (RNF-04) com `--dry-run` para revisão.
* **Multi-linguagem Expansível:** PHP/JS/Python hoje; HTML/CSS/SQL planejados.

---

## 2. Arquitetura do Sistema

```text
┌───────────────────────────────────────────────────────────────────────────────────┐
│                          CAPOEIRA CODE (CLI) ✅                                   │
│                                                                                   │
│  ┌────────────────┐    ┌──────────────────┐    ┌─────────────────────────┐        │
│  │ Context Engine │───>│ AST/Tree-Sitter  │───>│ Structural Reducer      │        │
│  └────────────────┘    └──────────────────┘    └──────────┬──────────────┘        │
│                                                          │ (contexto reduzido)    │
│  ┌──────────────────────────┐  ┌────────────────────────┐│                        │
│  │ Premissas do projeto     │  │ Instr. motor (run):     ││ (prompt)              │
│  │ projects/*.yaml + specs/ │  │ specs + skills + prompts││                        │
│  │ skills/ + prompts/       │  │ + RAG + perfil + instrução│                       │
│  └──────────────────────────┘  └───────────┬────────────┘│                        │
│                                            │              │                        │
│  ┌────────────────┐    ┌──────────────────▼──────────────▼──────────┐             │
│  │ Diff Applier   │<───│  LLM decide ações (create/replace/patch)   │             │
│  │ (multi-arquivo, │    └──────────────────┬────────────────────────┘             │
│  │  atômico)      │                       │ HTTP POST /api/chat                  │
│  └────────────────┘                        │                                      │
└────────────────────────────────────────────┼──────────────────────────────────────┘
                                              │ (JSON Ollama)
                              ┌──────────────▼───────────────────┐
                              │  LLM BACKEND (Ollama / CapoeiraHost)│
                              └──────────────┬───────────────────┘
                                             │ subprocess (RAG próprio)
                              ┌──────────────▼───────────────────┐
                              │  local-rag-system (docs/tickets)  │
                              └──────────────────────────────────┘
```

**Estado:** motor `run`, premissas por projeto, scanner de dependências, `ask` (RAG) e
applier multi-arquivo implementados e testados; não há componente de navegador neste repo.
Na v4.0.0, `capoeira [PATH]` inicia a **TUI** que: (a) cria `configs/<slug>/` no diretório
de config com workspace de sessão; (b) gera artefatos de scan (`tree.txt`,
`dependencies.json`, `asts/`); (c) roda o agente com ferramentas (item 5 da visão).

---

## 3. Especificação dos Módulos (CLI Engine)

### 3.1. Engine de Redução de Contexto (Context Reducer)
* **Parser Base:** `Tree-Sitter` com suporte a gramáticas parametrizáveis.
* **Linguagens:** **PHP** ✅, **JavaScript** ✅, **Python** ✅ (métodos, funções, deps via `require/use`, `import`, `import_from`); **HTML** ⏳, **CSS** ⏳, **SQL** ⏳ planejados.
* **Regra de Omissão:** corpos fora do símbolo-alvo viram `// ... [Omitted by CapoeiraCode] ...` (`OMISSION_PLACEHOLDER`) para PHP/JS e `# ... [Omitted by CapoeiraCode] ...` (`PYTHON_OMISSION_PLACEHOLDER`) para Python — em `cli/reducers/base.py`.

### 3.2. Interface de Redutores (Language Plugin Interface)

```python
# cli/reducers/base.py (resumo)
class BaseLanguageReducer(ABC):
    @abstractmethod
    def extract_skeleton(self, code_content: str, target_symbol: str) -> str: ...
    @abstractmethod
    def extract_dependencies(self, code_content: str) -> list[str]: ...
    def find_symbol_range(self, code_content: str, target_symbol: str) -> tuple[int, int] | None: ...
    def has_parse_errors(self, code_content: str) -> bool: ...
```

**Registro:** `get_reducer_for_path()` em `cli/reducers/__init__.py` (`.php`, `.js/.mjs/.cjs`, `.py`).

### 3.3. Premissas por Projeto (`cli/project/premises.py`) — novo
* Diretório de config: `CAPOEIRA_CONFIG_DIR` → `%APPDATA%\CapoeiraCode` → `~/.capoeira`.
* `projects/<nome>.yaml` (schema pydantic `Premises`): `name`, `description`, `stack`
  (language, project_root, template_engine, structure, conventions), `banco` (dsn **ou**
  schema_file), `frontend` (css_classes, components), `rag` (working_dir, python, doc_types),
  e seletores `specs`/`skills`/`prompts` (listas de nomes; **omitidas = carregar todos**,
  **vazias = não carregar nenhum**).
* `validate_banco()` orienta quando faltam `dsn`/`schema_file`.

### 3.4. Scanner de Dependências (`cli/project/scanner.py`) — novo
* `classify_module(path, structure)` — classifica controller/model/view/css/... por segmento de caminho.
* `extract_sql_tables(content)` — tabelas citadas em queries (FROM/INTO/UPDATE/TABLE/JOIN).
* `parse_schema_table_names(schema_sql)` / `schema_tables(schema_file)` — tabelas do dump.
* `scan_file(path, premises)` — {file, classification, dependencies, sql_tables} (reusa reducers + heurística SQL).

### 3.5. Integração com RAG (`cli/rag_client.py`) — novo
* `RagClient(premises)` exige `rag.working_dir`; executa via **subprocess**
  `python main.py query "<pergunta>" [--doc-type <map>]` no working dir do RAG.
* Retorna a saída (contexto) como texto; mapeia falha de processo/executável/timeout em `RagError`.

---

## 4. Contrato de Comunicação com o LLM (HTTP, compatível com Ollama)

`POST {base_url}/api/chat`, protocolo Ollama `stream=false`, stdlib `urllib`.

### 4.1. Requisição
```json
{
  "model": "gemini-pro",
  "stream": false,
  "messages": [
    { "role": "system", "content": "Você é o motor CapoeiraCode. Responda APENAS em formato JSON válido." },
    { "role": "user", "content": "[PROMPT COM PERFIL + SPECS + SKILLS + RAG + INSTRUÇÃO]" }
  ]
}
```
* `base_url` padrão `http://127.0.0.1:8765` (CapoeiraHost); Ollama nativo `http://127.0.0.1:11434`.

### 4.2. Resposta
```json
{ "model": "gemini-pro", "message": { "role": "assistant", "content": "{ ... }" }, "done": true }
```
### 4.3. Tempo de espera
`--timeout` (padrão 180 s); rede timeout ou back-end exceder o prazo levantam `LLMRequestError` → exit 1.

---

## 5. Protocolo de Resposta do LLM (Tool-Calling Simulado)

Todo prompt de mutação injeta o contrato de resposta. Duas formas aceitas:

**1) Ação única (compat):**
```json
{
  "file_path": "app/models/Db.php",
  "action": "replace_symbol | create_file | patch_diff",
  "target_symbol": "conectar",
  "code_content": "...",
  "explanation": "resumo de 1 linha"
}
```

**2) Lote multi-arquivo (v3.0.0):**
```json
{
  "files": [
    { "file_path": "...", "action": "create_file", "code_content": "...", "explanation": "..." },
    { "file_path": "...", "action": "replace_symbol", "target_symbol": "...", "code_content": "...", "explanation": "..." },
    { "file_path": "...", "action": "patch_diff", "code_content": "...", "explanation": "..." }
  ]
}
```

**Regras:**
* `action ∈ replace_symbol|create_file|patch_diff`; `target_symbol` obrigatório em `replace_symbol`.
* O applier tolera prosa e cercas ```` ```json ````.
* `apply_payload(raw, expected_file_path=None)`: com `expected_file_path`, o formato único é obrigado a casar o caminho (postura do `generate`).
* **Staging**: todas as ações são preparadas em memória (criações, splices de byte-range, diffs, re-parse); qualquer falha ⇒ `ApplyResult(ok=False)` e **nada** é gravado. Só após todas as validações os arquivos são escritos (tmp + `os.replace` por arquivo). *Isso estende a RNF-04 ao lote.*

### 5.1. Contrato de ferramentas do modo agente (TUI, v4.0.0)

No modo agente, o LLM responde a cada turno com `{"steps":[...]}` em vez do schema acima:

```json
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
```

* `read_file`/`list_dir` são **leituras automáticas** (sem aprovação).
* `run_shell`/`run_python` executam no **cwd do projeto** (`subprocess`), com timeout e
  saída truncada (limite ~8.000 chars).
* `write_file` aplica via **`ChangeApplier`** (atômico e multi-arquivo).
* `ask_user` é bloqueante na TUI; a resposta vira contexto.
* `done` encerra o turno; sem `done`, o loop itera até `--max-turns` (padrão 20) ou
  interrupção (`Ctrl+C`).
* Fragmento único (objeto com `tool`) também é aceito como atalho de um passo.

---

## 6. Requisitos Não-Funcionais (RNFs)

* **RNF-01 (Performance):** ✅ esqueletos em <200 ms para até 5.000 linhas (medido ~97 ms).
* **RNF-02 (Segurança Local):** ✅ comunicação só com loopback local; RAG via subprocess na máquina.
* **RNF-04 (Atomicidade):** ✅ falha de parse/validação ⇒ nada é escrito; **extendido ao lote multi-arquivo** (all-or-nothing) com retry de autocorreção até `--max-retries` (padrão 3).

> RNF-03 (reconexão de extensão) migrou para o CapoeiraHost na v2.0.0 e permanece fora.

---

## 7. Estrutura de Diretórios do Projeto

```text
capoeira-code/
├── cli/                            # ✅ implementado
│   ├── entry.py                    # entry `capoeira`: PATH abre a TUI; subcomandos → Click
│   ├── main.py                     # Click: run | ask | refactor | generate | explain | deps | tui
│   ├── llm_client.py               # HTTP /api/chat (Ollama-compatível, urllib; chat_messages)
│   ├── prompts.py                  # Builders de prompt; contrato multi-arquivo e steps (agente)
│   ├── applier.py                  # Aplicador atômico multi-arquivo (stage/commit)
│   ├── instruction/                # loader de specs/skills/prompts (+ render_project_profile)
│   ├── project/                    # premises.py (yaml) + scanner.py (deps/tabelas)
│   ├── rag_client.py               # subprocess -> local-rag-system
│   ├── tui/                        # modo agente interativo
│   │   ├── app.py                  # TUI prompt_toolkit + rich; /comandos (model, rescan, reset...)
│   │   ├── session.py              # workspace configs/<slug>/ + session.jsonl (1 sessão ativa/projeto)
│   │   ├── scan_artifacts.py       # gera tree.txt, dependencies.json, asts/
│   │   ├── permissions.py          # política de permissão (leitura auto; ask/readonly/auto)
│   │   ├── tools.py                # executores: read/list/run_shell/run_python/write_file
│   │   └── agent.py                # loop do agente: steps → execução → até done/max_turns
│   └── reducers/                   # Tree-Sitter PHP/JS/Python
├── tests/                          # ✅ 122 testes pytest
│   ├── test_reducers_*.py          # PHP/JS/Python
│   ├── test_applier.py
│   ├── test_applier_multi.py
│   ├── test_llm_client.py
│   ├── test_cli.py                 # refactor/generate/explain/deps (LLM stubado)
│   ├── test_cli_motor.py           # run/ask (LLM stubado + RAG mockado)
│   ├── test_premises.py
│   ├── test_scanner.py
│   ├── test_rag_client.py
│   ├── test_instruction.py
│   ├── test_prompts.py
│   ├── test_session.py
│   ├── test_scan_artifacts.py
│   ├── test_tools.py
│   ├── test_permissions.py
│   ├── test_agent.py
│   └── test_entry.py
├── examples/capoeira-config.template/  # modelo de config (yaml + specs/skills/prompts)
├── specs/capoeira-code-spec.md     # este arquivo
├── requirements.txt                # + prompt_toolkit, rich
├── requirements-dev.txt
├── pyproject.toml                  # entry `capoeira` (pip install -e .)
├── conftest.py
├── AGENTS.md
└── README.md
```

---

## 8. Código-Fonte e Interfaces dos Módulos Principais

### 8.1. CLI (Python)

```
python -m cli run "INSTRUÇÃO" [--project NOME] [--prompt FLUXO] [--skill NOME]
       [--file ARQ]... [--context ARQ]... [--rag PERGUNTA] [--doc-type user|tech|support]
       [--dry-run] [--max-retries N] [--base-url URL] [--model M] [--timeout SEG]

python -m cli ask "PERGUNTA" [--project NOME] [--doc-type ...]
python -m cli refactor ... | generate ... | explain ... | deps [--project NOME]
```

* **`run`** — carrega premissas (`--project`), specs/skills/prompts; injeta contexto dos
  `--file`/`--context` (esqueletos) e do `--rag`; envia build_run_prompt; o LLM responde
  ação única ou lote; aplica atomicamente. `--dry-run` renderiza diff colorido + confirmação.
* **`ask`** — chama o RAG (subprocess) e imprime a resposta/contexto.
* **`deps --project`** — além dos imports, classifica o módulo e lista tabelas SQL tocadas.
* `explain` mantido por compatibilidade (uso recomendado: RAG).

### 8.2. Premissas (`cli/project/premises.py`)
```python
class Premises(BaseModel):
    name: str; description: str = ""
    stack: StackPremises; banco: BancoPremises | None; frontend: FrontendPremises
    rag: RagPremises | None; specs/skills/prompts: list[str] | None = None
    def validate_banco(self) -> str: ...

def resolve_config_dir() -> Path: ...   # env -> %APPDATA%\CapoeiraCode -> ~/.capoeira
def load_premises(config_dir, project) -> Premises: ...
```

### 8.3. Scanner (`cli/project/scanner.py`)
```python
def classify_module(file_path, structure) -> str
def extract_sql_tables(content) -> list[str]
def parse_schema_table_names(schema_sql) -> list[str]  # CREATE TABLE
def scan_file(file_path, premises) -> dict             # {file, classification, dependencies, sql_tables}
def scan_project(root, premises) -> list[dict]
def schema_tables(schema_file) -> list[str]
```

### 8.4. Motor de instrução (`cli/instruction/loader.py`)
```python
class InstructionSet:
    specs: dict[str, str]; skills: dict[str, str]; prompts: dict[str, str]
    specs_combined / skills_combined -> str
    get_prompt(name) -> str
def load_instruction_set(config_dir, premises) -> InstructionSet
def render_project_profile(premises) -> str
```

### 8.5. Applier multi-arquivo (`cli/applier.py`)
```python
class CapoeiraResponse(BaseModel): file_path/action/target_symbol?/code_content/explanation
class CapoeiraBatch(BaseModel): files: list[CapoeiraResponse]

class ChangeApplier:
    apply_payload(raw, expected_file_path=None) -> ApplyResult     # stage + commit
    stage_payload(raw, expected_file_path=None) -> ApplyResult      # só valida/prepara (dry-run)
    commit_staged(staged: dict[str, str]) -> None
ApplyResult: ok, message, error, payload(CapoeiraResponse|None), staged(dict|None)
```
* `stage_payload` prepara tudo em memória; `commit_staged` grava (tmp + `os.replace`, criando diretórios). *Sem escrita parcial.*

### 8.6. Modo agente/TUI (`cli/tui/`)
* **`app.py` — `run_tui(project_path, project, readonly, model, base_url, timeout)`**: PromptSession (prompt_toolkit) + Console (rich); comandos `/model`, `/base-url`, `/premises`, `/rescan`, `/reset`, `/readonly`, `/help`, `/quit`; `Ctrl+C` interrompe o agente; `Ctrl+D` sai.
* **`session.py`**: `Session(config_dir, project_path)` — workspace `configs/<slug>/`, `session.jsonl` (histórico `{role, content}`), `workspace/`, `asts/`; 1 sessão ativa por projeto (`reset()` limpa).
* **`scan_artifacts.py`**: `generate_artifacts(session, premises)` → `{tree, num_files, ast_files, dependencies}`; persiste `tree.txt`, `dependencies.json`, `asts/<relpath>`; `artifacts_summary(result)` enxuto para o prompt.
* **`permissions.py`**: `PermissionGate(mode)` — `read_file/list_dir` sempre; `run_shell/run_python/write_file` conforme `ask` (y/n/a com "sempre na sessão"), `readonly` (nega), `auto` (aceita).
* **`tools.py`**: `apply_step(step, cwd, python, timeout)` → `ToolResult{ok, output}`; `write_file` delega ao `ChangeApplier` (aplicação imediata, caminho-resolvido como `expected`).
* **`agent.py`**: `AgentRun.run(user_prompt, ask_user, ask_permission)` — loop de `steps` até `done`; resultados de ferramentas viram mensagens de contexto; persistidos no `session.jsonl` (retomável).

### 8.7. Entry point (`cli/entry.py`, `pyproject.toml`)
```python
def main(argv=None):  # console script `capoeira`
    # se arg0 for subcomando conhecido ou opção ('-'), delega ao Click (cli.main:cli)
    # senão trata arg0 como PATH do projeto e chama run_tui (flag parsing limitado)
```
Instalação: `pip install -e .` cria os executáveis `capoeira`/`capoeira-code`.

---

## 9. Registro de Alterações

| Versão | Data | Descrição |
| --- | --- | --- |
| `1.0.0` | 18/08/2026 | Aprovação inicial da especificação. |
| `1.1.0` | 20/08/2026 | **Iteração 1 (CLI)**: reducers PHP/JS, server WS, applier atômico; 30 testes. |
| `2.0.0` | 07/09/2026 | **Iteração 3 (reajuste)**: removida comunicação via extensão/navegador; LLM via backend compatível com Ollama (`POST /api/chat`, stdlib); comandos `refactor/generate/explain/deps`; spec 53 testes. |
| `3.0.0` | 08/09/2026 | **Iteração 4 (motor de instrução)**: 86 testes. Novo comando **`run`** declarativo (estilo OpenCode) — instrução livre com specs/skills/prompts em arquivos, o LLM decide as ações. **Premissas por projeto** (`projects/*.yaml` em `CAPOEIRA_CONFIG_DIR`/`%APPDATA%\CapoeiraCode`/`~/.capoeira`) com stack/banco/frontend/rag. **Scanner** de dependências e tabelas (`cli/project/scanner.py`). ****`ask`** e `--rag`** integrando o `local-rag-system` via subprocess. **Applier multi-arquivo** (formato `files:[...]` + staging all-or-nothing, extensão da RNF-04 ao lote; formato único mantido por compat). `deps --project` classifica módulo e lista tabelas. Requires +`PyYAML`. |
| `4.0.0` | 08/09/2026 | **Iteração 5 (modo agente/TUI)**: 122 testes. `capoeira [PATH]` abre a **TUI interativa** (prompt_toolkit + rich) estilo OpenCode representando todo o fluxo da visão (item 5): workspace de sessão por projeto em `configs/<slug>/` (`session.jsonl` retomável, 1 sessão ativa + `/reset`); artefatos de scan `tree.txt`/`dependencies.json`/`asts/`; **loop de agente** com contrato de ferramentas (§5.1) — `read_file/list_dir/run_shell/run_python/write_file/ask_user/done`, aplicação `write_file` via applier, política de permissão (`readonly`/`ask`/`auto`, leitura automática, `--readonly`); `chat_messages` no `LLMClient`; entry point `capoeira` (pyproject) + subcomando `tui`; `python -m cli [PATH]` também funciona via `cli/entry.py`. Requires +`prompt_toolkit`/`rich`. |