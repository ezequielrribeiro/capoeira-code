# 📜 Software Specification & Implementation Architecture: CapoeiraCode

**Projeto:** CapoeiraCode  
**Versão:** `1.1.0`  
**Status:** `Approved — Iteração 1 (CLI) implementada e testada`  
**Data:** 20 de Agosto de 2026  

---

## 1. Visão Geral e Objetivos

### 1.1. Propósito
O **CapoeiraCode** é um agente CLI focado na manutenção, refatoração e compreensão de **sistemas legados**, operando em ambientes com acesso restrito a APIs pagas de LLM. Ele atua como um orquestrador local que se conecta a interfaces Web de LLMs (Gemini, Claude, Microsoft 365 Copilot, ChatGPT, etc.) via **WebSocket Bridge**.

### 1.2. Problema de Negócio
Sistemas legados possuem bases de código extensas, acopladas e com pouco suporte a contextos modernos. A interatividade via browser automation/injection impõe latência elevada e limites de UI.

### 1.3. Objetivos de Design
* **Economia Extrema de Tokens:** Redução de até 90% do contexto enviado através do uso de AST (*Tree-Sitter*) e grafos de dependência locais.
* **Agnóstico a LLMs Web:** Suporte a qualquer plataforma web por meio de adaptadores simples na extensão do navegador.
* **Multi-linguagem Expansível:** Suporte inicial para **PHP** e **JavaScript** (implementados), com **HTML** e **CSS** planejados e arquitetura pronta para novos parsers.
* **Operação Atômica:** Aplicação rigorosa de alterações sem depender do usuário para copiar/colar diffs.

---

## 2. Arquitetura do Sistema

```text
┌────────────────────────────────────────────────────────────────────────┐
│                          CAPOEIRA CODE (CLI) ✅                        │
│                                                                        │
│  ┌────────────────┐    ┌──────────────────┐    ┌────────────────────┐  │
│  │ Context Engine │───>│ AST/Tree-Sitter  │───>│ Structural Reducer │  │
│  └────────────────┘    └──────────────────┘    └─────────┬──────────┘  │
│                                                          │             │
│  ┌────────────────┐    ┌──────────────────┐              │ (Prompt)    │
│  │ Diff Applier   │<───│ Execution Agent  │<─────────────┘             │
│  └────────────────┘    └────────┬─────────┘                            │
└─────────────────────────────────┼──────────────────────────────────────┘
                                  │ (WebSocket Local / Port 8765)
┌─────────────────────────────────▼──────────────────────────────────────┐
│                    BROWSER EXTENSION BRIDGE (MV3) ⏳                   │
│                                                                        │
│  ┌────────────────┐    ┌──────────────────┐    ┌────────────────────┐  │
│  │ WS Client      │───>│ DOM Injector     │───>│ Provider Adapters  │  │
│  └────────────────┘    └──────────────────┘    │ (Gemini/Claude/365)│  │
│                                                └─────────┬──────────┘  │
└──────────────────────────────────────────────────────────┼─────────────┘
                                                           │ (DOM/UI)
┌──────────────────────────────────────────────────────────▼─────────────┐
│                          WEB LLM INTERFACE                             │
└────────────────────────────────────────────────────────────────────────┘
```

**Estado:** o CLI (metade superior) está implementado e testado; a extensão (MV3) é a próxima iteração.

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

> A interface é **Python** (o CLI é Python). A versão TypeScript presente na v1.0.0 era apenas conceitual e foi removida.

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

**Registro por extensão:** `cli/reducers/__init__.py` expõe `get_reducer_for_path()` mapeando `.php` → `PHPReducer` e `.js`/`.mjs`/`.cjs` → `JavaScriptReducer`.

---

## 4. Contrato do Protocolo WebSocket (CLI ↔ Extension)

Comunicação via JSON estruturado em `ws://127.0.0.1:8765`.

### 4.1. Payload: CLI -> Extensão (`SEND_PROMPT`)

