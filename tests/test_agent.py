"""测试 Agent 数据模型和执行器。"""

import tempfile
from pathlib import Path

import yaml

from soloflow.core.agent_runner import load_skills_for_agent, resolve_llm_config, run_agent
from soloflow.llm.client import LLMResult
from soloflow.models.agent import (
    AgentConfigOverride,
    AgentDefinition,
    AgentSoul,
)
from soloflow.models.skill import SkillConfig

# ── Agent 数据模型测试 ──


def test_agent_definition_defaults():
    """测试 Agent 默认值。"""
    agent = AgentDefinition(name="test-agent")
    assert agent.name == "test-agent"
    assert agent.description == ""
    assert agent.skills == []
    assert isinstance(agent.soul, AgentSoul)
    # BUG-AGENT-001: config 是 AgentConfigOverride（全 Optional，None=继承）
    assert isinstance(agent.config, AgentConfigOverride)
    assert agent.config.model is None
    assert agent.config.temperature is None
    assert agent.rules == []


def test_agent_system_prompt_empty():
    """测试空 Soul 的 system_prompt。"""
    agent = AgentDefinition(name="minimal-agent")
    assert agent.system_prompt == ""


def test_agent_system_prompt_full():
    """测试完整 Soul 的 system_prompt。"""
    agent = AgentDefinition(
        name="full-agent",
        description="A fully specified agent",
        soul=AgentSoul(
            personality="You are a helpful coding assistant.",
            values=["Accuracy", "Clarity", "Helpfulness"],
            behavior_rules=["Always explain your reasoning.", "Prefer simple solutions."],
        ),
        rules=["Never hallucinate APIs.", "Use type hints."],
    )
    prompt = agent.system_prompt
    assert "# Agent Role" in prompt
    assert "helpful coding assistant" in prompt
    assert "# Core Values" in prompt
    assert "Accuracy" in prompt
    assert "# Behavior" in prompt
    assert "Always explain your reasoning" in prompt
    assert "# Agent Rules" in prompt
    assert "Never hallucinate APIs" in prompt


def test_agent_system_prompt_partial_soul():
    """测试部分 Soul 字段。"""
    agent = AgentDefinition(
        name="partial",
        soul=AgentSoul(
            personality="A concise reviewer.",
        ),
        rules=["Be brief."],
    )
    prompt = agent.system_prompt
    assert "# Agent Role" in prompt
    assert "A concise reviewer" in prompt
    assert "# Core Values" not in prompt  # empty values should not appear
    assert "# Behavior" not in prompt  # empty behavior_rules should not appear
    assert "# Agent Rules" in prompt
    assert "Be brief." in prompt


def test_agent_config_override():
    """测试 Agent 级别的 config 字段（AgentConfigOverride）。"""
    agent = AgentDefinition(
        name="custom-config",
        config=AgentConfigOverride(
            model="deepseek-v4-flash",
            provider="deepseek",
            temperature=0.3,
            max_tokens=8192,
        ),
    )
    assert agent.config.model == "deepseek-v4-flash"
    assert agent.config.provider == "deepseek"
    assert agent.config.temperature == 0.3
    assert agent.config.max_tokens == 8192


# ── Agent YAML 序列化测试 ──


def test_agent_yaml_roundtrip():
    """测试 Agent 定义 YAML 序列化回路。"""
    agent = AgentDefinition(
        name="roundtrip-agent",
        description="Testing serialization",
        skills=["content-writer", "code-reviewer"],
        soul=AgentSoul(
            personality="A versatile assistant.",
            values=["Quality", "Speed"],
            behavior_rules=["Always verify."],
        ),
        rules=["No markdown in code blocks."],
        config=AgentConfigOverride(model="deepseek-v4-flash", temperature=0.5),
    )

    # 序列化
    data = agent.model_dump(exclude_defaults=True)
    yaml_str = yaml.dump(data, allow_unicode=True, default_flow_style=False)

    # 反序列化
    loaded_data = yaml.safe_load(yaml_str)
    loaded = AgentDefinition(**loaded_data)

    assert loaded.name == agent.name
    assert loaded.description == agent.description
    assert loaded.skills == agent.skills
    assert loaded.soul.personality == agent.soul.personality
    assert loaded.soul.values == agent.soul.values
    assert loaded.config.temperature == 0.5


