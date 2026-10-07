"""Shared decision-model harness for Laya and OpenThai-SystemOne.

Both models answer the same contract -- a ``state`` plus typed ``questions``
(``choice`` / ``score`` / ``noul``) and return calibrated probabilities in one
forward pass with zero output tokens -- so they are interchangeable backends
behind a single runner, not two integrations.

The comparison is scored by Laya's own harness (:mod:`laya.evals`), which
slices by ``language`` and ``model`` and already computes ECE, AURC and
selective accuracy. That is why this package implements one adapter and a
dataset instead of a second metric stack: two harnesses would produce two
numbers that cannot be compared.
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
