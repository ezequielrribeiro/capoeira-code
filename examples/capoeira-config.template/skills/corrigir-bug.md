# Skill: corrigir-bug (skills/corrigir-bug.md)

Procedimento para corrigir falhas em telas/arquivos existentes.

1. Leia a descrição do problema; use contexto adicional se fornecido (ticket,
   descrição do sintoma, trechos de código via `--file`/`--context`).
2. Localize a causa raiz no(s) arquivo(s) apontados (ou internamente se só houver a
   tela de origem do sintoma).
3. Prefira corrigir o mínimo necessário; não reescreva arquivos inteiros: use
   `replace_symbol` para funções/métodos ou `patch_diff` para trechos pequenos.
4. Mantenha os padrões do projeto (escapamento de saída, classes CSS, mensagens em pt-BR).
5. Quando o bug envolver dados, confira se a query é coerente com o schema.