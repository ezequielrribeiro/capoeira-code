import os

from cli import entry


def test_help_imprime_uso(monkeypatch, capsys):
    monkeypatch.setattr("cli.tui.app.run_tui", lambda **k: None)
    entry.main(["--help"])
    out = capsys.readouterr().out
    assert "Uso:" in out
    assert "--project" in out
    assert "--session" in out


def test_sem_args_abre_tui_no_cwd(monkeypatch):
    chamadas = {}

    def fake_run_tui(**kwargs):
        chamadas.update(kwargs)

    monkeypatch.setattr("cli.tui.app.run_tui", fake_run_tui)
    entry.main([])
    assert chamadas["project_path"] == os.getcwd()
    assert chamadas["readonly"] is False


def test_path_inicial_abre_tui(monkeypatch):
    chamadas = {}

    def fake_run_tui(**kwargs):
        chamadas.update(kwargs)

    monkeypatch.setattr("cli.tui.app.run_tui", fake_run_tui)
    entry.main(["C:/sistemas/garagens"])
    assert chamadas["project_path"] == "C:/sistemas/garagens"


def test_path_com_flags(monkeypatch):
    chamadas = {}

    def fake_run_tui(**kwargs):
        chamadas.update(kwargs)

    monkeypatch.setattr("cli.tui.app.run_tui", fake_run_tui)
    entry.main(
        ["C:/sistemas/garagens", "--project", "garagens", "--readonly", "--model", "gemini-pro", "--timeout", "60"]
    )
    assert chamadas["project_path"] == "C:/sistemas/garagens"
    assert chamadas["project"] == "garagens"
    assert chamadas["readonly"] is True
    assert chamadas["model"] == "gemini-pro"
    assert chamadas["timeout"] == 60.0


def test_flags_sem_path_nao_tratam_valor_como_path(monkeypatch):
    chamadas = {}

    def fake_run_tui(**kwargs):
        chamadas.update(kwargs)

    monkeypatch.setattr("cli.tui.app.run_tui", fake_run_tui)
    entry.main(["--project", "garagens"])
    assert chamadas["project"] == "garagens"
    assert chamadas["project_path"] == os.getcwd()  # "garagens" não virou PATH


def test_flag_session_chega_ao_run_tui(monkeypatch):
    chamadas = {}

    def fake_run_tui(**kwargs):
        chamadas.update(kwargs)

    monkeypatch.setattr("cli.tui.app.run_tui", fake_run_tui)
    entry.main(["--session", "refactor-login"])
    assert chamadas["session_name"] == "refactor-login"
    assert chamadas["project_path"] == os.getcwd()  # "refactor-login" não virou PATH


def test_palavra_nao_option_e_tratada_como_path(monkeypatch):
    chamadas = {}

    def fake_run_tui(**kwargs):
        chamadas.update(kwargs)

    monkeypatch.setattr("cli.tui.app.run_tui", fake_run_tui)
    entry.main(["qualquer-coisa"])
    assert chamadas["project_path"] == "qualquer-coisa"