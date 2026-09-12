import base64

from cli.instruction.loader import InstructionSet
from cli.llm_client import ChatReply
from cli.project.premises import EMPTY_PREMISES
from cli.tui.agent import AgentOptions, AgentRun, _decode_b64, _parse_tool_call_lines, _parse_value
from cli.tui.session import Session


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def chat_messages(self, messages, **kwargs):
        self.requests.append({"messages": messages, **kwargs})
        raw = self.responses.pop(0)
        if isinstance(raw, ChatReply):
            return raw
        return ChatReply(content=raw)


def _agent(tmp_path, responses, mode="auto", max_turns=5, cwd=None):
    proj = tmp_path / "app"
    proj.mkdir(exist_ok=True)
    instruction = InstructionSet(specs={}, skills={}, prompts={})
    options = AgentOptions(
        premises=EMPTY_PREMISES,
        instruction_set=instruction,
        artifacts_summary="ARTEFATOS",
        cwd=str(cwd or proj),
        max_turns=max_turns,
        mode=mode,
    )
    session = Session(config_dir=tmp_path, project_path=str(proj))
    session.ensure()
    return AgentRun(session, options, FakeClient(responses))


def _tool_call_line(name, args=None):
    line = f"[TOOL_CALL] {name}"
    if args:
        segs = [line]
        for key, value in args.items():
            if isinstance(value, str) and any(ch.isspace() for ch in value):
                value = f"'{value}'"
            segs.append(f"{key}={value}")
        line = " | ".join(segs)
    return line


def _b64(text: str) -> str:
    """Codifica conteúdo em base64 (como o modelo deve enviar nos [TOOL_CALL])."""
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _steps(lines):
    return "\n".join(lines)


def test_parse_tool_call_lines_aceita_contrato_do_host():
    steps = _parse_tool_call_lines(
        "Vou inspecionar o projeto.\n"
        + _tool_call_line("read_file", {"path": "app/views/vagas.php", "lines": [1, 120]})
        + "\n"
        + _tool_call_line("done", {"message": "Leitura concluída"})
    )
    assert steps == [
        {"tool": "read_file", "path": "app/views/vagas.php", "lines": [1, 120]},
        {"tool": "done", "message": "Leitura concluída"},
    ]


def test_parse_tool_call_lines_sem_argumentos():
    assert _parse_tool_call_lines("[TOOL_CALL] list_dir") == [{"tool": "list_dir"}]


def test_parse_tool_call_lines_valores_aspas_numeros_bool_lista():
    steps = _parse_tool_call_lines(
        _tool_call_line("write_file", {"path": "a b.php", "action": "create_file", "code_content": "<?php echo 1;", "enabled": True})
    )
    assert steps == [
        {
            "tool": "write_file",
            "path": "a b.php",
            "action": "create_file",
            "code_content": "<?php echo 1;",
            "enabled": True,
        }
    ]


def test_parse_tool_call_lines_linhas_invalidas_ignoradas():
    steps = _parse_tool_call_lines(
        "texto ao redor\n"
        "[TOOL_CALL] nome_mal | bad\n"
        + _tool_call_line("read_file", {"path": "x"})
    )
    assert steps == [{"tool": "read_file", "path": "x"}]


def test_parse_tool_call_lines_pipe_dentro_de_aspas():
    """Pipe dentro de valor com aspas é literal (não quebra a chamada)."""
    steps = _parse_tool_call_lines(
        "[TOOL_CALL] run_shell | cmd='php -l app | tail -5' | cwd='app && ls | wc -l'"
    )
    assert steps == [
        {"tool": "run_shell", "cmd": "php -l app | tail -5", "cwd": "app && ls | wc -l"}
    ]
    steps2 = _parse_tool_call_lines("[TOOL_CALL] done | message='A | B | C'")
    assert steps2 == [{"tool": "done", "message": "A | B | C"}]


def test_parse_tool_call_lines_espaco_ao_redor_do_igual():
    steps = _parse_tool_call_lines(
        "[TOOL_CALL] read_file | path = app/x.php | lines = [1, 120]"
    )
    assert steps == [{"tool": "read_file", "path": "app/x.php", "lines": [1, 120]}]


