"""Classifier: decides safe (auto) lane vs developer-flag, at goal intake.

Two of the three escalation triggers originate here:
  1. too risky         -> high blast radius (auth, money, data, irreversible)
  2. can't define done -> no oracle could prove this goal (unverifiable)
(The third trigger, "stuck", lives in the governor, mid-run.)

Design: the keyword pass is a SAFETY FLOOR, not the whole story. When an LLM is
available it scores blast radius + verifiability with judgement the keywords
cannot — but it may only ADD caution. If a high-blast keyword is present, or the
LLM (or the keywords) judge the goal unverifiable, we route to the developer lane
regardless of what the other source says. Caution composes; it never cancels.
"""
from __future__ import annotations
from dataclasses import dataclass

from . import llm

HIGH_BLAST = ["auth", "login", "oauth", "password", "payment", "billing", "charge",
              "refund", "migrate", "migration", "delete", "drop", "production",
              "pii", "personal data", "permission", "role", "access control"]

# crude verifiability hint: vague/aesthetic goals have no machine oracle
UNVERIFIABLE_HINTS = ["nicer", "better", "clean up", "improve ux", "modern look",
                      "feels", "polish", "tidy"]

_RISK_ORDER = {"low": 0, "medium": 1, "high": 2}

_LLM_SYSTEM = """\
You triage a software build goal for an autonomous build agent. Judge two things:
1. blast radius — could getting this wrong damage auth, money, user data, or do
   something irreversible (deploy/migrate/delete/send)?
2. verifiability — can "done" be proven by a runnable command or a driven browser
   flow, or is it purely subjective/aesthetic?

Reply with ONLY a JSON object:
{"risk":"low|medium|high","verifiable":true|false,
 "blast":["short tags of risky areas"],"reason":"one sentence"}"""


@dataclass
class Classification:
    risk: str          # low / medium / high
    lane: str          # auto / developer
    verifiable: bool
    blast: list[str]
    reason: str


def _decide(risk: str, verifiable: bool, blast: list[str]) -> tuple[str, str]:
    """Lane + reason from the merged signals. Any one red flag → developer."""
    if not verifiable:
        return ("developer",
                "Goal is too subjective to define a check for. "
                "A developer should scope what 'done' means.")
    if blast or risk == "high":
        area = f" ({', '.join(blast)})" if blast else ""
        return ("developer",
                f"Touches high-blast-radius area{area}. "
                "A developer should define criteria and review before merge.")
    return ("auto", "Low blast radius and verifiable — safe for the autonomous lane.")


def _keyword_classify(goal: str) -> Classification:
    g = goal.lower()
    blast = [k for k in HIGH_BLAST if k in g]
    verifiable = not any(h in g for h in UNVERIFIABLE_HINTS)
    risk = "high" if blast else ("medium" if not verifiable else "low")
    lane, reason = _decide(risk, verifiable, blast)
    return Classification(risk=risk, lane=lane, verifiable=verifiable,
                          blast=blast, reason=reason)


def classify(goal: str) -> Classification:
    """Keyword floor, optionally tightened (never loosened) by an LLM judgement."""
    kw = _keyword_classify(goal)
    drafted = llm.draft_json(_LLM_SYSTEM, goal)
    if not drafted:
        return kw

    # Merge conservatively: take the MORE cautious value on every axis.
    llm_risk = str(drafted.get("risk", "low")).lower()
    risk = max((kw.risk, llm_risk), key=lambda r: _RISK_ORDER.get(r, 0))
    verifiable = kw.verifiable and bool(drafted.get("verifiable", True))
    llm_blast = [str(b) for b in drafted.get("blast", []) if b]
    blast = sorted(set(kw.blast) | set(llm_blast))
    lane, reason = _decide(risk, verifiable, blast)
    # prefer the model's reason when it added the caution
    if lane == "developer" and drafted.get("reason"):
        reason = str(drafted["reason"])
    return Classification(risk=risk, lane=lane, verifiable=verifiable,
                          blast=blast, reason=reason)
