"""The governor is the seatbelt: it stops a runaway and detects thrashing.
Caps must fire EXACTLY at the boundary; stall must fire only after STALL_LIMIT
genuinely flat turns — never early (that would abandon a converging run)."""
from __future__ import annotations

from looping_mcp import governor as gov
from looping_mcp import state as st


def _state_with(passing, total, history):
    s = st.RunState()
    s.criteria = [
        st.Criterion(id=str(i), text=f"c{i}", oracle_type="command",
                     status="passing" if i < passing else "failing")
        for i in range(total)
    ]
    s.passing_history = list(history)
    return s


# ---- turn cap ----

def test_turn_cap_stops_exactly_at_boundary(monkeypatch):
    monkeypatch.setattr(gov, "MAX_TURNS", 40)
    s = _state_with(0, 3, [])

    s.turns = 39
    assert gov.check(s).action == "CONTINUE"   # one below — keep going

    s.turns = 40
    v = gov.check(s)
    assert v.action == "STOP" and "40" in v.reason   # exactly at cap


def test_est_token_cap_stops(monkeypatch):
    monkeypatch.setattr(gov, "MAX_EST_TOKENS", 1000)
    s = _state_with(0, 3, [])
    s.est_tokens = 999
    assert gov.check(s).action == "CONTINUE"
    s.est_tokens = 1000
    assert gov.check(s).action == "STOP"


# ---- stall detection ----

def test_stall_escalates_after_limit_flat_turns(monkeypatch):
    monkeypatch.setattr(gov, "MAX_TURNS", 1000)        # keep caps out of the way
    monkeypatch.setattr(gov, "MAX_EST_TOKENS", 10**9)
    monkeypatch.setattr(gov, "STALL_LIMIT", 6)

    # 6 flat turns at 1/3 passing → stuck
    s = _state_with(1, 3, [1, 1, 1, 1, 1, 1])
    v = gov.check(s)
    assert v.action == "ESCALATE" and "stuck" in v.reason


def test_stall_does_not_fire_before_limit(monkeypatch):
    monkeypatch.setattr(gov, "MAX_TURNS", 1000)
    monkeypatch.setattr(gov, "MAX_EST_TOKENS", 10**9)
    monkeypatch.setattr(gov, "STALL_LIMIT", 6)

    # only 5 flat turns — not stuck yet
    s = _state_with(1, 3, [1, 1, 1, 1, 1])
    assert gov.check(s).action == "CONTINUE"


def test_progress_within_window_is_not_a_stall(monkeypatch):
    monkeypatch.setattr(gov, "MAX_TURNS", 1000)
    monkeypatch.setattr(gov, "MAX_EST_TOKENS", 10**9)
    monkeypatch.setattr(gov, "STALL_LIMIT", 6)

    # passing climbed inside the window (0->1) → still converging, not stuck
    s = _state_with(1, 3, [0, 0, 0, 1, 1, 1])
    assert gov.check(s).action == "CONTINUE"


def test_all_passing_is_not_a_stall(monkeypatch):
    monkeypatch.setattr(gov, "MAX_TURNS", 1000)
    monkeypatch.setattr(gov, "MAX_EST_TOKENS", 10**9)
    monkeypatch.setattr(gov, "STALL_LIMIT", 6)

    # flat history but everything passes — that's success, not a stall
    s = _state_with(3, 3, [3, 3, 3, 3, 3, 3])
    assert gov.check(s).action == "CONTINUE"


def test_stall_limit_is_tunable(monkeypatch):
    monkeypatch.setattr(gov, "MAX_TURNS", 1000)
    monkeypatch.setattr(gov, "MAX_EST_TOKENS", 10**9)
    monkeypatch.setattr(gov, "STALL_LIMIT", 3)   # tighter threshold

    s = _state_with(1, 3, [1, 1, 1])
    assert gov.check(s).action == "ESCALATE"
    s2 = _state_with(1, 3, [1, 1])
    assert gov.check(s2).action == "CONTINUE"
