"""Shared fixtures. Every test that touches state gets an isolated state file so
runs never collide and never pollute the repo's real .looping_state.json."""
from __future__ import annotations
import pytest

from looping_mcp import state as st
from looping_mcp import gitops


@pytest.fixture
def state_file(tmp_path, monkeypatch):
    """Redirect the durable state path into a temp dir for the test's lifetime."""
    p = tmp_path / "state.json"
    monkeypatch.setattr(st, "STATE_PATH", p)
    return p


@pytest.fixture(autouse=True)
def isolate_git(request, monkeypatch):
    """The test suite itself lives in a git repo, so confirm() would otherwise cut
    real branches in it. Treat every test as a non-git project UNLESS it opts in
    with @pytest.mark.gitrepo (those set up their own throwaway repo)."""
    if "gitrepo" in request.keywords:
        return
    monkeypatch.setattr(gitops, "is_repo", lambda cwd=None: False)


def pytest_configure(config):
    config.addinivalue_line("markers", "gitrepo: test exercises real git in a temp repo")