```json
{
  "version": "1.0",
  "id": "req-uuid-1234",
  "action": "SEND_PROMPT",
  "payload": {
    "provider": "gemini",
    "systemPrompt": "Você é o motor CapoeiraCode. Responda APENAS em JSON.",
    "prompt": "[PROMPT REDUZIDO COM AST E ESQUELETO DO CÓDIGO]"
  }
}
```

* `id` é um UUIDv4 gerado pelo CLI a cada envio; `provider` ∈ `gemini|claude|chatgpt|copilot`.

### 4.2. Payload: Extensão -> CLI (`RESPONSE`)

```json
{
  "version": "1.0",
  "id": "req-uuid-1234",
  "action": "RESPONSE",
  "status": "SUCCESS",
  "payload": {
    "rawResponse": "{ \"file_path\": \"src/legacy_calculator.php\", \"action\": \"replace_symbol\", ... }"
  }
}
```

### 4.3. Correlação e Segurança (implementação vigente)

* **Correlação:** o CLI mantém um *future* por `id` e resolve a resposta casando `RESPONSE.id` com o `SEND_PROMPT.id`. **Fallback tolerante:** se a resposta não trouxer `id` e houver exatamente uma requisição pendente, ela resolve essa requisição (compatibilidade com extensões antigas). A extensão nova **deve** ecoar o `id`.
* **Validação de Origin (RNF-02):** o servidor fecha com código **1008** conexões cujo header `Origin` não esteja na allowlist: prefixos `chrome-extension://` e `moz-extension://`, e as origens `https://gemini.google.com`, `https://claude.ai`, `https://chatgpt.com`, `https://chat.openai.com` e `https://copilot.microsoft.com` (constantes em `cli/server.py`).
* **Ciclo de conexão:** o CLI aguarda a extensão via `asyncio.Event` (`wait_for_extension()`), sem polling nem `sleep` fixo.
* **Timeout:** `send_prompt_and_wait(prompt, provider, timeout=180.0)` levanta `TimeoutError` se o LLM não responder no prazo.

---

## 5. Protocolo de Resposta do LLM (Tool-Calling Simulado)

Para evitar que o LLM responda com textos conversacionais, todo prompt conterá a injeção do esquema de resposta obrigatório:

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
* Semântica de `code_content` por ação:
  * `create_file` → conteúdo completo do arquivo;
  * `replace_symbol` → definição completa e atualizada do símbolo-alvo (aplicada por byte-range Tree-Sitter, com re-parse de validação antes de gravar);
  * `patch_diff` → unified diff aplicado com checagem estrita de contexto.

---

## 6. Requisitos Não-Funcionais (RNFs)

* **RNF-01 (Performance):** ✅ Parsing de AST e geração de esqueletos em **< 200ms** para arquivos de até 5.000 linhas. *Medido: ~97 ms em arquivo PHP de 5.505 linhas.*
* **RNF-02 (Segurança Local):** ✅ Servidor aceita conexões exclusivamente em `127.0.0.1` e valida o header `Origin` contra a allowlist (§4.3), rejeitando com close `1008`.
* **RNF-03 (Resiliência):** ⏳ *Pertence à extensão (próxima iteração).* Reconexão com *Exponential Backoff* sem travar a UI do navegador.
* **RNF-04 (Atomicidade):** ✅ Falha no parse/validação do JSON do LLM ⇒ **nenhum** arquivo é modificado (escrita atômica via arquivo temporário + `os.replace`) e o CLI envia prompt de autocorreção com o erro, até `--max-retries` tentativas (padrão 3).

---

## 7. Estrutura de Diretórios do Projeto

