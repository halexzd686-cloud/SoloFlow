"""Rich live view regression tests."""

import json

import pytest
from rich.console import Console

from soloflow.live_view import FlowRunView, SkillLiveView, watch_flow


def _render(renderable) -> str:
    console = Console(record=True, width=100)
    console.print(renderable)
    return console.export_text()


def test_skill_live_view_reports_completion():
    view = SkillLiveView("content-writer")
    view.complete("hello")

    output = _render(view)
    assert "content-writer" in output
    assert "完成" in output
    assert "5 字符" in output


def test_flow_run_view_reads_persisted_state(tmp_path):
    state = {
        "flow_name": "demo-flow",
        "run_id": "run-demo",
        "status": "running",
        "total_tokens": 12,
        "steps": {
            "research": {
                "status": "done",
                "duration": 1.2,
                "tokens": 12,
                "skill": "market-researcher",
                "depends_on": [],
            },
            "write": {
                "status": "running",
                "duration": 0,
                "tokens": 0,
                "skill": "content-writer",
                "depends_on": ["research"],
            },
        },
    }
    (tmp_path / "run-demo.json").write_text(json.dumps(state), encoding="utf-8")

    view = FlowRunView("run-demo", tmp_path)
    output = _render(view)

    assert view.read_state() == state
    assert "demo-flow" in output
    assert "research" in output
    assert "write" in output
    assert "market-researcher" in output
    assert "12" in output


def test_watch_flow_returns_terminal_state(tmp_path):
    state = {"flow_name": "done-flow", "run_id": "run-done", "status": "done", "steps": {}}
    (tmp_path / "run-done.json").write_text(json.dumps(state), encoding="utf-8")

    assert watch_flow("run-done", tmp_path, refresh_interval=0) == state


def test_watch_flow_rejects_missing_run(tmp_path):
    with pytest.raises(FileNotFoundError, match="run-missing"):
        watch_flow("run-missing", tmp_path, refresh_interval=0)
