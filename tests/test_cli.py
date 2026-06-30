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
    # registers the looping-agent server, launched from this package, via `serve`
    assert cmd[:4] == ["claude", "mcp", "add", "looping-agent"]
    assert "serve" in cmd
    assert any(str(cli.PKG_ROOT) in part for part in cmd)   # pinned to this checkout


def test_launch_argv_prefers_absolute_venv_script(monkeypatch, tmp_path):
    # when the venv script exists, register uses its absolute path (no uv/PATH dep)
    fake_root = tmp_path
    (fake_root / ".venv" / "bin").mkdir(parents=True)
    (fake_root / ".venv" / "bin" / "loopai").write_text("#!/bin/sh\n")
    monkeypatch.setattr(cli, "PKG_ROOT", fake_root)
    argv = cli._launch_argv()
    assert argv == [str(fake_root / ".venv" / "bin" / "loopai"), "serve"]


def test_launch_argv_falls_back_to_uv_run(monkeypatch, tmp_path):
    monkeypatch.setattr(cli, "PKG_ROOT", tmp_path)   # no .venv here
    assert cli._launch_argv() == ["uv", "run", "--project", str(tmp_path), "loopai", "serve"]


def test_register_without_claude_cli_is_graceful(monkeypatch, capsys):
    def boom(*a, **k): raise FileNotFoundError()
    monkeypatch.setattr(cli.subprocess, "run", boom)
    assert cli._register() == 1
    assert "Register manually" in capsys.readouterr().err
