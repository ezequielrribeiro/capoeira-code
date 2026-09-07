# AGENTS.md

## Estado do repositório

- **Iteração 3 concluída (v2.0.0)**: o CLI Python existe, está testado e fala com LLM via **backend compatível com a API do Ollama** (`POST /api/chat`, stdlib `urllib`). **Não existe mais comunicação via extensão/navegador** — não procure por `extension/`, `server.py` ou `websockets`; o CapoeiraCode migrou esse papel para o [CapoeiraHost](https://github.com/ezequielrribeiro/capoeira-host).
- Fonte da verdade: `specs/capoeira-code-spec.md` (pt-BR, v2.0.0 — já reconciliada com a Iteração 3; §9 lista o histórico). Contratos de protocolo/schema vêm de lá; detalhes de implementação, o código manda.
- Documentação e strings visíveis ao usuário são em **pt-BR**.

## Comandos (Windows, a partir da raiz)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q                     # suíte completa
.\.venv\Scripts\python.exe -m pytest tests/test_applier.py  # arquivo único
.\.venv\Scripts\python.exe -m pytest -k nome_do_teste       # teste único
.\.venv\Scripts\python.exe -m cli refactor --file X.php --symbol Y --instruction "..." [--model M --base-url URL]
.\.venv\Scripts\python.exe -m cli generate  --file Z.py --instruction "..." [--context W.php]
.\.venv\Scripts\python.exe -m cli explain   --file X.php [--symbol Y]
.\.venv\Scripts\python.exe -m cli deps      --file X.php
```

- Rode sempre via `.\.venv\Scripts\python.exe` (o venv **não** está no PATH) e sempre da raiz (`cli` é pacote com imports relativos; `python -m cli` não funciona de dentro de `cli/`).
- Repositório git inicializado (branch `master`). Não há CI, linter ou formatter configurados — `pytest` verde é a barreira. Não commite sem pedido explícito.
- O CLI é **síncrono** (sem asyncio — não há WS). Para testar comandos, ver `tests/test_cli.py` (substitui `cli.main.LLMClient` por um stub) e `tests/test_llm_client.py` (servidor HTTP in-process simulando a API do Ollama).

## Desvios da spec já consolidados (não "corrigir" de volta)

1. **`tree-sitter-languages` substituído** por `tree-sitter` + `tree-sitter-php` + `tree-sitter-javascript` + `tree-sitter-python`: o pacote da spec está abandonado e não tem wheel p/ Python 3.13.
2. **API tree-sitter 0.26**: não existem `Node.sexp()` nem `Query.captures()`. Use `str(node)` e `QueryCursor(Query(lang, scm))` com `.matches()` (retorna `(idx, {capture: [nodes]})`) / `.captures()` (retorna dict).
3. **Comunicação com LLM via `cli/llm_client.py`** (HTTP `POST /api/chat`, Ollama-compatível, stdlib) — a antiga ponte WebSocket `server.py` foi **removida** em v2.0.0. Não recriar `websockets`/`extension/`.
4. **`applier.py`** implementa `replace_symbol` via splice de byte-range tree-sitter (`find_symbol_range`, adicionado à `BaseLanguageReducer`) — o esqueleto §8.1 sobrescreveria o arquivo inteiro.
5. **`apply_payload(raw, expected_file_path=None)`**: com `generate`, o applier barra o `file_path` retornado pelo LLM se ele não bater com o alvo — falha sem escrever nada.

## Contratos que não podem derivar

- Placeholder exato (token de comentário por linguagem): `// ... [Omitted by CapoeiraCode] ...` (`OMISSION_PLACEHOLDER`) para PHP/JS e `# ... [Omitted by CapoeiraCode] ...` (`PYTHON_OMISSION_PLACEHOLDER`) para Python — ambas em `cli/reducers/base.py`.
- Backend LLM: `POST {base_url}/api/chat` com corpo JSON Ollama `{model, stream:false, messages:[system, user]}`; default `http://127.0.0.1:8765` (CapoeiraHost), default `--model gemini-pro`. Sem chave de API.
- Schema LLM (§5): obrigatórios `file_path`, `action` ∈ `replace_symbol|create_file|patch_diff`, `code_content`.
- RNF-04: falha de parse/validação ⇒ **nada** é escrito (escrita atômica via tmp + `os.replace`) e o CLI envia prompt de autocorreção (máx. `--max-retries`, padrão 3).
- RNF-01: skeleton de arquivo de 5.000 linhas em < 200 ms (medido: ~97 ms).

## Gotchas do ambiente

- Console PowerShell exibe acentos UTF-8 quebrados (`Refatorao`) — é cosmético; as strings no código são UTF-8 corretas. Não "conserte" o código por causa disso.
- Inline de Python com `$`/aspas via `python -c` no PowerShell corrompe escaping; prefira escrever script temporário em `%LOCALAPPDATA%\Temp\opencode` e executá-lo.
- Testes do backend LLM rodam com `ThreadingHTTPServer` em porta efêmera dentro do próprio teste (sem serviço externo).

## Próxima iteração

- **Foco em codificação/artefatos**: candidatos a novos comandos/capacidades em cima do núcleo atual — reducers HTML/CSS, suporte a mais linguagens, `generate` com modelos de scaffolding por stack, e adaptação ao streaming (`stream:true`) do protocolo Ollama.