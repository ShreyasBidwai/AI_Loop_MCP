"""The branch-per-task merge flow, end to end through the server + dashboard:
confirm cuts a branch → loop to green → a merge gate is raised → the manager's
Approve on the dashboard performs the real merge."""
from __future__ import annotations
import subprocess

import pytest

from looping_mcp import server, dashboard, state as st, gitops


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(server, "PACING_SECONDS", 0.0)
    monkeypatch.setattr(server, "_last_action_ts", 0.0)


@pytest.fixture
def repo_cwd(tmp_path, monkeypatch):
    """A throwaway git repo that is also the process working directory, so the
    server's gitops calls (which use the process cwd) operate inside it."""
    r = tmp_path / "proj"
    r.mkdir()
    _git(["init"], r)
    _git(["branch", "-m", "main"], r)
    _git(["config", "user.email", "t@example.com"], r)
    _git(["config", "user.name", "Tester"], r)
    (r / "README").write_text("x\n")
    _git(["add", "-A"], r)
    _git(["commit", "-m", "init"], r)
    monkeypatch.chdir(r)
    return r


@pytest.mark.gitrepo
def test_confirm_cuts_a_task_branch(state_file, repo_cwd):
    server.propose("add a footer link")
    server.confirm(edited_criteria=[
        {"text": "ok", "oracle_type": "command", "oracle": "true"}])
    s = st.load()
    assert s.branch.startswith("loop/") and s.base == "main"
    assert gitops.current_branch() == s.branch       # we're working on it


@pytest.mark.gitrepo
def test_green_raises_merge_gate_and_approve_merges(state_file, repo_cwd):
    server.propose("create the feature file")
    server.confirm(edited_criteria=[
        {"text": "feature.txt exists", "oracle_type": "command",
         "oracle": "test -f feature.txt"}])
    branch = st.load().branch

    # not green yet → FAIL, keep looping
    server.get_next_action()
    assert server.report_result("nothing yet")["status"] == "FAIL"

    # agent does the work on the branch
    (repo_cwd / "feature.txt").write_text("done\n")
    server.get_next_action()
    out = server.report_result("created feature.txt")
    assert out["status"] == "DONE"

    # instead of plain done, a merge gate is raised and the manager is asked
    s = st.load()
    assert s.status == "ready_to_merge"
    assert s.gate and s.gate.kind == "merge" and s.gate.decided is None

    # Approve on the dashboard → the server performs the real merge
    assert dashboard.decide_gate(True) is True
    s = st.load()
    assert s.status == "merged"
    assert s.merge_result and s.merge_result["ok"] is True
    assert gitops.current_branch() == "main"
    assert (repo_cwd / "feature.txt").exists()        # merged into main

    # loop is closed afterwards
    assert server.get_next_action()["directive"] == "STOP"


@pytest.mark.gitrepo
def test_reject_merge_leaves_work_on_the_branch(state_file, repo_cwd):
    server.propose("create another file")
    server.confirm(edited_criteria=[
        {"text": "f2 exists", "oracle_type": "command", "oracle": "test -f f2.txt"}])
    branch = st.load().branch
    (repo_cwd / "f2.txt").write_text("x\n")
    server.get_next_action()
    server.report_result("did it")
    assert st.load().status == "ready_to_merge"

    dashboard.decide_gate(False)                       # "Not yet"
    s = st.load()
    assert s.status == "done" and s.gate is None
    assert gitops.current_branch() == branch           # still on the task branch
    assert not gitops.is_clean()                        # work left uncommitted here

    # main was never advanced — it still has only the initial commit, no merge.
    count = subprocess.run(["git", "rev-list", "--count", "main"], cwd=repo_cwd,
                           capture_output=True, text=True).stdout.strip()
    assert count == "1"


@pytest.mark.gitrepo
def test_non_git_dir_stays_plain_done(state_file, tmp_path, monkeypatch):
    plain = tmp_path / "plain"
    plain.mkdir()
    monkeypatch.chdir(plain)                            # real, but not a repo
    server.propose("add a thing")
    server.confirm(edited_criteria=[
        {"text": "ok", "oracle_type": "command", "oracle": "true"}])
    assert st.load().branch == ""                       # no branch cut
    server.get_next_action()
    assert server.report_result("done")["status"] == "DONE"
    assert st.load().status == "done"                   # plain done, no merge gate
