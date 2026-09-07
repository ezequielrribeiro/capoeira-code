from cli.prompts import (
    RESPONSE_SCHEMA,
    build_explain_prompt,
    build_generate_prompt,
    build_refactor_prompt,
    build_retry_prompt,
)


def test_build_refactor_prompt_inclui_schema_alvo_e_acao():
    prompt = build_refactor_prompt("src/x.php", "soma", "adicione validação", "<?php esquema")
    assert "soma" in prompt
    assert "src/x.php" in prompt
    assert 'action "replace_symbol"' in prompt
    assert '"replace_symbol"' in prompt
    assert '"create_file"' in prompt or "replace_symbol" in prompt
    assert '"code_content"' in prompt
    assert "ESQUELETO DO CÓDIGO DO PROJETO" in prompt
    assert "<?php esquema" in prompt


def test_build_retry_prompt_embute_erro_e_original():
    prompt = build_retry_prompt("PROMPT_ORIGINAL", "JSON inválido")
    assert "JSON inválido" in prompt
    assert "PROMPT_ORIGINAL" in prompt


def test_build_generate_prompt_create_file():
    prompt = build_generate_prompt("tests/test_calc.py", "gere testes", None, None)
    assert 'action "create_file"' in prompt
    assert '"tests/test_calc.py"' in prompt
    assert 'target_symbol "' not in prompt


def test_build_generate_prompt_replace_symbol_com_contexto():
    prompt = build_generate_prompt("src/x.py", "refatore", "load", "CONTEXTO_GERAL")
    assert 'action "replace_symbol"' in prompt
    assert 'target_symbol "load"' in prompt
    assert "CONTEXTO_GERAL" in prompt


def test_build_explain_prompt_contem_arquivo_e_esqueleto():
    prompt = build_explain_prompt("src/a.php", "soma", "<?php esqueleto")
    assert "src/a.php" in prompt
    assert "<?php esqueleto" in prompt
    assert "soma" in prompt


def test_response_schema_contrato():
    assert set(RESPONSE_SCHEMA["required"]) == {"file_path", "action", "code_content"}
    actions = RESPONSE_SCHEMA["properties"]["action"]["enum"]
    assert actions == ["replace_symbol", "create_file", "patch_diff"]