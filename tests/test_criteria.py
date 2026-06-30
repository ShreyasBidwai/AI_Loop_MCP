"""Criteria drafting: every criterion needs a machine oracle. No machine oracle
possible → unverifiable escalation, never an invented green check."""
from __future__ import annotations

from looping_mcp import criteria as crit
from looping_mcp import llm


# ---- fallback scaffold (no LLM) ----

def test_stub_returns_usable_criteria():
    r = crit.propose("add a footer link")
    assert r.unverifiable is False
    assert r.criteria, "scaffold should give the manager something to edit"
    assert all(c.oracle_type in ("command", "browser") for c in r.criteria)
    assert all(c.id for c in r.criteria)


# ---- LLM path ----

def test_llm_unverifiable_flag_escalates(monkeypatch):
    monkeypatch.setattr(llm, "draft_json",
                        lambda *a, **k: {"verifiable": False,
                                         "reason": "no command can prove 'feels nicer'"})
    r = crit.propose("make it feel nicer")
    assert r.unverifiable is True
    assert "feels nicer" in r.reason and not r.criteria


def test_llm_criteria_without_machine_oracle_are_dropped(monkeypatch):
    # model returns only a manual/no-oracle criterion → nothing survives → unverifiable
    monkeypatch.setattr(llm, "draft_json", lambda *a, **k: {
        "verifiable": True,
        "criteria": [
            {"text": "a human likes it", "oracle_type": "manual", "oracle": "ask someone"},
            {"text": "missing oracle", "oracle_type": "command", "oracle": ""},
        ],
    })
    r = crit.propose("polish the page")
    assert r.unverifiable is True
    assert "developer" in r.reason.lower() or "oracle" in r.reason.lower()


def test_llm_valid_criteria_pass_through(monkeypatch):
    monkeypatch.setattr(llm, "draft_json", lambda *a, **k: {
        "verifiable": True,
        "criteria": [
            {"text": "build passes", "oracle_type": "command", "oracle": "npm run build"},
            {"text": "the link appears", "oracle_type": "browser", "oracle": "open /about"},
            {"text": "junk", "oracle_type": "nonsense", "oracle": "x"},   # dropped
        ],
    })
    r = crit.propose("add a footer link")
    assert r.unverifiable is False
    assert [c.oracle_type for c in r.criteria] == ["command", "browser"]
    assert r.criteria[0].oracle == "npm run build"
