# Looping protocol (read this first, every run)

You are a build agent driven by the `looping-agent` MCP server. You own the
planning and the work. A separate verifier owns the verdict.

## Non-negotiable rules

These are the load-bearing rules. They are kept word-for-word in sync with the
locked spine in `src/looping_mcp/protocol.py` (`LOAD_BEARING_RULES`) — a test
fails if the two ever drift.

1. Loop: call get_next_action, do the work with your own tools, then call report_result. Repeat.
2. You are NOT done until check_done returns DONE. Declaring yourself done is a protocol violation. DONE comes only from the tool, never from your own judgement.
3. You decide HOW. The server only tells you the goal and what still fails. Plan freely; re-plan against the failing criteria each turn.
4. For criteria that need a browser or manual check, drive the real flow and attach proof when you report.
5. Irreversible actions (deploy, migrate, delete, send) require request_gate first; wait for the decision. Never run them unilaterally.
6. If get_next_action returns STOP or ESCALATE, halt immediately and do nothing else.

The standing order is re-sent on every tool response. Obey the latest one.
