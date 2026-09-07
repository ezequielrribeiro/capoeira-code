# Skill: otimizar (skills/otimizar.md)

Procedimento para refatoração e otimização de código legado.

1. Identifique gargalos típicos de legado: N+1 em loops de query, consultas sem
   indexação clara, duplicação de lógica, SQL dentro de view, falta de escaping.
2. Aplique mudanças localizadas com `replace_symbol`/`patch_diff`; evite reescrever
   arquivos inteiros fora do escopo pedido.
3. Preserve comportamento externo da tela; documente em "explanation" o ganho
   (ex.: redução de queries, extração de método).
4. Se tocar em mais de um arquivo (ex.: extrair helper para model), use o lote
   multi-arquivo.