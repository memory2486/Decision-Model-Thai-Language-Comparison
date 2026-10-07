"""OpenThai-SystemOne, behind the same contract.

OpenThai-SystemOne is a Thai + English System One decision model (0.8B, Apache
2.0, iApp Technology with OpenThai). Its served API is ``POST /v1/systemone``
with ``{state, questions}`` and the same ``choice | score | noul`` primitives
Laya uses, so nothing about the *interface* needs adapting -- only the answer
shape does, and only in one respect: OpenThai reports ``confidence`` as
``1 - normalized entropy`` and has no ``answer_confidence`` field at all.

Verified against the installed package::

    ChoiceAnswer  (type, choice, probabilities, confidence, abstain)
    ScoreAnswer   (type, score, legend, probabilities, confidence)
    NoulAnswer    (type, noul)          # no confidence at all

So the model's own number is recorded as ``native_confidence`` and the
thresholdable ``answer_confidence`` (``max(p)``) is computed here by the same
code that computes it for Laya. That is what makes the two comparable.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Mapping, Optional

from ..confidence import normalize_choice, normalize_noul, normalize_score
from . import Backend

DEFAULT_MODEL_PATH = os.environ.get("OPENTHAI_SYSTEMONE_MODEL", "iapp/OpenThai-SystemOne")


def _sdk():
    try:
        import openthai_systemone  # noqa: F401
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError(
            "the `openthai_systemone` package is not importable; install it with "
            "`pip install \"git+https://github.com/iapp-technology/openthai-systemone\"`"
        ) from exc
    return openthai_systemone


class OpenThaiBackend(Backend):
    """OpenThai-SystemOne on CUDA, MPS or CPU, chosen by the client itself."""

    name = "openthai"

    def __init__(
        self,
        model_path: str = DEFAULT_MODEL_PATH,
        device: Optional[str] = None,
        dtype: Any = None,
        eager: bool = False,
    ) -> None:
        self.model_path = model_path
        self.device = device
        self.dtype = dtype
        self._client = None
        if eager:
            self._ensure()

    def _ensure(self) -> None:
        if self._client is not None:
            return
        sdk = _sdk()
        kwargs: Dict[str, Any] = {}
        if self.device:
            kwargs["device"] = self.device
        if self.dtype is not None:
            kwargs["dtype"] = self.dtype
        self._client = sdk.SystemOneClient(self.model_path, **kwargs)

    # ------------------------------------------------------------------ conversion
    @staticmethod
    def to_sdk_questions(questions: Mapping[str, Any]) -> Dict[str, Any]:
        """Convert canonical question dicts into the SDK's typed question classes.

        The dataset holds one question format for both models, which is the
        point: if each model were asked in its own preferred phrasing, a
        difference in the answers could not be attributed to the models.
        """
        sdk = _sdk()
        out: Dict[str, Any] = {}
        for qid, question in questions.items():
            qtype = question.get("type")
            instructions = question.get("instructions", "")
            criteria = question.get("criteria")
            if qtype == "choice":
                if not isinstance(criteria, Mapping):
                    raise ValueError("choice question %r needs criteria as an object" % qid)
                out[str(qid)] = sdk.Choice(instructions=instructions, criteria=dict(criteria))
            elif qtype == "score":
                if not isinstance(criteria, (list, tuple)):
                    raise ValueError("score question %r needs criteria as a list of level labels" % qid)
                out[str(qid)] = sdk.Score(instructions=instructions, criteria=list(criteria))
            elif qtype == "noul":
                out[str(qid)] = sdk.Noul(instructions=instructions)
            else:
                raise ValueError("question %r has unsupported type %r" % (qid, qtype))
        return out

    # ------------------------------------------------------------------ inference
    def answers(self, state: Any, questions: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
        self._ensure()
        response = self._client.system_one(state=state, questions=self.to_sdk_questions(questions))
        out: Dict[str, Dict[str, Any]] = {}
        for qid, answer in (response.answers or {}).items():
            canonical = _normalize_answer(answer)
            if canonical is not None:
                out[qid] = canonical
        return out

    def unload(self) -> None:
        self._client = None
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:  # noqa: BLE001 - cache clearing is best effort
            pass


def _field(answer: Any, name: str, default: Any = None) -> Any:
    if isinstance(answer, Mapping):
        return answer.get(name, default)
    return getattr(answer, name, default)


def _normalize_answer(answer: Any) -> Optional[Dict[str, Any]]:
    """OpenThai answer object -> canonical answer dict."""
    qtype = _field(answer, "type")
    if qtype == "choice":
        return normalize_choice(
            _field(answer, "choice"),
            _field(answer, "probabilities"),
            native_confidence=_field(answer, "confidence"),
            abstain=_field(answer, "abstain"),
        )
    if qtype == "score":
        return normalize_score(
            _field(answer, "score"),
            _field(answer, "probabilities"),
            legend=_field(answer, "legend"),
            native_confidence=_field(answer, "confidence"),
        )
    if qtype == "noul":
        value = _field(answer, "noul")
        if value is None:
            return None
        return normalize_noul(value)
    return None
