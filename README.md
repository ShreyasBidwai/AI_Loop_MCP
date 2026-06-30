# Looping Agent MCP

An MCP server that turns a manager's plain-English goal into a **verified, looped, watchable** build run — driven entirely by the IDE's own agent (Antigravity / Claude Code). No SDK, no `claude -p`.

## The split (do not violate)

- **IDE agent** = the muscle + the planner. Owns the *how*. Does the file edits, runs commands, thinks in many directions.
- **This MCP server** = brain + checker + governor + dashboard. Owns the *what* (goal, criteria, verdict, caps) and the *how it's framed*. **Never dictates steps.**
- **Manager** = owns "is this what I meant" (goal + criteria confirmation).

## Locked core rules (load-bearing — never soften)

1. `DONE` comes **only** from `check_done`. The agent may never self-declare done.
2. The server returns the **goal + failing criteria**, never a prescribed step. (Hold the *what*, not the *how*.)
3. The standing order is **re-injected on every tool response** (survives context compaction).
4. Pacing + caps live in `get_next_action` — it can return `STOP` / `ESCALATE` and the agent has nothing left to call.
5. Three escalation triggers → one channel: **too risky**, **can't define done**, **stuck**. Each carries a reason + handoff.
6. Live counters show **real** numbers (turns, actions, criteria, elapsed). Token/budget is an **estimate**, labelled as such.

## Run

```bash
uv sync                  # creates the venv + installs deps
cp .env.example .env     # optional: tune caps / pacing / LLM drafting
uv run pytest            # 66 tests; all green
```

**The server is meant to be launched by your IDE, not by hand.** Register it from
**inside the project you want it to work on** — the verifier runs its command
oracles in the server's working directory, so it must be your project, not this
repo. Use `--project` (selects this package's venv) rather than `--directory`
(which would also change the cwd to here):

```bash
# run this from your target project's root:
claude mcp add looping-agent -- uv run --project /path/to/looping_MCP looping-mcp
```

The IDE starts it, speaks JSON-RPC over stdio, and stops it by closing stdin.
The watch dashboard comes up at <http://127.0.0.1:3000>.

### Running it by hand (to watch the dashboard)

`uv run looping-mcp` works, but it's a **stdio server**: that terminal becomes its
JSON-RPC input. Don't type shell commands into it — anything you type is parsed as
a protocol message and rejected (`Invalid JSON…`). Open the dashboard URL in a
browser, leave the terminal alone, and press **Ctrl-C** to stop it (clean exit;
use a *separate* terminal for other commands).

> Note: `stdout` is reserved for the JSON-RPC channel — all diagnostics go to `stderr`.

Register in the IDE's MCP config (see `specs/tool_contract.md`).

## Build it

You are not meant to hand-write this. Open `CLAUDE_CODE_BUILD.md` and feed Claude Code one phase at a time, running the checks after each. The scaffold here is the anchor; Claude Code fleshes the TODOs.
