import pytest

from cli import entry


def test_entry_sem_args_abre_tui_no_cwd(monkeypatch):
    chamadas = {}

    def fake_run_tui(**kwargs):
        chamadas.update(kwargs)

    monkeypatch.setattr("cli.tui.app.run_tui", fake_run_tui)
    entry.main([])
    assert "project_path" in chamadas


def test_entry_path_abre_tui(monkeypatch):
    chamadas = {}

    def fake_run_tui(**kwargs):
        chamadas.update(kwargs)

    monkeypatch.setattr("cli.tui.app.run_tui", fake_run_tui)
    entry.main(["C:/sistemas/garagens"])
    assert chamadas["project_path"] == "C:/sistemas/garagens"


def test_entry_path_com_flags_parsing(monkeypatch):
    chamadas = {}

    def fake_run_tui(**kwargs):
        chamadas.update(kwargs)

    monkeypatch.setattr("cli.tui.app.run_tui", fake_run_tui)
    entry.main(["C:/sistemas/garagens", "--project", "garagens", "--readonly", "--model", "gemini-pro"])
    assert chamadas["project"] == "garagens"
    assert chamadas["readonly"] is True
    assert chamadas["model"] == "gemini-pro"


def test_entry_subcomando_delega_ao_cli(monkeypatch):
    clicado = []

    def fake_cli():
        clicado.append(True)

    def fake_run_tui(**kwargs):
        raise AssertionError("não deveria abrir a TUI")

    monkeypatch.setattr("cli.main.cli", fake_cli)
    monkeypatch.setattr("cli.tui.app.run_tui", fake_run_tui)
    entry.main(["refactor", "--file", "x.php"])
    assert clicado == [True]


def test_entry_opcao_global_delega_ao_cli(monkeypatch):
    clicado = []

    def fake_cli():
        clicado.append(True)

    monkeypatch.setattr("cli.main.cli", fake_cli)
    entry.main(["--help"])
    assert clicado == [True]