"""测试 Skill 数据模型。"""

import pytest

from soloflow.models.skill import CoSTAR, SkillConfig, SkillFile, SkillMeta


def test_skill_meta_validation():
    """测试 meta 校验。"""
    meta = SkillMeta(name="content-writer", description="测试")
    assert meta.name == "content-writer"

    with pytest.raises(ValueError):
        SkillMeta(name="Content Writer", description="空格")

    with pytest.raises(ValueError):
        SkillMeta(name="内容写作", description="中文")


def test_skill_full_prompt():
    """测试 full_prompt 属性拼接。"""
    skill = SkillFile(
        meta=SkillMeta(name="test-skill", description="测试"),
        costar=CoSTAR(
            context="你是一位专家",
            objective="完成任务",
            style="专业风格",
            tone="真诚",
        ),
        config=SkillConfig(),
        rules=["规则1: 不做X", "规则2: 必须做Y"],
        body="## Instructions\n\n请按照要求完成任务。",
    )

    prompt = skill.full_prompt
    assert "# Context" in prompt
    assert "你是一位专家" in prompt
    assert "# Objective" in prompt
    assert "# Rules" in prompt
    assert "规则1" in prompt
    assert "## Instructions" in prompt


def test_skill_defaults():
    """测试默认值及已裁剪字段。"""
    skill = SkillFile(meta=SkillMeta(name="minimal", description="最小示例"))

    assert skill.config.model == "deepseek-v4-flash"
    assert skill.config.base_url == "https://api.deepseek.com"
    assert skill.config.api_key_env == "DEEPSEEK_API_KEY"
    assert skill.config.temperature == 0.7
    assert skill.costar.context == ""
    assert skill.rules == []
    assert "dependencies" not in SkillFile.model_fields
    assert "iteration" not in SkillFile.model_fields


def test_costar_empty():
    """测试空白 CoSTAR。"""
    co = CoSTAR()
    assert co.context == ""
    assert co.objective == ""
