# Skill: criar-sistema (skills/criar-sistema.md)

Procedimento para criar um sistema do zero (usado pelo /bootstrap).

1. Pergunte stack, nome, banco e primeiro domínio ao usuário (ask_user).
2. Se houver blueprint disponível (blueprints/), siga a estrutura dele; caso
   contrário, proponha uma estrutura simples e confirme com o usuário.
3. Crie a base com write_file (configuração do stack, código inicial, README).
4. Para o banco, gere `database/schema.sql` + `database/migrations/*.sql` —
   SEMPRE arquivos .sql; a execução fica por conta do usuário.
5. Valide o que der com run_shell (lint do stack, se disponível).
6. Encerre com "done" listando os arquivos gerados e os próximos passos.