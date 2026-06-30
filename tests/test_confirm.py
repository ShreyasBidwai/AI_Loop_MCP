"""confirm() lets the manager point criteria at the real project's verify
commands — patching proposed ones or replacing them wholesale — and validates
the oracle the verifier will actually run."""
from __future__ import annotations

from looping_mcp import server, state as st


def _proposed(state_file):
    """Two placeholder criteria, as propose() would leave them."""
    s = st.RunState(goal="g", status="awaiting_confirm", lane="auto")
    s.criteria = [
        st.Criterion(id="aaa", text="Build succeeds", oracle_type="command", oracle="npm run build"),
        st.Criterion(id="bbb", text="Tests pass", oracle_type="command", oracle="pytest -q"),
    ]
    st.save(s)
    return s


def test_no_args_keeps_proposed_criteria(state_file):
    _proposed(state_file)
    out = server.confirm()
    assert "kickoff_prompt" in out
    s = st.load()
    assert s.status == "running"
    assert [c.oracle for c in s.criteria] == ["npm run build", "pytest -q"]


def test_patch_existing_oracle_by_id(state_file):
    _proposed(state_file)
    out = server.confirm(edited_criteria=[
        {"id": "aaa", "text": "Build succeeds", "oracle_type": "command", "oracle": "cargo build"},
        {"id": "bbb", "text": "Tests pass", "oracle_type": "command", "oracle": "cargo test"},
    ])
    assert "kickoff_prompt" in out
    s = st.load()
    assert [c.oracle for c in s.criteria] == ["cargo build", "cargo test"]
    assert all(c.status == "pending" for c in s.criteria)   # re-armed for checking


def test_replace_with_brand_new_criteria(state_file):
    _proposed(state_file)
    server.confirm(edited_criteria=[
        {"text": "lints clean", "oracle_type": "command", "oracle": "ruff check ."},
        {"text": "page renders", "oracle_type": "browser", "oracle": "open /home"},
    ])
    s = st.load()
    assert len(s.criteria) == 2
    assert [c.text for c in s.criteria] == ["lints clean", "page renders"]
    assert s.criteria[0].oracle == "ruff check ."
    # new criteria get generated ids
    assert all(c.id and c.id not in ("aaa", "bbb") for c in s.criteria)


def test_command_oracle_cannot_be_empty(state_file):
    _proposed(state_file)
    out = server.confirm(edited_criteria=[
        {"text": "build", "oracle_type": "command", "oracle": ""},
    ])
    assert "error" in out and out["details"]
    # state not flipped to running on a bad confirm
    assert st.load().status == "awaiting_confirm"


def test_bad_oracle_type_rejected(state_file):
    _proposed(state_file)
    out = server.confirm(edited_criteria=[
        {"text": "x", "oracle_type": "vibes", "oracle": "feel it"},
    ])
    assert "error" in out


def test_empty_edit_list_is_rejected(state_file):
    _proposed(state_file)
    out = server.confirm(edited_criteria=[])
    assert "error" in out
    assert st.load().status == "awaiting_confirm"


def test_confirm_then_verifier_runs_the_real_command(state_file, tmp_path):
    server.PACING_SECONDS = 0.0
    server._last_action_ts = 0.0
    marker = tmp_path / "done.txt"
    s = st.RunState(goal="g", status="awaiting_confirm")
    s.criteria = [st.Criterion(id="x", text="placeholder", oracle_type="command", oracle="false")]
    st.save(s)
    # point it at a real check, then drive one loop
    server.confirm(edited_criteria=[
        {"id": "x", "text": "artifact exists", "oracle_type": "command",
         "oracle": f"test -f {marker}"},
    ])
    server.get_next_action()
    assert server.report_result("not yet")["status"] == "FAIL"
    marker.write_text("ok")
    server.get_next_action()
    assert server.report_result("did it")["status"] == "DONE"
