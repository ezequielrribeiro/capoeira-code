import json

from cli.instruction.loader import InstructionSet
from cli.project.premises import EMPTY_PREMISES, Premises
from cli.tui.agent import AgentOptions, AgentRun, _parse_steps
from cli.tui.session import Session


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)

    def chat_messages(self, messages, **kwargs):
        return self.responses.pop(0)


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


def _steps(steps):
    return json.dumps({"steps": steps})


def test_parse_steps_aceita_objeto_unico():
    assert _parse_steps('{"tool":"read_file","path":"x"}') == [{"tool": "read_file", "path": "x"}]


def test_parse_steps_rejeita_prosa():
    assert _parse_steps("parabéns, segue o arquivo") is None


def _yes(_d):
    return "y"


def test_run_executa_write_file_e_done(tmp_path):
    alvo = tmp_path / "app" / "sair.php"
    agent = _agent(
        tmp_path,
        [
            _steps(
                [
                    {"tool": "write_file", "path": "sair.php", "action": "create_file", "code_content": "x"},
                    {"tool": "done", "message": "Criei o arquivo."},
                ]
            )
        ],
    )
    result = agent.run("crie um arquivo", ask_user=lambda q: "?", ask_permission=_yes)
    assert result["done"] is True
    assert result["message"] == "Criei o arquivo."
    assert alvo.exists()
    assert len(agent.session.load_messages()) > 0


def test_run_ask_user_insere_resposta(tmp_path):
    agent = _agent(tmp_path, [_steps([{"tool": "ask_user", "question": "Nome?"}, {"tool": "done", "message": "ok"}])])
    result = agent.run("faça", ask_user=lambda q: "cadastro", ask_permission=_yes)
    assert result["done"] is True
    contents = [m["content"] for m in agent.session.load_messages()]
    assert any("cadastro" in c for c in contents)


def test_run_readonly_bloqueia_write(tmp_path):
    alvo = tmp_path / "app" / "bloqueado.php"
    agent = _agent(
        tmp_path,
        [
            _steps(
                [
                    {"tool": "write_file", "path": "bloqueado.php", "action": "create_file", "code_content": "y"},
                    {"tool": "done", "message": "fim"},
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
                    {"tool": "write_file", "path": "negado.php", "action": "create_file", "code_content": "y"},
                    {"tool": "done", "message": "fim"},
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
    agent = _agent(
        tmp_path,
        [_steps([{"tool": "read_file", "path": "a.txt"}])] * 3,
        max_turns=2,
    )
    result = agent.run("leia", ask_user=lambda q: "?", ask_permission=_yes)
    assert result["done"] is False
    assert "Limite de 2 turnos" in result["message"]


def test_run_formato_invalido_reformatado(tmp_path):
    agent = _agent(tmp_path, ["texto solto", _steps([{"tool": "done", "message": "corrigido"}])])
    result = agent.run("tarefa", ask_user=lambda q: "?", ask_permission=_yes)
    assert result["done"] is True
    assert result["message"] == "corrigido"