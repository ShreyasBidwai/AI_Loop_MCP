"""Shared fixtures. Every test that touches state gets an isolated state file so
runs never collide and never pollute the repo's real .looping_state.json."""
from __future__ import annotations
import pytest

from looping_mcp import state as st


@pytest.fixture
def state_file(tmp_path, monkeypatch):
    """Redirect the durable state path into a temp dir for the test's lifetime."""
    p = tmp_path / "state.json"
    monkeypatch.setattr(st, "STATE_PATH", p)
    return p
