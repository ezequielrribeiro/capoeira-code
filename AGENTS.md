# AGENTS.md

## Estado do repositório

- **Iteração 4 concluída (v3.0.0)**: o CLI Python é um **motor de instrução declarativo** (estilo OpenCode) + instrumentos técnicos. Fala com LLM via **backend compatível com a API do Ollama** (`POST /api/chat`, stdlib `urllib`). **Não existe comunicação via extensão/navegador**; esse papel é do [CapoeiraHost](https://github.com/ezequielrribeiro/capoeira-host).
- Fonte da verdade: `specs/capoeira-code-spec.md` (pt-BR, v3.0.0; §9 lista o histórico). Contratos de protocolo/schema vêm de lá; detalhes de implementação, o código manda.
- Documentação e strings visíveis ao usuário são em **pt-BR**.

## Comandos (Windows, a partir da raiz)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q                     # suíte completa
.\.venv\Scripts\python.exe -m pytest tests/test_applier.py  # arquivo único
.\.venv\Scripts\python.exe -m pytest -k nome_do_teste       # teste único
.\.venv\Scripts\python.exe -m cli run "INSTRUÇÃO" [--project X] [--prompt F] [--skill S] [--file A]... [--rag "q"] [--dry-run]
.\.venv\Scripts\python.exe -m cli ask "PERGUNTA" --project X [--doc-type user|tech|support]
.\.venv\Scripts\python.exe -m cli refactor --file X.php --symbol Y --instruction "..."
.\.venv\Scripts\python.exe -m cli generate --file Z.py --instruction "..."
.\.venv\Scripts\python.exe -m cli deps --file X.php [--project X]
```

- Rode sempre via `.\.venv\Scripts\python.exe` (venv não está no PATH) e sempre da raiz (`cli` usa imports relativos).
- Não há CI, linter ou formatter — `pytest` verde é a barreira. Não commite sem pedido explícito.
- Testes: `tests/test_cli.py` e `tests/test_cli_motor.py` substituem `cli.main.LLMClient` por stub; RAG é mockado em `cli.rag_client.subprocess.run`; backend LLM usa `ThreadingHTTPServer` in-process.

## Desvios da spec já consolidados (não "corrigir" de volta)

1. **`tree-sitter-languages` substituído** por `tree-sitter` + gramáticas oficiais (`tree-sitter-php`/`-javascript`/`-python`) — sem wheel p/ Python 3.13.
2. **API tree-sitter 0.26**: não existem `Node.sexp()` nem `Query.captures()`. Use `str(node)` e `QueryCursor(Query(lang, scm))` com `.matches()` / `.captures()`.
3. **Comunicação com LLM via `cli/llm_client.py`** (HTTP `POST /api/chat`, Ollama-compatível, stdlib) — a ponte WebSocket `server.py` foi removida em v2.0.0. Não recriar `websockets`/`extension/`.
4. **Applier multi-arquivo**: `apply_payload` aceita ação única (compat) **ou** `{"files": [...]}`; `stage_payload`/`commit_staged` (dry-run, atomicidade all-or-nothing do lote).
5. **`apply_payload(raw, expected_file_path=None)`**: com `generate`, o `file_path` retornado deve casar o alvo, senão falha sem escrever.
6. **Motor `run`** (`cli/instruction/loader.py` + `cli/project/premises.py` + `cli/rag_client.py`): premissas em `projects/<nome>.yaml` no dir de config; specs/skills/prompts em `.md`; listas vazias em `specs/skills/prompts` significam "nenhum", omissão significa "todos".

## Contratos que não podem derivar

- Placeholder exato: `// ... [Omitted by CapoeiraCode] ...` (`OMISSION_PLACEHOLDER`, PHP/JS) e `# ... [Omitted by CapoeiraCode] ...` (`PYTHON_OMISSION_PLACEHOLDER`, Python) — em `cli/reducers/base.py`.
- Backend LLM: `POST {base_url}/api/chat` JSON Ollama `{model, stream:false, messages:[system, user]}`; default `http://127.0.0.1:8765` (CapoeiraHost), `--model gemini-pro`. Sem chave de API.
- Diretório de config: `CAPOEIRA_CONFIG_DIR` → `%APPDATA%\CapoeiraCode` → `~/.capoeira`.
- Schema LLM (§5): ação única `{file_path, action ∈ replace_symbol|create_file|patch_diff, code_content}` **ou** lote `{"files": [...]}`.
- RNF-04: falha ⇒ nada é escrito (atômico, inclusive no lote) + autocorreção até `--max-retries` (padrão 3).
- RNF-01: skeleton < 200 ms para 5.000 linhas (medido ~97 ms).
- RAG: `RagClient` executa `python main.py query "<q>" [--doc-type mapeado]` no `rag.working_dir` das premissas (subprocess, independente do backend do CapoeiraCode).

## Gotchas do ambiente

- Console PowerShell exibe acentos UTF-8 quebrados (`Refatorao`) — cosmético; strings em código são UTF-8 corretas. Não "corrigir" por causa disso.
- Inline de Python com `$`/aspas via `python -c` no PowerShell corrompe escaping; use script temporário em `%LOCALAPPDATA%\Temp\opencode`.
- `click.confirm` no modo `--dry-run` requer `input=...` no `CliRunner` (ver `test_cli_motor.py`).
- Instalar o `PyYAML` no venv antes de rodar testes novos (`pip install -r requirements-dev.txt`).

## Próxima iteração

- **Fase 3 (UX)**: sessão/workspace por projeto em `.capoeira/`, saída `--json`, autodetecção de `--project`.
- **Fase 4**: reducers HTML/CSS/SQL, adaptação ao streaming (`stream:true`) do Ollama.
- Novos skills/prompts no template (`examples/capoeira-config.template`) conforme surgem fluxos.