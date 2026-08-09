"""Bundled asset discovery regression tests."""

from pathlib import Path

from soloflow.core import assets
from soloflow.core.skill_loader import find_skill, list_available_skills, load_skill


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


def test_all_asset_kinds_share_project_user_bundled_precedence(monkeypatch, tmp_path):
    project_root = tmp_path / "project"
    user_root = tmp_path / "home"
    bundled_root = tmp_path / "installed" / "_bundled"
    monkeypatch.setattr(Path, "home", lambda: user_root)
    monkeypatch.setattr(assets, "_BUNDLED_ROOT", bundled_root)

    fixtures = {
        "skill": ("skills/shared/SKILL.md", "skills/user-only/SKILL.md"),
        "flow": ("flows/shared.flow.yml", "flows/user-only.flow.yml"),
        "agent": ("agents/shared.agent.yml", "agents/user-only.agent.yml"),
    }
    for kind, (shared_rel, user_rel) in fixtures.items():
        project_path = project_root / shared_rel
        project_path.parent.mkdir(parents=True, exist_ok=True)
        project_path.write_text("project", encoding="utf-8")

        user_path = user_root / ".soloflow" / user_rel
        user_path.parent.mkdir(parents=True, exist_ok=True)
        user_path.write_text("user", encoding="utf-8")

        bundled_shared = bundled_root / shared_rel
        bundled_shared.parent.mkdir(parents=True, exist_ok=True)
        bundled_shared.write_text("bundled", encoding="utf-8")

        assert assets.find_asset(kind, "shared", project_root) == project_path
        assert assets.find_asset(kind, "user-only", project_root) == user_path
        listed = assets.list_asset_paths(kind, project_root)
        assert [(source, assets.asset_name(kind, path)) for source, path in listed] == [
            ("project", "shared"),
            ("user", "user-only"),
        ]


def test_agent_list_uses_bundled_assets_outside_project(monkeypatch, tmp_path):
    from soloflow.cli.agent import _list_agents

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


def test_bundled_skills_use_verified_deepseek_defaults():
    """安装包自带教程资产应只要求官方验证的 DeepSeek Key。"""
    source_root = Path(__file__).resolve().parents[1] / "skills"
    bundled_skills = sorted(source_root.rglob("SKILL.md"))

    assert bundled_skills
    for path in bundled_skills:
        skill = load_skill(path)
        assert skill.config.provider == "deepseek"
        assert skill.config.model == "deepseek-v4-flash"
