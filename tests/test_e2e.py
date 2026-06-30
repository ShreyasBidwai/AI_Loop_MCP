"""End-to-end dry run, driven entirely through the real server tools — the same
calls the IDE agent would make.

Covers the Phase 7 checks:
  - a safe goal completes via the loop, and DONE comes only after the verifier passes;
  - the dashboard's state API tells the story live;
  - a forced stall escalates cleanly with a handoff — bounded, not infinite spend;
  - a high-risk goal is refused at intake.
"""
from __future__ import annotations
import json
import urllib.request

import pytest

from looping_mcp import server, dashboard, state as st, governor as gov


@pytest.fixture(autouse=True)
def no_pacing(monkeypatch):
    monkeypatch.setattr(server, "PACING_SECONDS", 0.0)
    monkeypatch.setattr(server, "_last_action_ts", 0.0)


def _inject_criteria(*crits):
    """Replace the proposed scaffold with criteria whose oracles we control,
    simulating what the manager confirms for a real repo."""
    s = st.load()
    s.criteria = list(crits)
    st.save(s)


# ---- safe goal: propose → confirm → loop → DONE ----

def test_safe_goal_completes_through_the_loop(state_file, tmp_path):
    marker = tmp_path / "footer_done.txt"

    out = server.propose("change the footer copyright year to 2026")
    assert out["lane"] == "auto"                     # safe lane, no refusal

    # the manager/agent environment supplies real oracles: a build that passes,
    # and a feature check that passes only once the work is actually done.
    _inject_criteria(
        st.Criterion(id="build", text="build succeeds", oracle_type="command", oracle="true"),
        st.Criterion(id="feat", text="footer shows 2026", oracle_type="command",
                     oracle=f"test -f {marker}"),
    )

    kickoff = server.confirm()["kickoff_prompt"]
    assert "change the footer copyright year" in kickoff      # goal slot
    assert "PROTOCOL (non-negotiable)" in kickoff            # full spine

    # turn 1: agent asks what to do — gets the goal + what fails, never a step
    a1 = server.get_next_action()
    assert a1["directive"] == "CONTINUE"
    assert "step" not in a1
    assert any(f["id"] == "feat" for f in a1["failing"])

    # agent reports before doing the work → verifier says FAIL, keep going
    r1 = server.report_result("looked at the component")
    assert r1["status"] == "FAIL"
    assert "Do not stop" in r1["standing_order"]

    # agent now actually does the work (creates the artifact the oracle checks)
    marker.write_text("2026")

    # turn 2: report again → verifier passes both → DONE
    server.get_next_action()
    r2 = server.report_result("updated the year to 2026")
    assert r2["status"] == "DONE"
    assert st.load().status == "done"                # DONE only after verifier passed
    assert st.load().passing() == 2


def test_dashboard_state_api_tells_the_story(state_file, tmp_path):
    server.propose("change the footer copyright year to 2026")
    _inject_criteria(
        st.Criterion(id="build", text="build succeeds", oracle_type="command", oracle="true"),
    )
    server.confirm()
    server.get_next_action()
    server.report_result("did it")

    # read the live state exactly as the dashboard's browser poll does
    payload = json.loads(dashboard._state_payload())
    assert payload["goal"].startswith("change the footer")
    assert payload["status"] == "done"
    assert payload["turns"] >= 1 and payload["actions"] >= 1     # real counters
    assert payload["criteria"][0]["status"] == "passing"
    assert payload["_max_est_tokens"] == gov.MAX_EST_TOKENS      # cap for the bar


# ---- forced stall → clean, bounded escalation ----

def test_forced_stall_escalates_with_handoff_and_is_bounded(state_file, monkeypatch):
    monkeypatch.setattr(gov, "STALL_LIMIT", 4)
    monkeypatch.setattr(gov, "MAX_TURNS", 1000)        # ensure stall fires, not the cap
    monkeypatch.setattr(gov, "MAX_EST_TOKENS", 10**9)

    server.propose("add a never-satisfiable footer thing")
    _inject_criteria(
        st.Criterion(id="never", text="impossible check", oracle_type="command",
                     oracle="false"),
    )
    server.confirm()

    escalated = None
    for _ in range(50):                                # hard bound — must not loop forever
        a = server.get_next_action()
        if a["directive"] == "ESCALATE":
            escalated = a
            break
        assert a["directive"] == "CONTINUE"
        server.report_result("tried again, still failing")

    assert escalated is not None, "stall never escalated — would be infinite spend"
    esc = escalated["escalation"]
    assert esc["trigger"] == "stuck"
    assert esc["handoff"]["goal"].startswith("add a never-satisfiable")
    assert esc["handoff"]["passing"] == 0 and esc["handoff"]["total"] == 1
    # bounded: escalated well within our hard loop limit, not at turn 1000
    assert st.load().turns < 20


# ---- high-risk goal refused at intake ----

def test_high_risk_goal_refused_at_intake(state_file):
    out = server.propose("add oauth login and store user passwords")
    assert out["lane"] == "developer"
    assert out["escalation"]["trigger"] == "risk"
    # no criteria proposed, run never enters the loop
    s = st.load()
    assert s.status == "escalated" and s.criteria == []
    # and the agent-facing loop refuses to dispense any action
    assert server.get_next_action()["directive"] == "ESCALATE"
