"""Bundled asset discovery regression tests."""

from pathlib import Path

from soloflow.cli.agent import _list_agents
from soloflow.core import assets
from soloflow.core.skill_loader import find_skill, list_available_skills


def _write_skill(root: Path, name: str) -> Path:
    path = root / name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "---",
                f"name: {name}",
                "version: 1.0.0",
                f"description: {name} description",
                "---",
                "",
                "## Instructions",
                "",
                "Do the task.",
            ]
        ),
        encoding="utf-8",
    )
    return path


def test_find_skill_falls_back_to_bundled_assets(monkeypatch, tmp_path):
    bundled_root = tmp_path / "installed" / "_bundled"
    expected = _write_skill(bundled_root / "skills", "bundled-only-test")
    project_root = tmp_path / "empty-project"
    project_root.mkdir()

    monkeypatch.setattr(assets, "_BUNDLED_ROOT", bundled_root)

    assert find_skill("bundled-only-test", project_dir=project_root) == expected
    discovered = list_available_skills(project_dir=project_root, include_global=False)
    assert [(item["name"], item["source"]) for item in discovered] == [
        ("bundled-only-test", "bundled")
    ]


def test_project_flow_overrides_bundled_flow(monkeypatch, tmp_path):
    bundled_root = tmp_path / "installed" / "_bundled"
    bundled_flows = bundled_root / "flows"
    bundled_flows.mkdir(parents=True)
    (bundled_flows / "shared.flow.yml").write_text("bundled", encoding="utf-8")
    (bundled_flows / "bundled-only.flow.yml").write_text("bundled", encoding="utf-8")

    project_root = tmp_path / "project"
    project_flows = project_root / "flows"
    project_flows.mkdir(parents=True)
    project_shared = project_flows / "shared.flow.yml"
    project_shared.write_text("project", encoding="utf-8")

    monkeypatch.setattr(assets, "_BUNDLED_ROOT", bundled_root)

    assert assets.find_flow_path("shared", project_dir=project_root) == project_shared
    paths = assets.list_flow_paths(project_dir=project_root)
    assert [path.name for path in paths] == ["shared.flow.yml", "bundled-only.flow.yml"]


def test_agent_list_uses_bundled_assets_outside_project(monkeypatch, tmp_path):
    bundled_root = tmp_path / "installed" / "_bundled"
    bundled_agents = bundled_root / "agents"
    bundled_agents.mkdir(parents=True)
    (bundled_agents / "bundled-agent.agent.yml").write_text(
        "\n".join(
            [
                "name: bundled-agent",
                "description: Bundled agent",
                "skills:",
                "  - bundled-skill",
            ]
        ),
        encoding="utf-8",
    )

    empty_project = tmp_path / "empty-project"
    empty_project.mkdir()
    monkeypatch.chdir(empty_project)
    monkeypatch.setattr(assets, "_BUNDLED_ROOT", bundled_root)

    assert [agent["name"] for agent in _list_agents()] == ["bundled-agent"]
