"""The loop tools. Critical invariants under test:
  - DONE comes ONLY from the verifier — no agent-facing path self-declares done.
  - The standing order is present in EVERY CONTINUE and FAIL response.
  - Pacing actually delays (calls are spaced by ~PACING_SECONDS).
  - get_next_action returns goal + failing, never a prescribed step.
  - STOP/ESCALATE are sticky: nothing leaks back to CONTINUE afterwards.
"""
from __future__ import annotations
import time

import pytest

from looping_mcp import server, state as st, governor as gov, criteria, checker


@pytest.fixture(autouse=True)
def fast_pacing(monkeypatch):
    """Keep tests quick but still observably > 0 so pacing is measurable."""
    monkeypatch.setattr(server, "PACING_SECONDS", 0.05)
    monkeypatch.setattr(server, "_last_action_ts", 0.0)


@pytest.fixture
def running_state(state_file, monkeypatch):
    """A confirmed, running goal with one always-passing and one always-failing
    command criterion, so the verifier verdict is deterministic without a shell."""
    s = st.RunState(goal="add a footer link", status="running", lane="auto", risk="low")
    s.criteria = [
        st.Criterion(id="ok", text="build passes", oracle_type="command", oracle="true"),
        st.Criterion(id="bad", text="tests pass", oracle_type="command", oracle="false"),
    ]
    st.save(s)
    return s


# ---- get_next_action: goal + failing, never a step ----

def test_continue_returns_goal_and_failing_not_a_step(running_state):
    r = server.get_next_action()
    assert r["directive"] == "CONTINUE"
    assert r["goal"] == "add a footer link"
    assert "failing" in r and isinstance(r["failing"], list)
    # never prescribes HOW
    assert "step" not in r and "steps" not in r and "instructions" not in r
    # failing entries are {id,text,detail} — the WHAT, not the HOW
    assert {"id", "text", "detail"} >= set(r["failing"][0].keys())


def test_standing_order_in_every_continue(running_state):
    for _ in range(3):
        r = server.get_next_action()
        assert r["directive"] == "CONTINUE"
        assert r.get("standing_order"), "CONTINUE must carry the standing order"


# ---- report_result: DONE only from verifier; standing order on FAIL ----

def test_report_fail_carries_standing_order(running_state):
    r = server.report_result("tried something")
    assert r["status"] == "FAIL"
    assert any(f["id"] == "bad" for f in r["failing"])
    assert r.get("standing_order"), "FAIL must re-inject the standing order"
    assert "Do not stop" in r["standing_order"]


def test_done_only_when_verifier_passes_all(state_file):
    s = st.RunState(goal="g", status="running")
    s.criteria = [st.Criterion(id="ok", text="build", oracle_type="command", oracle="true")]
    st.save(s)
    r = server.report_result("done the build")
    assert r["status"] == "DONE"
    assert "Stop looping" in r["message"]
    # and state was actually marked done by the verifier, not by the agent
    assert st.load().status == "done"


def test_agent_cannot_reach_done_while_a_criterion_fails(running_state):
    # No amount of reporting flips DONE while 'bad' fails.
    for _ in range(5):
        r = server.report_result("claiming success anyway")
        assert r["status"] == "FAIL"
    assert st.load().status == "running"


def test_check_done_is_the_same_authority(running_state):
    assert server.check_done()["status"] == "FAIL"
    # make the failing one pass, then check_done flips to DONE
    s = st.load()
    s.criteria[1].oracle = "true"
    st.save(s)
    assert server.check_done()["status"] == "DONE"


# ---- pacing actually delays ----

def test_pacing_spaces_consecutive_calls(running_state, monkeypatch):
    monkeypatch.setattr(server, "PACING_SECONDS", 0.3)
    monkeypatch.setattr(server, "_last_action_ts", 0.0)
    server.get_next_action()              # first call sets the clock (no wait)
    t0 = time.time()
    server.get_next_action()              # second must be held ~PACING_SECONDS
    elapsed = time.time() - t0
    assert elapsed >= 0.25, f"expected pacing delay, got {elapsed:.3f}s"


# ---- governor STOP / ESCALATE are sticky ----

def test_stop_is_returned_and_sticky(running_state, monkeypatch):
    monkeypatch.setattr(gov, "MAX_TURNS", 0)   # cap already hit
    r = server.get_next_action()
    assert r["directive"] == "STOP"
    assert st.load().status == "stopped"
    # sticky: a second call still STOPs, never leaks a CONTINUE
    monkeypatch.setattr(gov, "MAX_TURNS", 999)   # even if the cap is lifted
    assert server.get_next_action()["directive"] == "STOP"
    # and report_result after a halt does not hand back "do not stop"
    rr = server.report_result("trying anyway")
    assert rr["status"] == "HALTED"


def test_escalate_is_returned_and_sticky(running_state, monkeypatch):
    monkeypatch.setattr(gov, "MAX_TURNS", 999)
    monkeypatch.setattr(gov, "MAX_EST_TOKENS", 10**9)
    monkeypatch.setattr(gov, "STALL_LIMIT", 3)
    s = st.load()
    s.passing_history = [0, 0, 0]   # 3 flat turns, 0/2 passing → stuck
    st.save(s)
    r = server.get_next_action()
    assert r["directive"] == "ESCALATE"
    assert r["escalation"]["trigger"] == "stuck"
    assert "goal" in r["escalation"]["handoff"]
    # sticky even if the stall window would now look fine
    s = st.load(); s.passing_history = []; st.save(s)
    assert server.get_next_action()["directive"] == "ESCALATE"


# ---- gate: WAIT carries a standing order, blocks action ----

def test_pending_gate_makes_get_next_action_wait(running_state):
    server.request_gate("php artisan migrate --env=prod", "irreversible schema change")
    r = server.get_next_action()
    assert r["directive"] == "WAIT"
    assert r.get("standing_order")
    assert st.load().gate.action.startswith("php artisan migrate")
