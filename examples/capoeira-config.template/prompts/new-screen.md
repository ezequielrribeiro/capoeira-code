# Prompt: new-screen (prompts/new-screen.md)

Crie uma nova tela para o sistema seguindo, obrigatoriamente, os padrões do projeto.

Detalhes do pedido:
- Nome da tela e funcionalidade.
- Dados/tabela principais (se o usuário informar).
- Menus/acessos envolvidos (se informado).

Entregue o lote multi-arquivo com `create_file` para:
- controller (app/controllers/<Nome>Controller.php) validando entrada;
- view (app/views/<nome>.php) com os layouts topo/rodape e classes CSS do projeto;
- css quando necessário (public/assets/css/<nome>.css);
- migração `.sql` quando houver mudança de schema (database/migrations/).

Use exclusivamente a estrutura de pastas e convenções definidas no PERFIL DO PROJETO.