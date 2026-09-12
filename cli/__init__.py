"""CapoeiraCode CLI - Agente para desenvolvimento e criação de artefatos em sistemas legados.

O LLM é acessado via o gateway local CapoeiraHost (`POST /api/chat`, stdlib `urllib`),
sem ponte WebSocket nem extensão de navegador.

A única interface é a TUI interativa (`capoeira [PATH]`):
- entry.py: entry point `capoeira` (sempre abre a TUI).
- tui/: modo agente interativo (TUI) com ferramentas de leitura/execução/escrita.
"""