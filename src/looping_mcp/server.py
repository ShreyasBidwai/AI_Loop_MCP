"""MCP server: the brain + checker + governor, exposed as tools the IDE agent calls.

The loop is the AGENT'S. This server only steers it: every response re-injects the
standing order and ends by telling the agent to come back. The server never
prescribes a step (holds the WHAT, not the HOW).
"""
from __future__ import annotations
import os, sys, time, signal, uuid
from mcp.server.fastmcp import FastMCP

from . import state as st
from . import classifier, criteria, checker, governor, protocol, dashboard, escalation, gitops

mcp = FastMCP("looping-agent")

PACING_SECONDS = float(os.getenv("PACING_SECONDS", "6"))   # per-action throttle
_last_action_ts = 0.0


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)   # ~4 chars/token; estimate only, never exact


# ---------- setup: manager-facing ----------

@mcp.tool()
def propose(goal: str, repo_context: str = "") -> dict:
    """Manager types a goal. Returns risk lane + proposed criteria for confirmation.
    May escalate immediately (too risky / can't define done)."""
    # Fresh run: clear any prior run's counters, verdict, escalation and gate so a
    # new goal (e.g. typed into the dashboard) never inherits stale state.
    s = st.RunState(goal=goal, status="proposing")
    cls = classifier.classify(goal)
    s.risk, s.lane = cls.risk, cls.lane

    # Trigger 1/2: classifier flags it at intake (too risky / can't define done).
    if cls.lane == "developer":
        trigger = "risk" if cls.verifiable else "unverifiable"
        s.escalation = escalation.build(trigger, cls.reason, goal)
        s.status = "escalated"
        s.log("classifier", f"escalated at intake: {cls.reason}")
        st.save(s)
        return {"lane": "developer", "escalation": s.escalation}

    # Drafting the criteria can ALSO surface "unverifiable": if no command/browser
    # oracle is possible, escalate — never ship an invented check.
    draft = criteria.propose(goal, repo_context)
    if draft.unverifiable:
        s.escalation = escalation.build("unverifiable", draft.reason, goal)
        s.status = "escalated"
        s.log("criteria", f"escalated: {draft.reason}")
        st.save(s)
        return {"lane": "developer", "escalation": s.escalation}

    s.criteria = draft.criteria
    s.status = "awaiting_confirm"
    s.log("classifier", "low risk — proposing criteria for confirmation")
    st.save(s)
    return {"lane": "auto", "risk": s.risk,
            "criteria": [{"id": c.id, "text": c.text} for c in s.criteria],
            "note": "Manager edits/confirms criteria, then call confirm()."}


def _coerce_criterion(e: dict, by_id: dict) -> tuple[st.Criterion | None, str]:
    """Build a validated Criterion from a manager/agent edit. An item with a known
    `id` patches that criterion (any field); otherwise it's a brand-new one. The
    resulting oracle is what the verifier will actually run, so it's validated."""
    base = by_id.get(e.get("id"))
    text = str(e.get("text", base.text if base else "")).strip()
    otype = str(e.get("oracle_type", base.oracle_type if base else "")).strip().lower()
    oracle = str(e.get("oracle", base.oracle if base else "")).strip()
    if not text:
        return None, "criterion is missing 'text'"
    if otype not in ("command", "browser", "manual"):
        return None, f"criterion {text!r}: oracle_type must be command|browser|manual"
    if otype in ("command", "browser") and not oracle:
        return None, f"criterion {text!r}: a {otype} oracle must be non-empty"
    cid = e["id"] if base else uuid.uuid4().hex[:6]
    # a fresh Criterion re-arms status to pending, so a changed command is re-checked
    return st.Criterion(id=cid, text=text, oracle_type=otype, oracle=oracle), ""


