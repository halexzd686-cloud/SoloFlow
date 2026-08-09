"""Agent 数据模型。

Agent = Skill + 角色设定 + LLM 绑定。
Agent 是薄层——它只是给 Skill 穿上一件"角色外套"。
"""

from pydantic import BaseModel, Field


class AgentConfigOverride(BaseModel):
    """Agent 的 LLM 配置覆盖（BUG-AGENT-001 修复）。

    全部字段 Optional：
    - None = 未配置，继承 Skill 的 config
    - 非 None = 显式覆盖

    修复前用"是否等于默认值"判断是否覆盖，无法区分
    "用户没配置"与"用户显式指定默认值"。现在 None 语义清晰。
    """

    model: str | None = Field(default=None, description="模型名（None=继承 Skill）")
    provider: str | None = Field(default=None, description="提供商（None=继承 Skill）")
    temperature: float | None = Field(default=None, description="温度（None=继承 Skill）")
    max_tokens: int | None = Field(default=None, description="最大输出 token（None=继承 Skill）")


class AgentSoul(BaseModel):
    """Agent 的性格与行为设定（蜂群思维中的"灵魂设定"）。"""

    personality: str = Field(default="", description="性格描述")
    values: list[str] = Field(default_factory=list, description="核心价值观")
    behavior_rules: list[str] = Field(default_factory=list, description="行为准则")


class AgentHeartbeat(BaseModel):
    """心跳机制——让 Agent 从被动执行者升级为主动工作者。"""

    enabled: bool = Field(default=False, description="是否启用心跳")
    interval: str = Field(default="1h", description="触发间隔（如 30m / 1h / 6h）")
    trigger_prompt: str = Field(default="", description="触发时执行的指令")


class AgentDefinition(BaseModel):
    """Agent 定义。

    一个 Agent 拥有：
    - 一份或多份 Skill（核心能力）
    - 一个 Soul（性格设定）
    - 一个 Heartbeat（可选心跳机制）
    - 独立的 LLM 配置覆盖
    """

    name: str = Field(..., description="Agent 名称 (kebab-case)")
    description: str = Field(default="", description="Agent 职责描述")
    skills: list[str] = Field(default_factory=list, description="绑定的 Skill 名称列表")
    soul: AgentSoul = Field(default_factory=AgentSoul, description="性格设定")
    heartbeat: AgentHeartbeat = Field(default_factory=AgentHeartbeat, description="心跳机制")
    config: AgentConfigOverride = Field(
        default_factory=AgentConfigOverride, description="LLM 配置覆盖（None=继承 Skill）"
    )
    rules: list[str] = Field(
        default_factory=list, description="Agent 级别的规则（叠加在 Skill 规则之上）"
    )

    @property
    def system_prompt(self) -> str:
        """生成 Agent 的系统级 prompt（角色设定部分）。"""
        parts = []

        if self.soul.personality:
            parts.append(f"# Agent Role\n{self.soul.personality}")

        if self.soul.values:
            parts.append("\n# Core Values\n" + "\n".join(f"- {v}" for v in self.soul.values))

        if self.soul.behavior_rules:
            parts.append("\n# Behavior\n" + "\n".join(f"- {r}" for r in self.soul.behavior_rules))

        if self.rules:
            parts.append("\n# Agent Rules\n" + "\n".join(f"- {r}" for r in self.rules))

        return "\n".join(parts)