```text
capoeira-code/
├── cli/                            # ✅ implementado
│   ├── __init__.py
│   ├── __main__.py                 # habilita `python -m cli` (executar da raiz)
│   ├── main.py                     # CLI (Click): comando `refactor`, prompt c/ schema (§5), retry (RNF-04)
│   ├── server.py                   # Servidor WebSocket local (allowlist Origin, correlação por id, timeout)
│   ├── applier.py                  # Aplicador atômico: create_file | replace_symbol | patch_diff
│   └── reducers/
│       ├── __init__.py             # get_reducer_for_path(): .php, .js, .mjs, .cjs, .py
│       ├── base.py                 # BaseLanguageReducer + OMISSION_PLACEHOLDER + PYTHON_OMISSION_PLACEHOLDER
│       ├── tree_sitter_php.py      # Redutor de contexto para PHP
│       ├── tree_sitter_js.py       # Redutor de contexto para JavaScript
│       └── tree_sitter_python.py   # Redutor de contexto para Python
├── tests/                          # ✅ 39 testes pytest (sem pytest-asyncio; asyncio.run in-process)
│   ├── fixtures/                   # legacy_calculator.php, dashboard.js, legacy_service.py
│   ├── test_reducers_php.py
│   ├── test_reducers_js.py
│   ├── test_reducers_python.py
│   ├── test_applier.py
│   └── test_server.py
├── extension/                      # ⏳ próxima iteração (MV3) — ver §8.2
│   ├── manifest.json
│   ├── content.js
│   └── adapters/
│       ├── gemini.js
│       └── claude.js
├── specs/capoeira-code-spec.md     # este arquivo
├── requirements.txt                # dependências de runtime
├── requirements-dev.txt            # -r requirements.txt + pytest
├── conftest.py                     # sys.path para `import cli` nos testes
├── AGENTS.md
└── README.md
```

---

## 8. Código-Fonte e Interfaces dos Módulos Principais

### 8.1. CLI & Servidor (Python) — estado implementado

> O código-fonte no repositório é canônico; esta seção documenta as interfaces e as
> decisões que **divergem do esqueleto original da v1.0.0** (não regredir).

#### `requirements.txt`
```text
websockets>=12.0
tree-sitter>=0.24
tree-sitter-php>=0.23
tree-sitter-javascript>=0.23
click>=8.1.7
pydantic>=2.7.0
```

> **Desvio consolidado:** o pacote `tree-sitter-languages` (citado na v1.0.0) está
> abandonado e **não possui wheel para Python 3.13**. Usam-se os pacotes oficiais
> por gramática. Construção do parser:
>
> ```python
> from tree_sitter import Language, Parser
> import tree_sitter_php, tree_sitter_javascript
>
> php_lang = Language(tree_sitter_php.language_php())   # arquivos .php (aceita HTML misto)
> php_parser = Parser(php_lang)
> js_lang = Language(tree_sitter_javascript.language()) # arquivos .js/.mjs/.cjs
> js_parser = Parser(js_lang)
> ```

> **API tree-sitter 0.26:** não existem `Node.sexp()` nem `Query.captures()`.
> Usar `str(node)` para s-expressions e `QueryCursor(Query(lang, scm))`, que oferece
> `.matches(root)` → `[(pattern_idx, {capture: [Node, ...]})]` e
> `.captures(root)` → `{capture: [Node, ...]}`.

#### `cli/server.py` (interface)
```python
class CapoeiraServer:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765): ...
    async def handler(self, websocket): ...          # fecha 1008 se Origin fora da allowlist
    async def wait_for_extension(self, timeout: float | None = None) -> None: ...
    async def send_prompt_and_wait(
        self, prompt: str, provider: str = "gemini", timeout: float = 180.0
    ) -> str: ...                                     # retorna payload.rawResponse
    async def start(self): ...                        # websockets.serve(...)
```

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
    def apply_payload(raw_json_str: str) -> ApplyResult: ...  # nunca levanta exceção

def apply_unified_diff(original: str, diff: str) -> str: ...  # ValueError se contexto não confere
```

* **`replace_symbol`** localiza o símbolo via `find_symbol_range` e aplica *splice* por
  byte-range UTF-8 — **não** sobrescreve o arquivo inteiro (o esqueleto v1.0.0 faria isso).
  O resultado é re-parseado; havendo erro de sintaxe, nada é gravado.
* **Escrita atômica:** grava em `<arquivo>.capoeira.tmp` e finaliza com `os.replace`.

#### `cli/main.py` (interface)
```
python -m cli refactor --file ARQUIVO --symbol SIMBOLO --instruction "TEXTO"
                       [--provider gemini|claude|chatgpt|copilot]  (padrão: gemini)
                       [--timeout SEGUNDOS]                        (padrão: 180)
                       [--max-retries N]                           (padrão: 3)
