"""Two-layer prompt.

LOCKED SPINE (this file, you own it, versioned) — protocol + escalation rules.
OPEN SLOTS (goal, criteria) — filled per run, the manager confirms them.

The manager edits the slots; never the spine. Keep them separate so tuning the
spine is a measurable optimization (version it, A/B it), not silent drift.

The load-bearing rules are defined ONCE here, as canonical strings, and the spine
is composed from them. `AGENTS.md` must carry these same strings word-for-word so
the prompt the agent boots with and the doc it reads cannot drift apart. The test
suite enforces that equality (see tests/test_protocol.py).
"""
from __future__ import annotations
from .state import RunState

SPINE_VERSION = "v1"

# The non-negotiables. Edited here and ONLY here. Each string is reproduced
# verbatim in AGENTS.md — a test fails if the two ever diverge.
LOAD_BEARING_RULES = (
    "Loop: call get_next_action, do the work with your own tools, then call "
    "report_result. Repeat.",
    "You are NOT done until check_done returns DONE. Declaring yourself done is a "
    "protocol violation. DONE comes only from the tool, never from your own judgement.",
    "You decide HOW. The server only tells you the goal and what still fails. Plan "
    "freely; re-plan against the failing criteria each turn.",
    "For criteria that need a browser or manual check, drive the real flow and "
    "attach proof when you report.",
    "Irreversible actions (deploy, migrate, delete, send) require request_gate "
    "first; wait for the decision. Never run them unilaterally.",
    "If get_next_action returns STOP or ESCALATE, halt immediately and do nothing else.",
)

_RULES_BLOCK = "\n".join(f"- {r}" for r in LOAD_BEARING_RULES)

LOCKED_SPINE = f"""\
You are a looping build agent. You do the planning and the work; a separate
verifier decides whether you are done.

PROTOCOL (non-negotiable):
{_RULES_BLOCK}
"""


def standing_order(s: RunState) -> str:
    """Re-injected on EVERY tool response so it survives context compaction.
    Always re-lists the criteria that currently fail — never a cached list."""
    fails = s.failing()
    if not fails:
        return "All criteria pass. Call check_done to confirm DONE."
    lines = "\n".join(f"  - {c.text}" + (f" ({c.detail})" if c.detail else "")
                      for c in fails)
    return ("Do not stop. Criteria still failing:\n" + lines +
            "\nFix them, then call report_result again.")


def assemble_kickoff(s: RunState) -> str:
    """Full framed prompt the agent is started with = spine + slots.
    Contains the complete locked spine plus this run's goal and criteria."""
    crit = "\n".join(f"  - {c.text}" for c in s.criteria)
    return (f"{LOCKED_SPINE}\n"
            f"--- THIS RUN ---\n"
            f"END GOAL: {s.goal}\n"
            f"ACCEPTANCE CRITERIA (done = all pass):\n{crit}\n\n"
            f"Begin by calling get_next_action.")