@mcp.tool()
def confirm(edited_criteria: list[dict] | None = None) -> dict:
    """Manager confirms the criteria, optionally REPLACING them with the project's
    real checks, then returns the kickoff prompt.

    If `edited_criteria` is given it becomes the authoritative final list. Each item
    is {id?, text, oracle_type, oracle} where oracle_type is "command" (a shell
    command that exits 0 on success), "browser" (a flow the agent proves), or
    "manual". An item whose `id` matches a proposed criterion patches it (and
    re-arms it for checking); any other item is added new. This is how you point a
    criterion at YOUR stack — e.g. {"text":"build passes","oracle_type":"command",
    "oracle":"cargo build"}. Returns {error, details} if a criterion is malformed."""
    s = st.load()
    if edited_criteria is not None:
        by_id = {c.id: c for c in s.criteria}
        rebuilt, errors = [], []
        for e in edited_criteria:
            c, err = _coerce_criterion(e, by_id)
            (errors if err else rebuilt).append(err or c)
        if errors:
            return {"error": "invalid criteria — fix and call confirm again",
                    "details": errors}
        if not rebuilt:
            return {"error": "edited_criteria was empty — provide at least one criterion"}
        s.criteria = rebuilt
    if not s.criteria:
        return {"error": "no criteria to confirm — call propose first"}
    s.status = "running"
    s.started_at = time.time()
    s.turns = 0

    # Branch-per-task: cut a fresh branch off the current one so the agent's work
    # is isolated until the manager approves the merge. Skipped (gracefully) when
    # the project isn't a git repo.
    if gitops.is_repo():
        s.base = gitops.current_branch()
        branch = gitops.slug(s.goal)
        ok, detail = gitops.create_branch(branch)
        if ok:
            s.branch = branch
            s.log("git", f"working on branch {branch} (base {s.base})")
        else:
            s.log("git", f"could not create task branch: {detail[:160]}")

    s.log("manager", f"criteria confirmed ({len(s.criteria)}) — run started")
    st.save(s)
    return {"kickoff_prompt": protocol.assemble_kickoff(s)}


# ---------- the loop: agent-facing ----------

@mcp.tool()
def get_next_action() -> dict:
    """Agent calls this each turn. Enforces pacing + caps. Returns the goal and
    what still fails (NOT a prescribed step), or STOP / ESCALATE / DONE."""
    global _last_action_ts
    s = st.load()

    # Terminal states are sticky: once we have halted, no CONTINUE may leak back
    # out. The agent has nothing left to call (README rule 4).
    if s.status == "escalated":
        return {"directive": "ESCALATE", "escalation": s.escalation}
    if s.status == "stopped":
        return {"directive": "STOP", "reason": "run already stopped — halt."}
    if s.status == "done":
        return {"directive": "STOP", "reason": "run already verified DONE — halt."}
    if s.status == "merged":
        return {"directive": "STOP", "reason": f"task branch merged into {s.base} — halt."}
    if s.gate and s.gate.decided is None:
        return {"directive": "WAIT",
                "reason": f"human gate pending: {s.gate.action}",
                "standing_order": "Stop and wait for approval on the dashboard."}

    # A decided gate is consumed once and reported back so the agent knows the
    # verdict: approved → it may perform the action; rejected → plan around it.
    gate_decision = None
    if s.gate and s.gate.decided is not None:
        gate_decision = {"action": s.gate.action, "approved": s.gate.decided}
        s.gate = None

    v = governor.check(s)
    if v.action == "STOP":
        s.status = "stopped"; s.log("governor", v.reason); st.save(s)
        return {"directive": "STOP", "reason": v.reason}
    if v.action == "ESCALATE":
        # Trigger 3: governor sees no progress mid-run. Carry a progress snapshot.
        s.escalation = escalation.build(
            "stuck", v.reason, s.goal,
            progress={"passing": s.passing(), "total": s.total(), "turns": s.turns})
        s.status = "escalated"; s.log("governor", v.reason); st.save(s)
        return {"directive": "ESCALATE", "escalation": s.escalation}

    # pacing: hold the response to keep cadence under the rate wall + watchable
    wait = PACING_SECONDS - (time.time() - _last_action_ts)
    if wait > 0:
        time.sleep(wait)
    _last_action_ts = time.time()

    s.turns += 1
    s.actions += 1
    s.est_tokens += _estimate_tokens(s.goal + protocol.standing_order(s))
    s.log("agent", f"turn {s.turns} dispatched")
    st.save(s)
    resp = {"directive": "CONTINUE",
            "goal": s.goal,
            "failing": [{"id": c.id, "text": c.text, "detail": c.detail}
                        for c in s.failing()],
            "standing_order": protocol.standing_order(s)}
    if gate_decision is not None:
        resp["gate_decision"] = gate_decision
    return resp


