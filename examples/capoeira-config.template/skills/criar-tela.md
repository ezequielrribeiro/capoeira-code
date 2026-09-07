# Skill: criar-tela (skills/criar-tela.md)

Procedimento para criar uma nova tela no padrão do sistema.

1. Identifique o módulo (controller/views/css/migração) a partir do pedido.
2. Siga a estructura da tela: Controller que valida e orquestra, View que usa os
   layouts `topo.php`/`rodape.php`, classes CSS do projeto, e migração `.sql` quando
   houver tabela nova.
3. Produza o lote multi-arquivo com `create_file` para cada arquivo da tela.
4. Ao final, resuma o que foi criado em "explanation" de cada ação.