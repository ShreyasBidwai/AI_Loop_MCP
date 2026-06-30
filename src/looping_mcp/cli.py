"""`loopai` — friendly launcher for the looping-agent MCP.

Usage:
  loopai             Run the MCP server (backend) + dashboard (frontend).
  loopai serve       Same as above. This is what an IDE registration launches.
  loopai dashboard   Run ONLY the dashboard / control panel (no stdio), Ctrl-C to
                     stop. Use this to open the panel by hand without the terminal
                     turning into a JSON-RPC stream.
  loopai register    Register the server with Claude Code for the CURRENT project
                     (so the verifier runs against this repo).
  loopai -h|--help   Show this help.
"""
from __future__ import annotations
import os, sys, signal, subprocess
from pathlib import Path

# The looping_MCP project root (…/src/looping_mcp/cli.py → parents[2]).
PKG_ROOT = Path(__file__).resolve().parents[2]


def _serve() -> None:
    """Backend (MCP stdio) + frontend (dashboard), via the server entrypoint."""
    from . import server
    server.main()


def _dashboard_only() -> None:
    """Frontend only. Blocks until a signal, then exits cleanly."""
    from . import dashboard
    dashboard.start_in_background()
    print(f"[loopai] control panel at http://127.0.0.1:{dashboard.PORT} — Ctrl-C to stop.",
          file=sys.stderr, flush=True)

    def _stop(_signum=None, _frame=None):
        print("[loopai] stopped.", file=sys.stderr, flush=True)
        os._exit(0)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    signal.pause()   # sleep until SIGINT/SIGTERM; no busy loop


def _launch_argv() -> list[str]:
    """How the IDE should start the server. Prefer the venv's console script
    (absolute path — needs neither PATH nor uv, runs in the IDE's project dir);
    fall back to `uv run` if the venv isn't built yet."""
    bindir = "Scripts" if os.name == "nt" else "bin"
    script = PKG_ROOT / ".venv" / bindir / "loopai"
    if script.exists():
        return [str(script), "serve"]
    return ["uv", "run", "--project", str(PKG_ROOT), "loopai", "serve"]


def _register() -> int:
    """Register with Claude Code for the project in the CURRENT directory. The
    server is launched from this package's venv, so it uses these deps while
    running in (and verifying against) the caller's project."""
    target = os.getcwd()
    cmd = ["claude", "mcp", "add", "looping-agent", "--", *_launch_argv()]
    try:
        subprocess.run(cmd, check=True)
        print(f"[loopai] registered 'looping-agent' for project: {target}", file=sys.stderr)
        print("[loopai] restart your IDE, then run /mcp to confirm it connected.",
              file=sys.stderr)
        return 0
    except FileNotFoundError:
        print("[loopai] 'claude' CLI not found. Register manually with:\n  "
              + " ".join(cmd), file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as e:
        print(f"[loopai] registration failed (exit {e.returncode}). Command was:\n  "
              + " ".join(cmd), file=sys.stderr)
        return e.returncode


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    cmd = argv[0] if argv else "serve"
    if cmd in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    if cmd == "serve":
        _serve()
        return 0
    if cmd == "dashboard":
        _dashboard_only()
        return 0
    if cmd == "register":
        return _register()
    print(f"loopai: unknown command {cmd!r}\n\n{__doc__}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
