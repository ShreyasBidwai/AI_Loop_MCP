"""The verifier. DONE comes from here and nowhere else.

Three tiers, on purpose:
  - command oracles: run a real shell command, pass on exit 0. (tests, build, lint)
    On failure we capture the command, the exit code, and the real output tail so
    the agent re-plans on a concrete signal — not a guess.
  - browser/manual oracles: the agent must ATTACH proof (an artifact path that
    exists on disk, or a URL). "Tests pass" is not "the product is right" — a
    manager needs to SEE the flow. No proof → the criterion stays failing.

Returns a strict machine verdict so the agent has nothing left to self-judge.
"""
from __future__ import annotations
import os
import subprocess
from pathlib import Path

from .state import RunState

ORACLE_TIMEOUT = int(os.getenv("ORACLE_TIMEOUT", "600"))   # seconds; tunable
_HEAD = 600     # keep the start (where the first error usually is) ...
_TAIL = 1400    # ... and the end (final summary line), drop the noisy middle


def _truncate(text: str) -> str:
    text = text.strip()
    if len(text) <= _HEAD + _TAIL:
        return text
    omitted = len(text) - _HEAD - _TAIL
    return f"{text[:_HEAD]}\n…[{omitted} chars omitted]…\n{text[-_TAIL:]}"


def _run_command(cmd: str, timeout: int | None = None) -> tuple[bool, str]:
    """Run a shell command. Return (passed, detail). On failure `detail` names the
    command, the exit code, and the real combined output — specific enough to act on."""
    timeout = ORACLE_TIMEOUT if timeout is None else timeout   # read at call time
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"`{cmd}` timed out after {timeout}s (no exit)."
    except Exception as e:                       # pragma: no cover - defensive
        return False, f"`{cmd}` could not run: {type(e).__name__}: {e}"

    if p.returncode == 0:
        return True, ""
    output = _truncate((p.stdout or "") + (p.stderr or ""))
    detail = f"`{cmd}` exited {p.returncode}."
    if output:
        detail += f"\n{output}"
    return False, detail


def _proof_ok(value: str) -> bool:
    """A proof is real if it's a URL or an artifact path that actually exists.
    An empty string or a path to nothing is not proof."""
    value = (value or "").strip()
    if not value:
        return False
    if value.startswith(("http://", "https://")):
        return True
    return Path(value).exists()


def evaluate(s: RunState, proof: dict | None = None) -> dict:
    """proof: optional {criterion_id: artifact_path|url} supplied by the agent for
    browser/manual criteria. Returns {status: DONE|FAIL, failing: [...]}."""
    proof = proof or {}
    for c in s.criteria:
        if c.oracle_type == "command":
            ok, detail = _run_command(c.oracle)
            c.status = "passing" if ok else "failing"
            c.detail = detail

        elif c.oracle_type in ("browser", "manual"):
            attached = proof.get(c.id)
            if _proof_ok(attached):
                c.status = "passing"
                c.detail = f"proof: {attached}"
            else:
                c.status = "failing"
                if attached:
                    c.detail = (f"proof not found ({attached}) — attach a real "
                                f"artifact path or URL")
                elif c.oracle_type == "browser":
                    c.detail = ("no browser proof attached — drive the flow and "
                                "attach the recording/screenshot path in report_result")
                else:
                    c.detail = ("awaiting human confirmation — attach the approval "
                                "reference in report_result")

    s.passing_history.append(s.passing())
    failing = [{"id": c.id, "text": c.text, "detail": c.detail} for c in s.failing()]
    return {"status": "DONE" if not failing else "FAIL", "failing": failing}
