# CapoeiraCode

Agente **interativo (TUI)** para manutenção, refatoração, criação de telas/artefatos e
**automação de rotina** em **sistemas legados** (foco inicial em PHP). O CapoeiraCode reduz
o contexto do código via AST (Tree-Sitter) e conversa com um **backend compatível com a API
do Ollama** — tanto o [Ollama](https://ollama.com) nativo quanto o gateway
[CapoeiraHost](https://github.com/ezequielrribeiro/capoeira-host) — via HTTP/JSON
(`POST /api/chat`). Sem navegador, sem extensão, sem ponte WebSocket.

**Toda a interação é pela TUI** (`capoeira [PATH]`): você escreve instruções livres e o
agente decide as ações — lendo arquivos, executando comandos e aplicando mudanças
atômicas (multi-arquivo) — como no chat do Gemini/Copilot, mas local. Stack e padrões são
definidos por você em arquivos `.md` (`specs/`, `skills/`, `prompts/`, `blueprints/`) no
diretório de config ou no próprio prompt.

A especificação completa está em [`specs/capoeira-code-spec.md`](specs/capoeira-code-spec.md).

## Status do projeto

| Componente | Status |
| --- | --- |
| Modo agente/TUI (`capoeira [PATH]`), sessão, scan e ferramentas | ✅ Implementado e testado |
| Criar do zero: bootstrap, streaming e `blueprints/` | ✅ Implementados e testados |
| Premissas por projeto (`projects/*.yaml`) + scanner de dependências | ✅ Implementados |
| `/ask` (RAG) e `/deps` (scan local) dentro da TUI | ✅ Implementados e testados |
| Reducers HTML/CSS/SQL | ⏳ Futuro |
| Sessão múltipla por projeto, `--json` | ⏳ Futuro |

## Requisitos

- Python 3.13+ (funciona em 3.10+; as dependências têm wheels abi3)
- Um backend compatível com Ollama rodando:
  - **CapoeiraHost** (padrão): `python -m server.main` em `http://127.0.0.1:8765` (subir também a extensão no navegador com uma aba logada do provedor), ou
  - **Ollama nativo**: `ollama serve` em `http://127.0.0.1:11434` com algum modelo (`ollama pull qwen2.5-coder`).
- **Opcional** — [local-rag-system](https://github.com/ezequielrribeiro/local-rag-system)
  para contexto (docs/tickets) via `/ask` na TUI.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip install -e .   # cria os executáveis `capoeira` / `capoeira-code`
```

## Uso (TUI)

```powershell
capoeira "C:\sistemas\garagens"        # raiz do projeto (padrão: diretório atual)
capoeira --project garagens --readonly # flags de entrada (veja abaixo)
# equivalência sem instalar o entry point:
.\.venv\Scripts\python.exe -m cli "C:\sistemas\garagens"
```

Entrada (flags): `--project NOME` (premissas `projects/<nome>.yaml`), `--readonly`
(bloqueia execução/escrita), `--model M`, `--base-url URL`, `--timeout SEG`, `--help`.

Ao iniciar, o CapoeiraCode:
1. cria o workspace de sessão em `<config>/configs/garagens/` (`tree.txt`,
   `dependencies.json`, `asts/`, `session.jsonl` — retomável);
2. carrega premissas (`projects/<slug>.yaml`) e specs/skills/prompts/blueprints do config;
3. mostra o prompt `capoeira> `. Digite a instrução e pressione `Enter`.

O LLM responde com **passos de ferramentas**: `read_file`, `list_dir`, `run_shell`,
`run_python`, `write_file`, `ask_user`, `done`. Leituras são automáticas; execução e
escrita pedem aprovação na TUI (`y`/`n`/`a` = sempre na sessão). `Ctrl+C` interrompe o
turno; `/reset` limpa a sessão. Respostas chegam em **streaming**.

Em um diretório vazio (ou sem stack reconhecido), digite **`/bootstrap`**: o agente pergunta
a stack, nome e banco, cria a estrutura base e gera `database/schema.sql` +
`migrations/*.sql` — **você executa os `.sql`** no banco desejado. Defina a stack/estrutura
nos `.md` do config (`blueprints/`, `specs/`, `skills/`) ou no próprio prompt.

### Comandos da TUI

| Comando | Descrição |
| --- | --- |
| `/help` | ajuda |
| `/model M`, `/base-url URL` | trocar backend/modelo |
| `/premises` | recarregar premissas e artefatos do config |
| `/rescan` | regenerar artefatos de scan do projeto |
| `/reset` | apagar sessão/histórico e rescaneiar |
| `/bootstrap` | criar sistema do zero (stack/banco → base + `.sql`) |
| `/max-turns N` | limite de turnos do agente |
| `/readonly` | alternar somente-leitura |
| `/ask <pergunta> [--doc-type user\|tech\|support]` | consultar o `local-rag-system` |
| `/deps <arquivo>` | módulo, dependências e tabelas SQL de um arquivo (sem LLM) |
| `/quit` | sair |

Em falha de parse/validação, **nada é escrito** (RNF-04: escrita atômica via tmp +
`os.replace`); no lote multi-arquivo, all-or-nothing.

## Configuração por projeto (premissas)

Crie um diretório de config do CapoeiraCode (`CAPOEIRA_CONFIG_DIR`, ou
`%APPDATA%\CapoeiraCode` no Windows, ou `~/.capoeira`) com:

```text
CapoeiraCode/
├── projects/*.yaml      # premissas por sistema legado (veja examples/)
├── specs/*.md           # regras/padrões do sistema (declarativo)
├── skills/*.md          # procedimentos que o motor pode usar
├── prompts/*.md         # fluxos pré-escritos (bootstrap, new-screen, bugfix, ...)
└── blueprints/*.md      # exemplos de estrutura/stack (usados no bootstrap/agente)
```

Um `projects/<nome>.yaml` descreve stack, estrutura de pastas, convenções, **banco**
(schema/dump SQL) e onde roda o `local-rag-system`. Modelo em
[`examples/capoeira-config.template`](examples/capoeira-config.template).

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

O backend LLM é testado com servidor HTTP `ThreadingHTTPServer` in-process simulando a API
do Ollama (incluindo streaming NDJSON); RAG e ferramentas com subprocess mockado — sem
navegador nem serviços externos.

## Arquitetura

```text
cli/
├── entry.py             # `capoeira [PATH] [flags]` → sempre abre a TUI (única interface)
├── llm_client.py        # Cliente HTTP /api/chat compatível com Ollama (urllib; stream)
├── prompts.py           # Contratos de prompt; TOOLS_CONTRACT do agente (steps)
├── applier.py           # Aplicador atômico multi-arquivo (create/replace/patch)
├── instruction/         # Loader de specs/skills/prompts/blueprints do config
├── project/             # Premissas por projeto (yaml) + scanner de dependências/banco
├── rag_client.py        # Integração com local-rag-system (subprocess; /ask)
└── tui/                 # Modo agente interativo (prompt_toolkit + rich)
    ├── app.py           # TUI + /comandos (inclui /ask e /deps), streaming, bootstrap
    ├── session.py       # workspace configs/<slug>/ + session.jsonl (retomável)
    ├── scan_artifacts.py# tree.txt, dependencies.json, asts/ (+ is_empty_project)
    ├── permissions.py   # política (leitura auto; ask/readonly/auto)
    ├── tools.py         # executores read/list/run_shell/run_python/write_file
    ├── agent.py         # loop de steps até done/max_turns (streaming)
    └── bootstrap.py     # instrução/funções do criar-do-zero (/bootstrap)
```

## Contratos estáveis (não mudar sem atualizar a spec)

- Placeholder de omissão: `// ... [Omitted by CapoeiraCode] ...`
- Backend LLM: `POST {base_url}/api/chat` (JSON Ollama `{model, stream, messages}`)
- Schema de resposta (write_file): `{file_path, action, code_content, ...}` com
  `action ∈ replace_symbol|create_file|patch_diff`; batch `{"files": [...]}` (multi-arquivo)
- **Agente (TUI)**: resposta `{"steps":[{tool,...}]}` (§5.1 da spec); leitura automática,
  execução/escrita sob política de permissão; resposta em streaming (`stream:true`)
- RNF-04: falha ⇒ nada é escrito; multi-arquivo é all-or-nothing
- Diretório de config: `CAPOEIRA_CONFIG_DIR` → `%APPDATA%\CapoeiraCode` → `~/.capoeira`
- Sessão: `configs/<slug>/` com `session.jsonl` (1 sessão ativa por projeto + `/reset`)
- Bootstrap/stack: definido pelo usuário via `blueprints/`-`specs/`-`skills/`-`prompts/` `.md` ou prompt (sem stack hardcoded); banco vira `.sql` para o usuário executar