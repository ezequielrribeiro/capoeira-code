from pathlib import Path

from cli.tui.session import DEFAULT_SESSION, Session, name_slug, slugify, workspace_dir


def test_slugify():
    assert slugify("C:/projetos/meu-projeto") == "meu-projeto"
    assert slugify("C:/projetos/Sistema Garagens!!") == "sistema-garagens"


def test_name_slug_para_sessao():
    assert name_slug("refactor login") == "refactor-login"
    assert name_slug("  ") == DEFAULT_SESSION


def test_workspace_dir_dentro_do_config(tmp_path):
    d = workspace_dir(tmp_path, "C:/x/projeto")
    assert d == tmp_path / "configs" / "projeto"


def test_session_default_fica_sob_sessions(tmp_path):
    s = Session(config_dir=tmp_path, project_path=str(tmp_path / "app"))
    assert s.name == DEFAULT_SESSION
    assert s.dir == s.project_dir / "sessions" / DEFAULT_SESSION
    assert s.history_file == s.dir / "session.jsonl"
    assert s.workspace == s.project_dir / "workspace"
    assert s.history_file.parent == s.dir


def test_session_nomeada(tmp_path):
    s = Session(config_dir=tmp_path, project_path=str(tmp_path / "app"), name="refactor login")
    assert s.name == "refactor-login"
    assert s.history_file.parent.name == "refactor-login"


def test_session_ensure_e_estrutura(tmp_path, monkeypatch):
    monkeypatch.setenv("CAPOEIRA_CONFIG_DIR", str(tmp_path))
    s = Session(config_dir=tmp_path, project_path=str(tmp_path / "app"))
    s.ensure()
    assert s.workspace.is_dir()
    assert s.asts.is_dir()
    assert s.dir.is_dir()
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


def test_session_record_tool_roundtrip(tmp_path):
    s = Session(config_dir=tmp_path, project_path=str(tmp_path / "app"))
    s.ensure()
    s.record("tool", "[FERRAMENTA write_file] ...", tool_name="write_file", tool_call_id="call_0")
    msgs = s.load_messages()
    assert msgs[0]["role"] == "tool"
    assert msgs[0]["tool_name"] == "write_file"
    assert msgs[0]["tool_call_id"] == "call_0"
    assert "[FERRAMENTA write_file]" in msgs[0]["content"]


def test_sessoes_isoladas(tmp_path):
    a = Session(config_dir=tmp_path, project_path=str(tmp_path / "app"), name="a")
    b = Session(config_dir=tmp_path, project_path=str(tmp_path / "app"), name="b")
    a.ensure()
    b.ensure()
    a.record("user", "conteúdo da A")
    assert [m["content"] for m in a.load_messages()] == ["conteúdo da A"]
    assert b.load_messages() == []


def test_list_sessions_do_projeto(tmp_path):
    proj = str(tmp_path / "app")
    for n in ("b", "a"):
        s = Session(config_dir=tmp_path, project_path=proj, name=n)
        s.ensure()
        s.record("user", "x")
    assert Session.list_sessions(tmp_path, proj) == ["a", "b"]


def test_migracao_do_legado_para_default(tmp_path):
    proj = str(tmp_path / "app")
    pdir = workspace_dir(tmp_path, proj)
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "session.jsonl").write_text('{"role": "user", "content": "legado"}\n', encoding="utf-8")
    s = Session(config_dir=tmp_path, project_path=proj)
    assert [m["content"] for m in s.load_messages()] == ["legado"]
    assert s.history_file.is_file()
    assert not (pdir / "session.jsonl").exists()
    assert Session.list_sessions(tmp_path, proj) == [DEFAULT_SESSION]


def test_reset_limpa_historico_mas_preserva_workspace_compartilhado(tmp_path):
    s = Session(config_dir=tmp_path, project_path=str(tmp_path / "app"))
    s.ensure()
    s.record("user", "x")
    (s.workspace / "tree.txt").write_text("fake", encoding="utf-8")
    s.reset()
    assert [] == s.load_messages()
    assert (s.workspace / "tree.txt").exists()
    assert s.workspace.is_dir()