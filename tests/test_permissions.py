from cli.tui.permissions import MODE_AUTO, MODE_READONLY, PermissionGate


def _gate(mode):
    return PermissionGate(mode)


def test_leitura_sempre_automatica():
    for mode in (MODE_READONLY, "ask", MODE_AUTO):
        g = _gate(mode)
        assert g.allow("read_file", "a", lambda _: "n") is True
        assert g.allow("list_dir", "a", lambda _: "n") is True


def test_readonly_bloqueia_escrita_e_execucao():
    g = _gate(MODE_READONLY)
    assert g.allow("run_shell", "rm -rf", lambda _: "y") is False
    assert g.allow("write_file", "x", lambda _: "y") is False


def test_auto_aceita_tudo():
    g = _gate(MODE_AUTO)
    assert g.allow("run_shell", "qualquer", lambda _: "n") is True


def test_ask_pede_aprovacao():
    g = _gate("ask")
    calls = []
    ask = lambda d: calls.append(d) or "y"
    assert g.allow("run_shell", "php -l x.php", ask) is True
    assert calls == ["php -l x.php"]


def test_ask_aceita_negacao():
    g = _gate("ask")
    assert g.allow("write_file", "x", lambda _: "n") is False


def test_ask_sempre_na_sessao():
    g = _gate("ask")
    assert g.allow("run_python", "x", lambda _: "a") is True
    assert g.allow("run_python", "x", lambda _: "n") is True  # memorizado