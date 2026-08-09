"""测试 Skill 加载器。"""

import tempfile
from pathlib import Path

from soloflow.core.skill_loader import (
    _parse_frontmatter,
    list_skills,
    load_skill,
    save_skill,
    validate_skill,
)
from soloflow.models.skill import (
    CoSTAR,
    SkillConfig,
    SkillExample,
    SkillFile,
    SkillMeta,
    SkillTest,
)


def test_parse_frontmatter():
    """测试 frontmatter 解析。"""
    text = """---
name: test-skill
version: 1.0.0
description: 测试技能
tags:
  - test
  - demo
---
# 正文内容

这是一段正文。"""

    fm, body = _parse_frontmatter(text)
    assert fm["name"] == "test-skill"
    assert fm["version"] == "1.0.0"
    assert fm["tags"] == ["test", "demo"]
    assert "正文内容" in body


def test_parse_no_frontmatter():
    """测试无 frontmatter 的纯文本。"""
    text = "# 只有正文"
    fm, body = _parse_frontmatter(text)
    assert fm == {}
    assert "只有正文" in body


def test_load_and_save_roundtrip():
    """测试加载-保存-再加载的完整回路。"""
    skill = SkillFile(
        meta=SkillMeta(name="roundtrip-test", description="回路测试"),
        costar=CoSTAR(context="测试背景", objective="测试目标"),
        config=SkillConfig(),
        rules=["规则1", "规则2"],
        body="## Instructions\n\n测试正文。",
    )

    with tempfile.TemporaryDirectory() as tmp:
        # 保存
        saved = save_skill(skill, Path(tmp) / "roundtrip-test")
        assert saved.exists()

        # 加载
        loaded = load_skill(saved)
        assert loaded.meta.name == "roundtrip-test"
        assert loaded.meta.description == "回路测试"
        assert loaded.costar.context == "测试背景"
        assert loaded.rules == ["规则1", "规则2"]
        assert "测试正文" in loaded.body


def test_roundtrip_preserves_examples_tests_and_extensions():
    """BUG-SKILL-001 回归测试：load → save → load 必须无损。

    覆盖此前会静默丢失的字段:
    - examples
    - tests
    - 未知 frontmatter 扩展字段
    """
    skill = SkillFile(
        meta=SkillMeta(name="full-roundtrip", description="完整回路"),
        costar=CoSTAR(context="背景", objective="目标"),
        config=SkillConfig(),
        rules=["规则1"],
        examples=[
            SkillExample(input="输入示例", output="期望输出"),
            SkillExample(input="输入2", output="输出2"),
        ],
        tests=[
            SkillTest(check="检查项", expected="期望结果"),
        ],
        body="## Instructions\n\n正文。",
        extra_frontmatter={"custom_meta": {"foo": "bar"}, "legacy_flag": True},
    )

    with tempfile.TemporaryDirectory() as tmp:
        saved = save_skill(skill, Path(tmp) / "full-roundtrip")
        loaded = load_skill(saved)

        # 元信息与配置
        assert loaded.meta.name == skill.meta.name
        assert loaded.meta.version == skill.meta.version
        assert loaded.costar.context == "背景"
        assert loaded.config.model == skill.config.model
        assert loaded.rules == ["规则1"]

        # examples 完整保留
        assert len(loaded.examples) == 2
        assert loaded.examples[0].input == "输入示例"
        assert loaded.examples[0].output == "期望输出"
        assert loaded.examples[1].input == "输入2"

        # tests 完整保留
        assert len(loaded.tests) == 1
        assert loaded.tests[0].check == "检查项"
        assert loaded.tests[0].expected == "期望结果"

        # 未知扩展字段保留
        assert loaded.extra_frontmatter == {"custom_meta": {"foo": "bar"}, "legacy_flag": True}

        # 二次 round-trip 仍然无损（稳定性）
        saved2 = save_skill(loaded, Path(tmp) / "again")
        loaded2 = load_skill(saved2)
        assert loaded2.examples == loaded.examples
        assert loaded2.tests == loaded.tests
        assert loaded2.extra_frontmatter == loaded.extra_frontmatter


def test_validate_skill_ok():
    """测试校验通过的情况。"""
    skill = SkillFile(
        meta=SkillMeta(name="ok-skill", description="没问题"),
        body="## Instructions\n\n一些内容。",
    )

    issues = validate_skill(skill, strict=False)
    assert len(issues) == 0


def test_validate_skill_empty_body():
    """测试空 body 校验失败。"""
    skill = SkillFile(
        meta=SkillMeta(name="empty-skill", description="空正文"),
        body="",
    )

    issues = validate_skill(skill, strict=False)
    assert any("body" in i.lower() for i in issues)


def test_validate_skill_strict_missing_costar():
    """测试严格模式下缺少 CoSTAR 字段。"""
    skill = SkillFile(
        meta=SkillMeta(name="strict-test", description="严格测试"),
        body="有正文",
    )

    issues = validate_skill(skill, strict=True)
    assert any("context" in i.lower() for i in issues)
    assert any("objective" in i.lower() for i in issues)


def test_list_skills():
    """测试列出 Skill。"""
    with tempfile.TemporaryDirectory() as tmp:
        # 创建几个 Skill
        for name in ["skill-a", "skill-b"]:
            skill = SkillFile(
                meta=SkillMeta(name=name, description=f"{name} 描述"),
                body="正文",
            )
            save_skill(skill, Path(tmp) / name)

        results = list_skills(tmp)
        assert len(results) == 2
        names = {r["name"] for r in results}
        assert names == {"skill-a", "skill-b"}