def test_agent_yaml_file_save_load():
    """测试 Agent YAML 文件保存和加载。"""
    agent = AgentDefinition(
        name="file-agent",
        description="Agent for file test",
        skills=["market-researcher"],
        soul=AgentSoul(personality="A data-driven analyst."),
    )

    with tempfile.TemporaryDirectory() as tmp:
        # 保存
        agent_path = Path(tmp) / f"{agent.name}.agent.yml"
        data = agent.model_dump(exclude_defaults=True)
        agent_path.write_text(
            yaml.dump(data, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )

        # 确认文件存在
        assert agent_path.exists()

        # 加载
        loaded_data = yaml.safe_load(agent_path.read_text(encoding="utf-8"))
        loaded = AgentDefinition(**loaded_data)

        assert loaded.name == "file-agent"
        assert loaded.description == "Agent for file test"
        assert loaded.skills == ["market-researcher"]
        assert loaded.soul.personality == "A data-driven analyst."


# ── Agent 执行器测试 ──


def test_load_skills_for_agent_no_skills():
    """测试无 Skill 绑定时的行为。"""
    agent = AgentDefinition(name="no-skills-agent")
    loaded = load_skills_for_agent(agent)
    assert loaded == []


def test_load_skills_for_agent_valid_skill():
    """测试加载有效 Skill。"""
    agent = AgentDefinition(name="writer-agent", skills=["content-writer"])
    loaded = load_skills_for_agent(agent)
    assert len(loaded) == 1
    name, skill = loaded[0]
    assert name == "content-writer"
    assert skill.meta.name == "content-writer"


def test_load_skills_for_agent_mixed_skills():
    """测试混合有效/无效 Skill。"""
    agent = AgentDefinition(
        name="mixed-agent",
        skills=["content-writer", "nonexistent-skill-xyz"],
    )
    loaded = load_skills_for_agent(agent)
    # 有效 Skill 应该被加载，无效的被跳过
    assert len(loaded) == 1
    assert loaded[0][0] == "content-writer"


def test_load_skills_for_agent_multiple_skills():
    """测试加载多个有效 Skill。"""
    agent = AgentDefinition(
        name="multi-skill-agent",
        skills=["content-writer", "code-reviewer"],
    )
    loaded = load_skills_for_agent(agent)
    assert len(loaded) == 2
    names = [name for name, _ in loaded]
    assert "content-writer" in names
    assert "code-reviewer" in names


def test_run_agent_dry_run():
    """测试 Agent 执行 dry_run 模式。"""
    agent = AgentDefinition(
        name="test-runner",
        skills=["content-writer"],
        soul=AgentSoul(
            personality="A helpful writing assistant.",
            values=["Clarity"],
        ),
    )

    results = run_agent(agent, "Write a hello world article.", dry_run=True)
    assert len(results) == 1
    assert results[0] == "[DRY RUN]"


def test_run_agent_no_skills():
    """测试无有效 Skill 时执行失败。"""
    agent = AgentDefinition(name="no-skills-runner")
    results = run_agent(agent, "Do something.")
    assert results == []


def test_run_agent_multi_count_dry_run():
    """测试抽卡模式 dry_run。"""
    agent = AgentDefinition(
        name="multi-runner",
        skills=["content-writer"],
    )
    results = run_agent(agent, "Write something.", count=3, dry_run=True)
    # dry_run 只返回一个 [DRY RUN]（在第一个循环迭代前就返回）
    assert len(results) >= 1


# ── AgentSoul 直接测试 ──


def test_agent_soul_empty():
    """测试空 Soul。"""
    soul = AgentSoul()
    assert soul.personality == ""
    assert soul.values == []
    assert soul.behavior_rules == []


def test_agent_soul_with_values():
    """测试带价值观的 Soul。"""
    soul = AgentSoul(
        personality="A meticulous reviewer.",
        values=["Thoroughness", "Constructiveness"],
        behavior_rules=["Find at least 3 issues.", "Suggest fixes for each."],
    )
    assert len(soul.values) == 2
    assert "Thoroughness" in soul.values
    assert len(soul.behavior_rules) == 2


# ── BUG-AGENT-001: resolve_llm_config 覆盖语义 ──


def test_resolve_llm_config_all_none_inherits_skill():
    """BUG-AGENT-001: Agent config 全 None 时完全继承 Skill 配置。"""
    fallback = SkillConfig(
        model="skill-model", provider="deepseek", temperature=0.3, max_tokens=2048
    )
    model, provider, temp, max_tok = resolve_llm_config(None, fallback)
    assert (model, provider, temp, max_tok) == ("skill-model", "deepseek", 0.3, 2048)


def test_resolve_llm_config_partial_override():
    """BUG-AGENT-001: 只覆盖部分字段，其余继承。"""
    fallback = SkillConfig(
        model="skill-model", provider="deepseek", temperature=0.3, max_tokens=2048
    )
    override = AgentConfigOverride(model="agent-model")  # 只覆盖 model
    model, provider, temp, max_tok = resolve_llm_config(override, fallback)
    assert model == "agent-model"
    assert provider == "deepseek"  # 继承
    assert temp == 0.3  # 继承
    assert max_tok == 2048  # 继承


def test_resolve_llm_config_explicit_default_value_is_override():
    """BUG-AGENT-001 关键回归: 显式指定"默认值"必须被尊重为覆盖。

    修复前用"是否等于默认值"判断，导致用户显式指定
    temperature=0.7 也会被忽略。现在非 None 即覆盖。
    """
    fallback = SkillConfig(model="skill-model", temperature=0.3)
    # 用户显式写 temperature=0.7（恰好等于全局默认值）
    override = AgentConfigOverride(temperature=0.7)
    model, provider, temp, max_tok = resolve_llm_config(override, fallback)
    assert temp == 0.7  # 显式覆盖生效，而不是回退到 0.3
    assert model == "skill-model"


def test_agent_config_serialization_roundtrip():
    """Agent config 保存/加载回路：None 字段不丢失。"""
    agent = AgentDefinition(
        name="cfg-agent",
        config=AgentConfigOverride(model="my-model", provider="zhipu"),
    )
    # CLI 保存用 exclude_defaults + exclude_none，避免 None 字段进入 YAML
    data = agent.model_dump(exclude_defaults=True, exclude_none=True)
    assert data["config"] == {"model": "my-model", "provider": "zhipu"}
    reloaded = AgentDefinition(**data)
    assert reloaded.config.model == "my-model"
    assert reloaded.config.provider == "zhipu"
    assert reloaded.config.temperature is None


# ── GAP-AGENT-003: 内置 Agent 示例 ──


def test_builtin_agent_examples_load():
    """GAP-AGENT-003: 内置 Agent 示例可以正常加载。"""
    from soloflow.cli.agent import _load_agent

    agent = _load_agent("content-editor")
    assert agent.name == "content-editor"
    assert "content-writer" in agent.skills
    assert agent.soul.personality
    # 全 None config → 继承 Skill
    assert agent.config.model is None

    agent2 = _load_agent("code-guardian")
    assert agent2.name == "code-guardian"
    assert "code-reviewer" in agent2.skills
    # 显式覆盖生效
    assert agent2.config.temperature == 0.2


# ── BUG-AGENT-002: Flow Agent 步骤使用统一配置解析 ──


def test_flow_agent_step_uses_agent_config():
    """BUG-AGENT-002 回归: Flow 的 Agent 步骤必须应用 Agent config 覆盖。"""
    from unittest.mock import patch

    from soloflow.core.flow_engine import run_flow
    from soloflow.models.flow import FlowDefinition, FlowStep

    flow = FlowDefinition(
        name="agent-step-flow",
        steps=[
            FlowStep(id="review", skill="code-reviewer", agent="code-guardian"),
        ],
    )

    captured = {}

    def fake_build_step_prompt(step, context):
        return "PROMPT"

    def fake_call_llm_full(prompt, **kwargs):
        captured["model"] = kwargs.get("model")
        captured["temperature"] = kwargs.get("temperature")
        return LLMResult(content="output")

    # code-guardian 显式设置 temperature=0.2 → 步骤必须用 0.2
    with (
        patch("soloflow.core.flow_engine._build_step_prompt", fake_build_step_prompt),
        patch("soloflow.core.flow_engine.call_llm_full", fake_call_llm_full),
    ):
        result = run_flow(flow)

    assert result.status == "done"
    assert captured["temperature"] == 0.2


# ── P2-001: 统一 Agent 搜索目录 ──


def test_list_agents_includes_builtin_examples(monkeypatch, tmp_path):
    """P2-001 回归: sf agent list 内部列表必须包含 agents/ 内置示例。"""
    import os

    from soloflow.cli.agent import _list_agents

    orig = os.getcwd()
    monkeypatch.chdir(tmp_path)  # 空目录，排除 cwd 干扰
    os.chdir(orig)  # 恢复 cwd 以访问项目 agents/ 目录
    try:
        agents = _list_agents()
        names = [a["name"] for a in agents]
        assert "content-editor" in names, "content-editor 应出现在 agent list"
        assert "code-guardian" in names, "code-guardian 应出现在 agent list"
    finally:
        os.chdir(tmp_path)


def test_list_agents_dedup_priority(monkeypatch, tmp_path):
    """P2-001: 同名 Agent 出现在多个目录时只保留最高优先级一项。"""
    from soloflow.cli import agent as agent_cli

    # 构造: agents/ 下 name=dup-agent 版本 A；.soloflow/agents/ 下同名版本 B
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    (agents_dir / "dup-agent.agent.yml").write_text(
        "name: dup-agent\ndescription: from agents dir\nskills: [content-writer]\n",
        encoding="utf-8",
    )
    global_dir = tmp_path / ".soloflow" / "agents"
    global_dir.mkdir(parents=True)
    (global_dir / "dup-agent.agent.yml").write_text(
        "name: dup-agent\ndescription: from global dir\nskills: [code-reviewer]\n",
        encoding="utf-8",
    )

    original_dirs = agent_cli._agent_search_dirs
    agent_cli._agent_search_dirs = lambda: [
        tmp_path / "agents",
        tmp_path / ".soloflow" / "agents",
    ]
    try:
        agents = agent_cli._list_agents()
    finally:
        agent_cli._agent_search_dirs = original_dirs

    dup = [a for a in agents if a["name"] == "dup-agent"]
    assert len(dup) == 1, "同名 Agent 必须去重"
    assert "agents dir" in dup[0]["description"], "应保留优先级最高（agents/）的版本"
