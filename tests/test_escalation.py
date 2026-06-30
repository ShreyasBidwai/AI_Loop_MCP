"""Three triggers, one channel. Every escalation — wherever it originates — has
the same shape: a known trigger, a reason, and a handoff that always carries the
goal (plus a progress snapshot when one exists)."""
from __future__ import annotations
import os

import pytest

from looping_mcp import escalation as esc
from looping_mcp import server, state as st, governor as gov, classifier, criteria


def test_intake_triggers_carry_reason_and_goal():
    for trig in ("risk", "unverifiable"):
        e = esc.build(trig, "because reasons", "ship the thing")
        assert e["trigger"] == trig
        assert e["reason"] == "because reasons"
        assert e["handoff"]["goal"] == "ship the thing"
        assert "passing" not in e["handoff"]   # no progress snapshot at intake


def test_stuck_trigger_carries_progress_snapshot():
    e = esc.build("stuck", "no progress", "ship",
                  progress={"passing": 1, "total": 3, "turns": 7})
    assert e["handoff"] == {"goal": "ship", "passing": 1, "total": 3, "turns": 7}


def test_unknown_trigger_rejected():
    with pytest.raises(ValueError):
        esc.build("vibes", "nope", "goal")


# ---- the three triggers reach the channel through the server ----

def test_risk_trigger_via_propose(state_file):
    out = server.propose("add oauth login and password reset")
    assert out["lane"] == "developer"
    assert out["escalation"]["trigger"] == "risk"
    assert out["escalation"]["handoff"]["goal"]


def test_unverifiable_trigger_via_propose_classifier(state_file):
    out = server.propose("make the homepage feel more polished")
    assert out["lane"] == "developer"
    assert out["escalation"]["trigger"] == "unverifiable"


def test_unverifiable_trigger_via_criteria_draft(state_file, monkeypatch):
    # classifier says auto/verifiable, but criteria drafting finds no oracle.
    monkeypatch.setattr(criteria, "propose",
                        lambda goal, ctx="": criteria.CriteriaResult(
                            unverifiable=True, reason="no oracle possible"))
    out = server.propose("do the needful")
    assert out["lane"] == "developer"
    assert out["escalation"]["trigger"] == "unverifiable"
    assert out["escalation"]["reason"] == "no oracle possible"


def test_stuck_trigger_via_governor(state_file, monkeypatch):
    monkeypatch.setattr(server, "PACING_SECONDS", 0.0)
    monkeypatch.setattr(gov, "STALL_LIMIT", 2)
    monkeypatch.setattr(gov, "MAX_TURNS", 999)
    s = st.RunState(goal="g", status="running")
    s.criteria = [st.Criterion(id="1", text="c", oracle_type="command", status="failing")]
    s.passing_history = [0, 0]
    st.save(s)
    out = server.get_next_action()
    assert out["directive"] == "ESCALATE"
    assert out["escalation"]["trigger"] == "stuck"
    assert out["escalation"]["handoff"]["passing"] == 0


# ---- threshold is tunable, not hard-coded magic ----

def test_stall_threshold_reads_from_env():
    # governor pulls STALL_LIMIT from the environment at import; re-importing with
    # a patched env reflects the new value (i.e. it is configurable, not a magic literal).
    import importlib
    os.environ["STALL_LIMIT"] = "9"
    try:
        reloaded = importlib.reload(gov)
        assert reloaded.STALL_LIMIT == 9
    finally:
        del os.environ["STALL_LIMIT"]
        importlib.reload(gov)   # restore default for other tests
