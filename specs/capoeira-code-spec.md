# 📜 Software Specification & Implementation Architecture: CapoeiraCode

**Projeto:** CapoeiraCode  
**Versão:** `1.0.0`  
**Status:** `Approved`  
**Data:** 18 de Agosto de 2026  

---

## 1. Visão Geral e Objetivos

### 1.1. Propósito
O **CapoeiraCode** é um agente CLI focado na manutenção, refatoração e compreensão de **sistemas legados**, operando em ambientes com acesso restrito a APIs pagas de LLM. Ele atua como um orquestrador local que se conecta a interfaces Web de LLMs (Gemini, Claude, Microsoft 365 Copilot, ChatGPT, etc.) via **WebSocket Bridge**.

### 1.2. Problema de Negócio
Sistemas legados possuem bases de código extensas, acopladas e com pouco suporte a contextos modernos. A interatividade via browser automation/injection impõe latência elevada e limites de UI.

### 1.3. Objetivos de Design
* **Economia Extrema de Tokens:** Redução de até 90% do contexto enviado através do uso de AST (*Tree-Sitter*) e grafos de dependência locais.
* **Agnóstico a LLMs Web:** Suporte a qualquer plataforma web por meio de adaptadores simples na extensão do navegador.
* **Multi-linguagem Expansível:** Suporte inicial para **PHP**, **JavaScript**, **HTML** e **CSS**, com arquitetura pronta para novos parsers.
* **Operação Atômica:** Aplicação rigorosa de alterações sem depender do usuário para copiar/colar diffs.

---

## 2. Arquitetura do Sistema

```text
┌────────────────────────────────────────────────────────────────────────┐
│                          CAPOEIRA CODE (CLI)                           │
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
│                    BROWSER EXTENSION BRIDGE (MV3)                      │
│                                                                        │
│  ┌────────────────┐    ┌──────────────────┐    ┌────────────────────┐  │
│  │ WS Client      │───>│ DOM Injector     │───>│ Provider Adapters  │  │
│  └────────────────┘    └──────────────────┘    │ (Gemini/Claude/365)│  │
│                                                └─────────┬──────────┘  │
└──────────────────────────────────────────────────────────┼─────────────┘
                                                           │ (DOM/UI)
┌──────────────────────────────────────────────────────────▼─────────────┐
│                          WEB LLM INTERFACE                             │
└──────────────────────────────────────────────────────────▼─────────────┘
```

---

## 3. Especificação dos Módulos (CLI Engine)

### 3.1. Engine de Redução de Contexto (Context Reducer)
* **Parser Base:** `Tree-Sitter` com suporte a gramáticas parametrizáveis.
* **Linguagens Iniciais Suportadas:**
  * **PHP:** Extração de métodos, classes, traits e resolução de `require`/`include` e namespaces.
  * **JavaScript:** Extração de funções, rotas, ES modules / CommonJS.
  * **HTML:** Seleção semântica de nós.
  * **CSS:** Isolação de seletores relacionados a componentes específicos.
* **Regra de Omissão:** Qualquer bloco de código fora do símbolo-alvo (*target symbol*) deve ser substituído por `// ... [Omitted by CapoeiraCode] ...` ou equivalente na linguagem.

### 3.2. Adaptador de Suporte a Linguagens (Language Plugin Interface)

```typescript
interface LanguageAdapter {
  languageId: 'php' | 'javascript' | 'html' | 'css';
  fileExtensions: string[];
  
  // Extrai esqueleto mantendo apenas o símbolo alvo
  extractSkeleton(fileContent: string, targetSymbol: string): string;
  
  // Extrai dependências importadas/referenciadas no bloco
  extractDependencies(fileContent: string, targetSymbol: string): string[];
}
```

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

### 4.2. Payload: Extensão -> CLI (`RESPONSE`)

```json
{
  "version": "1.0",
  "id": "req-uuid-1234",
  "action": "RESPONSE",
  "status": "SUCCESS",
  "payload": {
    "rawResponse": "{
  "file_path": "src/legacy_calculator.php",
  "action": "replace",
  ... 
}"
  }
}
```

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

