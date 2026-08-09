"""Skill 数据模型 —— SoloFlow 的核心数据结构。

一个 Skill 文件采用 YAML frontmatter + Markdown body 格式，
人机双读、Git 友好、符合 agentskills.io 社区标准。

依赖版本锁定：
- 支持 `skill-name` (任意版本)
- 支持 `skill-name@1.2.0` (精确版本)
- 支持 `skill-name@>=1.0.0` (最低版本约束)
"""

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class RulePriority(StrEnum):
    """Skill 规则的优先级。"""

    MUST = "must"  # 不可打破
    SHOULD = "should"  # 尽量遵守
    MAY = "may"  # 可参考


def parse_dependency_spec(spec: str) -> tuple[str, str | None, str | None]:
    """解析依赖规格字符串为 (名称, 约束符, 版本号)。

    支持格式:
        "skill-name"           → ("skill-name", None, None)
        "skill-name@1.2.0"     → ("skill-name", "==", "1.2.0")
        "skill-name@>=1.0.0"   → ("skill-name", ">=", "1.0.0")
        "skill-name@^1.0"      → ("skill-name", "^", "1.0")

    Args:
        spec: 依赖规格字符串。

    Returns:
        (name, constraint, version) 元组。
    """
    if "@" not in spec:
        return (spec, None, None)

    name, version_part = spec.split("@", 1)
    name = name.strip()
    version_part = version_part.strip()

    # 解析版本约束符（注意 ^ 和 ~ 需要放在靠后避免与正则锚点混淆）
    constraint_match = re.match(r"^(>=|<=|!=|~=|\^|>|<)?(.+)$", version_part)
    if constraint_match:
        constraint = constraint_match.group(1) or "=="
        version = constraint_match.group(2)
        return (name, constraint, version)

    return (name, "==", version_part)


def check_version_compatible(actual: str, constraint: str | None, target: str | None) -> bool:
    """检查实际版本是否满足约束（BUG-SKILL-002 修复）。

    使用 packaging.Version 完整解析 SemVer：
    - 支持预发布: 1.0.0-alpha
    - 支持构建元数据: 1.0.0+build.1
    - ~= 使用 packaging.specifiers 原生语义
    - ^ 保持自定义语义（主版本相同且 >= target）

    Args:
        actual: 实际安装的版本号（如 "1.2.0"）。
        constraint: 约束符（"==", ">=", "<=", "!=", "~=", "^", ">", "<"）。
        target: 目标版本号。

    Returns:
        True 表示兼容。
    """
    if constraint is None or target is None:
        return True  # 无版本约束，总是兼容

    try:
        from packaging.version import InvalidVersion, Version
    except ImportError:
        # packaging 不可用时回退到简化比较
        return _check_version_simple(actual, constraint, target)

    try:
        a_ver = Version(actual)
        t_ver = Version(target)
    except (InvalidVersion, ValueError):
        return False

    if constraint == "==":
        return a_ver == t_ver
    elif constraint in (">=", "<=", ">", "<", "!=", "~="):
        spec = f"{constraint}{target}"
        try:
            from packaging.specifiers import SpecifierSet

            return a_ver in SpecifierSet(spec)
        except Exception:
            return False
    elif constraint == "^":
        # ^0.2.3 语义: 主版本相同且 >= target
        # （0.x 特殊规则: 0.2.3 → >=0.2.3 <0.3.0，此处保持简化）
        if a_ver.release[0] != t_ver.release[0]:
            return False
        return a_ver >= t_ver
    else:
        return True  # 未知约束符，放行


def _check_version_simple(actual: str, constraint: str | None, target: str | None) -> bool:
    """简化版版本比较（packaging 不可用时的回退）。"""
    try:
        a_parts = [int(x) for x in actual.split(".")]
        t_parts = [int(x) for x in target.split(".")]
    except (ValueError, AttributeError):
        return False

    while len(a_parts) < 3:
        a_parts.append(0)
    while len(t_parts) < 3:
        t_parts.append(0)

    a_tuple = tuple(a_parts)
    t_tuple = tuple(t_parts)

    if constraint == "==":
        return a_tuple == t_tuple
    elif constraint == ">=":
        return a_tuple >= t_tuple
    elif constraint == "<=":
        return a_tuple <= t_tuple
    elif constraint == ">":
        return a_tuple > t_tuple
    elif constraint == "<":
        return a_tuple < t_tuple
    elif constraint == "!=":
        return a_tuple != t_tuple
    elif constraint in ("~=", "^"):
        return a_tuple[0] == t_tuple[0] and a_tuple >= t_tuple
    else:
        return True


