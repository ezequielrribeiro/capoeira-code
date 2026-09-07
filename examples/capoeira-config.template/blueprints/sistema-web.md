# Blueprint: sistema-web (blueprints/sistema-web.md)

Exemplo de estrutura recomendada para um sistema web legado/novo (stack a critério
do usuário). Use como ponto de partida, adaptando ao que for definido.

## Estrutura sugerida (PHP, sem framework — padrão deste config)
```
projeto/
├── app/
│   ├── controllers/        # fluxo HTTP + validação
│   ├── models/             # acesso a banco (PDO centralizado)
│   ├── views/              # telas (.php), com layouts topo/rodape
│   └── helpers/            # funções utilitárias (mensagens, escaping)
├── public/
│   └── assets/
│       ├── css/
│       └── js/
├── database/
│   ├── schema.sql          # dump completo (CREATE TABLE)
│   └── migrations/         # <N>-descricao.sql incrementais
├── README.md
└── composer.json           # (se PHP + Composer)
```

## Regras
- Toda tela inclui os layouts da aplicação; nada de HTML solto sem layout.
- Escapar toda saída (`htmlspecialchars`); nunca concatener SQL.
- Banco: gerar `schema.sql` + `migrations/*.sql`; o usuário executa no banco dele.
- Mensagens ao usuário em pt-BR via helpers.

(Adapte este arquivo à stack real do seu sistema: Python/Flask, Node, etc.)