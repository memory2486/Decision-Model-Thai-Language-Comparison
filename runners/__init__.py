"""Backends behind one runner.

The contract ``laya.evals.evaluate`` states is exactly one method:
``predict(state, questions, model=...)``. ``model`` names *which* checkpoint
answers, and it is forwarded verbatim from ``laya.evals.Example.model``, so a
single dataset selects the backend per row and the harness slices the results
by model for free.

Registered keys:

===========  ===========================================================
``laya-auto`` Laya's ``Router``: detects script/language and dispatches.
               The only Laya key that can read Thai.
``laya-en``   Laya's English checkpoint, loaded directly. Kept as an
               explicit key so the "English checkpoint on Thai" failure
               mode can be *measured* rather than accidentally hit.
``laya-ml``   Laya's multilingual checkpoint (mmBERT-base) directly.
``openthai``  OpenThai-SystemOne (Thai + English).
===========  ===========================================================

Backends are constructed lazily and cached: a run that only asks ``openthai``
never loads ~1.5 GB of Laya weights.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Mapping, Optional

from ..limits import validate_questions, validate_state

DEFAULT_MODEL = "laya-auto"

ANSWER_KWARG = "_latency_ms"


class UnknownModel(KeyError):
    """The requested backend key is not registered."""


class Backend:
    """What a runner needs from a backend: a name and per-question answers."""

    name = "backend"

    def answers(self, state: Any, questions: Mapping[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Return canonical answers keyed by question id. Measured, not fabricated."""
        raise NotImplementedError

    def unload(self) -> None:
        """Release model weights if held."""
        return None


class DecisionRunner:
    """Run one labelled decision through a named backend.

    Satisfies ``laya.evals.evaluate``'s runner contract. Each canonical answer
    carries a ``_latency_ms`` key recording the wall time of the backend call
    that produced it, because the harness computes latency for the whole run
    only -- it does not expose it per slice, and per-backend latency is one of
    the quantities this comparison is for. It is an extra key on an answer
    dict, so nothing in ``laya.evals`` reads it, and the report reads it
    knowingly.
    """

    def __init__(self, model: str = DEFAULT_MODEL, preload: bool = False,
                 release_between_models: bool = False) -> None:
        self.model = model
        self._factories: Dict[str, Any] = {}
        self._loaded: Dict[str, Backend] = {}
        #: Unload every other backend when the requested model changes. Four
        #: checkpoints do not fit an 8 GB card at once (Laya's Router alone
        #: holds English and multilingual), so a comparison run over several
        #: backends has to swap rather than accumulate. `bench` orders the
        #: dataset by model block so this costs one load per backend, not one
        #: per row.
        self.release_between_models = release_between_models
        self._current: Optional[str] = None
        #: Which checkpoint actually answered, per call. For `laya-auto` this
        #: is the only evidence that a Thai row reached `multilingual`.
        self.routing_log: list = []
        if preload:
            self.preload()

    # ------------------------------------------------------------------ registry
    def register(self, key: str, factory) -> "DecisionRunner":
        """Register ``factory() -> Backend`` under ``key``."""
        self._factories[key] = factory
        return self

    @classmethod
    def with_defaults(cls, preload: bool = False, **kwargs: Any) -> "DecisionRunner":
        runner = cls(**kwargs)
        from .laya_backend import LayaBackend
        from .openthai_backend import OpenThaiBackend

        runner.register("laya-auto", lambda: LayaBackend(mode="auto"))
        runner.register("laya-en", lambda: LayaBackend(mode="english"))
        runner.register("laya-ml", lambda: LayaBackend(mode="multilingual"))
        runner.register("openthai", lambda: OpenThaiBackend())
        if preload:
            runner.preload()
        return runner

    def known_models(self) -> list:
        return sorted(self._factories)

    def backend(self, model: Optional[str] = None) -> Backend:
        key = model or self.model
        if key not in self._factories:
            raise UnknownModel(
                "unknown model %r; registered: %s" % (key, ", ".join(self.known_models()))
            )
        if key not in self._loaded:
            self._loaded[key] = self._factories[key]()
        return self._loaded[key]

    def preload(self) -> None:
        for key in self._factories:
            self.backend(key)

    def unload(self) -> None:
        for backend in self._loaded.values():
            backend.unload()
        self._loaded.clear()

    # ------------------------------------------------------------------ runner contract
    def predict(
        self,
        state: Any,
        questions: Mapping[str, Any],
        model: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Answer ``questions`` about ``state`` with ``model``."""
        questions = validate_questions(questions)
        validate_state(state)
        key = model or self.model
        if self.release_between_models and self._current is not None and self._current != key:
            self._release_all()
        self._current = key
        backend = self.backend(key)
        started = time.perf_counter()
        answers = backend.answers(state, questions)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        for answer in answers.values():
            answer[ANSWER_KWARG] = elapsed_ms
        routing = {"model": backend.name, "requested": key}
        detail = getattr(backend, "last_routing", None)
        if detail:
            routing.update(detail)
        self.routing_log.append({"requested": key, "answered_by": routing.get("model"),
                                 "reason": routing.get("reason")})
        return {"answers": answers, "routing": routing}

    def _release_all(self) -> None:
        for backend in self._loaded.values():
            backend.unload()
        self._loaded.clear()
        _empty_cuda_cache()

    def close(self) -> None:
        self.unload()


def _empty_cuda_cache() -> None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:  # noqa: BLE001 - reclaiming memory is best effort
        pass


def runner_from_env(**kwargs: Any) -> DecisionRunner:
    """Build the default runner, honouring ``DECISION_MODEL`` for the default key."""
    import os

    return DecisionRunner.with_defaults(model=os.environ.get("DECISION_MODEL", DEFAULT_MODEL), **kwargs)


__all__ = ["Backend", "DecisionRunner", "DEFAULT_MODEL", "UnknownModel", "runner_from_env", "ANSWER_KWARG"]
