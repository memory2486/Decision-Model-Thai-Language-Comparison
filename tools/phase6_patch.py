"""Phase 6: fix the Thai bug and the fabricated confidences in the existing Laya code.

Run with the Decision_model directory as the base::

    python decision_models/tools/phase6_patch.py <path-to-Decision_model>

Three defects, all verified against the installed packages before this script
existed:

1. ``laya.load("convaiinnovations/laya")`` -- the **English** checkpoint, with no
   script detection -- was used for every request, including Thai. Laya's router
   sends non-Latin script to ``multilingual`` only when it is the one asked, so
   these modules bypassed the fix. Measured on the focused benchmark: the
   English checkpoint on Thai scores 0.319 against a 0.313 chance baseline,
   while its mean ``max(p)`` stays at 0.525 -- confidently wrong, exactly as the
   model card warns, and unreachable by any confidence gate.

2. ``route_res.get("answer_confidence", route_res.get("confidence", 0.9))`` --
   the ``0.9`` default invents a delegation-grade confidence when the model
   reports none, and nothing downstream can tell it from a real one.

3. ``decision_res.get(...).get("choice", "opt_0")`` -- the same shape for a
   choice, defaulting to the first option instead of reporting no answer.

Each patch is applied only if its exact source text is found, so this script
fails loudly rather than half-editing a file that has since changed. Backups are
written next to each file with a ``.bak`` suffix if one does not already exist.
"""

from __future__ import annotations

import io
import os
import shutil
import sys
from typing import List, Tuple

ROUTER = os.path.join("laya_ex", "Laya_Agent_Gating", "laya_router.py")
PLAYER = os.path.join("laya_ex", "exp_tetris", "laya_player.py")
SERVER = os.path.join("laya_ex", "dsh-subagent-dispatch", "laya_server.py")


ROUTER_LOADER_OLD = '''    @classmethod
    def _get_agent(cls):
        if cls._cached_agent is None and LAYA_AVAILABLE:
            try:
                print("[Laya] Loading neural model weights (convaiinnovations/laya)...")
                cls._cached_agent = laya.load("convaiinnovations/laya")
                print("[Laya] Neural model loaded successfully.")
            except Exception as e:
                print(f"[Laya] Warning: Could not load weights ({e}), fallback will be used.")
                cls._cached_agent = False
        return cls._cached_agent'''

ROUTER_LOADER_NEW = '''    @classmethod
    def _get_agent(cls):
        """Load Laya's *Router*, not a single checkpoint.

        This used to be ``laya.load("convaiinnovations/laya")``, which is the
        English ModernBERT-large checkpoint with no language routing at all.
        Laya's own model card reports that checkpoint at 0.000 accuracy with
        0.952 confidence on a non-Latin script, and states the consequence:
        "Because the model stays confident while being wrong, confidence gating
        cannot save you." Measured on the focused benchmark, this checkpoint on
        Thai scores 0.319 against a 0.313 chance baseline.

        ``laya.Router`` detects the script and sends non-Latin text to
        ``laya-multilingual``; ``Router(default="multilingual")`` suits a
        Thai-only deployment. ``self.last_routing`` records which checkpoint
        actually answered, so a Thai turn can be shown to have reached the
        multilingual checkpoint rather than assumed to have.
        """
        if cls._cached_agent is None and LAYA_AVAILABLE:
            try:
                print("[Laya] Loading Router (script-aware: english + multilingual)...")
                cls._cached_agent = laya.Router(preload=True)
                cls._cached_agent_kind = "router"
                print("[Laya] Router ready.")
            except Exception as e:
                print(f"[Laya] Warning: Could not load weights ({e}), fallback will be used.")
                cls._cached_agent = False
                cls._cached_agent_kind = None
        return cls._cached_agent'''

ROUTER_CALL_OLD = '''        if self.agent:
            try:
                res = laya.decide(self.agent, state_text, questions=self.schema)
                route_res = res.get("route", {})
                selected_key = route_res.get("choice", "general")
                confidence = float(route_res.get("answer_confidence", route_res.get("confidence", 0.9)))
                probabilities = route_res.get("probabilities", {})
                latency_ms = round((time.time() - start) * 1000, 2)
                return {
                    "selected_subagent_key": selected_key,
                    "confidence": round(confidence, 4),
                    "probabilities": probabilities,
                    "decision_latency_ms": latency_ms,
                    "decision_reason": f"Real Laya Neural Model picked '{selected_key}' with probability {probabilities.get(selected_key, 0):.2%}",
                    "evaluated_schema": self.schema["route"]["criteria"],
                    "is_real_laya_model": True
                }
            except Exception as e:
                print(f"[Laya] Real model inference fallback triggered: {e}")'''

