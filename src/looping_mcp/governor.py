"""The resource governor + convergence guard.

This is the seatbelt for a manager-run, no-developer loop. It is the only thing
that stops a runaway when the goal was never verifiable. It does NOT measure real
tokens (the IDE burns those, out of our reach) — it enforces turn/estimate caps
and detects thrashing.
"""
from __future__ import annotations
import os
from dataclasses import dataclass
from .state import RunState

MAX_TURNS = int(os.getenv("MAX_TURNS", "40"))
MAX_EST_TOKENS = int(os.getenv("MAX_EST_TOKENS", "400000"))
STALL_LIMIT = int(os.getenv("STALL_LIMIT", "6"))   # turns with no new criterion passing


@dataclass
class Verdict:
    action: str    # CONTINUE | STOP | ESCALATE
    reason: str = ""


def check(s: RunState) -> Verdict:
    if s.turns >= MAX_TURNS:
        return Verdict("STOP", f"turn cap reached ({MAX_TURNS})")
    if s.est_tokens >= MAX_EST_TOKENS:
        return Verdict("STOP", f"estimated token cap reached (~{MAX_EST_TOKENS})")

    # convergence: passing count must keep climbing, else we're thrashing.
    hist = s.passing_history
    if len(hist) >= STALL_LIMIT:
        window = hist[-STALL_LIMIT:]
        if max(window) == min(window) and s.passing() < s.total():
            return Verdict("ESCALATE",
                           f"no progress for {STALL_LIMIT} turns at "
                           f"{s.passing()}/{s.total()} criteria — stuck")
    return Verdict("CONTINUE")
