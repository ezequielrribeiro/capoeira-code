# CapoeiraCode

Agente CLI para manutenção, refatoração e compreensão de **sistemas legados**, operando
em ambientes com acesso restrito a APIs pagas de LLM. O CLI reduz o contexto do código
via AST (Tree-Sitter) e conversa com interfaces **Web** de LLMs (Gemini, Claude,
ChatGPT, Copilot) através de uma ponte WebSocket local com uma extensão de navegador.

A especificação completa está em [`specs/capoeira-code-spec.md`](specs/capoeira-code-spec.md).

## Status do projeto

| Componente | Status |
| --- | --- |
| CLI Python (reducers PHP/JS, servidor WS, applier) | ✅ Implementado e testado |
| Extensão Chrome MV3 (`extension/`) | ⏳ Próxima iteração |
| Reducers HTML/CSS | ⏳ Futuro |

## Requisitos

- Python 3.13+ (funciona em 3.10+; as dependências têm wheels abi3)
- Chrome/Edge para a extensão (quando ela existir)

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

> **Nota de dependência:** a spec §8.1 citava `tree-sitter-languages`, mas esse pacote
> está abandonado e **não tem wheel para Python 3.13**. Usamos `tree-sitter` +
> `tree-sitter-php` + `tree-sitter-javascript` (pacotes oficiais, mesma capacidade).

## Uso

```powershell
# Sempre a partir da raiz do repositório
.\.venv\Scripts\python.exe -m cli refactor `
  --file caminho/para/legado.php `
  --symbol nome_do_metodo `
  --instruction "Extraia a lógica de desconto para um método privado" `
  --provider gemini
```

O CLI sobe a ponte em `ws://127.0.0.1:8765`, aguarda a extensão conectar, envia o
prompt reduzido e aplica a resposta **atomicamente** (RNF-04: se o JSON do LLM falhar
no parse, nada é escrito e um prompt de autocorreção é enviado, até `--max-retries`
vezes — padrão 3).

Opções: `--provider gemini|claude|chatgpt|copilot`, `--timeout 180`, `--max-retries 3`.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest -q          # suíte completa
.\.venv\Scripts\python.exe -m pytest tests/test_applier.py -q   # arquivo único
.\.venv\Scripts\python.exe -m pytest -k replace_symbol -q       # por nome
```

## Arquitetura (CLI)

```text
cli/
├── main.py        # Click: comando `refactor`, montagem do prompt com schema (spec §5), retry RNF-04
├── server.py      # WebSocket ws://127.0.0.1:8765; allowlist de Origin (RNF-02); correlação por id
├── applier.py     # Pydantic + ações create_file / replace_symbol / patch_diff; escrita atômica
└── reducers/      # Tree-Sitter PHP/JS: extract_skeleton, extract_dependencies, find_symbol_range
```

Contratos estáveis (não mudar sem atualizar a spec):

- Placeholder de omissão: `// ... [Omitted by CapoeiraCode] ...`
- Protocolo WS: `{version, id, action, payload}` com `SEND_PROMPT` / `RESPONSE`
- Schema de resposta do LLM: `file_path`, `action` (`replace_symbol|create_file|patch_diff`),
  `code_content` (obrigatórios), `target_symbol`, `explanation`
- Servidor aceita apenas `127.0.0.1` e origens na allowlist (extensões + páginas de LLM)
