"""gitops: real git in throwaway repos. The merge must commit pending work, and a
conflict must abort cleanly (no half-merged repo, stay on the task branch)."""
from __future__ import annotations
import subprocess

import pytest

from looping_mcp import gitops


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "proj"
    r.mkdir()
    _git(["init"], r)
    _git(["branch", "-m", "main"], r)
    _git(["config", "user.email", "t@example.com"], r)
    _git(["config", "user.name", "Tester"], r)
    (r / "f.txt").write_text("hello\n")
    _git(["add", "-A"], r)
    _git(["commit", "-m", "init"], r)
    return r


def test_slug_is_safe_and_prefixed():
    s = gitops.slug("Change the Footer © 2026!!  ")
    assert s.startswith("loop/")
    assert all(ch.isalnum() or ch in "-/" for ch in s)


@pytest.mark.gitrepo
def test_is_repo_and_current_branch(repo):
    assert gitops.is_repo(str(repo)) is True
    assert gitops.current_branch(str(repo)) == "main"


@pytest.mark.gitrepo
def test_is_repo_false_outside(tmp_path):
    assert gitops.is_repo(str(tmp_path)) is False


@pytest.mark.gitrepo
def test_create_branch_then_merge_commits_pending_work(repo):
    cwd = str(repo)
    ok, _ = gitops.create_branch("loop/x", cwd)
    assert ok and gitops.current_branch(cwd) == "loop/x"

    (repo / "new.txt").write_text("feature\n")        # uncommitted work on the branch
    ok, detail = gitops.merge("loop/x", "main", "add new file", cwd)
    assert ok and "merged" in detail
    assert gitops.current_branch(cwd) == "main"
    assert (repo / "new.txt").exists()                # change landed on main
    assert gitops.is_clean(cwd)


@pytest.mark.gitrepo
def test_merge_conflict_aborts_and_stays_on_branch(repo):
    cwd = str(repo)
    # divergent edits to the same file → guaranteed conflict
    (repo / "f.txt").write_text("main side\n")
    _git(["commit", "-am", "main edit"], repo)

    gitops.create_branch("loop/y", cwd)
    # branch off main's parent so it conflicts: reset the branch to before main edit
    _git(["reset", "--hard", "HEAD~1"], repo)
    (repo / "f.txt").write_text("branch side\n")
    _git(["commit", "-am", "branch edit"], repo)

    ok, detail = gitops.merge("loop/y", "main", "y", cwd)
    assert ok is False and "conflict" in detail.lower()
    assert gitops.current_branch(cwd) == "loop/y"      # not left half-merged
    assert gitops.is_clean(cwd)                        # abort cleaned up


@pytest.mark.gitrepo
def test_merge_without_branch_is_rejected(repo):
    ok, detail = gitops.merge("", "main", "x", str(repo))
    assert ok is False and "no task branch" in detail


@pytest.mark.gitrepo
def test_toplevel_and_remote(repo):
    assert gitops.toplevel(str(repo)) == str(repo.resolve())
    assert gitops.remote_url(str(repo)) == ""        # no origin configured
    _git(["remote", "add", "origin", "https://example.com/x.git"], repo)
    assert gitops.remote_url(str(repo)) == "https://example.com/x.git"


@pytest.mark.gitrepo
def test_toplevel_empty_outside_repo(tmp_path):
    assert gitops.toplevel(str(tmp_path)) == ""
