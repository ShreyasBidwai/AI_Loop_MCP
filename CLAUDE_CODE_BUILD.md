# Claude Code build guide

Feed Claude Code ONE phase at a time. After each, run the checks before moving on
(your maker/checker discipline). The scaffold in this repo is the anchor — Claude
Code fleshes the `TODO(claude-code)` markers and hardens everything.

**Standing instruction for every phase:** "Hold the architecture: the server owns
the WHAT (goal, criteria, verdict, caps), never the HOW. The agent plans. Never
let the server prescribe steps. Keep the locked protocol spine separate from the
editable slots."

---

## Phase 0 — verify the ground
**Prompt:** "Set up the repo with `uv`. Install deps. Confirm the MCP Python SDK
import path (`mcp.server.fastmcp.FastMCP`) against the current docs and fix if
changed. Run the smoke import of state/governor/classifier/criteria/protocol/checker."
**Checks:**
- [ ] `uv sync` succeeds, `mcp` imports.
- [ ] SDK tool-decorator API matches current docs (or code updated to match).
- [ ] Dependency-free modules import with no error.

## Phase 1 — state + governor
**Prompt:** "Review `state.py` and `governor.py`. Add tests: caps trigger STOP at
the boundary; stall detection triggers ESCALATE after STALL_LIMIT flat turns;
state round-trips to disk."
**Checks:**
- [ ] Turn cap → STOP exactly at MAX_TURNS.
- [ ] Flat passing-count for STALL_LIMIT turns → ESCALATE (and not before).
- [ ] State survives reload (nothing kept only in memory).

## Phase 2 — protocol (two layers)
**Prompt:** "Review `protocol.py`. Confirm the locked spine and the open slots are
separate. `standing_order()` must list current failing criteria. `assemble_kickoff`
must contain the full spine + goal + criteria."
**Checks:**
- [ ] Editing goal/criteria never touches spine text.
- [ ] `standing_order` re-lists failures every call.
- [ ] `AGENTS.md` rules match the spine word-for-word on the load-bearing rules.

## Phase 3 — the loop tools
**Prompt:** "Implement/verify `get_next_action`, `report_result`, `check_done`,
`request_gate` in `server.py`. Critical invariants: DONE only from the verifier;
every CONTINUE/FAIL response embeds the standing order; pacing actually delays;
get_next_action returns goal+failing, never a step."
**Checks:**
- [ ] Agent cannot reach DONE without `check_done` passing.
- [ ] Standing order present in every CONTINUE and FAIL response.
- [ ] Pacing delay observable (calls spaced by PACING_SECONDS).
- [ ] STOP/ESCALATE returned when governor says so; no action leaks after.

## Phase 4 — classifier + criteria + escalation
**Prompt:** "Harden `classifier.py` and `criteria.py`. Replace keyword stubs with
an LLM draft (same return shapes). Enforce: a criterion with no command/browser
oracle = `unverifiable` escalation, never a fake check. Wire all 3 triggers into
the one escalation channel with reason + handoff."
**Checks:**
- [ ] High-blast goal (auth/payments/migrate) → developer lane at intake.
- [ ] Vague/aesthetic goal → unverifiable escalation, not invented criteria.
- [ ] Stuck mid-run → escalation carries goal + progress snapshot.
- [ ] Escalation threshold tunable (not hard-coded magic).

## Phase 5 — the verifier
**Prompt:** "Harden `checker.py`. Command oracles run real shell + capture failure
detail. Browser oracles require an attached proof path or stay failing. Feed
specific failure detail back so the agent re-plans on signal, not guesses."
**Checks:**
- [ ] Failing command → criterion failing + truncated real error in `detail`.
- [ ] Browser criterion without proof never passes.
- [ ] `detail` is specific enough to act on.

## Phase 6 — dashboard
**Prompt:** "Verify `dashboard.py` serves on :3000, light theme, polls state.
Counters real (turns/actions/criteria/elapsed). Budget shown as ~estimate bar,
labelled. Show escalation + pending gate prominently."
**Checks:**
- [ ] Live updates within ~2s of a tool call.
- [ ] No number presented as exact token count; estimate clearly marked `~`.
- [ ] Escalation + gate render distinctly (developer/amber).

## Phase 7 — end-to-end dry run
**Prompt:** "Register the server in the IDE. On a SAFE low-risk goal (e.g. a copy
change in an existing component), run the full flow: propose → confirm → loop →
DONE, watching the dashboard. Then force a stall and confirm escalation fires."
**Checks:**
- [ ] Safe goal completes via the loop, DONE only after verifier passed.
- [ ] Dashboard told the story live.
- [ ] Forced stall → clean escalation with handoff, not infinite spend.
- [ ] A high-risk goal is refused at intake.

---

## Definition of done (v1)
A manager types a safe goal, confirms criteria, and watches it complete — with the
system refusing what's risky, flagging what it can't verify, and stopping cleanly
when stuck. No developer in the loop for the safe lane; a warm handoff for the rest.
