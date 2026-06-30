"""`loopai` dispatch. We don't launch real servers here — we verify the command
router calls the right entrypoint and handles help/unknown commands."""
from __future__ import annotations

from looping_mcp import cli


def test_default_and_serve_route_to_serve(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_serve", lambda: calls.append("serve"))
    assert cli.main([]) == 0           # no args → serve
    assert cli.main(["serve"]) == 0
    assert calls == ["serve", "serve"]


def test_dashboard_routes_to_dashboard_only(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_dashboard_only", lambda: calls.append("dash"))
    assert cli.main(["dashboard"]) == 0
    assert calls == ["dash"]


def test_register_routes_to_register(monkeypatch):
    monkeypatch.setattr(cli, "_register", lambda: 0)
    assert cli.main(["register"]) == 0


def test_help_returns_zero_and_prints_usage(monkeypatch, capsys):
    assert cli.main(["--help"]) == 0
    assert "loopai" in capsys.readouterr().out


def test_unknown_command_is_error(capsys):
    assert cli.main(["frobnicate"]) == 2
    assert "unknown command" in capsys.readouterr().err


def test_register_command_targets_this_package(monkeypatch):
    captured = {}
    def fake_run(cmd, check):
        captured["cmd"] = cmd
        class R: returncode = 0
        return R()
    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    rc = cli._register()
    assert rc == 0
    cmd = captured["cmd"]
    # registers the looping-agent server, pinned to this package, via loopai serve
    assert cmd[:4] == ["claude", "mcp", "add", "looping-agent"]
    assert str(cli.PKG_ROOT) in cmd and "serve" in cmd


def test_register_without_claude_cli_is_graceful(monkeypatch, capsys):
    def boom(*a, **k): raise FileNotFoundError()
    monkeypatch.setattr(cli.subprocess, "run", boom)
    assert cli._register() == 1
    assert "Register manually" in capsys.readouterr().err
