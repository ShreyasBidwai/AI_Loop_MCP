"""Git orchestration for the branch-per-task flow.

The server bends its "never do the HOW" rule for exactly two contained git
operations: cut a task branch at confirm, and merge it back on the manager's
approval. Everything here is defensive — it checks it's in a repo, captures real
git output, and on a merge conflict aborts and stays on the task branch rather
than leaving the repo half-merged.

All functions take an optional cwd (defaults to the process working directory,
which for an IDE-launched server is the target project).
"""
from __future__ import annotations
import re
import subprocess
import uuid


def _git(args: list[str], cwd: str | None = None) -> tuple[bool, str]:
    try:
        p = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                           text=True, timeout=120)
    except FileNotFoundError:
        return False, "git is not installed"
    except subprocess.TimeoutExpired:
        return False, f"git {' '.join(args)} timed out"
    out = (p.stdout + p.stderr).strip()
    return p.returncode == 0, out


def is_repo(cwd: str | None = None) -> bool:
    ok, out = _git(["rev-parse", "--is-inside-work-tree"], cwd)
    return ok and out.strip() == "true"


def current_branch(cwd: str | None = None) -> str:
    ok, out = _git(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
    return out.strip() if ok else ""


def toplevel(cwd: str | None = None) -> str:
    """Absolute path of the repo root, or "" if not in a repo."""
    ok, out = _git(["rev-parse", "--show-toplevel"], cwd)
    return out.strip() if ok else ""


def remote_url(cwd: str | None = None) -> str:
    """origin's URL, or "" if there's no origin / not a repo."""
    ok, out = _git(["remote", "get-url", "origin"], cwd)
    return out.strip() if ok else ""


def is_clean(cwd: str | None = None) -> bool:
    ok, out = _git(["status", "--porcelain"], cwd)
    return ok and out.strip() == ""


def slug(goal: str) -> str:
    """A safe, unique-ish branch name from a goal: loop/<slug>-<4hex>."""
    s = re.sub(r"[^a-z0-9]+", "-", goal.lower()).strip("-")[:40].strip("-")
    return f"loop/{s or 'task'}-{uuid.uuid4().hex[:4]}"


def create_branch(name: str, cwd: str | None = None) -> tuple[bool, str]:
    """Cut and switch to a new branch from the current HEAD."""
    ok, out = _git(["checkout", "-b", name], cwd)
    return ok, out


def merge(branch: str, base: str, goal: str, cwd: str | None = None) -> tuple[bool, str]:
    """Commit any pending work on `branch`, then merge it into `base` with a merge
    commit. On conflict, abort and return to `branch` so the repo is never left in
    a half-merged state. Returns (ok, human-readable detail)."""
    if not is_repo(cwd):
        return False, "not a git repository"
    if not branch or not base:
        return False, "no task branch recorded for this run"

    # make sure the branch carries the work as commits (the merge needs them)
    if not is_clean(cwd):
        ok, out = _git(["add", "-A"], cwd)
        if not ok:
            return False, f"git add failed: {out}"
        ok, out = _git(["commit", "-m", f"loop: {goal}"[:200]], cwd)
        if not ok:
            return False, f"git commit failed: {out}"

    ok, out = _git(["checkout", base], cwd)
    if not ok:
        return False, f"could not switch to base {base!r}: {out}"

    ok, out = _git(["merge", "--no-ff", "-m", f"Merge {branch}: {goal}"[:200], branch], cwd)
    if not ok:
        _git(["merge", "--abort"], cwd)
        _git(["checkout", branch], cwd)           # leave them where the work is
        return False, f"merge conflict — aborted, stayed on {branch}. {out[-800:]}"

    return True, f"merged {branch} into {base}"
