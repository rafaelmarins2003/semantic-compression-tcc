import json

import pytest

from src.data.llm.clients import LLMError
from src.evaluation import judge as jz
from src.transpiler.xml import transpile

DSL = 'process "P" { start -> task "Check order" -> end "Done" }'
OK = {"problems": {c: [] for c in jz.CRITERIA}, "score": 4}


def test_user_prompt_shows_rendering_not_xml():
    prompt = jz.build_user_prompt("Orders are checked {always}.", transpile(DSL))
    assert "Orders are checked {always}." in prompt
    assert 'activity "Check order"' in prompt
    assert "<" not in prompt and "Task_" not in prompt


def test_valid_verdict_is_accepted():
    assert jz.parse_verdict(json.dumps(OK))["score"] == 4


@pytest.mark.parametrize(
    "resposta",
    [
        "not json",
        json.dumps({**OK, "score": 4.5}),
        json.dumps({**OK, "score": 6}),
        json.dumps({**OK, "problems": {"tasks": []}}),
    ],
)
def test_invalid_verdict_is_rejected(resposta):
    with pytest.raises(LLMError):
        jz.parse_verdict(resposta)


def test_judge_records_prompt_hash_and_usage(monkeypatch):
    def falso(user_prompt, **kwargs):
        assert kwargs["model"] == jz.JUDGE_MODEL
        assert kwargs["json_schema"] is jz.SCHEMA
        return json.dumps(OK), {"usage": {"completion_tokens": 9}, "finish_reason": "stop"}

    monkeypatch.setattr(jz, "generate_meta", falso)
    resultado = jz.judge("Orders are checked.", transpile(DSL), api_key="k")
    assert resultado["score"] == 4
    assert resultado["usage"]["completion_tokens"] == 9
    assert len(resultado["prompt_sha"]) == 64