def test_run_run_shell_com_pipe_no_comando_executa(tmp_path):
    """Chamada run_shell com pipe dentro de aspas é parseada e executada
    (não vira 'prosa final' — sem escrita/perda do passo)."""
    agent = _agent(
        tmp_path,
        [
            _steps(
                [
                    "[TOOL_CALL] run_shell | cmd='echo capoeira | findstr capoeira'",
                    _tool_call_line("done", {"message": "fim"}),
                ]
            )
        ],
    )
    result = agent.run("rode o comando", ask_user=lambda q: "?", ask_permission=_yes)
    assert result["done"] is True
    tools = [m for m in agent.session.load_messages() if m["role"] == "tool"]
    assert any("run_shell" in m["content"] for m in tools)


def test_parse_tool_call_lines_code_content_base64_multilinha():
    """code_content em base64 (uma linha, sem escapes/aspas) sobrevive ao parse
    e é decodificado para o conteúdo real com quebras de linha."""
    codigo = "<?php\n$nome = \"Maria\";\necho $nome;\n?>"
    line = (
        "[TOOL_CALL] write_file | path='nova.php' | action='create_file' | "
        f"code_content={_b64(codigo)}"
    )
    steps = _parse_tool_call_lines(line)
    assert steps == [
        {
            "tool": "write_file",
            "path": "nova.php",
            "action": "create_file",
            "code_content": _b64(codigo),
        }
    ]
    assert _decode_b64(steps[0]["code_content"]) == codigo


def test_parse_value_unescape_sequencias_conhecidas_e_literal():
    assert _parse_value(r"'a\nb'") == "a\nb"
    assert _parse_value(r"'a\\nb'") == "a\\nb"
    assert _parse_value(r"'it\'s'") == "it's"
    assert _parse_value(r"'a\\b'") == "a\\b"


def test_parse_tool_call_lines_valor_truncado_sinaliza():
    """Valor com aspas abertas mas não fechadas (conteúdo cortado no meio da
    chamada) é sinalizado como `_truncated` — não deve ser gravado como arquivo."""
    steps = _parse_tool_call_lines(
        "[TOOL_CALL] write_file | path='trunc.php' | action='create_file' | code_content='<?php"
    )
    assert steps and steps[0]["_truncated"] is True


def _yes(_d):
    return "y"


def test_run_executa_write_file_e_done(tmp_path):
    alvo = tmp_path / "app" / "sair.php"
    agent = _agent(
        tmp_path,
        [
            _steps(
                [
                    _tool_call_line("write_file", {"path": "sair.php", "action": "create_file", "code_content": _b64("x")}),
                    _tool_call_line("done", {"message": "Criei o arquivo."}),
                ]
            )
        ],
    )
    result = agent.run("crie um arquivo", ask_user=lambda q: "?", ask_permission=_yes)
    assert result["done"] is True
    assert result["message"] == "Criei o arquivo."
    assert alvo.exists()
    assert len(agent.session.load_messages()) > 0


def test_tool_call_retorna_no_formato_do_host(tmp_path):
    """Linhas [TOOL_CALL] retornam ao LLM como role:"tool" com tool_call_id — o
    transcript do CapoeiraHost renderiza [TOOL_RESULT] (id) ..."""
    alvo = tmp_path / "app" / "host.php"
    agent = _agent(
        tmp_path,
        [
            _steps(
                [
                    _tool_call_line("write_file", {"path": "host.php", "action": "create_file", "code_content": _b64("ok")}),
                    _tool_call_line("done", {"message": "Criado."}),
                ]
            )
        ],
    )
    result = agent.run("crie", ask_user=lambda q: "?", ask_permission=_yes)
    assert result["done"] is True
    assert alvo.exists()
    records = [m for m in agent.session.load_messages() if m["role"] == "tool"]
    assert records and records[0]["tool_name"] == "write_file"
    assert records[0]["tool_call_id"] == "call_0"


def test_run_ask_user_insere_resposta(tmp_path):
    agent = _agent(
        tmp_path,
        [
            _steps(
                [
                    _tool_call_line("ask_user", {"question": "Nome?"}),
                    _tool_call_line("done", {"message": "ok"}),
                ]
            )
        ],
    )
    result = agent.run("faça", ask_user=lambda q: "cadastro", ask_permission=_yes)
    assert result["done"] is True
    contents = [m["content"] for m in agent.session.load_messages()]
    assert any("cadastro" in c for c in contents)


