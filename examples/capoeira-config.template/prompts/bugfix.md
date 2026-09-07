# Prompt: bugfix (prompts/bugfix.md)

Corrija o bug descrito a seguir em arquivos existentes do sistema.

Instruções:
- Use a descrição do problema; quando houver contexto (--file/--context) ou contexto
  de base de conhecimento (--rag), aproveite para localizar a causa raiz.
- Corrija o mínimo necessário. Ações recomendadas: `replace_symbol` para métodos/funções
  e `patch_diff` para ajustes pontuais.
- Nunca quebre o padrão de layoute nem desative o escaping de saída.
- Ao final, explique em uma/duas linhas a causa raiz e a correção em cada ação.