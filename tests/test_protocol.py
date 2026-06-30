"""Two layers, kept apart: the LOCKED SPINE is owned here and versioned; the OPEN
SLOTS (goal, criteria) are per-run. Editing a slot must never touch spine text.
The standing order must re-list current failures on every call (it survives
context compaction precisely because it is recomputed, never cached)."""
from __future__ import annotations
from pathlib import Path

from looping_mcp import protocol as p
from looping_mcp import state as st

AGENTS_MD = Path(__file__).resolve().parents[1] / "AGENTS.md"


def _state(goal, crits):
    s = st.RunState(goal=goal)
    s.criteria = [st.Criterion(id=i, text=t, oracle_type="command",
                               status=stt, detail=d)
                  for (i, t, stt, d) in crits]
    return s


# ---- spine vs slots separation ----

def test_editing_slots_never_touches_spine():
    before = p.LOCKED_SPINE
    s1 = _state("goal A", [("1", "build passes", "failing", "")])
    s2 = _state("a totally different goal B", [("9", "ship it", "failing", "")])
    k1, k2 = p.assemble_kickoff(s1), p.assemble_kickoff(s2)

    # the spine text is byte-identical inside both kickoffs and unchanged globally
    assert p.LOCKED_SPINE == before
    assert p.LOCKED_SPINE in k1 and p.LOCKED_SPINE in k2
    # only the slots differ between the two kickoffs
    assert "goal A" in k1 and "goal B" in k2
    assert "build passes" in k1 and "ship it" in k2


def test_kickoff_contains_full_spine_goal_and_all_criteria():
    s = _state("add a footer link", [
        ("1", "build succeeds", "pending", ""),
        ("2", "link is visible end to end", "pending", ""),
    ])
    k = p.assemble_kickoff(s)
    assert p.LOCKED_SPINE in k                      # full spine
    assert "add a footer link" in k                 # goal slot
    assert "build succeeds" in k and "link is visible end to end" in k  # all criteria
    assert "Begin by calling get_next_action." in k


# ---- standing order re-lists failures every call ----

def test_standing_order_relists_current_failures():
    s = _state("g", [
        ("1", "build passes", "passing", ""),
        ("2", "tests pass", "failing", "3 failed in suite/test_x"),
        ("3", "lint clean", "pending", ""),
    ])
    so = p.standing_order(s)
    assert "Do not stop" in so
    assert "tests pass" in so and "3 failed in suite/test_x" in so  # failing + detail
    assert "lint clean" in so                                       # pending counts as failing
    assert "build passes" not in so                                 # passing omitted


def test_standing_order_updates_as_state_changes():
    s = _state("g", [("2", "tests pass", "failing", "")])
    first = p.standing_order(s)
    assert "Do not stop" in first
    # criterion now passes — same function, recomputed, different verdict
    s.criteria[0].status = "passing"
    second = p.standing_order(s)
    assert second != first
    assert "Call check_done to confirm DONE." in second


# ---- AGENTS.md matches the spine word-for-word on load-bearing rules ----

def test_agents_md_carries_every_load_bearing_rule_verbatim():
    doc = AGENTS_MD.read_text()
    for rule in p.LOAD_BEARING_RULES:
        assert rule in doc, f"AGENTS.md is missing the load-bearing rule:\n{rule}"


def test_spine_is_built_from_the_load_bearing_rules():
    for rule in p.LOAD_BEARING_RULES:
        assert rule in p.LOCKED_SPINE
