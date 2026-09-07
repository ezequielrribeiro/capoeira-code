# 00 — Arquitetura (specs/00-arquitetura.md)

O sistema é PHP antigo sem framework: cada módulo é um par Controller + View (tela
`.php`) que invoca Models central no banco.

- Toda tela carrega `app/views/layouts/topo.php` (cabeçalho/menu) e fecha com
  `app/views/layouts/rodape.php`.
- O controller valida entrada (via `$_POST`/`$_GET`), chama o model e `include` a view.
- Não existe autoload Composer: arquivos são referenciados por `require_once` com
  caminho relativo a partir de `app/`.
- Banco relacional MySQL; acesso exclusivamente pela classe `app/models/Db.php`.
- Migrações são arquivos `.sql` incrementais em `database/migrations/`.