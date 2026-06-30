"""The verifier is the only source of DONE. Command oracles run a real shell and
capture actionable failure detail; browser/manual oracles never pass without real
attached proof."""
from __future__ import annotations

from looping_mcp import checker
from looping_mcp import state as st


def _state(*criteria):
    s = st.RunState(goal="g")
    s.criteria = list(criteria)
    return s


def _crit(id, otype, oracle="", status="pending"):
    return st.Criterion(id=id, text=f"crit {id}", oracle_type=otype,
                        oracle=oracle, status=status)


# ---- command oracles ----

def test_passing_command_passes_with_no_detail():
    s = _state(_crit("ok", "command", "true"))
    v = checker.evaluate(s)
    assert v["status"] == "DONE"
    assert s.criteria[0].status == "passing"
    assert s.criteria[0].detail == ""


def test_failing_command_captures_cmd_exit_and_output():
    s = _state(_crit("bad", "command", "echo boom-detail >&2; exit 3"))
    v = checker.evaluate(s)
    assert v["status"] == "FAIL"
    c = s.criteria[0]
    assert c.status == "failing"
    assert "exited 3" in c.detail          # real exit code
    assert "boom-detail" in c.detail       # real stderr captured
    assert c.oracle in c.detail            # names the command — actionable
    # and the failure detail is surfaced upward to the agent
    assert v["failing"][0]["detail"] == c.detail


def test_command_output_is_truncated():
    # 50k of output must not blow up the detail field
    big = "python3 -c \"print('x'*50000); raise SystemExit(1)\""
    s = _state(_crit("big", "command", big))
    checker.evaluate(s)
    d = s.criteria[0].detail
    assert "omitted" in d and len(d) < 3000


def test_timeout_is_reported(monkeypatch):
    monkeypatch.setattr(checker, "ORACLE_TIMEOUT", 1)
    s = _state(_crit("slow", "command", "sleep 5"))
    checker.evaluate(s)
    assert s.criteria[0].status == "failing"
    assert "timed out" in s.criteria[0].detail


# ---- browser / manual oracles need real proof ----

def test_browser_without_proof_never_passes():
    s = _state(_crit("ui", "browser", "drive the flow"))
    v = checker.evaluate(s)
    assert v["status"] == "FAIL"
    assert s.criteria[0].status == "failing"
    assert "no browser proof" in s.criteria[0].detail


def test_browser_with_nonexistent_proof_path_fails():
    s = _state(_crit("ui", "browser"))
    v = checker.evaluate(s, proof={"ui": "/no/such/recording.mp4"})
    assert v["status"] == "FAIL"
    assert "proof not found" in s.criteria[0].detail


def test_browser_with_existing_proof_file_passes(tmp_path):
    art = tmp_path / "flow.png"
    art.write_text("fake recording")
    s = _state(_crit("ui", "browser"))
    v = checker.evaluate(s, proof={"ui": str(art)})
    assert v["status"] == "DONE"
    assert s.criteria[0].status == "passing"
    assert str(art) in s.criteria[0].detail


def test_browser_with_url_proof_passes():
    s = _state(_crit("ui", "browser"))
    v = checker.evaluate(s, proof={"ui": "https://example.com/run/123/video"})
    assert v["status"] == "DONE"
    assert s.criteria[0].status == "passing"


def test_manual_without_proof_fails():
    s = _state(_crit("ok", "command", "true"), _crit("hum", "manual"))
    v = checker.evaluate(s)
    assert v["status"] == "FAIL"
    assert "awaiting human confirmation" in s.criteria[1].detail


def test_mixed_criteria_overall_verdict_and_history():
    s = _state(_crit("ok", "command", "true"),
               _crit("bad", "command", "false"))
    v = checker.evaluate(s)
    assert v["status"] == "FAIL"
    assert s.passing() == 1 and s.total() == 2
    assert s.passing_history[-1] == 1     # convergence tracking advanced