class SkillMeta(BaseModel):
    """Skill 元信息。"""

    name: str = Field(..., description="Skill 名称 (kebab-case)", max_length=64)
    version: str = Field(default="0.1.0", description="语义化版本号")
    author: str = Field(default="unknown", description="作者")
    description: str = Field(default="", description="简短描述", max_length=1024)
    license: str = Field(default="MIT", description="SPDX 许可证标识")
    tags: list[str] = Field(default_factory=list, description="分类标签")

    @field_validator("name")
    @classmethod
    def name_must_be_kebab(cls, v: str) -> str:
        """验证 name 为 kebab-case 格式。"""
        if not re.match(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$", v):
            raise ValueError(f"Skill 名称必须是 kebab-case 格式: {v}")
        return v


class CoSTAR(BaseModel):
    """CoSTAR 结构化提示词框架。

    Context → Objective → Style → Tone → Audience → Response_format
    """

    context: str = Field(default="", description="背景信息 —— 你是什么样的专家")
    objective: str = Field(default="", description="目标 —— 要完成什么任务")
    style: str = Field(default="", description="风格 —— 参考风格/结构要求")
    tone: str = Field(default="", description="语气 —— 真诚/专业/幽默等")
    audience: str = Field(default="", description="受众 —— 目标读者/用户画像")
    response_format: str = Field(default="", description="输出格式 —— JSON/Markdown/纯文本等")


class SkillExample(BaseModel):
    """输入→输出的示例对，帮助 AI 理解期望。"""

    input: str = Field(..., description="示例输入")
    output: str = Field(..., description="期望输出")


class SkillTest(BaseModel):
    """质量评估测试用例。"""

    check: str = Field(..., description="检查项描述")
    expected: str = Field(..., description="期望结果")


class SkillIteration(BaseModel):
    """Skill 自我迭代的元数据（由 sf skill iter 自动管理）。"""

    version: int = Field(default=0, description="迭代次数")
    score: float | None = Field(default=None, description="最近一次评估得分")
    evaluated_at: str | None = Field(default=None, description="最近评估时间")
    changelog: list[str] = Field(default_factory=list, description="每次迭代的变更记录")


class SkillConfig(BaseModel):
    """Skill 的 LLM 配置。"""

    model: str = Field(default="claude-sonnet-4-20250514", description="默认模型")
    provider: str = Field(default="anthropic", description="默认 LLM 提供商")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="温度参数")
    max_tokens: int = Field(default=4096, gt=0, description="最大输出 token 数")


class SkillFile(BaseModel):
    """完整的 Skill 文件数据结构。

    这是 SoloFlow 的核心数据类型，一个 Skill 文件包含：
    - meta: 元信息（名称、版本、作者等）
    - costar: CoSTAR 结构化提示词
    - config: LLM 调用配置
    - rules: 不可打破的规则列表
    - examples: 输入→输出示例
    - tests: 质量评估标准
    - body: Markdown 正文（实际的 prompt 模板）
    - dependencies: 依赖的其他 Skill
    - iteration: 迭代元数据
    """

    meta: SkillMeta = Field(..., description="元信息")
    costar: CoSTAR = Field(default_factory=CoSTAR, description="CoSTAR 提示词")
    config: SkillConfig = Field(default_factory=SkillConfig, description="LLM 配置")
    rules: list[str] = Field(default_factory=list, description="规则清单")
    examples: list[SkillExample] = Field(default_factory=list, description="示例")
    tests: list[SkillTest] = Field(default_factory=list, description="测试用例")
    body: str = Field(default="", description="Markdown 正文 —— 实际 prompt 模板")
    dependencies: list[str] = Field(default_factory=list, description="依赖的 Skill 名称")
    iteration: SkillIteration = Field(default_factory=SkillIteration, description="迭代元数据")
    extra_frontmatter: dict[str, Any] = Field(
        default_factory=dict,
        description="原始 frontmatter 中无法映射到已知字段的扩展键，保存时原样写回（向前兼容）",
    )

    @property
    def full_prompt(self) -> str:
        """将 CoSTAR 字段和 body 组合为完整 prompt。"""
        parts = []

        if self.costar.context:
            parts.append(f"# Context\n{self.costar.context}")
        if self.costar.objective:
            parts.append(f"# Objective\n{self.costar.objective}")
        if self.costar.style:
            parts.append(f"# Style\n{self.costar.style}")
        if self.costar.tone:
            parts.append(f"# Tone\n{self.costar.tone}")
        if self.costar.audience:
            parts.append(f"# Audience\n{self.costar.audience}")
        if self.costar.response_format:
            parts.append(f"# Response Format\n{self.costar.response_format}")

        if self.rules:
            rules_text = "\n".join(f"- {r}" for r in self.rules)
            parts.append(f"# Rules\n{rules_text}")

        if self.examples:
            examples_text = []
            for i, ex in enumerate(self.examples, 1):
                examples_text.append(f"## Example {i}\nInput: {ex.input}\nOutput: {ex.output}")
            parts.append("# Examples\n" + "\n".join(examples_text))

        if self.body:
            parts.append(self.body)

        return "\n\n".join(parts)
