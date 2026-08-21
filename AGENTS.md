# AGENTS.md

## Estado do repositório

- **Iteração 1 concluída**: o CLI Python existe e está testado. A **extensão Chrome (`extension/`) ainda não existe** — não procure por ela nem assuma E2E funcional.
- Fonte da verdade: `specs/capoeira-code-spec.md` (pt-BR, v1.0.0 "Approved"). Contratos de protocolo/schema vêm de lá; quando o esqueleto da spec divergir da necessidade real, o código atual manda (ver "Desvios" abaixo).
- Documentação e strings visíveis ao usuário são em **pt-BR**.

## Comandos (Windows, a partir da raiz)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q                     # suíte completa
.\.venv\Scripts\python.exe -m pytest tests/test_applier.py  # arquivo único
.\.venv\Scripts\python.exe -m pytest -k nome_do_teste       # teste único
.\.venv\Scripts\python.exe -m cli refactor --file X.php --symbol Y --instruction "..."
```

- Rode sempre via `.\.venv\Scripts\python.exe` (o venv **não** está no PATH) e sempre da raiz (`cli` é pacote com imports relativos; `python -m cli` não funciona de dentro de `cli/`).
- Não há git, CI, linter ou formatter configurados — `pytest` verde é a barreira.

## Desvios da spec já consolidados (não "corrigir" de volta)

1. **`tree-sitter-languages` substituído** por `tree-sitter` + `tree-sitter-php` + `tree-sitter-javascript`: o pacote da spec está abandonado e não tem wheel p/ Python 3.13.
2. **API tree-sitter 0.26**: não existem `Node.sexp()` nem `Query.captures()`. Use `str(node)` e `QueryCursor(Query(lang, scm))` com `.matches()` (retorna `(idx, {capture: [nodes]})`) / `.captures()` (retorna dict).
3. **`server.py`** valida `Origin` (RNF-02) no handler fechando com código 1008; aguarda a extensão com `asyncio.Event` (o `asyncio.sleep(2)` do esqueleto era placeholder); `SEND_PROMPT` leva `id` (uuid) + `provider` (§4.1) e a RESPONSE é correlacionada pelo `id`.
4. **`applier.py`** implementa `replace_symbol` via splice de byte-range tree-sitter (`find_symbol_range`, adicionado à `BaseLanguageReducer`) — o esqueleto §8.1 sobrescreveria o arquivo inteiro.

## Contratos que não podem derivar

- Placeholder exato: `// ... [Omitted by CapoeiraCode] ...` (constante `OMISSION_PLACEHOLDER` em `cli/reducers/base.py`).
- WS: bind só em `127.0.0.1:8765`; allowlist de origens em `cli/server.py` (`chrome-extension://`, `moz-extension://` + origens https dos 4 providers).
- Schema LLM (§5): obrigatórios `file_path`, `action` ∈ `replace_symbol|create_file|patch_diff`, `code_content`.
- RNF-04: falha de parse/validação ⇒ **nada** é escrito (escrita atômica via tmp + `os.replace`) e o CLI envia prompt de autocorreção (máx. `--max-retries`, padrão 3).
- RNF-01: skeleton de arquivo de 5.000 linhas em < 200 ms (medido: ~97 ms).

## Gotchas do ambiente

- Console PowerShell exibe acentos UTF-8 quebrados (`Refatorao`) — é cosmético; as strings no código são UTF-8 corretas. Não "conserte" o código por causa disso.
- Inline de Python com `$`/aspas via `python -c` no PowerShell corrompe escaping; prefira escrever script temporário em `%LOCALAPPDATA%\Temp\opencode` e executá-lo.
- Testes do servidor rodam in-process com `asyncio.run` (sem `pytest-asyncio`) e porta efêmera (`port=0`).

## Próxima iteração

- `extension/` (MV3): `manifest.json`, `content.js` (reconexão com backoff exponencial, RNF-03), `adapters/gemini.js`, `adapters/claude.js` — esqueletos na spec §8.2. A extensão deve **ecoar o `id`** do `SEND_PROMPT` na `RESPONSE`.
