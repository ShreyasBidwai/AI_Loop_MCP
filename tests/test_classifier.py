"""Intake triage. Keyword pass is a safety FLOOR; an LLM may add caution but
never remove it. High-blast goals → developer lane; aesthetic goals → unverifiable."""
from __future__ import annotations

from looping_mcp import classifier as clf
from looping_mcp import llm


# ---- keyword floor (no LLM) ----

def test_high_blast_goal_goes_to_developer():
    for goal in ["add oauth login", "run the payment refund flow",
                 "migrate the production database"]:
        c = clf.classify(goal)
        assert c.lane == "developer" and c.risk == "high"
        assert c.blast, "should name the high-blast area"


def test_aesthetic_goal_is_unverifiable():
    c = clf.classify("make the dashboard feel nicer and more modern")
    assert c.lane == "developer"
    assert c.verifiable is False
    assert "scope" in c.reason.lower() or "subjective" in c.reason.lower()


def test_plain_goal_is_auto_lane():
    c = clf.classify("add a footer link to the about page")
    assert c.lane == "auto" and c.risk == "low" and c.verifiable is True


# ---- LLM may only ADD caution ----

def test_llm_cannot_de_escalate_a_high_blast_keyword(monkeypatch):
    # model tries to call an auth change low-risk; keyword floor overrides it.
    monkeypatch.setattr(llm, "draft_json",
                        lambda *a, **k: {"risk": "low", "verifiable": True,
                                         "blast": [], "reason": "looks fine"})
    c = clf.classify("change the oauth token lifetime")
    assert c.lane == "developer"           # floor held
    assert "oauth" in c.blast


def test_llm_can_escalate_a_benign_looking_goal(monkeypatch):
    # keywords see nothing risky, but the model spots a data-loss risk.
    monkeypatch.setattr(llm, "draft_json",
                        lambda *a, **k: {"risk": "high", "verifiable": True,
                                         "blast": ["bulk record deletion"],
                                         "reason": "wipes user records irreversibly"})
    c = clf.classify("tidy up stale rows in the users table")
    assert c.lane == "developer" and c.risk == "high"
    assert "bulk record deletion" in c.blast
    assert "irreversibl" in c.reason


def test_llm_can_flag_unverifiable(monkeypatch):
    monkeypatch.setattr(llm, "draft_json",
                        lambda *a, **k: {"risk": "low", "verifiable": False,
                                         "blast": [], "reason": "purely subjective"})
    c = clf.classify("improve the overall vibe")
    assert c.lane == "developer" and c.verifiable is False