def test_run_write_file_multilinha_base64_escreve_fonte_igual(tmp_path):
    """code_content em base64 grava o arquivo com o conteúdo multilinha íntegro."""
    alvo = tmp_path / "app" / "aula.php"
    codigo = "<?php\n$msg = \"oi\";\necho $msg;\n?>"
    line = (
        "[TOOL_CALL] write_file | path='aula.php' | action='create_file' | "
        f"code_content={_b64(codigo)}"
    )
    agent = _agent(
        tmp_path,
        [
            _steps(
                [
                    line,
                    _tool_call_line("done", {"message": "Criei o arquivo."}),
                ]
            )
        ],
    )
    result = agent.run("crie o arquivo", ask_user=lambda q: "?", ask_permission=_yes)
    assert result["done"] is True
    assert alvo.exists()
    assert alvo.read_text(encoding="utf-8") == codigo


def test_run_write_file_truncado_nao_escreve(tmp_path):
    """code_content cortado (aspas não fechadas) não grava arquivo corrupto; vira
    erro retornado ao modelo para reenvio em UMA linha."""
    alvo = tmp_path / "app" / "trunc.php"
    agent = _agent(
        tmp_path,
        [
            "[TOOL_CALL] write_file | path='trunc.php' | action='create_file' | code_content='<?php",
            _tool_call_line("done", {"message": "fim"}),
        ],
    )
    result = agent.run("crie o arquivo", ask_user=lambda q: "?", ask_permission=_yes)
    assert result["done"] is True
    assert not alvo.exists()
    contents = " ".join(m.get("content", "") for m in agent.session.load_messages())
    assert "truncado" in contents


def test_run_write_file_multilinha_quebrado_pelo_host_nao_escreve(tmp_path):
    """Quando o conteúdo chega quebrado em várias linhas físicas (como o host repassa
    ao cortar o `[TOOL_CALL]` em `code_content='<?php`), o agente NÃO grava arquivo
    corrupto — devolve erro e o turno segue para o próximo pedido do modelo."""
    alvo = tmp_path / "app" / "quebrado.php"
    codigo = "<?php\n$mensagem = \"ok\";\n?>"
    agent = _agent(
        tmp_path,
        [
            _steps(
                [
                    _tool_call_line("write_file", {"path": "quebrado.php", "action": "create_file", "code_content": codigo}),
                    _tool_call_line("done", {"message": "fim"}),
                ]
            )
        ],
    )
    result = agent.run("crie", ask_user=lambda q: "?", ask_permission=_yes)
    assert result["done"] is True
    assert not alvo.exists()
    contents = " ".join(m.get("content", "") for m in agent.session.load_messages())
    assert "truncado" in contents


def test_decode_b64():
    codigo = "<?php\n$msg = \"oi\";\necho $msg;\n?>"
    assert _decode_b64(base64.b64encode(codigo.encode()).decode()) == codigo
    assert _decode_b64("PD9waHAK") == "<?php\n"
    assert _decode_b64("abc") is None  # tamanho não múltiplo de 4
    assert _decode_b64("isso não é b64") is None  # caracteres fora do alfabeto
    assert _decode_b64("") is None
    assert _decode_b64("isiA") is None  # decodifica mas não é UTF-8


def test_run_write_file_sem_base64_nao_escreve(tmp_path):
    """code_content que não é base64 (contrato estrito) não grava arquivo; vira erro."""
    alvo = tmp_path / "app" / "raw.php"
    agent = _agent(
        tmp_path,
        [
            _steps(
                [
                    "[TOOL_CALL] write_file | path='raw.php' | action='create_file' | code_content=isso-nao-e-base64",
                    _tool_call_line("done", {"message": "fim"}),
                ]
            )
        ],
    )
    result = agent.run("crie", ask_user=lambda q: "?", ask_permission=_yes)
    assert result["done"] is True
    assert not alvo.exists()
    contents = " ".join(m.get("content", "") for m in agent.session.load_messages())
    assert "base64" in contents


