"""One ``POST /v1/systemone`` in front of both models.

Both engines already implement this route -- ``laya-serve`` for Laya and
``openthai_systemone.server`` for OpenThai -- so this module exists for the one
thing neither can do alone: pick between them, and normalise the answer so a
client cannot tell which one replied unless it asks.

Two properties are deliberate:

* **The reply carries both confidence notions.** Every answer includes
  ``answer_confidence`` (max-p, computed here identically for both models) and
  ``confidence`` (entropy), plus ``native_confidence``/``native_answer_confidence``
  and ``abstain`` where the model provides them. A client that gates on
  ``answer_confidence`` gets a comparable threshold; a client that gates on
  ``confidence`` is not silently given a different quantity by a model swap.
* **Language selects the backend, and selection is pure Python.** Script
  detection costs microseconds and needs no weights, so routing a request never
  loads the model that will not answer it.

The policy is data, not code, so it can be set from the measured results:
``DECISION_ROUTER_POLICY`` accepts ``lang:th=openthai,lang:en=laya-en`` plus a
``default=`` entry.
"""

# NOTE: deliberately no `from __future__ import annotations` in this module.
# FastAPI resolves a handler's parameter annotations against its *module*
# globals, so a postponed `request: Request` string cannot see the `Request`
# imported inside `create_app`, and FastAPI then treats it as a query
# parameter -- every POST answers 422 with `loc: ["query","request"]`. Removing
# the future import makes the annotation resolve at definition time, inside the
# closure where `Request` is bound.
import os
import time
from typing import Any, Dict, Mapping, Optional

from .runners import DecisionRunner, UnknownModel
from .runners.laya_backend import LayaBackend  # noqa: F401 - re-exported for callers

#: Fallback policy, used when ``DECISION_ROUTER_POLICY`` says nothing.
#:
#: The plan assumed language would be the discriminator -- a Thai-first model
#: for Thai, an English model for English. The measurement refused that: on the
#: focused set OpenThai-SystemOne leads in *both* languages (en 0.814 vs 0.767,
#: th 0.723 vs 0.596) and on calibration (AURC 0.060 vs 0.142-0.299). Language
#: is therefore not the switch, so the default is a single backend and the
#: ``lang:``/``script:`` keys stay supported for callers who want to branch
#: (they are still the right shape for a Thai-only deployment).
#:
#: What the measurement does trade is time: OpenThai was the slowest backend
#: (p50 573 ms) and Laya's multilingual checkpoint the fastest (p50 107 ms), so
#: a latency-bound caller should set ``DECISION_ROUTER_POLICY=default=laya-ml``
#: and accept ~4 points of accuracy for roughly 5x the speed.
DEFAULT_POLICY: Dict[str, str] = {"default": "openthai"}

#: Documented alternative for latency-bound callers (see above).
LATENCY_POLICY: Dict[str, str] = {"default": "laya-ml"}

#: Where a request with no letters at all goes.
SCRIPT_FALLBACK = "openthai"


def parse_policy(spec: Optional[str] = None) -> Dict[str, str]:
    """Parse ``key=value,key=value`` into a policy dict."""
    text = spec if spec is not None else os.environ.get("DECISION_ROUTER_POLICY", "")
    if not text.strip():
        return dict(DEFAULT_POLICY)
    policy: Dict[str, str] = {}
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "=" not in chunk:
            raise ValueError("policy entry %r is not key=value" % chunk)
        key, value = chunk.split("=", 1)
        policy[key.strip()] = value.strip()
    return policy or dict(DEFAULT_POLICY)


def detect_script(state: Any) -> str:
    """Dominant script of the state, via Laya's pure-Python detector."""
    try:
        from laya import detect_script as _detect

        text = state if isinstance(state, str) else _stringify(state)
        return _detect(text) or "unknown"
    except Exception:  # noqa: BLE001 - never fail a request over detection
        return "unknown"


