# 01 — Padrões de telas (specs/01-padroes-telas.md)

## Estrutura de uma nova tela
1. `app/controllers/<Nome>Controller.php` — validação e fluxo.
2. `app/views/<nome>.php` — exibição (HTML + PHP), começando e terminando com os layouts.
3. CSS próprio em `public/assets/css/<nome>.css` (se necessário).

## Regras obrigatórias
- Usar as classes CSS do projeto: `btn`, `card`, `table`, `alert`, `form-control`.
- Formulários sempre com `method="post"` e `action` apontando para o controller.
- Nunca embutir SQL na view; passar dados prontos do controller/model.
- Escapar saída com `htmlspecialchars()` para qualquer dado vindo do usuário/banco.
- Mensagens de erro/sucesso via `alert alert-danger` / `alert alert-success`.

## Migrações
- Toda mudança de schema vira um arquivo `database/migrations/<N>-descricao.sql`
  com `CREATE TABLE`/`ALTER TABLE`; atualizar também `database/schema.sql`.