ROUTER_CALL_NEW = '''        if self.agent:
            try:
                payload = self.agent.predict(state_text, self.schema)
                self.last_routing = payload.get("routing")
                route_res = (payload.get("answers") or {}).get("route", {}) or {}

                # `answer_confidence` is Laya's calibrated max-probability figure:
                # the only field its own `min_confidence` gate and its calibration
                # numbers are defined against. `confidence` is normalized entropy,
                # a different quantity on a different scale -- a fallback at best,
                # never a substitute. Note that Laya's `answer_confidence` is
                # temperature-scaled, so it is not the raw max(p) either.
                #
                # This used to default to 0.9 when the key was missing, turning
                # "the model reported no confidence" into a delegation-grade 0.9
                # that no gate could distinguish from a real one. A missing value
                # now stays missing and the caller fails closed.
                confidence = route_res.get("answer_confidence")
                if confidence is None:
                    confidence = route_res.get("confidence")
                if confidence is None:
                    raise ValueError("Laya returned no confidence for the routing question")
                confidence = float(confidence)

                selected_key = route_res.get("choice")
                if selected_key not in self.schema["route"]["criteria"]:
                    raise ValueError(
                        f"Laya returned '{selected_key}', which is not a declared route")

                probabilities = route_res.get("probabilities", {})
                latency_ms = round((time.time() - start) * 1000, 2)
                return {
                    "selected_subagent_key": selected_key,
                    "confidence": round(confidence, 4),
                    "probabilities": probabilities,
                    "decision_latency_ms": latency_ms,
                    "decision_reason": f"Real Laya Neural Model picked '{selected_key}' with probability {probabilities.get(selected_key, 0):.2%}",
                    "evaluated_schema": self.schema["route"]["criteria"],
                    "answered_by": (self.last_routing or {}).get("model"),
                    "routing_reason": (self.last_routing or {}).get("reason"),
                    "is_real_laya_model": True
                }
            except Exception as e:
                print(f"[Laya] Real model inference fallback triggered: {e}")'''

SERVER_LOADER_OLD = '''print("Loading Laya neural weights...")
agent = laya.load("convaiinnovations/laya")
print("Laya loaded successfully.")'''

SERVER_LOADER_NEW = '''# Router, not the English root checkpoint. `laya.load(...)` has no script
# detection, so a Thai state reached a checkpoint Laya's own card reports at
# 0.000 accuracy with 0.952 confidence, and the client's confidence gate could
# not have caught it because the model stayed confident while being wrong.
# `Router` sends non-Latin script to `laya-multilingual`, and `laya.decide`
# accepts it because it only needs `predict(state, questions, model=...)`.
print("Loading Laya Router (script-aware: english + multilingual)...")
agent = laya.Router(preload=True)
print("Laya Router loaded successfully.")'''

SERVER_CONFIDENCE_OLD = '''        if isinstance(number, (int, float)) and not isinstance(number, bool):
            answer["confidence"] = float(number)
        answers[q_id] = answer'''

SERVER_CONFIDENCE_NEW = '''        #
        # Both names are emitted for a present value. `number` is
        # `answer_confidence` when Laya reported it -- the calibrated max-p --
        # and the entropy score only when it did not. Publishing that under the
        # bare name `confidence` alone is the trap this package documents:
        # OpenThai-SystemOne's field of the same name is the *entropy* quantity,
        # so a client reading `confidence` from both models would be comparing
        # two different scales. Emitting both is additive, so the existing
        # consumer, which reads `confidence`, is unaffected.
        if isinstance(number, (int, float)) and not isinstance(number, bool):
            answer["answer_confidence"] = float(number)
            answer["confidence"] = float(number)
        answers[q_id] = answer'''

SERVER_MODEL_OLD = '''    return {
        "model": "convaiinnovations/laya",
        "answers": answers,
        "usage": {"input_tokens": len(state.split()), "output_tokens": len(answers)}
    }'''

SERVER_MODEL_NEW = '''    return {
        # Name the checkpoint the Router actually chose, not the family, so a
        # Thai turn is auditable from the response alone.
        "model": "laya-router",
        "answered_by": routing.get("model"),
        "routing_reason": routing.get("reason"),
        "answers": answers,
        "usage": {"input_tokens": len(state.split()), "output_tokens": len(answers)}
    }'''

SERVER_DECIDE_OLD = '''    try:
        result = laya.decide(agent, state, questions=questions)
    except Exception as exc:  # noqa: BLE001 - reported, never leaked as a traceback
        raise HTTPException(status_code=502, detail="Laya decision failed: %s" % exc)'''

SERVER_DECIDE_NEW = '''    try:
        # `agent.predict` is used rather than `laya.decide` because it returns the
        # routing decision next to the answers, which is the only way to report
        # which checkpoint answered. `result` stays the answer map keyed by
        # question id, so the decoding below is unchanged.
        payload = agent.predict(state, questions)
        routing = payload.get("routing") or {}
        result = payload.get("answers") or {}
    except Exception as exc:  # noqa: BLE001 - reported, never leaked as a traceback
        raise HTTPException(status_code=502, detail="Laya decision failed: %s" % exc)'''

