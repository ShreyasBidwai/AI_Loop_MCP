"""Criteria proposal: turn a plain goal into checkable acceptance criteria.

THE KEYSTONE. The manager replaces the developer everywhere except defining
"done" — so this step authors the criteria + their oracles, then the manager
confirms them in plain language before any loop starts.

Hard rule: every criterion needs a MACHINE oracle — a runnable "command" or a
driven "browser" flow. If the goal cannot be reduced to at least one machine
oracle, that is the "can't define done" escalation: we return `unverifiable`
with a reason and DO NOT invent a fake check. A green check that proves nothing
is worse than an honest escalation.

When an LLM is available it drafts criteria from the goal (+ repo context). When
it is not, a deterministic template scaffold keeps the pipeline runnable; the
manager edits it before confirming. Criterion text stays in product language
(manager-readable); the oracle stays technical.
"""
from __future__ import annotations
import uuid
from dataclasses import dataclass, field

from . import llm
from .state import Criterion

MACHINE_ORACLES = ("command", "browser")

_LLM_SYSTEM = """\
Turn a software build goal into acceptance criteria for an autonomous build agent.
Each criterion MUST be provable by a machine oracle:
  - "command": a shell command that exits 0 on success (build/test/lint/etc).
  - "browser": a real UI flow the agent drives and attaches proof of.
Criterion text is plain product language a non-engineer can confirm. The oracle is
technical. Prefer concrete commands you can infer from the goal/context; do not
invent a command for a stack you cannot see — use a browser oracle instead.

If "done" for this goal cannot be proven by ANY command or browser flow (it is
purely subjective/aesthetic), do NOT invent criteria.

Reply with ONLY a JSON object:
{"verifiable":true,
 "criteria":[{"text":"...","oracle_type":"command|browser","oracle":"..."}]}
or, if unverifiable:
{"verifiable":false,"reason":"one sentence on why no oracle is possible"}"""


@dataclass
class CriteriaResult:
    """Either a usable set of criteria, or an unverifiable escalation signal."""
    criteria: list[Criterion] = field(default_factory=list)
    unverifiable: bool = False
    reason: str = ""


def _cid() -> str:
    return uuid.uuid4().hex[:6]


def _template_scaffold(goal: str) -> list[Criterion]:
    """Deterministic fallback when no LLM is available. A starting point the
    manager edits — not a claim that these are the right checks."""
    return [
        Criterion(id=_cid(), text="Build succeeds", oracle_type="command",
                  oracle="npm run build"),
        Criterion(id=_cid(), text="Test suite passes", oracle_type="command",
                  oracle="pytest -q"),
        Criterion(id=_cid(), text="No new lint errors", oracle_type="command",
                  oracle="ruff check ."),
        Criterion(id=_cid(), text=f"Feature works end to end: {goal}",
                  oracle_type="browser",
                  oracle="drive the real flow, record proof"),
    ]


def _from_llm(drafted: dict) -> CriteriaResult:
    """Validate an LLM draft. Drop criteria without a machine oracle; if none
    survive (or the model flagged it), escalate as unverifiable — never fake one."""
    if drafted.get("verifiable") is False:
        return CriteriaResult(unverifiable=True,
                              reason=str(drafted.get("reason")
                                         or "No machine oracle is possible for this goal."))
    out: list[Criterion] = []
    for c in drafted.get("criteria", []):
        otype = str(c.get("oracle_type", "")).lower()
        oracle = str(c.get("oracle", "")).strip()
        text = str(c.get("text", "")).strip()
        if otype in MACHINE_ORACLES and oracle and text:
            out.append(Criterion(id=_cid(), text=text, oracle_type=otype, oracle=oracle))
    if not out:
        return CriteriaResult(unverifiable=True,
                              reason="Could not derive a single command or browser "
                                     "oracle for this goal — a developer should scope 'done'.")
    return CriteriaResult(criteria=out)


def propose(goal: str, repo_context: str = "") -> CriteriaResult:
    """Draft acceptance criteria, or escalate as unverifiable. Same call shape
    whether or not an LLM is configured."""
    user = f"GOAL: {goal}"
    if repo_context:
        user += f"\n\nREPO CONTEXT:\n{repo_context}"
    drafted = llm.draft_json(_LLM_SYSTEM, user)
    if drafted:
        return _from_llm(drafted)
    return CriteriaResult(criteria=_template_scaffold(goal))
