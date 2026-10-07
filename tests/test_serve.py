"""The dispatcher must pick by language and never blur the two confidence scales."""

import pytest

from decision_models.confidence import normalize_choice, normalize_noul
from decision_models.runners import Backend, DecisionRunner
from decision_models.serve import (
    DEFAULT_POLICY,
    choose_model,
    create_app,
    decide,
    detect_script,
    parse_policy,
)

QUESTIONS = {
    "department": {"type": "choice", "instructions": "which?",
                   "criteria": {"billing": "money", "technical": "bugs"}},
    "refund": {"type": "noul", "instructions": "refund?"},
}


class FakeBackend(Backend):
    def __init__(self, name, choice):
        self.name = name
        self._choice = choice

    def answers(self, state, questions):
        probabilities = {k: 0.02 for k in questions["department"]["criteria"]}
        probabilities[self._choice] = 0.96
        return {
            "department": normalize_choice(self._choice, probabilities, native_confidence=0.8),
            "refund": normalize_noul(0.97),
        }


def make_runner():
    runner = DecisionRunner()
    runner.register("laya-en", lambda: FakeBackend("laya-en", "technical"))
    runner.register("openthai", lambda: FakeBackend("openthai", "billing"))
    return runner


def test_policy_parses_pairs_and_falls_back_to_the_default():
    assert parse_policy("lang:th=openthai,default=laya-en") == {"lang:th": "openthai", "default": "laya-en"}
    assert parse_policy("") == DEFAULT_POLICY


def test_policy_rejects_malformed_entries():
    with pytest.raises(ValueError):
        parse_policy("openthai")


def test_thai_text_is_detected_as_thai_script():
    assert detect_script("โดนหักเงินซ้ำสองครั้ง ขอเงินคืนด่วน") == "thai"


def test_english_text_is_detected_as_latin():
    assert detect_script("I was charged twice") == "latin"


def test_choice_follows_the_script():
    policy = {"lang:th": "openthai", "default": "laya-en"}
    assert choose_model("โดนหักเงินซ้ำ", policy) == "openthai"
    assert choose_model("I was charged twice", policy) == "laya-en"


def test_an_explicit_model_overrides_the_policy():
    policy = {"lang:th": "openthai", "default": "laya-en"}
    assert choose_model("โดนหักเงินซ้ำ", policy, requested="laya-en") == "laya-en"
    assert choose_model("hello", policy, requested="auto") == "laya-en"


def test_state_with_no_letters_uses_the_default():
    policy = {"lang:th": "openthai", "default": "laya-en"}
    assert choose_model("12345", policy) == "laya-en"


def test_the_default_policy_does_not_branch_on_language():
    """The measurement said language is not the discriminator, so the default is one backend."""
    assert DEFAULT_POLICY == {"default": "openthai"}


def test_decide_returns_both_confidence_notations():
    # Policy pinned so the test reads one backend's answer regardless of the default.
    result = decide(make_runner(), "I was charged twice", QUESTIONS, policy={"default": "laya-en"})
    answer = result["answers"]["department"]
    assert answer["choice"] == "technical"
    # The thresholdable quantity, identical in meaning across models.
    assert answer["answer_confidence"] == pytest.approx(0.96)
    # The entropy quantity, which is what both APIs call `confidence`.
    assert answer["confidence"] < answer["answer_confidence"]
    assert answer["native_confidence"] == pytest.approx(0.8)


def test_decide_routes_thai_to_the_thai_first_model():
    result = decide(make_runner(), "โดนหักเงินซ้ำสองครั้ง", QUESTIONS)
    assert result["requested"] == "openthai"
    assert result["answers"]["department"]["choice"] == "billing"
    assert result["script"] == "thai"


def test_decide_reports_zero_output_tokens():
    """Neither model generates text, so there is nothing to parse."""
    result = decide(make_runner(), "hello", QUESTIONS, policy={"default": "openthai"})
    assert result["usage"]["output_tokens"] == 0
    assert result["usage"]["latency_ms"] >= 0.0


def test_decide_never_invents_a_confidence():
    class Silent(Backend):
        name = "silent"

        def answers(self, state, questions):
            return {"department": {"type": "choice", "choice": "billing", "probabilities": None},
                    "refund": {"type": "noul", "noul": 0.5}}

    runner = DecisionRunner()
    runner.register("quiet", lambda: Silent())
    result = decide(runner, "hello", QUESTIONS, model="quiet")
    answer = result["answers"]["department"]
    assert "confidence" not in answer
    assert "answer_confidence" not in answer


def test_http_app_answers_a_request():
    starlette_testclient = pytest.importorskip("fastapi.testclient")
    client = starlette_testclient.TestClient(create_app(runner=make_runner(),
                                                       policy={"lang:th": "openthai", "default": "laya-en"}))
    response = client.post("/v1/systemone", json={"state": "I was charged twice", "questions": QUESTIONS})
    assert response.status_code == 200
    payload = response.json()
    assert payload["answers"]["department"]["choice"] == "technical"


def test_http_app_healthz_reports_the_policy():
    starlette_testclient = pytest.importorskip("fastapi.testclient")
    client = starlette_testclient.TestClient(create_app(runner=make_runner(),
                                                       policy={"default": "laya-en"}))
    assert client.get("/healthz").json()["policy"] == {"default": "laya-en"}


def test_http_app_rejects_a_body_without_questions():
    starlette_testclient = pytest.importorskip("fastapi.testclient")
    client = starlette_testclient.TestClient(create_app(runner=make_runner()))
    assert client.post("/v1/systemone", json={"state": "hello"}).status_code == 422


def test_http_app_rejects_an_unknown_model():
    starlette_testclient = pytest.importorskip("fastapi.testclient")
    client = starlette_testclient.TestClient(create_app(runner=make_runner()))
    response = client.post("/v1/systemone",
                           json={"state": "hello", "questions": QUESTIONS, "model": "nope"})
    assert response.status_code == 422