```
* Monta o prompt com o schema da §5 injetado; em falha de aplicação, reenvia prompt de
  autocorreção com a mensagem de erro (RNF-04). Exit code `0` em sucesso, `1` em falha.

### 8.2. Extensão Web (Chrome MV3) — planejada (próxima iteração)

> Esqueletos mantidos da v1.0.0, com os **ajustes obrigatórios** listados ao final.

#### `extension/manifest.json`
```json
{
  "manifest_version": 3,
  "name": "CapoeiraCode Bridge",
  "version": "1.0.0",
  "description": "Ponte WebSocket entre o CapoeiraCode CLI e UIs Web de LLMs.",
  "permissions": ["activeTab"],
  "host_permissions": [
    "*://chatgpt.com/*",
    "*://claude.ai/*",
    "*://gemini.google.com/*",
    "*://copilot.microsoft.com/*"
  ],
  "content_scripts": [
    {
      "matches": [
        "*://chatgpt.com/*",
        "*://claude.ai/*",
        "*://gemini.google.com/*",
        "*://copilot.microsoft.com/*"
      ],
      "js": ["adapters/gemini.js", "adapters/claude.js", "content.js"]
    }
  ]
}
```

#### Contrato dos adaptadores (`extension/adapters/*.js`)
```javascript
window.CapoeiraXxxAdapter = {
  name: "gemini",                       // ou "claude"
  match: () => boolean,                 // true se a página atual é do provider
  getSelectors: () => ({ input, submit, stopButton, responses }),
  async injectAndSend(promptText) { ... }
};
```

#### `extension/content.js` (fluxo)
1. Conecta em `ws://127.0.0.1:8765`.
2. Ao receber `SEND_PROMPT`: seleciona o adaptador compatível via `match()`,
   injeta `systemPrompt + "\n\n" + prompt` e aguarda o fim da geração
   (ausência do `stopButton`).
3. Envia `RESPONSE` com o texto da última resposta.

**Ajustes obrigatórios em relação ao esqueleto v1.0.0:**
* `content.js` **deve ecoar o `id`** recebido no `SEND_PROMPT` ao montar a `RESPONSE` (§4.3).
* Reconexão deve usar **Exponential Backoff** (ex.: 1s → 2s → … → teto de 30s), não o `setTimeout(connect, 3000)` fixo do esqueleto (RNF-03).
* O `manifest.json` deve carregar **todos** os adaptadores antes de `content.js`.
* O WebSocket da content script envia `Origin` da página do LLM ou da extensão — ambas as formas já constam na allowlist do servidor (§4.3), não é necessário alterar o CLI.

---

## 9. Registro de Alterações

| Versão | Data | Descrição |
| --- | --- | --- |
| `1.0.0` | 18/08/2026 | Aprovação inicial da especificação. |
| `1.1.0` | 20/08/2026 | **Iteração 1 (CLI) entregue** — 30 testes pytest verdes. Desvios consolidados: (1) `tree-sitter-languages` substituído por `tree-sitter` + gramáticas oficiais (sem wheel p/ Python 3.13); (2) migração para a API tree-sitter 0.26 (`QueryCursor`); (3) `BaseLanguageReducer` ganhou `find_symbol_range`/`has_parse_errors` e a §3.2 passou de TypeScript para Python; (4) `applier` reescrito: extração robusta de JSON, 3 ações, escrita atômica (RNF-04); (5) `server` com allowlist de Origin (RNF-02), `asyncio.Event`, correlação por `id` e timeout; (6) `main.py` com entrypoint `python -m cli` e loop de autocorreção; (7) RNFs 01, 02 e 04 verificados; RNF-03 alocado à extensão; (8) repositório git inicializado. |
