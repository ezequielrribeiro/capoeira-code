# Prompt: optimize (prompts/optimize.md)

Otimize/refatore o código descrito nos arquivos informados.

Foco: gargalos típicos de legado — consultas N+1, queries repetidas, lógica duplicada,
SQL em views, falta de indexação apontada pelo schema, e chamadas caras em loop.

Regras:
- Aplicar `replace_symbol`/`patch_diff`; reescrever arquivo inteiro só quando realmente
  necessário (e justificando).
- Manter o comportamento observável da tela idêntico.
- Explicar em "explanation" o ganho obtido (ex.: "removeu N+1 extraindo query única").