---

## 6. Requisitos Não-Funcionais (RNFs)

* **RNF-01 (Performance):** O tempo gasto pelo CLI no parsing de AST e geração de esqueletos não deve exceder **200ms** para arquivos de até 5.000 linhas.
* **RNF-02 (Segurança Local):** O servidor WebSocket local aceitará conexões exclusivamente da interface `127.0.0.1` e validará chamadas via `Origin` header.
* **RNF-03 (Resiliência):** Caso a extensão perca a conexão WebSocket, tentativas de reconexão (*Exponential Backoff*) devem ocorrer sem travar a UI do navegador.
* **RNF-04 (Atomicidade):** Em caso de falha no parse do JSON retornado pelo LLM, o CLI **não deve modificar** nenhum arquivo local e deve solicitar uma autocorreção (*retry prompt*).

---

## 7. Estrutura de Diretórios do Projeto

```text
capoeira-code/
├── cli/
│   ├── __init__.py
│   ├── main.py                  # Ponto de entrada do CLI (Click)
│   ├── server.py                # Servidor WebSocket local
│   ├── applier.py               # Aplicador atômico do JSON do LLM
│   └── reducers/
│       ├── __init__.py
│       ├── base.py              # Interface abstrata para parsers
│       ├── tree_sitter_php.py   # Redutor de contexto para PHP
│       └── tree_sitter_js.py    # Redutor de contexto para JavaScript
├── extension/
│   ├── manifest.json            # Chrome Extension Manifest V3
│   ├── content.js               # Script de injeção no DOM e cliente WS
│   └── adapters/
│       ├── gemini.js            # Adaptador de seletores para o Gemini
│       └── claude.js            # Adaptador de seletores para o Claude
├── requirements.txt             # Dependências Python do CLI
└── README.md
```

---

## 8. Código-Fonte Esqueleto dos Módulos Principais

### 8.1. CLI & Servidor (Python)

#### `requirements.txt`
```text
websockets>=12.0
tree-sitter>=0.22.0
tree-sitter-languages>=1.10.0
click>=8.1.7
pydantic>=2.7.0
```

#### `cli/reducers/base.py`
```python
from abc import ABC, abstractmethod

class BaseLanguageReducer(ABC):
    """Interface base para os adaptadores de linguagem baseados em Tree-Sitter."""

    @abstractmethod
    def extract_skeleton(self, code_content: str, target_symbol: str) -> str:
        """
        Retorna o código reduzido, omitindo corpos de funções/métodos irrelevantes
        e preservando o corpo do target_symbol.
        """
        pass

    @abstractmethod
    def extract_dependencies(self, code_content: str) -> list[str]:
        """Extrai nomes de arquivos ou módulos importados no arquivo atual."""
        pass
```

#### `cli/reducers/tree_sitter_php.py`
```python
from tree_sitter_languages import get_parser, get_language
from .base import BaseLanguageReducer

class PHPReducer(BaseLanguageReducer):
    def __init__(self):
        self.language_name = "php"
        self.parser = get_parser(self.language_name)
        self.language = get_language(self.language_name)

    def extract_skeleton(self, code_content: str, target_symbol: str) -> str:
        tree = self.parser.parse(bytes(code_content, "utf8"))
        
        query_scm = """
        (method_declaration name: (name) @func_name body: (compound_statement) @func_body) @func_node
        (function_definition name: (name) @func_name body: (compound_statement) @func_body) @func_node
        """
        query = self.language.query(query_scm)
        captures = query.captures(tree.root_node)

        functions = []
        current_func = {}
        
        for node, capture_name in captures:
            if capture_name == "func_node":
                current_func = {"node": node}
                functions.append(current_func)
            elif capture_name == "func_name":
                current_func["name"] = code_content[node.start_byte:node.end_byte]
            elif capture_name == "func_body":
                current_func["body"] = node

        lines = code_content.splitlines()
        modified_lines = list(lines)

        for func in reversed(functions):
            name = func.get("name")
            body_node = func.get("body")
            if not body_node:
                continue

            start_row, start_col = body_node.start_point
            end_row, end_col = body_node.end_point

            if name != target_symbol:
                indent = " " * start_col
                placeholder = f"{indent}{{\n{indent}    // ... [Omitted by CapoeiraCode] ...\n{indent}}}"
                modified_lines[start_row:end_row + 1] = [placeholder]

        return "\n".join(modified_lines)

    def extract_dependencies(self, code_content: str) -> list[str]:
        return []
```