@mcp.tool()
def report_result(summary: str, proof: dict | None = None) -> dict:
    """Agent reports what it did. Runs the verifier. Returns FAIL+failing (with the
    re-injected standing order) or DONE. `proof` maps criterion_id -> artifact path
    for browser/manual criteria."""
    s = st.load()

    # After a halt — or once green and awaiting/after merge — the loop is closed.
    # Never hand back a "do not stop" standing order that contradicts that.
    if s.status in ("stopped", "escalated", "ready_to_merge", "merged"):
        return {"status": "HALTED",
                "reason": f"run is {s.status}; the loop is closed — do not continue."}

    s.actions += 1
    s.est_tokens += _estimate_tokens(summary)
    s.log("agent", summary[:160])

    verdict = checker.evaluate(s, proof)

    if verdict["status"] == "DONE":
        return _finalize_green(s)
    st.save(s)
    return {"status": "FAIL",
            "failing": verdict["failing"],
            "standing_order": protocol.standing_order(s)}


def _finalize_green(s: st.RunState) -> dict:
    """All criteria pass. On a git project, raise a merge gate and ask the manager
    on the dashboard — the run isn't truly done until the task branch is merged.
    Off git, it's a plain DONE."""
    if s.branch and s.base:
        s.status = "ready_to_merge"
        s.gate = st.Gate(kind="merge",
                         action=f"merge {s.branch} into {s.base}",
                         reason="all acceptance criteria pass")
        s.log("verifier", f"all criteria pass — awaiting merge approval ({s.branch} → {s.base})")
        st.save(s)
        return {"status": "DONE",
                "message": f"All criteria pass. Awaiting merge approval on the "
                           f"dashboard ({s.branch} → {s.base}). Stop looping."}
    s.status = "done"
    s.log("verifier", "all criteria pass — DONE")
    st.save(s)
    return {"status": "DONE", "message": "Verified complete. Stop looping."}


@mcp.tool()
def check_done() -> dict:
    """Explicit verifier call. Same authority as report_result's check — DONE only
    comes from here. When it goes green on a git project, a merge gate is raised."""
    s = st.load()
    verdict = checker.evaluate(s)
    if verdict["status"] == "DONE" and s.status not in ("merged", "ready_to_merge"):
        _finalize_green(s)
        return {"status": "DONE", "failing": []}
    st.save(s)
    return verdict


@mcp.tool()
def request_gate(action: str, reason: str) -> dict:
    """Agent asks permission for an irreversible action (deploy/migrate/delete/send).
    Sets a pending gate the manager approves on the dashboard."""
    s = st.load()
    s.gate = st.Gate(action=action, reason=reason)
    s.status = "blocked_gate"
    s.log("agent", f"requested gate: {action}")
    st.save(s)
    return {"status": "PENDING",
            "standing_order": "Stop and wait for the manager's decision."}


def main() -> None:
    srv = dashboard.start_in_background()   # serves :3000 reading the same state file

    # An stdio MCP server is normally managed by the IDE, which stops it by closing
    # stdin — then mcp.run() returns and the `finally` below tears the dashboard
    # down cleanly. But when a human runs it by hand and hits Ctrl-C, stdin stays
    # open: the stdin reader thread is blocked on read, anyio can't cancel it, and
    # mcp.run() never returns (it hangs). So on a signal we hard-exit. Run state is
    # written synchronously on every tool call, so there is nothing to flush.
    def _stop(_signum=None, _frame=None):
        print("[looping-agent] stopped.", file=sys.stderr, flush=True)
        os._exit(0)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    try:
        mcp.run()   # stdio transport for the IDE; blocks until stdin closes
    finally:
        # Normal path: the IDE closed stdin, mcp.run() returned. Stop the dashboard
        # so it isn't spawning request threads as the interpreter tears down.
        try:
            srv.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
