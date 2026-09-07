"""CapoeiraCode CLI - Agente para desenvolvimento e criação de artefatos em sistemas legados.

O LLM é acessado via backend compatível com a API do Ollama (Ollama nativo ou
CapoeiraHost), sem ponte WebSocket nem extensão de navegador.

Módulos:
- entry.py: entry point `capoeira` (PATH abre a TUI; subcomandos usam o Click).
- main.py: comandos Click (run/refactor/generate/explain/deps/ask/tui).
- tui/: modo agente interativo (TUI) com ferramentas de leitura/execução/escrita.
"""