#### `cli/applier.py`
```python
import json
import os
from pydantic import BaseModel, Field

class CapoeiraResponse(BaseModel):
    file_path: str = Field(description="Caminho do arquivo a ser modificado")
    action: str = Field(description="Ação: replace_symbol, create_file")
    code_content: str = Field(description="O novo código do símbolo ou arquivo")
    explanation: str = Field(default="", description="Resumo da alteração")

class ChangeApplier:
    @staticmethod
    def apply_payload(raw_json_str: str) -> bool:
        try:
            clean_json = raw_json_str.strip()
            if "```json" in clean_json:
                clean_json = clean_json.split("```json")[1].split("```")[0].strip()
            
            data = json.loads(clean_json)
            payload = CapoeiraResponse(**data)
            
            os.makedirs(os.path.dirname(os.path.abspath(payload.file_path)), exist_ok=True)
            with open(payload.file_path, "w", encoding="utf-8") as f:
                f.write(payload.code_content)
            
            print(f"[Applier] Alteração aplicada em {payload.file_path}: {payload.explanation}")
            return True

        except Exception as e:
            print(f"[Applier Error] Falha ao aplicar alteração: {e}")
            return False
```

#### `cli/server.py`
```python
import asyncio
import json
import websockets

class CapoeiraServer:
    def __init__(self, host="127.0.0.1", port=8765):
        self.host = host
        self.port = port
        self.active_socket = None
        self.response_future = None

    async def handler(self, websocket):
        self.active_socket = websocket
        print("\n[CapoeiraCode Bridge] Extensão conectada!")
        try:
            async for message in websocket:
                data = json.loads(message)
                if data.get("action") == "RESPONSE":
                    if self.response_future and not self.response_future.done():
                        self.response_future.set_result(data.get("payload"))
        except websockets.exceptions.ConnectionClosed:
            print("\n[CapoeiraCode Bridge] Conexão encerrada.")
            self.active_socket = None

    async def send_prompt_and_wait(self, prompt: str) -> str:
        if not self.active_socket:
            raise ConnectionError("Nenhuma extensão conectada via WebSocket.")

        payload = {
            "version": "1.0",
            "action": "SEND_PROMPT",
            "payload": {
                "prompt": prompt,
                "systemPrompt": "Você é o motor CapoeiraCode. Responda APENAS em formato JSON válido."
            }
        }

        loop = asyncio.get_running_loop()
        self.response_future = loop.create_future()
        
        await self.active_socket.send(json.dumps(payload))
        print("[CapoeiraCode CLI] Prompt enviado. Aguardando processamento...")

        response_payload = await self.response_future
        return response_payload.get("rawResponse", "")

    async def start(self):
        return await websockets.serve(self.handler, self.host, self.port)
```

#### `cli/main.py`
```python
import asyncio
import click
from reducers.tree_sitter_php import PHPReducer
from server import CapoeiraServer
from applier import ChangeApplier

server = CapoeiraServer()

@click.group()
def cli():
    """CapoeiraCode CLI - Agente para desenvolvimento e refatoração em sistemas legados."""
    pass

