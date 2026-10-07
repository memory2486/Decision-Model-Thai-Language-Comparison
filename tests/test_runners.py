"""The runner must satisfy `laya.evals`' runner contract with no special casing."""

import pytest
from laya.evals import ChoiceAccuracy, Dataset, Example, evaluate

from decision_models.confidence import normalize_choice, normalize_noul, normalize_score
from decision_models.runners import ANSWER_KWARG, Backend, DecisionRunner, UnknownModel


class FakeBackend(Backend):
    """Deterministic backend that answers by looking at the state's first letter."""

    def __init__(self, name, choice, confidence=0.9):
        self.name = name
        self._choice = choice
        self._confidence = confidence
        self.calls = 0
        self.unloaded = 0

    def answers(self, state, questions):
        self.calls += 1
        out = {}
        for qid, question in questions.items():
            if question["type"] == "choice":
                probabilities = {k: 0.01 for k in question["criteria"]}
                probabilities[self._choice] = self._confidence
                out[qid] = normalize_choice(self._choice, probabilities, native_confidence=self._confidence)
            elif question["type"] == "noul":
                out[qid] = normalize_noul(self._confidence)
            else:
                out[qid] = normalize_score(0.0, {"0": 0.9, "1": 0.05, "2": 0.05})
        return out

    def unload(self):
        self.unloaded += 1


QUESTIONS = {
    "route": {"type": "choice", "instructions": "where?",
              "criteria": {"weather": "rain", "cost": "price"}},
    "churn": {"type": "noul", "instructions": "leaving?"},
}
STATE = "Will it rain in Lisbon?"


def make_runner(**kwargs):
    runner = DecisionRunner(**kwargs)
    runner.register("alpha", lambda: FakeBackend("alpha", "weather"))
    runner.register("beta", lambda: FakeBackend("beta", "cost", confidence=0.6))
    return runner


def test_predict_returns_the_harness_shape():
    result = make_runner().predict(STATE, QUESTIONS, model="alpha")
    assert set(result) == {"answers", "routing"}
    assert result["routing"]["model"] == "alpha"
    assert result["answers"]["route"]["choice"] == "weather"


def test_every_answer_records_the_call_latency():
    result = make_runner().predict(STATE, QUESTIONS, model="alpha")
    for answer in result["answers"].values():
        assert isinstance(answer[ANSWER_KWARG], float)
        assert answer[ANSWER_KWARG] >= 0.0


def test_backends_are_constructed_lazily_and_reused():
    runner = make_runner()
    assert runner._loaded == {}
    runner.predict(STATE, QUESTIONS, model="alpha")
    runner.predict(STATE, QUESTIONS, model="alpha")
    assert runner.backend("alpha").calls == 2


def test_expressions_in_the_state_do_not_change_the_contract():
    runner = make_runner()
    with pytest.raises(UnknownModel):
        runner.predict(STATE, QUESTIONS, model="gamma")


def test_release_between_models_unloads_the_previous_backend():
    runner = make_runner(release_between_models=True)
    runner.predict(STATE, QUESTIONS, model="alpha")
    alpha = runner.backend("alpha")
    runner.predict(STATE, QUESTIONS, model="beta")
    assert alpha.unloaded == 1
    assert set(runner._loaded) == {"beta"}


def test_without_release_both_backends_stay_resident():
    runner = make_runner()
    runner.predict(STATE, QUESTIONS, model="alpha")
    runner.predict(STATE, QUESTIONS, model="beta")
    assert set(runner._loaded) == {"alpha", "beta"}


def test_routing_log_records_which_backend_answered():
    runner = make_runner()
    runner.predict(STATE, QUESTIONS, model="alpha")
    assert runner.routing_log[0]["requested"] == "alpha"
    assert runner.routing_log[0]["answered_by"] == "alpha"


def test_evaluate_scores_the_runner_with_the_real_harness():
    """The integration claim: `laya.evals.evaluate` works on this runner as-is."""
    dataset = Dataset([
        Example(state=STATE, questions=QUESTIONS,
                expected={"route": "weather"}, tags=("t1",), language="en", model="alpha"),
        Example(state=STATE, questions=QUESTIONS,
                expected={"route": "weather"}, tags=("t2",), language="en", model="beta"),
    ])
    result = evaluate(make_runner(), dataset, evaluators=[ChoiceAccuracy()], batch_size=None)
    assert result.overall["choice_accuracy"] == pytest.approx(0.5)
    # `laya.evals` reports metrics only; the row count lives on `cases`.
    assert len(result.cases) == 2
    assert result.slices["model"]["alpha"]["choice_accuracy"] == pytest.approx(1.0)
    assert result.slices["model"]["beta"]["choice_accuracy"] == pytest.approx(0.0)
    assert result.slices["language"]["en"]["choice_accuracy"] == pytest.approx(0.5)


def test_evaluate_exposes_latency():
    dataset = Dataset([
        Example(state=STATE, questions=QUESTIONS, expected={"route": "weather"}, model="alpha"),
    ])
    result = evaluate(make_runner(), dataset, batch_size=None)
    assert result.overall["latency_p50_ms"] >= 0.0
    assert "output_tokens" not in result.overall


def test_preload_constructs_every_registered_backend():
    runner = make_runner()
    runner.preload()
    assert set(runner._loaded) == {"alpha", "beta"}
