# CapoeiraCode

Agente CLI para manutenção, refatoração, **compreensão** e **criação de artefatos** de
**sistemas legados**. O CLI reduz o contexto do código via AST (Tree-Sitter) e conversa
com um **backend compatível com a API do Ollama** — tanto o [Ollama](https://ollama.com)
nativo quanto o gateway [CapoeiraHost](https://github.com/ezequielrribeiro/capoeira-host) —
via HTTP/JSON (`POST /api/chat`). Sem navegador, sem extensão, sem ponte WebSocket.

A especificação completa está em [`specs/capoeira-code-spec.md`](specs/capoeira-code-spec.md).

## Status do projeto

| Componente | Status |
| --- | --- |
| CLI Python (reducers PHP/JS/Python, applier atômico, cliente Ollama) | ✅ Implementado e testado |
| Comandos `refactor`, `generate`, `explain`, `deps` | ✅ Implementados e testados |
| Reducers HTML/CSS | ⏳ Futuro |

## Requisitos

- Python 3.13+ (funciona em 3.10+; as dependências têm wheels abi3)
- Um backend compatível com Ollama rodando:
  - **CapoeiraHost** (padrão): `python -m server.main` em `http://127.0.0.1:8765` (subir também a extensão no navegador com uma aba logada do provedor), ou
  - **Ollama nativo**: `ollama serve` em `http://127.0.0.1:11434` com algum modelo (`ollama pull qwen2.5-coder`).

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

> **Nota de dependência:** a spec §8.1 citava `tree-sitter-languages`, mas esse pacote
> está abandonado e **não tem wheel para Python 3.13**. Usamos `tree-sitter` +
> `tree-sitter-php` + `tree-sitter-javascript` (pacotes oficiais, mesma capacidade).
> A comunicação com o LLM usa apenas a stdlib (`urllib`), sem dependências novas.

## Uso

Sempre a partir da raiz do repositório. Opções comuns a comandos que chamam o LLM:
`--base-url` (padrão `http://127.0.0.1:8765`), `--model` (padrão `gemini-pro`) e `--timeout`.

### `refactor` — refatorar um símbolo de um arquivo legado

```powershell
.\.venv\Scripts\python.exe -m cli refactor `
  --file caminho/para/legado.php `
  --symbol nome_do_metodo `
  --instruction "Extraia a lógica de desconto para um método privado" `
  --model gemini-pro
```

Com Ollama nativo: `--base-url http://127.0.0.1:11434 --model qwen2.5-coder`.

### `generate` — criar artefatos que auxiliam a codificação

Testes, esqueleto de módulo, scaffolding, documentação — qualquer arquivo novo
(ação `create_file`), ou reescrever um símbolo existente (use `--symbol`):

```powershell
# Gerar testes para um arquivo
.\.venv\Scripts\python.exe -m cli generate `
  --file tests/test_legacy_calculator.php `
  --instruction "Crie testes de unidade cobrindo os métodos da classe LegacyCalculator" `
  --context src/legacy_calculator.php
```

### `explain` — compreensão de código legado (somente leitura)

```powershell
.\.venv\Scripts\python.exe -m cli explain --file src/legacy_calculator.php --symbol soma
```

### `deps` — dependências do arquivo (sem LLM, rápido)

```powershell
.\.venv\Scripts\python.exe -m cli deps --file src/dashboard.js
```

### Falha de aplicação

Se o JSON do LLM falhar no parse/validação, **nada é escrito** (RNF-04: escrita atômica
via tmp + `os.replace`) e um prompt de autocorreção é reenviado, até `--max-retries`
vezes — padrão 3.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest -q          # suíte completa
.\.venv\Scripts\python.exe -m pytest tests/test_applier.py -q   # arquivo único
.\.venv\Scripts\python.exe -m pytest -k replace_symbol -q       # por nome
```

Os testes do backend LLM usam um servidor HTTP `ThreadingHTTPServer` in-process
(porta efêmera) simulando a API do Ollama — sem navegador nem serviço externo.

## Arquitetura (CLI)

```text
cli/
├── main.py        # Click: comandos refactor/generate/explain/deps; retry RNF-04
├── llm_client.py  # Cliente HTTP /api/chat compatível com Ollama (urllib, stdlib)
├── prompts.py     # Builders de prompt (schema §5 injetado; explain/generate/retry)
├── applier.py     # Pydantic + ações create_file / replace_symbol / patch_diff; escrita atômica
└── reducers/      # Tree-Sitter PHP/JS/Python: extract_skeleton, extract_dependencies, find_symbol_range
```

Contratos estáveis (não mudar sem atualizar a spec):

- Placeholder de omissão: `// ... [Omitted by CapoeiraCode] ...`
- Backend LLM: `POST {base_url}/api/chat` (JSON Ollama: `{model, stream:false, messages}`),
  sem chaves de API — reaproveita o backend local
- Schema de resposta do LLM: `file_path`, `action` (`replace_symbol|create_file|patch_diff`),
  `code_content` (obrigatórios), `target_symbol`, `explanation`
- `create_file` e `patch_diff` validam o `file_path` retornado; em `replace_symbol` o
  byte-range vem do Tree-Sitter e o resultado é re-parseado antes de gravar