@cli.command()
@click.option('--file', required=True, help="Caminho do arquivo legado")
@click.option('--symbol', required=True, help="Nome do método/função alvo")
@click.option('--instruction', required=True, help="O que deve ser alterado/refatorado")
def refactor(file: str, symbol: str, instruction: str):
    """Reduz o contexto do arquivo via AST e solicita a alteração ao LLM."""
    
    async def run():
        with open(file, "r", encoding="utf-8") as f:
            code = f.read()

        reducer = PHPReducer()
        reduced_code = reducer.extract_skeleton(code, target_symbol=symbol)

        prompt = f"""INSTRUÇÃO: {instruction}
SÍMBOLO ALVO: {symbol}
CAMINHO DO ARQUIVO: {file}

ESQUELETO DO CÓDIGO DO PROJETO:
{reduced_code}

Retorne um JSON com a propriedade "code_content" contendo o código atualizado.
"""

        async with await server.start():
            await asyncio.sleep(2)
            raw_response = await server.send_prompt_and_wait(prompt)
            success = ChangeApplier.apply_payload(raw_response)
            
            if success:
                click.echo(click.style("Refatoração concluída com sucesso!", fg="green"))
            else:
                click.echo(click.style("Falha ao aplicar alterações.", fg="red"))

    asyncio.run(run())

if __name__ == "__main__":
    cli()
```

---

### 8.2. Extensão Web (Chrome MV3)

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
      "js": ["adapters/gemini.js", "content.js"]
    }
  ]
}
```

#### `extension/adapters/gemini.js`
```javascript
window.CapoeiraGeminiAdapter = {
  name: "gemini",
  match: () => window.location.hostname.includes("gemini.google.com"),
  
  getSelectors: () => ({
    input: '.input-area div[contenteditable="true"], textarea',
    submit: 'button[aria-label*="Enviar"], button.send-button',
    stopButton: 'button[aria-label*="Parar"], .stop-generating-icon',
    responses: '.model-response-text, message-content'
  }),

  async injectAndSend(promptText) {
    const sel = this.getSelectors();
    const inputEl = document.querySelector(sel.input);
    if (!inputEl) throw new Error("Input do Gemini não encontrado.");

    inputEl.focus();
    document.execCommand('insertText', false, promptText);
    inputEl.dispatchEvent(new Event("input", { bubbles: true }));

    await new Promise(r => setTimeout(r, 400));
    
    const submitBtn = document.querySelector(sel.submit);
    if (submitBtn) submitBtn.click();
  }
};
```

#### `extension/content.js`
```javascript
(function () {
  const WS_URL = "ws://127.0.0.1:8765";
  let socket = null;

  function getActiveAdapter() {
    if (window.CapoeiraGeminiAdapter && window.CapoeiraGeminiAdapter.match()) {
      return window.CapoeiraGeminiAdapter;
    }
    return null;
  }

  function connect() {
    socket = new WebSocket(WS_URL);

    socket.onopen = () => {
      console.log("[CapoeiraCode Bridge] Conectado ao CLI local.");
    };

    socket.onmessage = async (event) => {
      const data = JSON.parse(event.data);
      
      if (data.action === "SEND_PROMPT") {
        const adapter = getActiveAdapter();
        if (!adapter) {
          console.error("[CapoeiraCode Bridge] Nenhum adaptador compatível.");
          return;
        }

        const fullPrompt = `${data.payload.systemPrompt}\n\n${data.payload.prompt}`;
        await adapter.injectAndSend(fullPrompt);
        waitForCompletion(adapter);
      }
    };

    socket.onclose = () => {
      setTimeout(connect, 3000);
    };
  }

  function waitForCompletion(adapter) {
    const interval = setInterval(() => {
      const sel = adapter.getSelectors();
      const isGenerating = !!document.querySelector(sel.stopButton);

      if (!isGenerating) {
        clearInterval(interval);
        const responseNodes = document.querySelectorAll(sel.responses);
        if (responseNodes.length > 0) {
          const lastResponse = responseNodes[responseNodes.length - 1].innerText;
          
          socket.send(JSON.stringify({
            action: "RESPONSE",
            status: "SUCCESS",
            payload: { rawResponse: lastResponse }
          }));
        }
      }
    }, 1000);
  }

  connect();
})();
```
