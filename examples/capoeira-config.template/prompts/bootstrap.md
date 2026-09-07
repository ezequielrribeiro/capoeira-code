# Prompt: bootstrap (prompts/bootstrap.md)

Crie um sistema do zero neste diretório, seguindo este roteiro:

1. Pergunte ao usuário (ask_user) o necessário para começar: tecnologia/stack e
   versão, nome do sistema, banco de dados e o primeiro domínio/tela.
2. Monte a estrutura base conforme o blueprint/stack escolhido e crie os arquivos
   de configuração do stack (composer.json/requirements/package.json), o README
   e um exemplo inicial funcional.
3. Banco: gere SEMPRE `database/schema.sql` e `database/migrations/<N>-descricao.sql`;
   informe no "done" que o usuário deve executar os .sql no banco desejado.
4. Não crie além do escopo definido; pergunte antes de decisões importantes.
5. Encerre o turno com um "done" resumindo o que foi criado.