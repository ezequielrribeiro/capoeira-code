# CapoeiraCode

Agente CLI para manutenção, refatoração, criação de telas/artefatos e **automação de
rotina** em **sistemas legados** (foco inicial em PHP). O CLI reduz o contexto do código
via AST (Tree-Sitter) e conversa com um **backend compatível com a API do Ollama** —
tanto o [Ollama](https://ollama.com) nativo quanto o gateway
[CapoeiraHost](https://github.com/ezequielrribeiro/capoeira-host) — via HTTP/JSON
(`POST /api/chat`). Sem navegador, sem extensão, sem ponte WebSocket.

O CapoeiraCode também funciona como um **motor de instrução declarativo** (estilo OpenCode):
você escreve `specs`, `skills` e `prompts` em arquivos e o LLM decide as ações (inclusive
lote multi-arquivo), aplicadas atomicamente — sem subcomandos fixos por fluxo.

A especificação completa está em [`specs/capoeira-code-spec.md`](specs/capoeira-code-spec.md).

## Status do projeto

| Componente | Status |
| --- | --- |
| CLI Python (reducers PHP/JS/Python, applier multi-arquivo, cliente Ollama) | ✅ Implementado e testado |
| Motor de instrução (`run`), `ask` (RAG), `deps --project` | ✅ Implementados e testados |
| Premissas por projeto (`projects/*.yaml`) + scanner de dependências | ✅ Implementados |
| Reducers HTML/CSS/SQL | ⏳ Futuro |
| Sessão persistente/`--json`/autodetecção de projeto | ⏳ Futuro (Fase 3) |

## Requisitos

- Python 3.13+ (funciona em 3.10+; as dependências têm wheels abi3)
- Um backend compatível com Ollama rodando:
  - **CapoeiraHost** (padrão): `python -m server.main` em `http://127.0.0.1:8765` (subir também a extensão no navegador com uma aba logada do provedor), ou
  - **Ollama nativo**: `ollama serve` em `http://127.0.0.1:11434` com algum modelo (`ollama pull qwen2.5-coder`).
- **Opcional** — [local-rag-system](https://github.com/ezequielrribeiro/local-rag-system)
  para injetar contexto (docs/tickets) via `--rag`/`ask`.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

## Configuração por projeto (premissas)

Crie um diretório de config do CapoeiraCode (`CAPOEIRA_CONFIG_DIR`, ou
`%APPDATA%\CapoeiraCode` no Windows, ou `~/.capoeira`) com a seguinte estrutura:

```text
CapoeiraCode/
├── projects/*.yaml      # premissas por sistema legado (veja examples/)
├── specs/*.md           # regras/padrões do sistema (declarativo)
├── skills/*.md          # procedimentos que o motor pode usar
└── prompts/*.md         # fluxos pré-escritos (new-screen, bugfix, optimize, ...)
```

Um `projects/<nome>.yaml` descreve stack, estrutura de pastas, convenções, **banco**
(schema/dump SQL) e onde roda o `local-rag-system`. Modelo em
[`examples/capoeira-config.template`](examples/capoeira-config.template).

## Uso

Sempre a partir da raiz do repositório. Opções comuns: `--base-url`
(padrão `http://127.0.0.1:8765`), `--model` (padrão `gemini-pro`) e `--timeout`.

### `run` — motor de instrução (o coração)

Você descreve a tarefa e o LLM decide **quais arquivos** criar/editar e com que ação
(`create_file` / `replace_symbol` / `patch_diff`), em lote multi-arquivo se preciso —
aplicado atomicamente (RNF-04).

```powershell
# Nova tela seguindo os prompts/skills do projeto
.\.venv\Scripts\python.exe -m cli run `
  "Crie a tela de cadastro de garagens com controller, view, CSS e migração SQL" `
  --project exemplo-garagens `
  --prompt new-screen `
  --skill criar-tela

# Correção de bug com contexto RAG (tickets/docs) e dry-run
.\.venv\Scripts\python.exe -m cli run `
  "Corrija o erro de listagem de vagas descrito" `
  --project exemplo-garagens `
  --prompt bugfix `
  --file app/views/vagas.php `
  --rag "ticket bloqueio no cadastro de vaga" `
  --doc-type support `
  --dry-run
```

`--dry-run` mostra o diff colorido e pede confirmação antes de gravar.

### `ask` — consultar o `local-rag-system`

```powershell
.\.venv\Scripts\python.exe -m cli ask "Como alterar a senha?" --project exemplo-garagens --doc-type user
```

### Comandos clássicos (mantidos)

```powershell
# Refatorar um símbolo específico
.\.venv\Scripts\python.exe -m cli refactor --file app/models/Db.php --symbol conectar --instruction "..."

# Gerar artefato (testes/esqueleto/docs)
.\.venv\Scripts\python.exe -m cli generate --file tests/test_Garagens.php --instruction "Crie testes" --context app/models/Garagens.php

# Explicar código (depreciado — use o RAG para levantamento)
.\.venv\Scripts\python.exe -m cli explain --file app/views/vagas.php --symbol listar

# Dependências do arquivo (+ --project para classificar módulo e tabelas)
.\.venv\Scripts\python.exe -m cli deps --file app/views/vagas.php --project exemplo-garagens
```

Em falha de parse/validação, **nada é escrito** (RNF-04: escrita atômica via tmp +
`os.replace`) e um prompt de autocorreção é reenviado até `--max-retries` (padrão 3).

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Os testes do backend LLM usam um servidor HTTP `ThreadingHTTPServer` in-process
simulando a API do Ollama; o RAG é testado com subprocess mockado — sem navegador nem
serviços externos.

## Arquitetura (CLI)

```text
cli/
├── main.py              # Click: run (motor) | ask | refactor | generate | explain | deps
├── llm_client.py        # Cliente HTTP /api/chat compatível com Ollama (urllib, stdlib)
├── prompts.py           # Builders de prompt; contrato multi-arquivo do motor run
├── applier.py           # Aplicador atômico multi-arquivo (create/replace/patch) em batch
├── instruction/         # Loader de specs/skills/prompts do diretório de config
├── project/             # Premissas por projeto (yaml) + scanner de dependências/banco
├── rag_client.py        # Integração com local-rag-system (subprocess)
└── reducers/            # Tree-Sitter PHP/JS/Python: esqueleto, deps, find_symbol_range
```

## Contratos estáveis (não mudar sem atualizar a spec)

- Placeholder de omissão: `// ... [Omitted by CapoeiraCode] ...`
- Backend LLM: `POST {base_url}/api/chat` (JSON Ollama `{model, stream:false, messages}`)
- Schema de resposta: ação única `{file_path, action, code_content, ...}` **ou** lote
  `{"files": [...]}` (multi-arquivo); `action ∈ replace_symbol|create_file|patch_diff`
- RNF-04: falha ⇒ nada é escrito; multi-arquivo é all-or-nothing
- Diretório de config: `CAPOEIRA_CONFIG_DIR` → `%APPDATA%\CapoeiraCode` → `~/.capoeira`