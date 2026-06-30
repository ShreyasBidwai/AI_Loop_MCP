# Tool contract

The MCP server exposes 6 tools. Setup tools are manager-facing (called by the
dashboard / MCP App). Loop tools are agent-facing.

## Setup (manager-facing)

### `propose(goal, repo_context?) -> dict`
Classifies the goal. Returns either:
- `{lane:"developer", escalation:{trigger, reason, handoff}}` — too risky OR
  can't define done. Stop; route to a developer.
- `{lane:"auto", risk, criteria:[{id,text}], note}` — proceed to confirm.

### `confirm(edited_criteria?) -> {kickoff_prompt}`
Manager confirms/edits criteria. Returns the assembled kickoff prompt
(locked spine + goal/criteria slots) to start the IDE agent with.

## Loop (agent-facing)

### `get_next_action() -> dict`
Enforces pacing + caps. Returns one of:
- `{directive:"CONTINUE", goal, failing:[...], standing_order}` — keep going.
- `{directive:"STOP", reason}` — cap hit. Halt.
- `{directive:"ESCALATE", escalation}` — stuck. Halt, hand off.
- `{directive:"WAIT", reason, standing_order}` — gate pending.
> Never returns a prescribed step. Only goal + what fails.

### `report_result(summary, proof?) -> dict`
Runs the verifier. Returns:
- `{status:"DONE", message}` — verified complete. Stop.
- `{status:"FAIL", failing:[...], standing_order}` — keep fixing.
`proof` = `{criterion_id: artifact_path}` for browser/manual criteria.

### `check_done() -> {status, failing}`
Explicit verifier call. Same authority as the check inside `report_result`.

### `request_gate(action, reason) -> {status:"PENDING", standing_order}`
Agent asks permission for an irreversible action. Manager decides on dashboard.

## Three escalation triggers → one channel

| Trigger | Where | Meaning |
|---|---|---|
| risk | `propose` (intake) | high blast radius — developer owns it |
| unverifiable | `propose` (intake) | no oracle possible — developer scopes "done" |
| stuck | `governor` (mid-run) | no progress N turns — warm handoff |

## IDE registration (Python, stdio)

```json
{ "mcpServers": {
  "looping-agent": { "command": "python", "args": ["-m", "looping_mcp.server"] }
}}
```
Antigravity: `.agents/mcp_config.json` or `~/.gemini/config/mcp_config.json`.
Claude Code: `.mcp.json` / `claude mcp add`.
> Verify exact config path + the MCP Python SDK API against current docs — both move.
