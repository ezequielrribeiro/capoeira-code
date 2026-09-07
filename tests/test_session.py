from pathlib import Path

from cli.tui.session import Session, slugify, workspace_dir


def test_slugify():
    assert slugify("C:/projetos/meu-projeto") == "meu-projeto"
    assert slugify("C:/projetos/Sistema Garagens!!") == "sistema-garagens"


def test_workspace_dir_dentro_do_config(tmp_path):
    d = workspace_dir(tmp_path, "C:/x/projeto")
    assert d == tmp_path / "configs" / "projeto"


def test_session_ensure_e_estrutura(tmp_path, monkeypatch):
    monkeypatch.setenv("CAPOEIRA_CONFIG_DIR", str(tmp_path))
    s = Session(config_dir=tmp_path, project_path=str(tmp_path / "app"))
    s.ensure()
    assert s.workspace.is_dir()
    assert s.asts.is_dir()
    assert s.history_file.parent == s.dir


def test_session_record_e_load(tmp_path):
    s = Session(config_dir=tmp_path, project_path=str(tmp_path / "app"))
    s.ensure()
    assert s.has_history is False
    s.record("user", "oi")
    s.record("assistant", "{\"steps\": []}")
    msgs = s.load_messages()
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "oi"
    assert msgs[1]["role"] == "assistant"
    assert s.has_history is True


def test_session_reset_limpa_historico(tmp_path):
    s = Session(config_dir=tmp_path, project_path=str(tmp_path / "app"))
    s.ensure()
    s.record("user", "x")
    (s.workspace / "tree.txt").write_text("fake", encoding="utf-8")
    s.reset()
    assert [] == s.load_messages()
    assert not (s.workspace / "tree.txt").exists()
    assert s.workspace.is_dir()