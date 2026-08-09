"""Skill 数据模型 —— SoloFlow 的核心数据结构。

一个 Skill 文件采用 YAML frontmatter + Markdown body 格式，
人机双读、Git 友好、符合 agentskills.io 社区标准。
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


class SkillConfig(BaseModel):
    """Skill 的 LLM 配置。"""

    model: str = Field(default="deepseek-v4-flash", description="默认模型")
    provider: str = Field(default="deepseek", description="默认 LLM 提供商")
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
    """

    meta: SkillMeta = Field(..., description="元信息")
    costar: CoSTAR = Field(default_factory=CoSTAR, description="CoSTAR 提示词")
    config: SkillConfig = Field(default_factory=SkillConfig, description="LLM 配置")
    rules: list[str] = Field(default_factory=list, description="规则清单")
    examples: list[SkillExample] = Field(default_factory=list, description="示例")
    tests: list[SkillTest] = Field(default_factory=list, description="测试用例")
    body: str = Field(default="", description="Markdown 正文 —— 实际 prompt 模板")
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
