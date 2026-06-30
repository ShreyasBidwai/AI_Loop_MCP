"""State must survive reload — nothing load-bearing may live only in memory,
or context compaction / a process restart would silently erase the run."""
from __future__ import annotations

from looping_mcp import state as st


def test_empty_load_when_no_file(state_file):
    s = st.load()
    assert s.status == "idle"
    assert s.criteria == []
    assert s.turns == 0


def test_round_trip_to_disk(state_file):
    s = st.RunState(goal="ship the thing", status="running", risk="low", lane="auto")
    s.criteria = [
        st.Criterion(id="a1", text="build passes", oracle_type="command",
                     oracle="make build", status="passing"),
        st.Criterion(id="b2", text="flow works", oracle_type="browser",
                     oracle="drive it", status="failing", detail="no proof"),
    ]
    s.turns, s.actions, s.est_tokens = 7, 12, 3456
    s.passing_history = [0, 1, 1, 2]
    s.gate = st.Gate(action="deploy", reason="irreversible")
    s.escalation = {"trigger": "stuck", "reason": "flat", "handoff": {"goal": "x"}}
    s.log("agent", "did a thing")

    st.save(s)
    assert state_file.exists()

    r = st.load()
    # scalars
    assert (r.goal, r.status, r.risk, r.lane) == ("ship the thing", "running", "low", "auto")
    assert (r.turns, r.actions, r.est_tokens) == (7, 12, 3456)
    assert r.passing_history == [0, 1, 1, 2]
    # nested dataclasses rehydrate as objects, not dicts
    assert all(isinstance(c, st.Criterion) for c in r.criteria)
    assert r.criteria[0].status == "passing" and r.criteria[1].detail == "no proof"
    assert isinstance(r.gate, st.Gate) and r.gate.action == "deploy"
    assert r.gate.decided is None
    assert r.escalation["trigger"] == "stuck"
    assert r.activity and r.activity[0]["msg"] == "did a thing"


def test_helpers_passing_total_failing():
    s = st.RunState()
    s.criteria = [
        st.Criterion(id="1", text="a", oracle_type="command", status="passing"),
        st.Criterion(id="2", text="b", oracle_type="command", status="failing"),
        st.Criterion(id="3", text="c", oracle_type="command", status="pending"),
    ]
    assert s.passing() == 1
    assert s.total() == 3
    assert [c.id for c in s.failing()] == ["2", "3"]   # pending counts as not-yet-passing


def test_activity_log_capped_and_newest_first():
    s = st.RunState()
    for i in range(250):
        s.log("agent", f"msg {i}")
    assert len(s.activity) == 200          # capped
    assert s.activity[0]["msg"] == "msg 249"   # newest first
