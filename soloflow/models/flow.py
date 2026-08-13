"""Flow 数据模型 —— 多步骤 AI 工作流编排。

Flow = DAG of Steps，每个 Step = Skill/Agent + 输入映射 + 依赖关系。
"""

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


class StepInput(BaseModel):
    """Step 的输入变量映射。

    支持三种来源：
    - $input.xxx —— Flow 级别的输入参数
    - $steps.<step_id>.output —— 前序步骤的输出
    - 直接字符串 —— 字面量
    """

    mapping: dict[str, Any] = Field(default_factory=dict, description="变量名 → 值/引用")


class FlowStep(BaseModel):
    """Flow 中的一个步骤。

    每个步骤：
    - 绑定一个 Skill（或 Agent）
    - 定义输入变量映射
    - 声明依赖的前序步骤
    """

    id: str = Field(..., description="步骤 ID（在 Flow 内唯一）")
    skill: str = Field(..., description="使用的 Skill 名称")
    agent: str | None = Field(
        default=None, description="使用的 Agent 名称（可选，优先级高于 skill）"
    )
    description: str = Field(default="", description="步骤描述")
    input: StepInput = Field(default_factory=StepInput, description="输入变量映射")
    depends_on: list[str] = Field(default_factory=list, description="依赖的前序步骤 ID 列表")
    # BUG-FLOW-008 部分: 步骤级策略（0 = 使用引擎默认值）
    timeout: float = Field(default=0.0, ge=0.0, description="单次 LLM 调用超时秒数（0=默认 120s）")
    retries: int = Field(default=0, ge=0, description="可重试错误的最大重试次数（0=默认 2 次）")

    @model_validator(mode="before")
    @classmethod
    def accept_playbook_alias(cls, data):
        """Accept the user-facing ``playbook`` key while keeping ``skill`` internally."""
        if isinstance(data, dict) and "skill" not in data and "playbook" in data:
            data = dict(data)
            data["skill"] = data["playbook"]
        return data

    @field_validator("id")
    @classmethod
    def id_must_be_kebab(cls, v: str) -> str:
        r"""P2-005: Step ID 限制为 kebab-case，防止路径穿越（../、/、\）。"""
        if not re.match(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$", v):
            raise ValueError(
                f"Step ID '{v}' 必须是 kebab-case（小写字母/数字/连字符，"
                f"如 research、write-article）"
            )
        return v


class FlowDefinition(BaseModel):
    """完整的 Flow 工作流定义。

    示例 YAML:
    ```yaml
    name: blog-pipeline
    version: 1.0.0
    description: End-to-end blog post creation

    input:
      topic:
        type: string
        required: true
        description: Blog post topic

    steps:
      - id: research
        skill: market-researcher
        input:
          mapping:
            topic: $input.topic
      - id: write
        skill: content-writer
        input:
          mapping:
            topic: $input.topic
            research: $steps.research.output
        depends_on: [research]
    ```
    """

    name: str = Field(..., description="Flow 名称")
    version: str = Field(default="0.1.0", description="版本号")
    description: str = Field(default="", description="描述")
    input_schema: dict[str, Any] = Field(default_factory=dict, description="输入参数 schema")
    steps: list[FlowStep] = Field(..., description="步骤列表", min_length=1)
    output: dict[str, str] = Field(default_factory=dict, description="输出映射")


class StepResult(BaseModel):
    """单个步骤的执行结果。"""

    step_id: str
    status: str = "pending"  # pending | running | done | failed
    output: str | None = None
    error: str | None = None
    duration: float = 0.0
    tokens: int = 0


class FlowResult(BaseModel):
    """Flow 的执行结果。"""

    flow_name: str
    run_id: str = Field(default="", description="运行 ID（恢复时复用原 run ID）")
    status: str = "pending"
    steps: dict[str, StepResult] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(
        default_factory=dict, description="Flow 正式输出映射（$flow.output）"
    )
    total_duration: float = 0.0
    total_tokens: int = 0