def _stringify(state: Any) -> str:
    if isinstance(state, Mapping):
        return " ".join(_stringify(v) for v in state.values())
    if isinstance(state, (list, tuple)):
        return " ".join(_stringify(v) for v in state)
    return str(state)


#: Script -> language token used as a policy key.
SCRIPT_TO_LANG = {"thai": "th", "lao": "th", "latin": "en"}


def choose_model(state: Any, policy: Mapping[str, str], requested: Optional[str] = None) -> str:
    """Which backend should answer this request."""
    if requested and requested not in ("auto", ""):
        return requested
    script = detect_script(state)
    lang = SCRIPT_TO_LANG.get(script)
    if lang and ("lang:" + lang) in policy:
        return policy["lang:" + lang]
    if "script:" + script in policy:
        return policy["script:" + script]
    return policy.get("default", SCRIPT_FALLBACK)


def decide(
    runner: DecisionRunner,
    state: Any,
    questions: Mapping[str, Any],
    model: Optional[str] = None,
    policy: Optional[Mapping[str, str]] = None,
) -> Dict[str, Any]:
    """Answer one request, whichever backend the policy selects."""
    policy = policy or parse_policy()
    chosen = choose_model(state, policy, model)
    started = time.perf_counter()
    result = runner.predict(state, questions, model=chosen)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    script = detect_script(state)
    answers = result.get("answers") or {}
    return {
        "model": result.get("routing", {}).get("model", chosen),
        "requested": chosen,
        "script": script,
        "routing": result.get("routing", {}),
        "answers": {qid: _wire_answer(answer) for qid, answer in answers.items()},
        "usage": {
            "input_tokens": len(_stringify(state).split()),
            # Documented 0 for both engines: neither generates text, so there is
            # nothing to parse and nothing to hallucinate.
            "output_tokens": 0,
            "questions": len(questions),
            "latency_ms": round(elapsed_ms, 2),
        },
    }


def _wire_answer(answer: Mapping[str, Any]) -> Dict[str, Any]:
    """The union wire shape: both models' fields, no invented values."""
    out: Dict[str, Any] = {"type": answer.get("type")}
    for key in ("choice", "score", "noul", "legend", "probabilities"):
        if key in answer and answer[key] is not None:
            out[key] = answer[key]
    for key in ("answer_confidence", "confidence", "native_confidence",
                "native_answer_confidence", "abstain"):
        if answer.get(key) is not None:
            out[key] = answer[key]
    out["_latency_ms"] = answer.get("_latency_ms")
    return out


def create_app(runner: Optional[DecisionRunner] = None, policy: Optional[Mapping[str, str]] = None):
    """Build the FastAPI app exposing ``POST /v1/systemone``."""
    from fastapi import FastAPI, HTTPException, Request

    app = FastAPI(title="Decision-model dispatcher (Laya + OpenThai-SystemOne)")
    active_policy = dict(policy or parse_policy())
    active_runner = runner or DecisionRunner.with_defaults()

    @app.get("/healthz")
    def healthz() -> Dict[str, Any]:
        return {
            "ok": True,
            "policy": active_policy,
            "models": active_runner.known_models(),
            "ready": sorted(active_runner._loaded),
        }

    @app.post("/v1/systemone")
    async def systemone(request: Request) -> Dict[str, Any]:
        try:
            payload = await request.json()
        except Exception as exc:  # noqa: BLE001 - malformed JSON is a 422
            raise HTTPException(status_code=422, detail="body is not valid JSON: %s" % exc) from exc
        state = payload.get("state")
        questions = payload.get("questions")
        if state is None or not isinstance(questions, Mapping) or not questions:
            raise HTTPException(status_code=422, detail="body needs 'state' and non-empty 'questions'")
        try:
            return decide(active_runner, state, questions,
                          model=payload.get("model"), policy=active_policy)
        except UnknownModel as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return app


def main() -> None:
    import uvicorn

    host = os.environ.get("DECISION_HOST", "127.0.0.1")
    port = int(os.environ.get("DECISION_PORT", "8077"))
    uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    main()
