"""CLI command-surface regression tests."""

from typer.testing import CliRunner

from soloflow.cli import skill
from soloflow.cli.main import app

runner = CliRunner()


def test_top_level_help_is_small_and_has_no_removed_commands():
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in ("run", "version", "mcp", "mcp-config", "skill", "flow", "agent"):
        assert command in result.output
    for removed in ("dashboard", "registry", "mcp-config-set"):
        assert removed not in result.output


def test_run_shortcut_delegates_to_skill_run(monkeypatch):
    captured = {}

    def fake_run(**kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(skill, "run", fake_run)
    result = runner.invoke(app, ["run", "content-writer", "test task", "--dry-run"])

    assert result.exit_code == 0
    assert captured == {
        "skill_name": "content-writer",
        "prompt": "test task",
        "input_file": None,
        "count": 1,
        "dry_run": True,
        "stream": False,
    }


def test_removed_nested_commands_are_absent():
    skill_help = runner.invoke(app, ["skill", "--help"])
    agent_help = runner.invoke(app, ["agent", "--help"])
    flow_help = runner.invoke(app, ["flow", "--help"])

    assert skill_help.exit_code == 0
    assert agent_help.exit_code == 0
    assert flow_help.exit_code == 0
    assert "iter" not in skill_help.output
    assert "heartbeat" not in agent_help.output
    assert "watch" in flow_help.output


def test_mcp_config_options_are_merged():
    result = runner.invoke(app, ["mcp-config", "--help"])

    assert result.exit_code == 0
    assert "--set-token" in result.output
    assert "--allow-tools" in result.output
    assert "--clear" in result.output
