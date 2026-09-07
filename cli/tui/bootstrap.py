"""Bootstrap: criação de um sistema do zero a partir da raiz do projeto."""

BUILTIN_BOOTSTRAP_PROMPT = """Estamos criando um sistema do zero neste diretório.

Passos obrigatórios:
1) Faça perguntas ao usuário (ask_user) até ter o necessário para começar:
   - tecnologia/stack principal (ex.: PHP, Python, Node) e versão;
   - nome do sistema e domínio principal;
   - banco de dados (MySQL/Postgres) e tabelas iniciais;
   - preferência de estrutura (mvc, pastas simples, etc.), se não houver blueprint.
2) Defina a estrutura de pastas base e crie os arquivos de configuração do stack
   (composer.json/requirements.txt/package.json etc.), o código inicial de exemplo
   e o arquivo de leitura/instruções (README).
3) Para o banco, SEMPRE gere:
   - database/schema.sql (dump completo das tabelas);
   - database/migrations/<N>-descricao.sql (criações incrementais);
   e avise o usuário em "done" que ele deve executar os arquivos .sql no banco
   desejado — NÃO tente aplicar SQL por linha de comando.
4) Crie apenas o que estiver definido; pergunte antes de decisões importantes
   (orcamento de escopo, autenticação, etc.).
5) Ao final, encerre com um passo "done" resumindo o que foi criado."""


def bootstrap_instruction(instruction_set) -> str:
    """Retorna a instrução de bootstrap (customizada via prompts/bootstrap.md ou padrão)."""
    try:
        custom = instruction_set.get_prompt("bootstrap")
    except AttributeError:
        custom = ""
    return custom or BUILTIN_BOOTSTRAP_PROMPT