def test_run_write_file_conteudo_numerico_via_base64(tmp_path):
    """Conteúdo numérico codificado em base64 não vira int no parse e é gravado íntegro."""
    alvo = tmp_path / "app" / "num.php"
    agent = _agent(
        tmp_path,
        [
            _steps(
                [
                    _tool_call_line("write_file", {"path": "num.php", "action": "create_file", "code_content": _b64("123")}),
                    _tool_call_line("done", {"message": "fim"}),
                ]
            )
        ],
    )
    result = agent.run("crie", ask_user=lambda q: "?", ask_permission=_yes)
    assert result["done"] is True
    assert alvo.exists()
    assert alvo.read_text(encoding="utf-8") == "123"


def test_run_run_python_base64_executa(tmp_path):
    """run_python com código em base64 executa localmente."""
    codigo = 'import os\nprint(",".join(sorted(os.listdir("."))[:3]))'
    agent = _agent(
        tmp_path,
        [
            _steps(
                [
                    _tool_call_line("run_python", {"code": _b64(codigo)}),
                    _tool_call_line("done", {"message": "fim"}),
                ]
            )
        ],
    )
    result = agent.run("liste", ask_user=lambda q: "?", ask_permission=_yes)
    assert result["done"] is True
    tools = [m for m in agent.session.load_messages() if m["role"] == "tool"]
    assert any("run_python" in m["content"] for m in tools)


def test_run_run_python_sem_base64_vira_erro(tmp_path):
    """run_python com código cru (não base64) vira erro ao modelo (contrato estrito)."""
    agent = _agent(
        tmp_path,
        [
            _steps(
                [
                    "[TOOL_CALL] run_python | code=print(1)",
                    _tool_call_line("done", {"message": "fim"}),
                ]
            )
        ],
    )
    result = agent.run("rode", ask_user=lambda q: "?", ask_permission=_yes)
    assert result["done"] is True
    contents = " ".join(m.get("content", "") for m in agent.session.load_messages())
    assert "base64" in contents


def test_run_readonly_bloqueia_write(tmp_path):
    alvo = tmp_path / "app" / "bloqueado.php"
    agent = _agent(
        tmp_path,
        [
            _steps(
                [
                    _tool_call_line("write_file", {"path": "bloqueado.php", "action": "create_file", "code_content": _b64("y")}),
                    _tool_call_line("done", {"message": "fim"}),
                ]
            )
        ],
        mode="readonly",
    )
    result = agent.run("escreva", ask_user=lambda q: "?", ask_permission=_yes)
    assert not alvo.exists()
    contents = [m["content"] for m in agent.session.load_messages()]
    assert any("NÃO AUTORIZADA" in c for c in contents)


def test_run_ask_negacao_nao_executa(tmp_path):
    alvo = tmp_path / "app" / "negado.php"
    agent = _agent(
        tmp_path,
        [
            _steps(
                [
                    _tool_call_line("write_file", {"path": "negado.php", "action": "create_file", "code_content": _b64("y")}),
                    _tool_call_line("done", {"message": "fim"}),
                ]
            )
        ],
        mode="ask",
    )
    result = agent.run("escreva", ask_user=lambda q: "?", ask_permission=lambda d: "n")
    assert not alvo.exists()
    assert result["done"] is True


def test_run_max_turns_sem_done(tmp_path):
    proj = tmp_path / "app"
    proj.mkdir(exist_ok=True)
    (proj / "a.txt").write_text("ok", encoding="utf-8")
    agente = _agent(
        tmp_path,
        [_tool_call_line("read_file", {"path": "a.txt"})] * 3,
        max_turns=2,
    )
    result = agente.run("leia", ask_user=lambda q: "?", ask_permission=_yes)
    assert result["done"] is False
    assert "Limite de 2 turnos" in result["message"]


def test_prosa_vira_done(tmp_path):
    agent = _agent(tmp_path, [ChatReply(content="tudo pronto")])
    result = agent.run("conclua", ask_user=lambda q: "?", ask_permission=_yes)
    assert result["done"] is True
    assert result["message"] == "tudo pronto"


def test_unwrap_text_legado(tmp_path):
    agent = _agent(tmp_path, [ChatReply(content='{"text": "resumo legado"}')])
    result = agent.run("conclua", ask_user=lambda q: "?", ask_permission=_yes)
    assert result["done"] is True
    assert result["message"] == "resumo legado"


