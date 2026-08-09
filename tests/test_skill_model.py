"""测试 Skill 数据模型。"""

import pytest

from soloflow.models.skill import (
    CoSTAR,
    SkillConfig,
    SkillFile,
    SkillIteration,
    SkillMeta,
    check_version_compatible,
    parse_dependency_spec,
)


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
    """测试默认值。"""
    skill = SkillFile(
        meta=SkillMeta(name="minimal", description="最小示例"),
    )

    assert skill.config.model == "claude-sonnet-4-20250514"
    assert skill.config.temperature == 0.7
    assert skill.costar.context == ""
    assert skill.iteration.version == 0
    assert skill.rules == []
    assert skill.dependencies == []


def test_costar_empty():
    """测试空白 CoSTAR。"""
    co = CoSTAR()
    assert co.context == ""
    assert co.objective == ""


def test_skill_iteration_defaults():
    """测试迭代元数据默认值。"""
    it = SkillIteration()
    assert it.version == 0
    assert it.score is None
    assert it.changelog == []


# ── 新增测试: 依赖版本解析 ──


def test_parse_dependency_no_version():
    """测试无版本号的依赖。"""
    name, constraint, version = parse_dependency_spec("code-reviewer")
    assert name == "code-reviewer"
    assert constraint is None
    assert version is None


def test_parse_dependency_exact_version():
    """测试精确版本依赖。"""
    name, constraint, version = parse_dependency_spec("code-reviewer@1.2.0")
    assert name == "code-reviewer"
    assert constraint == "=="
    assert version == "1.2.0"


def test_parse_dependency_min_version():
    """测试最低版本约束。"""
    name, constraint, version = parse_dependency_spec("writer@>=2.0.0")
    assert name == "writer"
    assert constraint == ">="
    assert version == "2.0.0"


def test_parse_dependency_other_constraints():
    """测试各种约束符。"""
    assert parse_dependency_spec("a@<=1.0.0") == ("a", "<=", "1.0.0")
    assert parse_dependency_spec("a@!=0.5.0") == ("a", "!=", "0.5.0")
    assert parse_dependency_spec("a@~=1.5.0") == ("a", "~=", "1.5.0")
    assert parse_dependency_spec("a@^2.0") == ("a", "^", "2.0")
    assert parse_dependency_spec("a@>0.9.0") == ("a", ">", "0.9.0")
    assert parse_dependency_spec("a@<2.0.0") == ("a", "<", "2.0.0")


# ── 新增测试: 版本兼容检查 ──


def test_version_compatible_exact():
    """测试精确版本匹配。"""
    assert check_version_compatible("1.2.0", "==", "1.2.0") is True
    assert check_version_compatible("1.2.0", "==", "1.3.0") is False


def test_version_compatible_min():
    """测试最低版本约束。"""
    assert check_version_compatible("2.0.0", ">=", "1.0.0") is True
    assert check_version_compatible("0.9.0", ">=", "1.0.0") is False
    assert check_version_compatible("1.0.0", ">=", "1.0.0") is True


def test_version_compatible_no_constraint():
    """测试无约束总是兼容。"""
    assert check_version_compatible("0.1.0", None, None) is True
    assert check_version_compatible("any", "==", "1.0.0") is False  # 非数字版本


def test_version_compatible_max():
    """测试最高版本约束。"""
    assert check_version_compatible("1.0.0", "<=", "2.0.0") is True
    assert check_version_compatible("3.0.0", "<=", "2.0.0") is False


def test_version_compatible_not_equal():
    """测试不等约束。"""
    assert check_version_compatible("1.0.0", "!=", "2.0.0") is True
    assert check_version_compatible("1.0.0", "!=", "1.0.0") is False


def test_version_compatible_caret():
    """测试 ^ 兼容约束。"""
    assert check_version_compatible("1.5.0", "^", "1.0.0") is True
    assert check_version_compatible("2.0.0", "^", "1.0.0") is False


# ── 新增测试: 依赖校验 ──


def test_validate_dependencies_empty():
    """测试空依赖列表。"""
    from soloflow.core.skill_loader import validate_dependencies

    assert validate_dependencies([]) == []


def test_validate_dependencies_installed_satisfied():
    """测试已安装且版本满足的依赖。"""
    from soloflow.core.skill_loader import validate_dependencies

    # code-reviewer v1.0.0 已安装
    issues = validate_dependencies(["code-reviewer@>=0.5.0"])
    assert len(issues) == 0


def test_validate_dependencies_installed_not_satisfied():
    """测试已安装但版本不满足的依赖。"""
    from soloflow.core.skill_loader import validate_dependencies

    # code-reviewer v1.0.0 已安装，不满足 >=2.0.0
    issues = validate_dependencies(["code-reviewer@>=2.0.0"])
    assert len(issues) == 1
    assert "版本不兼容" in issues[0]


def test_validate_dependencies_not_installed():
    """测试未安装的依赖。"""
    from soloflow.core.skill_loader import validate_dependencies

    issues = validate_dependencies(["non-existent-skill@1.0.0"])
    assert len(issues) == 1
    assert "未找到" in issues[0]


# ── BUG-SKILL-002: 完整 SemVer 版本比较 ──


def test_version_compatible_prerelease():
    """BUG-SKILL-002: 支持预发布版本（1.0.0-alpha）。"""
    from soloflow.models.skill import check_version_compatible

    # == 精确匹配预发布
    assert check_version_compatible("1.0.0-alpha", "==", "1.0.0-alpha") is True
    # 预发布 != 正式版
    assert check_version_compatible("1.0.0-alpha", "==", "1.0.0") is False
    # >= 正式版对预发布为 False（1.0.0-alpha < 1.0.0）
    assert check_version_compatible("1.0.0-alpha", ">=", "1.0.0") is False


def test_version_compatible_build_metadata():
    """BUG-SKILL-002: 支持构建元数据（1.0.0+build.1，PEP 440 local version）。"""
    from soloflow.models.skill import check_version_compatible

    # PEP 440: local version 与同一 public version 严格不等（排序在后）
    assert check_version_compatible("1.0.0+build.1", "==", "1.0.0") is False
    # 精确匹配 local version 本身
    assert check_version_compatible("1.0.0+build.1", "==", "1.0.0+build.1") is True
    # >= 语义: local version 满足 >= public version
    assert check_version_compatible("1.0.0+build.1", ">=", "1.0.0") is True


def test_version_compatible_tilde_specifier():
    """BUG-SKILL-002: ~= 使用 packaging 原生兼容范围语义。"""
    from soloflow.models.skill import check_version_compatible

    # ~=2.2 允许 2.2 到 3.0（不含）
    assert check_version_compatible("2.5.0", "~=", "2.2") is True
    assert check_version_compatible("2.2.0", "~=", "2.2") is True
    assert check_version_compatible("3.0.0", "~=", "2.2") is False


def test_version_compatible_invalid():
    """BUG-SKILL-002: 无效版本返回 False。"""
    from soloflow.models.skill import check_version_compatible

    assert check_version_compatible("not-a-version", "==", "1.0.0") is False
    assert check_version_compatible("1.0.0", ">=", "not-a-version") is False
