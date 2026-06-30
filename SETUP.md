# Setup guide

Full setup for a new developer, start to finish. Tested on Linux and macOS.
Replace the two paths where noted.

Needs: [`uv`](https://docs.astral.sh/uv/) (Python tooling), and — to drive real
work — the `claude` CLI (Claude Code). `uv` handles Python itself (pulls 3.12).

## One-time setup

```bash
# 1. Install uv (skip if already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env          # load it onto PATH for this shell
# (persist for new shells: echo 'source $HOME/.local/bin/env' >> ~/.bashrc)

# 2. Get the project
git clone https://github.com/ShreyasBidwai/AI_Loop_MCP.git
cd AI_Loop_MCP

# 3. Install deps + the `loopai` / `looping-mcp` commands into .venv
uv sync

# 4. (optional) verify the build
uv run pytest -q                     # expect: 88 passed

# 5. Put `loopai` on PATH so it works from anywhere
ln -s "$(pwd)/.venv/bin/loopai" ~/.local/bin/loopai
#    (~/.local/bin is already on PATH from step 1)
```

> No `curl`? Use `wget -qO- https://astral.sh/uv/install.sh | sh`.

## Use it on a project

```bash
# 6. Register it for the project you want it to work on (run FROM that project)
cd /path/to/your-target-project
loopai register                      # adds 'looping-agent' to Claude Code here

# 7. Restart Claude Code, then inside it:
#      /mcp                 -> confirm 'looping-agent' is connected (6 tools)
#    open the dashboard:    http://127.0.0.1:3000
```

From the dashboard: type a goal -> **Propose** -> edit the criteria to your
project's real verify commands -> **Confirm & arm run** -> tell the IDE agent once
"drive the looping-agent run to DONE" -> watch it loop to green.

## Just want to see the dashboard (no IDE)

```bash
loopai dashboard                     # control panel at http://127.0.0.1:3000, Ctrl-C to stop
```

## The `loopai` command

| command | what it does |
|---|---|
| `loopai` / `loopai serve` | MCP server (backend) **+** dashboard (frontend) — what the IDE launches |
| `loopai dashboard` | **frontend only**, no stdio — open the control panel by hand, Ctrl-C to stop |
| `loopai register` | register with Claude Code for the current project |

## Notes / gotchas

- **`loopai` lives in `.venv`, not global PATH.** If you skip step 5, invoke it as
  `uv run loopai …` from the `AI_Loop_MCP` folder, or `source .venv/bin/activate`
  first, or call `<repo>/.venv/bin/loopai …` by absolute path.
- **Run `loopai register` from the target project's directory** — that's what
  scopes the registration. It writes an absolute launch path, so the IDE needs no
  PATH/`uv` dependency at launch time.
- **`/mcp` says "failed to connect"?** The IDE launched without `uv`/PATH. Either
  do step 5, or re-register with the absolute venv path (which `loopai register`
  already emits when the venv exists).
- **Don't copy a `.venv/` between machines** — it has platform-specific binaries.
  Copy the source and `uv sync` fresh (`.venv/` is gitignored anyway).
- **Verifier commands run on `/bin/sh`** in the IDE's project directory — the
  acceptance-criteria oracles must be commands that work in that project.
- **Optional LLM-drafted criteria:** `uv sync --extra llm` and put
  `ANTHROPIC_API_KEY=…` in `.env` (`cp .env.example .env`). Without it, criteria
  are generic placeholders you edit in the dashboard.

## What it is (one line)

A supervisor for a coding agent: you (or the dashboard) set a goal + checkable
criteria; the IDE agent does the work; this server holds the verdict, the caps,
and the escalations — `DONE` only ever comes from re-running the real checks. See
[`README.md`](README.md) for the architecture and [`tool_contract.md`](tool_contract.md)
for the tools.