def test_multi_tool_calls_um_proximo_request(tmp_path):
    alvo1 = tmp_path / "app" / "a.php"
    alvo2 = tmp_path / "app" / "b.php"
    agent = _agent(
        tmp_path,
        [
            _steps(
                [
                    _tool_call_line("write_file", {"path": "a.php", "action": "create_file", "code_content": _b64("a")}),
                    _tool_call_line("write_file", {"path": "b.php", "action": "create_file", "code_content": _b64("b")}),
                ]
            ),
            _tool_call_line("done", {"message": "fim"}),
        ],
    )
    result = agent.run("crie a e b", ask_user=lambda q: "?", ask_permission=_yes)
    assert result["done"] is True
    assert alvo1.exists() and alvo2.exists()

    client = agent.client
    assert len(client.requests) == 2
    second = client.requests[1]["messages"]

    assistant = [m for m in second if m.get("role") == "assistant"]
    assert len(assistant) == 1
    assert "path=a.php" in assistant[0]["content"]
    assert "path=b.php" in assistant[0]["content"]
    assert "tool_calls" not in assistant[0]

    tool_msgs = [m for m in second if m.get("role") == "tool"]
    assert len(tool_msgs) == 2
    assert [m["tool_call_id"] for m in tool_msgs] == ["call_0", "call_1"]
    assert [m["tool_name"] for m in tool_msgs] == ["write_file", "write_file"]


def test_tool_call_sem_argumentos_registra_linha(tmp_path):
    """Tool call sem argumentos é registrada no histórico como a própria linha
    `[TOOL_CALL] nome` (contrato textual de linha única do host)."""
    agent = _agent(
        tmp_path,
        [
            "[TOOL_CALL] list_dir",
            _tool_call_line("done", {"message": "fim"}),
        ],
    )
    result = agent.run("liste o projeto", ask_user=lambda q: "?", ask_permission=_yes)
    assert result["done"] is True
    client = agent.client
    assert len(client.requests) == 2
    assistant = [m for m in client.requests[1]["messages"] if m.get("role") == "assistant"]
    assert len(assistant) == 1
    assert assistant[0]["content"] == "[TOOL_CALL] list_dir"


def test_reenvia_historico_completo_no_proximo_request(tmp_path):
    """Stateless: o histórico completo (sistema + turnos anteriores) é reenviado
    a cada requisição — o round-trip de tool calling vai embutido na mensagem."""
    alvo = tmp_path / "app" / "delta.php"
    agent = _agent(
        tmp_path,
        [
            _tool_call_line("write_file", {"path": "delta.php", "action": "create_file", "code_content": _b64("x")}),
            _tool_call_line("done", {"message": "ok delta"}),
        ],
    )
    result = agent.run("crie delta", ask_user=lambda q: "?", ask_permission=_yes)
    assert result["done"] is True
    assert alvo.exists()
    client = agent.client
    assert len(client.requests) == 2

    first = client.requests[0]["messages"]
    roles = [m["role"] for m in first]
    assert roles == ["system", "user"]
    assert "crie delta" in first[1]["content"]

    second = client.requests[1]["messages"]
    assert second[0]["role"] == "system"
    contents = " ".join(m.get("content", "") for m in second)
    assert "crie delta" in contents
    assert "FERRAMENTA write_file" in contents


def test_sistema_reenviado_em_toda_requisicao(tmp_path):
    """Stateless: o sistema (perfil/contrato) é enviado em toda requisição,
    junto com o histórico completo dos turnos anteriores."""
    agent = _agent(
        tmp_path,
        [_tool_call_line("done", {"message": "fim"}), _tool_call_line("done", {"message": "fim 2"})],
    )
    agent.run("tarefa", ask_user=lambda q: "?", ask_permission=_yes)
    agent.run("outra", ask_user=lambda q: "?", ask_permission=_yes)
    first = agent.client.requests[0]["messages"]
    second = agent.client.requests[1]["messages"]
    assert [m["role"] for m in first] == ["system", "user"]
    assert second[0]["role"] == "system"
    assert any(m["role"] == "assistant" for m in second)
    assert "tarefa" in " ".join(m.get("content", "") for m in second)