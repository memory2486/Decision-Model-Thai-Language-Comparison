"""Laya backends: the Router, and the two checkpoints behind it.

The distinction matters more than it looks. ``laya.load("convaiinnovations/laya")``
loads the **English** ModernBERT-large checkpoint with no language routing at
all -- which is what every pre-existing experiment in ``Decision_model`` did,
including its Thai paths. Laya's own model card reports that checkpoint at
0.000 accuracy with 0.952 confidence on a non-Latin script, and states the
consequence plainly: "Because the model stays confident while being wrong,
confidence gating cannot save you."

``laya.Router`` is the only key here that reads Thai, because
``Router._route`` dispatches a non-Latin script to ``multilingual``. It is
therefore the default, and the direct checkpoints exist so the failure mode is
something this harness measures rather than something it suffers.
"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from ..confidence import normalize_choice, normalize_noul, normalize_score
from . import Backend

REPO = "convaiinnovations/laya"

#: `mode` -> (repo, subfolder). `auto` is handled by `laya.Router` instead.
CHECKPOINTS = {
    "english": (REPO, None),
    "multilingual": (REPO, "multilingual"),
    "typed-decisions": (REPO, "typed-decisions"),
}


def _laya():
    try:
        import laya  # noqa: F401
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError(
            "the `laya` package is not importable; install it with `pip install laya`"
        ) from exc
    return laya


class LayaBackend(Backend):
    """One Laya checkpoint, or the Router that picks between them.

    ``mode="auto"`` uses ``laya.Router`` and lets language detection choose
    (English and multilingual are the two automatic options; the Router's stock
    ``default`` is English for text with no letters or an unidentified Latin
    language). ``mode`` naming a checkpoint in :data:`CHECKPOINTS` loads that
    checkpoint directly, bypassing detection entirely.
    """

    def __init__(self, mode: str = "auto", device: Optional[str] = None, preload: bool = False) -> None:
        self.mode = mode
        self.device = device
        self.name = "laya-" + mode
        self._router = None
        self._agent = None
        self.document = None
        #: The Router's own explanation of which checkpoint answered, or None
        #: when a checkpoint was loaded directly. Reset on every call.
        self.last_routing = None
        if preload:
            self._ensure()

    # ------------------------------------------------------------------ loading
    def _ensure(self) -> None:
        if self._router is not None or self._agent is not None:
            return
        laya = _laya()
        if self.mode == "auto":
            self._router = laya.Router(preload=True, **({"device": self.device} if self.device else {}))
            self.document = "laya.Router (language-aware)"
            return
        if self.mode not in CHECKPOINTS:
            raise ValueError("unknown Laya mode %r; expected 'auto' or one of %s"
                             % (self.mode, ", ".join(sorted(CHECKPOINTS))))
        repo, subfolder = CHECKPOINTS[self.mode]
        kwargs: Dict[str, Any] = {}
        if subfolder:
            kwargs["subfolder"] = subfolder
        if self.device:
            kwargs["device"] = self.device
        self._agent = laya.load(repo, **kwargs)
        self.document = repo + (("/" + subfolder) if subfolder else " (English root)")

    # ------------------------------------------------------------------ inference
    def answers(self, state: Any, questions: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
        self._ensure()
        result = self._predict(state, questions)
        # The Router resolves the script and says which checkpoint it picked;
        # that string is how a Thai row is shown to have reached
        # `multilingual` rather than the English checkpoint.
        self.last_routing = result.get("routing") if isinstance(result, Mapping) else None
        return _normalize(result)

    def _predict(self, state: Any, questions: Mapping[str, Any]) -> Any:
        if self._router is not None:
            return self._router.predict(state, questions)
        return self._agent.predict(state, questions)

    def unload(self) -> None:
        self._router = None
        self._agent = None
        self.last_routing = None


def _normalize(result: Any) -> Dict[str, Dict[str, Any]]:
    """Convert Laya's raw answer dicts into the canonical shape."""
    raw = (result or {}).get("answers") or {}
    out: Dict[str, Dict[str, Any]] = {}
    for qid, answer in raw.items():
        if not isinstance(answer, Mapping):
            continue
        qtype = answer.get("type")
        # Laya reports two numbers itself: `answer_confidence` (max-p, the one
        # its own gate and calibration figures use) and `confidence` (entropy).
        # Both are recorded verbatim under `native_*` so the harness's numbers
        # can be checked against the model's, rather than trusted.
        if qtype == "choice":
            out[qid] = normalize_choice(
                answer.get("choice"),
                answer.get("probabilities"),
                native_confidence=answer.get("confidence"),
                abstain=answer.get("abstain"),
                native_answer_confidence=answer.get("answer_confidence"),
            )
        elif qtype == "score":
            out[qid] = normalize_score(
                answer.get("score"),
                answer.get("probabilities"),
                legend=answer.get("legend"),
                native_confidence=answer.get("confidence"),
                native_answer_confidence=answer.get("answer_confidence"),
            )
        elif qtype == "noul":
            value = answer.get("noul", answer.get("value"))
            if value is None:
                continue
            out[qid] = normalize_noul(value, native_confidence=answer.get("confidence"))
    return out
