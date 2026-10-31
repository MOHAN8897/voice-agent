from types import SimpleNamespace

from scripts import security_audit


def test_strix_passes_api_key_by_name_without_copying_secret_into_arguments(monkeypatch):
    captured = {}
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-secret")

    def capture(cmd, description):
        captured["cmd"] = cmd
        captured["description"] = description
        return 0

    monkeypatch.setattr(security_audit, "run_cmd", capture)

    assert security_audit.run_strix("https://staging.invalid") == 0
    assert "OPENAI_API_KEY" in captured["cmd"]
    assert "OPENAI_API_KEY=test-only-secret" not in captured["cmd"]


def test_security_runner_does_not_log_command_arguments(monkeypatch, capsys):
    monkeypatch.setattr(security_audit.subprocess, "run", lambda _cmd: SimpleNamespace(returncode=0))

    assert security_audit.run_cmd(
        ["docker", "--env", "TOKEN=test-only-secret"], "test scan"
    ) == 0

    output = capsys.readouterr().out
    assert "test-only-secret" not in output
    assert "--env" not in output