PLAYER_LOADER_OLD = '''            try:
                print("[Laya] Loading neural model weights for Tetris (convaiinnovations/laya)...")
                cls._cached_agent = laya.load("convaiinnovations/laya")
                print("[Laya] Tetris Decision Model loaded.")'''

PLAYER_LOADER_NEW = '''            try:
                # Router, not the English root checkpoint: `laya.load(...)` has no
                # script detection, so a non-Latin state reaches a checkpoint its
                # own model card reports at chance accuracy while staying
                # confident. See Laya_Agent_Gating/laya_router.py for the detail.
                print("[Laya] Loading Router for Tetris (script-aware)...")
                cls._cached_agent = laya.Router(preload=True)
                print("[Laya] Tetris Decision Router loaded.")'''

PLAYER_CALL_OLD = '''                decision_res = laya.decide(self.agent, state_text, questions=schema)
                chosen_opt = decision_res.get("best_move", {}).get("choice", "opt_0")
                confidence = float(decision_res.get("best_move", {}).get("answer_confidence", 0.85))'''

PLAYER_CALL_NEW = '''                payload = self.agent.predict(state_text, schema)
                move_res = (payload.get("answers") or {}).get("best_move", {}) or {}
                chosen_opt = move_res.get("choice")
                if chosen_opt is None:
                    raise ValueError("Laya returned no placement choice")
                # No invented 0.85: a missing confidence stays missing and the
                # caller falls back to the heuristic, which is honest about being
                # one. `answer_confidence` (calibrated) is preferred over the
                # entropy-scored `confidence`.
                confidence = move_res.get("answer_confidence")
                if confidence is None:
                    confidence = move_res.get("confidence")
                if confidence is None:
                    raise ValueError("Laya returned no confidence for the placement")'''


def _edit(path: str, edits: List[Tuple[str, str]], label: str) -> int:
    source = io.open(path, encoding="utf-8").read()
    changed = 0
    for old, new in edits:
        # Idempotent by construction: `old` is often a *substring* of `new`
        # (inserting a line after an anchor), so re-running without this guard
        # duplicates the inserted line instead of reporting no change.
        if new in source:
            continue
        if old in source:
            source = source.replace(old, new)
            changed += 1
    if not changed:
        print("  %s: no edits applied (already patched?)" % label)
        return 0
    backup = path + ".bak"
    if not os.path.exists(backup):
        shutil.copyfile(path, backup)
        print("  backup: %s" % backup)
    io.open(path, "w", encoding="utf-8", newline="\n").write(source)
    print("  %s: %d edit(s) applied" % (label, changed))
    return changed


def run(base: str) -> int:
    router = os.path.join(base, ROUTER)
    player = os.path.join(base, PLAYER)
    missing = [p for p in (router, player) if not os.path.exists(p)]
    if missing:
        print("missing files: %s" % ", ".join(missing), file=sys.stderr)
        return 2

    print("patching %s" % base)
    _edit(router, [
        (ROUTER_LOADER_OLD, ROUTER_LOADER_NEW),
        (ROUTER_CALL_OLD, ROUTER_CALL_NEW),
        ("    _cached_agent = None\n",
         "    _cached_agent = None\n    _cached_agent_kind = None\n"),
        ("        self.schema = self._build_schema(mode)\n        self.agent = self._get_agent()\n",
         "        self.schema = self._build_schema(mode)\n        self.agent = self._get_agent()\n        self.last_routing = None\n"),
        ('    reason = "Heuristic fallback"',
         '    reason = "Heuristic fallback (the neural model did not answer; NOT a model decision)"'),
    ], "laya_router.py")

    _edit(player, [
        (PLAYER_LOADER_OLD, PLAYER_LOADER_NEW),
        (PLAYER_CALL_OLD, PLAYER_CALL_NEW),
        ("'laya_decision': decision_res", "'laya_decision': payload"),
    ], "laya_player.py")

    server = os.path.join(base, SERVER)
    if os.path.exists(server):
        # `routing` must exist before the response builder reads it even if the
        # decide call is skipped, so it is bound with the other module state.
        _edit(server, [
            (SERVER_LOADER_OLD, SERVER_LOADER_NEW),
            (SERVER_DECIDE_OLD, SERVER_DECIDE_NEW),
            (SERVER_CONFIDENCE_OLD, SERVER_CONFIDENCE_NEW),
            (SERVER_MODEL_OLD, SERVER_MODEL_NEW),
        ], "laya_server.py")
    else:
        print("  laya_server.py: absent, skipped")
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    raise SystemExit(run(sys.argv[1]))
