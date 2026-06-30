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

## Branch-per-task & the merge gate

On a git project, each task is isolated and merged only on the manager's say-so:

1. `confirm` cuts a fresh task branch (`loop/<slug>-<hash>`) off the current branch (the *base*); the agent does all its work there.
2. When **every** criterion goes green, the run doesn't silently finish — it enters `ready_to_merge` and the dashboard shows **"✅ all criteria pass — merge `branch` → `base`?"**
3. The manager clicks **Merge** (or **Not yet**). On approve, the server commits any pending work and runs `git merge --no-ff`; a conflict aborts cleanly and leaves the work on the task branch. On reject, the work stays on the branch for a human.

Off git (not a repo), it's a plain `DONE` with no branch or merge gate.

## Run

> New here? **[`SETUP.md`](SETUP.md)** has the full copy-paste setup for a fresh machine.

```bash
uv sync                  # creates the venv + installs deps
cp .env.example .env     # optional: tune caps / pacing / LLM drafting
uv run pytest            # 88 tests; all green
```

**The server is meant to be launched by your IDE, not by hand.** Register it from
**inside the project you want it to work on** — the verifier runs its command
oracles in the server's working directory, so it must be your project, not this
repo. Use `--project` (selects this package's venv) rather than `--directory`
(which would also change the cwd to here):

```bash
# run this from your target project's root — registers + pins this package:
loopai register
# (equivalent to: claude mcp add looping-agent -- uv run --project /path/to/looping_MCP loopai serve)
```

The IDE starts it, speaks JSON-RPC over stdio, and stops it by closing stdin.
The watch dashboard comes up at <http://127.0.0.1:3000>.

### The `loopai` command

| command | what it does |
|---|---|
| `loopai` / `loopai serve` | MCP server (backend) **+** dashboard (frontend) — what the IDE launches |
| `loopai dashboard` | **frontend only**, no stdio — open the control panel by hand, Ctrl-C to stop |
| `loopai register` | register with Claude Code for the current project |

> **`loopai` lives in the project's `.venv`, not on your global PATH.** After
> `uv sync`, invoke it one of these ways:
> - `uv run loopai …` — from the looping_MCP folder, or
> - `source .venv/bin/activate` then `loopai …`, or
> - by absolute path from anywhere: `/abs/looping_MCP/.venv/bin/loopai …`
>   (add that dir to PATH, or `ln -s` it into `~/.local/bin`, for a bare `loopai`).
>
> `loopai register` writes an absolute-path launch command, so the IDE can start
> the server with no PATH/uv dependency — run it from your **target project** dir
> (that's the project the registration is scoped to).

### Running it by hand (to watch the dashboard)

Use **`loopai dashboard`** — it serves the control panel with no stdio, so the
terminal stays a normal terminal (just press Ctrl-C to stop). Avoid `loopai serve`
by hand: that's a **stdio server**, so the terminal becomes its JSON-RPC input and
anything you type is rejected as a protocol message.

> Note: `stdout` is reserved for the JSON-RPC channel — all diagnostics go to `stderr`.

Register in the IDE's MCP config (see `specs/tool_contract.md`).

## Build it

You are not meant to hand-write this. Open `CLAUDE_CODE_BUILD.md` and feed Claude Code one phase at a time, running the checks after each. The scaffold here is the anchor; Claude Code fleshes the TODOs.
