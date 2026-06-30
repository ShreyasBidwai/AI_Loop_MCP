"""The watch dashboard. It must serve the page + a live state API, expose only
estimate-labelled budget (never an exact token claim), render escalation + gate
prominently, and let the manager resolve a gate."""
from __future__ import annotations
import json
import threading
import urllib.request
import urllib.error

import pytest

from looping_mcp import dashboard, server, state as st


@pytest.fixture
def live_server(state_file):
    """Start the real dashboard on an ephemeral port and tear it down after."""
    srv = dashboard._make_server(0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    yield base
    srv.shutdown()


def _get(url):
    with urllib.request.urlopen(url, timeout=3) as r:
        return r.status, r.read().decode()


def _post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ---- serves page + state ----

def test_serves_light_theme_page(live_server):
    code, html = _get(live_server + "/")
    assert code == 200
    assert "<title>Looping agent</title>" in html
    assert "--bg:#faf9f5" in html         # light theme tokens present
    assert "setInterval(tick,1500)" in html   # polls within ~2s


def test_state_api_returns_real_counters_and_caps(live_server):
    s = st.RunState(goal="add a footer link", status="running", turns=3, actions=5)
    s.criteria = [st.Criterion(id="1", text="build", oracle_type="command",
                               status="passing")]
    st.save(s)
    code, body = _get(live_server + "/api/state")
    data = json.loads(body)
    assert code == 200
    assert data["goal"] == "add a footer link"
    assert data["turns"] == 3 and data["actions"] == 5    # real counters
    assert data["_max_est_tokens"] == dashboard.governor.MAX_EST_TOKENS  # served cap


def test_budget_never_presented_as_exact_token_count(live_server):
    _, html = _get(live_server + "/")
    # the only token figure is explicitly an estimate, marked ~
    assert "estimate, not a real token count" in html
    assert "~${(s.est_tokens" in html     # rendered with a ~ prefix


def test_escalation_and_gate_render_distinctly(live_server):
    _, html = _get(live_server + "/")
    assert "needs a developer" in html and "#a32d2d" in html   # developer/red
    assert "human gate" in html and "#854f0b" in html          # amber gate


# ---- gate resolution ----

def test_gate_approve_resolves_and_resumes(live_server):
    server.request_gate("php artisan migrate --env=prod", "irreversible")
    assert st.load().status == "blocked_gate"

    code, body = _post(live_server + "/api/gate", {"decision": "approve"})
    assert code == 200 and body["applied"] is True
    s = st.load()
    assert s.gate.decided is True and s.status == "running"

    # next action consumes the decision and tells the agent it was approved
    out = server.get_next_action()
    assert out["directive"] == "CONTINUE"
    assert out["gate_decision"]["approved"] is True
    assert st.load().gate is None     # consumed


def test_gate_reject_resolves(live_server):
    server.request_gate("delete the prod bucket", "dangerous")
    code, body = _post(live_server + "/api/gate", {"decision": "reject"})
    assert code == 200 and body["applied"] is True
    assert st.load().gate.decided is False
    out = server.get_next_action()
    assert out["gate_decision"]["approved"] is False


def test_gate_post_with_no_pending_gate_is_conflict(live_server):
    st.save(st.RunState(goal="g", status="running"))
    code, body = _post(live_server + "/api/gate", {"decision": "approve"})
    assert code == 409 and body["applied"] is False


# ---- control panel: propose + confirm straight from the dashboard ----

def test_control_panel_markup_present(live_server):
    _, html = _get(live_server + "/")
    assert 'id=control' in html and 'id=live' in html
    assert "function propose()" in html and "function arm()" in html
    # control region only rebuilds on phase change, so typing isn't clobbered
    assert "key!==controlKey" in html


def test_propose_endpoint_safe_goal(live_server):
    code, out = _post(live_server + "/api/propose",
                      {"goal": "change the footer copyright year to 2026"})
    assert code == 200 and out["lane"] == "auto"
    assert st.load().status == "awaiting_confirm"


def test_propose_endpoint_refuses_risky_goal(live_server):
    code, out = _post(live_server + "/api/propose",
                      {"goal": "add oauth login and store passwords"})
    assert code == 200 and out["lane"] == "developer"
    assert out["escalation"]["trigger"] == "risk"


def test_propose_endpoint_requires_goal(live_server):
    code, out = _post(live_server + "/api/propose", {"goal": "   "})
    assert code == 400 and "error" in out


def test_confirm_endpoint_arms_run_with_real_commands(live_server):
    _post(live_server + "/api/propose", {"goal": "change the footer year"})
    code, out = _post(live_server + "/api/confirm", {"criteria": [
        {"text": "build passes", "oracle_type": "command", "oracle": "true"},
    ]})
    assert code == 200 and "kickoff_prompt" in out
    s = st.load()
    assert s.status == "running"
    assert s.criteria[0].oracle == "true"


def test_confirm_endpoint_rejects_bad_criteria(live_server):
    _post(live_server + "/api/propose", {"goal": "change the footer year"})
    code, out = _post(live_server + "/api/confirm", {"criteria": [
        {"text": "build", "oracle_type": "command", "oracle": ""},
    ]})
    assert code == 400 and "error" in out
    assert st.load().status == "awaiting_confirm"
