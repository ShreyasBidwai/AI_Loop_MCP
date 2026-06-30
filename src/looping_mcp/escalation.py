"""One escalation channel, three triggers.

| trigger      | origin               | meaning                                   |
|--------------|----------------------|-------------------------------------------|
| risk         | classifier (intake)  | high blast radius — a developer owns it    |
| unverifiable | classifier/criteria  | no machine oracle possible — scope "done"  |
| stuck        | governor (mid-run)   | no progress for N turns — warm handoff     |

Every escalation, whatever its origin, is built here so the shape is identical:
a trigger, a human-readable reason, and a handoff payload that always carries the
goal (plus a progress snapshot when we have one). The dashboard renders this; a
developer picks it up from it.
"""
from __future__ import annotations
from typing import Optional

VALID_TRIGGERS = ("risk", "unverifiable", "stuck")


def build(trigger: str, reason: str, goal: str,
          progress: Optional[dict] = None) -> dict:
    """Construct an escalation. `progress` is the {passing,total,...} snapshot
    when we have one (the 'stuck' trigger); intake triggers omit it."""
    if trigger not in VALID_TRIGGERS:
        raise ValueError(f"unknown escalation trigger: {trigger!r}")
    handoff: dict = {"goal": goal}
    if progress:
        handoff.update(progress)
    return {"trigger": trigger, "reason": reason, "handoff": handoff}
