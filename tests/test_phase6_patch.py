"""Guard the Phase 6 fixes to the pre-existing experiments.

Those files live outside this package, so these tests skip when the directory is
absent rather than failing on a machine that never had it. They assert the three
defects stay fixed, because each one is invisible at runtime: the English
checkpoint on Thai returns an answer, and a fabricated confidence looks exactly
like a real one.

The checks parse the source and inspect the **AST**, not substrings. The patched
files explain the old defects in their docstrings -- ``laya.load("...")`` and the
defaulted `.get` calls appear there as prose -- so a substring test would fail on
the explanation rather than on the code it is guarding.
"""

import ast
import os

import pytest

DECISION_MODEL = os.environ.get(
    "DECISION_MODEL_DIR", os.path.expanduser("~/Desktop/Decision_model"))
ROUTER = os.path.join(DECISION_MODEL, "laya_ex", "Laya_Agent_Gating", "laya_router.py")
PLAYER = os.path.join(DECISION_MODEL, "laya_ex", "exp_tetris", "laya_player.py")
SERVER = os.path.join(DECISION_MODEL, "laya_ex", "dsh-subagent-dispatch", "laya_server.py")

#: Every module that was loading a checkpoint directly. `laya_server.py` matters
#: most: it is the served component, so its defect was reachable over HTTP.
PATCHED = tuple(path for path in (ROUTER, PLAYER, SERVER) if os.path.exists(path))

#: `.get` keys whose default would fabricate a decision.
DECISION_KEYS = ("answer_confidence", "confidence", "choice")

pytestmark = pytest.mark.skipif(
    not os.path.exists(ROUTER),
    reason="the pre-existing Decision_model experiments are not present on this machine",
)


def parse(path):
    with open(path, "r", encoding="utf-8") as handle:
        return ast.parse(handle.read(), filename=path)


def read(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def dotted_name(node):
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def calls_to(tree, dotted):
    return [node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and dotted_name(node.func) == dotted]


def gets_with_defaults(tree, keys=DECISION_KEYS):
    """Defaults that *fabricate* a decision, as opposed to falling back safely.

    The distinction is not pedantic, and getting it wrong makes the guard fire on
    correct code:

    * ``.get("answer_confidence", 0.9)`` -- a **literal** default. The model
      reported nothing and the code invented a delegation-grade 0.9 that no
      downstream gate can distinguish from a real one. This is the defect.
    * ``.get("answer_confidence", q_res.get("confidence"))`` -- a **chained
      fallback**, which terminates in ``None`` if neither field is present. That
      is the answer-first-then-entropy rule every adapter in this package
      applies (``confidence_of`` in Python, ``answerConfidenceOf`` in TypeScript):
      a missing confidence stays missing and the caller fails closed. Flagging
      it would be flagging the fix.
    * any default at all for ``choice`` -- a choice is a decision, so defaulting
      it (even to another lookup) reports one option as the answer nobody voted
      for.
    """
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute) or node.func.attr != "get":
            continue
        if not node.args or not isinstance(node.args[0], ast.Constant):
            continue
        key = node.args[0].value
        if key not in keys:
            continue
        candidates = list(node.args[1:])
        candidates += [kw.value for kw in node.keywords if kw.arg == "default"]
        for value in candidates:
            literal = isinstance(value, ast.Constant) and value.value is not None
            if literal or key == "choice":
                offenders.append("%s.get(%r, %s)" % (
                    dotted_name(node.func.value) or "?", key, ast.dump(value)))
    return offenders


@pytest.mark.parametrize("path", PATCHED)
def test_no_checkpoint_is_loaded_directly(path):
    """`laya.load` bypasses script detection, which is the whole Thai bug."""
    direct = calls_to(parse(path), "laya.load")
    assert not direct, "%s still calls laya.load, which cannot read Thai" % path


@pytest.mark.parametrize("path", PATCHED)
def test_the_script_aware_router_is_constructed(path):
    assert calls_to(parse(path), "laya.Router"), "%s does not build a Router" % path


@pytest.mark.parametrize("path", PATCHED)
def test_no_decision_is_defaulted(path):
    """A defaulted `.get("answer_confidence", 0.9)` invents a delegation-grade number."""
    assert not gets_with_defaults(parse(path))


def test_all_three_missed_modules_are_covered():
    """The served module was missed on the first pass; this fails if one is dropped again."""
    assert {os.path.basename(p) for p in PATCHED} == {
        "laya_router.py", "laya_player.py", "laya_server.py"}


def test_the_served_module_reports_which_checkpoint_answered():
    source = read(SERVER)
    assert "answered_by" in source
    assert "routing_reason" in source
    assert calls_to(parse(SERVER), "agent.predict"), "the server must read the routing decision"


def test_the_guard_would_catch_a_regression():
    """A test that cannot fail is not a guard: feed it the original defects."""
    defective = ast.parse(
        "x = route_res.get('answer_confidence', route_res.get('confidence', 0.9))\n"
        "y = move_res.get('choice', 'opt_0')\n"
        "z = route_res.get('choice', default=0.5)\n"
        "w = route_res.get('confidence', 0.85)\n"
    )
    # The literal 0.9 inside x, both choice defaults, and the literal 0.85 in w.
    assert len(gets_with_defaults(defective)) == 4


def test_the_guard_accepts_a_chained_fallback_that_terminates_in_none():
    """The safe pattern must not be flagged, or the guard would ban the fix."""
    safe = ast.parse(
        "a = q_res.get('answer_confidence', q_res.get('confidence'))\n"
        "b = q_res.get('answer_confidence')\n"
        "c = q_res.get('confidence')\n"
    )
    assert gets_with_defaults(safe) == []


def test_without_a_model_the_heuristic_says_it_is_a_heuristic():
    assert "NOT a model decision" in read(ROUTER)


def test_routing_metadata_is_recorded():
    """Which checkpoint answered has to be observable, not assumed."""
    tree = parse(ROUTER)
    assigned = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            # `self.last_routing = ...` targets an Attribute, not a Name.
            if isinstance(target, ast.Name):
                assigned.add(target.id)
            elif isinstance(target, ast.Attribute):
                assigned.add(target.attr)
    assert "last_routing" in assigned
    source = read(ROUTER)
    assert "routing_reason" in source
    assert "answered_by" in source
