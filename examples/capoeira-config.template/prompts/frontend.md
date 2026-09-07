# Prompt: frontend (prompts/frontend.md)

Faça ajustes de front-end na(s) tela(s)/arquivo(s) indicada(s).

Instruções:
- Mantenha as classes CSS do projeto (btn, card, table, alert, form-control...).
- Use `patch_diff` para ajustes pontuais de HTML/CSS e `replace_symbol` quando mexer
  em um bloco/função inteira.
- Preserve a estrutura dos layouts (topo/rodape) e o comportamento JavaScript atual,
  a menos que o pedido diga o contrário.
- Indique claramente em "explanation" o que mudou (layout, responsividade, classes, a11y).