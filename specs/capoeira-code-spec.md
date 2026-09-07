# 📜 Software Specification & Implementation Architecture: CapoeiraCode

**Projeto:** CapoeiraCode  
**Versão:** `2.0.0`  
**Status:** `Approved — Iteração 3 (backend LLM via Ollama/CapoeiraHost, foco em codificação) implementada e testada`  
**Data:** 7 de Setembro de 2026  

---

## 1. Visão Geral e Objetivos

### 1.1. Propósito
O **CapoeiraCode** é um agente CLI focado na manutenção, refatoração, compreensão e
**criação de artefatos** de **sistemas legados**. O CLI reduz o contexto do código via
AST (*Tree-Sitter*) e conversa com um **backend compatível com a API do Ollama** —
Ollama nativo ou o gateway local [CapoeiraHost](https://github.com/ezequielrribeiro/capoeira-host) —
via HTTP/JSON (`POST /api/chat`). Não há navegador, extensão nem ponte WebSocket.

### 1.2. Problema de Negócio
Sistemas legados possuem bases de código extensas, acopladas e com pouco suporte a
contextos modernos. A interatividade via browser automation/injection impõe latência
elevada, limites de UI e risco de bloqueio das plataformas de LLM.

### 1.3. Objetivos de Design
* **Economia Extrema de Tokens:** Redução de até 90% do contexto enviado através do uso de AST (*Tree-Sitter*) e grafos de dependência locais.
* **Backend-Agnóstico (API Ollama):** Comunicação única via `POST {base_url}/api/chat`, funcionando com Ollama nativo ou gateways Ollama-compatíveis (CapoeiraHost) — sem chave de API nem dependência de UI de navegador.
* **Multi-linguagem Expansível:** Suporte inicial para **PHP**, **JavaScript** e **Python** (implementados), com **HTML** e **CSS** planejados e arquitetura pronta para novos parsers.
* **Operação Atômica:** Aplicação rigorosa de alterações sem depender do usuário para copiar/colar diffs.
* **Criação de Artefatos:** Geração de testes, esqueletos de módulo, scaffolding e documentação como meninos de primeira classe (`create_file`/`replace_symbol`).

---

## 2. Arquitetura do Sistema

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│                          CAPOEIRA CODE (CLI) ✅                              │
│                                                                              │
│  ┌────────────────┐    ┌──────────────────┐    ┌────────────────────────┐    │
│  │ Context Engine │───>│ AST/Tree-Sitter  │───>│ Structural Reducer     │    │
│  └────────────────┘    └──────────────────┘    └─────────┬──────────────┘    │
│                                                          │ (Prompt)          │
│  ┌────────────────┐    ┌──────────────────┐              │                   │
│  │ Diff Applier   │<───│ CLI Commands     │<─────────────┘                   │
│  │ (create/replace │    │ refactor ·       │                                 │
│  │         /patch)│    │ generate ·        │                                 │
│  └────────────────┘    │ explain · deps    │                                 │
│                        └─────────┬─────────┘                                 │
└──────────────────────────────────┼───────────────────────────────────────────┘
                                   │ (HTTP POST /api/chat — JSON Ollama)
┌──────────────────────────────────▼───────────────────────────────────────────┐
│                LLM BACKEND (compatível com a API do Ollama)                  │
│                                                                              │
│  Ollama nativo (http://127.0.0.1:11434)  ·  CapoeiraHost (http://127.0.0.1:8765)│
└──────────────────────────────────────────────────────────────────────────────┘
```

**Estado:** todo o fluxo (CLI + comunicação com o backend) está implementado e testado;
não há componente de navegador/extensão neste repositório (o CapoeiraHost cuida disso).

---

## 3. Especificação dos Módulos (CLI Engine)

### 3.1. Engine de Redução de Contexto (Context Reducer)
* **Parser Base:** `Tree-Sitter` com suporte a gramáticas parametrizáveis.
* **Linguagens:**
  * **PHP** ✅ — Extração de métodos, classes e resolução de `require`/`include`/`require_once`/`include_once` e `use` (namespaces).
  * **JavaScript** ✅ — `function_declaration`, `generator_function_declaration`, `method_definition`, arrow functions e `function_expression` em declaradores; dependências via `import` e `require(...)`.
  * **Python** ✅ — `function_definition` (cobre `def`, `async def` e métodos de classe); dependências via `import_statement` e `import_from_statement`.
  * **HTML** ⏳ — Seleção semântica de nós (planejado).
  * **CSS** ⏳ — Isolação de seletores relacionados a componentes específicos (planejado).
* **Regra de Omissão (token de comentário por linguagem):** Qualquer bloco de código fora do símbolo-alvo (*target symbol*) é substituído pelo placeholder exato no token de comentário da linguagem — `// ... [Omitted by CapoeiraCode] ...` (`OMISSION_PLACEHOLDER`) para PHP/JS e `# ... [Omitted by CapoeiraCode] ...` (`PYTHON_OMISSION_PLACEHOLDER`) para Python — ambos em `cli/reducers/base.py`. No Python (delimitado por indentação, sem chaves) o `PythonReducer` sobrescreve `_replace_bodies` para omitir o corpo como um comentário `# ...` no nível de indentação do bloco.

### 3.2. Interface de Redutores (Language Plugin Interface)

> A interface é **Python** (o CLI é Python).

```python
# cli/reducers/base.py (resumo da interface real)
class BaseLanguageReducer(ABC):
    """Subclasses definem self.language e self.parser no __init__."""

    @abstractmethod
    def extract_skeleton(self, code_content: str, target_symbol: str) -> str:
        """Código reduzido: corpos fora do target_symbol viram OMISSION_PLACEHOLDER."""

    @abstractmethod
    def extract_dependencies(self, code_content: str) -> list[str]:
        """Arquivos/módulos importados no arquivo atual."""

    # Concretos (usados pelo applier na ação replace_symbol):
    def find_symbol_range(self, code_content: str, target_symbol: str) -> tuple[int, int] | None:
        """Byte-range UTF-8 da definição completa do símbolo, ou None."""

    def has_parse_errors(self, code_content: str) -> bool:
        """True se o Tree-Sitter reportar erro de sintaxe."""
```

**Registro por extensão:** `cli/reducers/__init__.py` expõe `get_reducer_for_path()` mapeando `.php` → `PHPReducer`, `.js`/`.mjs`/`.cjs` → `JavaScriptReducer` e `.py` → `PythonReducer`.

---

## 4. Contrato de Comunicação com o LLM (HTTP, compatível com Ollama)

Comunicação via JSON em `POST {base_url}/api/chat` (protocolo Ollama `stream=false`).
O CLI usa a **stdlib** (`urllib.request`) — sem pip de novas dependências.

### 4.1. Requisição (CLI → Backend)

```json
{
  "model": "gemini-pro",
  "stream": false,
  "messages": [
    { "role": "system", "content": "Você é o motor CapoeiraCode. Responda APENAS em formato JSON válido." },
    { "role": "user", "content": "[PROMPT REDUZIDO COM AST E ESQUELETO DO CÓDIGO]" }
  ]
}
```

* `model` é um perfil do backend: no CapoeiraHost são perfis do `models.json` (ex.: `gemini-pro`, `claude-sonnet`); no Ollama nativo, um modelo baixado (ex.: `qwen2.5-coder`).
* `base_url` padrão: **`http://127.0.0.1:8765`** (CapoeiraHost). Para Ollama nativo: `--base-url http://127.0.0.1:11434`.

### 4.2. Resposta (Backend → CLI)

```json
{
  "model": "gemini-pro",
  "message": { "role": "assistant", "content": "{ \"file_path\": \"src/legacy_calculator.php\", \"action\": \"replace_symbol\", ... }" },
  "done": true
}
```

* O CLI extrai `message.content` e o repassa ao `ChangeApplier`.
* **Erros mapeados:** 404 (modelo não registrado), 502 (falha reportada pelo provider Web), 503 (provedor/aba offline), 504 (timeout do backend) — todos convertidos em `LLMRequestError` com mensagem legível.

### 4.3. Tempo de espera

`LLMClient.chat(prompt)` respeita `--timeout` (padrão **180 s**). Timeout de rede ou
estouro do prazo do backend levantam `LLMRequestError` e o comando termina com exit code 1.

---

## 5. Protocolo de Resposta do LLM (Tool-Calling Simulado)

Para evitar que o LLM responda com textos conversacionais, todo prompt de mutação conterá a injeção do esquema de resposta obrigatório:

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "type": "object",
  "properties": {
    "file_path": { "type": "string" },
    "action": { "type": "string", "enum": ["replace_symbol", "create_file", "patch_diff"] },
    "target_symbol": { "type": "string" },
    "code_content": { "type": "string" },
    "explanation": { "type": "string", "description": "Resumo de 1 linha da alteração" }
  },
  "required": ["file_path", "action", "code_content"]
}
```

**Notas de implementação (vigentes):**
* `target_symbol` é opcional no schema, mas **obrigatório** quando `action = "replace_symbol"` (validado pelo applier).
* O applier tolera prosa e cercas ```` ```json ```` ao redor do JSON (extrai o primeiro objeto JSON balanceado via `raw_decode`).
* `apply_payload(raw, expected_file_path=None)`: quando `expected_file_path` é informado (comando `generate`), o `file_path` retornado **deve** casar exatamente — senão a aplicação falha e nada é escrito (defesa contra caminhos alucinados pelo LLM).
* Semântica de `code_content` por ação:
  * `create_file` → conteúdo completo do arquivo;
  * `replace_symbol` → definição completa e atualizada do símbolo-alvo (aplicada por byte-range Tree-Sitter, com re-parse de validação antes de gravar);
  * `patch_diff` → unified diff aplicado com checagem estrita de contexto.

---

## 6. Requisitos Não-Funcionais (RNFs)

* **RNF-01 (Performance):** ✅ Parsing de AST e geração de esqueletos em **< 200ms** para arquivos de até 5.000 linhas. *Medido: ~97 ms em arquivo PHP de 5.505 linhas.*
* **RNF-02 (Segurança Local):** ✅ O CLI fala apenas com o **loopback local** (default `127.0.0.1`); clientes escolhem livremente a porta/base URL. Não há servidor de rede aberto no CapoeiraCode.
* **RNF-04 (Atomicidade):** ✅ Falha no parse/validação do JSON do LLM ⇒ **nenhum** arquivo é modificado (escrita atômica via arquivo temporário + `os.replace`) e o CLI envia prompt de autocorreção com o erro, até `--max-retries` tentativas (padrão 3).

> **Removido em v2.0.0:** a antiga RNF-03 (reconexão com backoff da extensão de navegador)
> pertencia ao bridge WebSocket e migrou integralmente para o
> [CapoeiraHost](https://github.com/ezequielrribeiro/capoeira-host). A validação de Origin
> (antiga RNF-02) era exclusiva da ponte WS e deixou de fazer sentido no transporte HTTP local.

---

## 7. Estrutura de Diretórios do Projeto

```text
capoeira-code/
├── cli/                            # ✅ implementado
│   ├── __init__.py
│   ├── __main__.py                 # habilita `python -m cli` (executar da raiz)
│   ├── main.py                     # CLI (Click): refactor | generate | explain | deps; retry (RNF-04)
│   ├── llm_client.py               # Cliente HTTP /api/chat (Ollama-compatível) via urllib (stdlib)
│   ├── prompts.py                  # Builders de prompt + RESPONSE_SCHEMA (spec §5)
│   ├── applier.py                  # Aplicador atômico: create_file | replace_symbol | patch_diff
│   └── reducers/
│       ├── __init__.py             # get_reducer_for_path(): .php, .js, .mjs, .cjs, .py
│       ├── base.py                 # BaseLanguageReducer + OMISSION_PLACEHOLDER + PYTHON_OMISSION_PLACEHOLDER
│       ├── tree_sitter_php.py      # Redutor de contexto para PHP
│       ├── tree_sitter_js.py       # Redutor de contexto para JavaScript
│       └── tree_sitter_python.py   # Redutor de contexto para Python
├── tests/                          # ✅ 53 testes pytest (sem pytest-asyncio)
│   ├── fixtures/                   # legacy_calculator.php, dashboard.js, legacy_service.py
│   ├── test_reducers_php.py
│   ├── test_reducers_js.py
│   ├── test_reducers_python.py
│   ├── test_applier.py
│   ├── test_llm_client.py          # stub HTTP in-process (ThreadingHTTPServer) da API Ollama
│   ├── test_prompts.py
│   └── test_cli.py                 # comandos Click com LLMClient stubado
├── specs/capoeira-code-spec.md     # este arquivo
├── requirements.txt                # dependências de runtime (sem websockets)
├── requirements-dev.txt            # -r requirements.txt + pytest
├── conftest.py                     # sys.path para `import cli` nos testes
├── AGENTS.md
└── README.md
```

---

## 8. Código-Fonte e Interfaces dos Módulos Principais

### 8.1. CLI (Python) — estado implementado

> O código-fonte no repositório é canônico; esta seção documenta as interfaces.

#### `requirements.txt`
```text
tree-sitter>=0.24
tree-sitter-php>=0.23
tree-sitter-javascript>=0.23
tree-sitter-python>=0.23
click>=8.1.7
pydantic>=2.7.0
```

> **v2.0.0:** removido `websockets` (a ponte WS foi substituída pelo cliente HTTP Ollama
> via stdlib; nenhuma dependência nova foi adicionada).

#### `cli/llm_client.py` (interface)
```python
DEFAULT_BASE_URL = "http://127.0.0.1:8765"   # CapoeiraHost; Ollama nativo: 127.0.0.1:11434
DEFAULT_MODEL = "gemini-pro"
DEFAULT_TIMEOUT = 180.0

class LLMClient:
    def __init__(self, base_url, model, timeout, system_prompt=...): ...
    def chat(self, prompt: str) -> str: ...          # POST /api/chat; retorna message.content

class LLMRequestError(Exception): ...                # conexão, status HTTP ou conteúdo inválido
```

#### `cli/main.py` (interface)
```
python -m cli refactor --file ARQUIVO --symbol SIMBOLO --instruction "TEXTO"
                       [--base-url URL] [--model MODELO] [--timeout SEG] [--max-retries N]

python -m cli generate --file ARQUIVO --instruction "TEXTO"
                       [--symbol SIMBOLO] [--context ARQUIVO]
                       [--base-url URL] [--model MODELO] [--timeout SEG] [--max-retries N]

python -m cli explain --file ARQUIVO [--symbol SIMBOLO]
                      [--base-url URL] [--model MODELO] [--timeout SEG]

python -m cli deps --file ARQUIVO
```

* `refactor` — reduz o arquivo por AST, pede `replace_symbol` do símbolo alvo.
* `generate` — cria artefatos (`create_file`), com contexto opcional de um arquivo
  relacionado (`--context`); com `--symbol`, reescreve um símbolo existente.
* `explain` — somente leitura; imprime a explicação do esqueleto.
* `deps` — sem LLM; imprime `extract_dependencies()`.
* Em falha de aplicação, reenvia prompt de autocorreção com a mensagem de erro (RNF-04).
  Exit code `0` em sucesso, `1` em falha.

#### `cli/applier.py` (interface)
```python
class CapoeiraResponse(BaseModel):   # pydantic v2 — espelha o schema da §5
    file_path: str
    action: Literal["replace_symbol", "create_file", "patch_diff"]
    target_symbol: str | None = None
    code_content: str
    explanation: str = ""

@dataclass
class ApplyResult:
    ok: bool
    message: str = ""
    error: str = ""
    payload: CapoeiraResponse | None = None

class ChangeApplier:
    @staticmethod
    def apply_payload(raw_json_str: str, expected_file_path: str | None = None) -> ApplyResult: ...
    # nunca levanta exceção; RNF-04

def apply_unified_diff(original: str, diff: str) -> str: ...  # ValueError se contexto não confere
```

* **`replace_symbol`** localiza o símbolo via `find_symbol_range` e aplica *splice* por
  byte-range UTF-8 — **não** sobrescreve o arquivo inteiro. O resultado é re-parseado;
  havendo erro de sintaxe, nada é gravado.
* **`create_file`** cria diretórios automaticamente (`os.makedirs`).
* **Escrita atômica:** grava em `<arquivo>.capoeira.tmp` e finaliza com `os.replace`.

#### `cli/prompts.py` (interface)
```python
RESPONSE_SCHEMA = {...}                       # schema da §5

def build_refactor_prompt(file_path, symbol, instruction, skeleton) -> str: ...
def build_generate_prompt(file_path, instruction, symbol | None, context | None) -> str: ...
def build_explain_prompt(file_path, symbol | None, skeleton) -> str: ...
def build_retry_prompt(original_prompt, error) -> str: ...
```

---

## 9. Registro de Alterações

| Versão | Data | Descrição |
| --- | --- | --- |
| `1.0.0` | 18/08/2026 | Aprovação inicial da especificação. |
| `1.1.0` | 20/08/2026 | **Iteração 1 (CLI) entregue** — 30 testes pytest verdes. Desvios consolidados: (1) `tree-sitter-languages` substituído por `tree-sitter` + gramáticas oficiais (sem wheel p/ Python 3.13); (2) migração para a API tree-sitter 0.26 (`QueryCursor`); (3) `BaseLanguageReducer` ganhou `find_symbol_range`/`has_parse_errors` e a §3.2 passou de TypeScript para Python; (4) `applier` reescrito: extração robusta de JSON, 3 ações, escrita atômica (RNF-04); (5) `server` com allowlist de Origin (RNF-02), `asyncio.Event`, correlação por `id` e timeout; (6) `main.py` com entrypoint `python -m cli` e loop de autocorreção; (7) RNFs 01, 02 e 04 verificados; RNF-03 alocado à extensão; (8) repositório git inicializado. |
| `2.0.0` | 07/09/2026 | **Iteração 3 (reajuste) entregue** — 53 testes pytest verdes. Removida toda a comunicação via extensão/navegador (bridge WebSocket `server.py`, `websockets`, allowlist de Origin, RNF-03). LLM acessado via **back-end compatível com a API do Ollama** (`POST /api/chat`, stdlib `urllib`, sem novas dependências): `cli/llm_client.py` com default `http://127.0.0.1:8765` (CapoeiraHost) e perfis `--model`. `main.py` síncrono (sem asyncio) com 4 comandos — `refactor`, **`generate`** (criação de artefatos: testes/esqueleto/scaffolding, com `--context`), **`explain`** (somente leitura) e **`deps`** (sem LLM). `cli/prompts.py` centraliza os builders de prompt. `apply_payload` ganhou `expected_file_path` para barrar caminhos divergentes do LLM antes da escrita (RNF-04 estendida). Spec §4 reescrita (protocolo HTTP), §2 diagrama atualizado, §6 RNFs reajustadas (removida a antiga RNF-03 de extensão). |