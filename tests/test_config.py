"""Project-local environment loading tests."""

import os

from typer.testing import CliRunner

from soloflow.cli.main import app
from soloflow.config import load_project_env


def test_load_project_env_reads_current_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SOLOFLOW_TEST_API_KEY", raising=False)
    (tmp_path / ".env").write_text("SOLOFLOW_TEST_API_KEY=from-dotenv\n", encoding="utf-8")

    assert load_project_env()
    assert os.environ["SOLOFLOW_TEST_API_KEY"] == "from-dotenv"


def test_load_project_env_does_not_override_process_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("SOLOFLOW_TEST_API_KEY", "from-process")
    (tmp_path / ".env").write_text("SOLOFLOW_TEST_API_KEY=from-dotenv\n", encoding="utf-8")

    assert load_project_env(tmp_path)
    assert os.environ["SOLOFLOW_TEST_API_KEY"] == "from-process"


def test_load_project_env_does_not_search_parent_directories(monkeypatch, tmp_path):
    child = tmp_path / "child"
    child.mkdir()
    monkeypatch.chdir(child)
    monkeypatch.delenv("SOLOFLOW_TEST_API_KEY", raising=False)
    (tmp_path / ".env").write_text("SOLOFLOW_TEST_API_KEY=from-parent\n", encoding="utf-8")

    assert not load_project_env()
    assert "SOLOFLOW_TEST_API_KEY" not in os.environ


def test_cli_callback_loads_project_env(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SOLOFLOW_TEST_API_KEY", raising=False)
    (tmp_path / ".env").write_text("SOLOFLOW_TEST_API_KEY=from-cli\n", encoding="utf-8")

    result = CliRunner().invoke(app, ["version"])

    assert result.exit_code == 0
    assert os.environ["SOLOFLOW_TEST_API_KEY"] == "from-cli"
