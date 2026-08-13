"""面向普通用户的工作助手应用层。

这一层把网页表单转换为可保存、可版本化、可运行的工作助手定义，
并复用现有 Runner 的模型调用边界。
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from soloflow.core.runner import execute_prompt
from soloflow.llm.client import DEFAULT_API_KEY_ENV, DEFAULT_BASE_URL, DEFAULT_MODEL


class PrivacyConfirmationError(ValueError):
    """用户尚未确认将必要内容发送给 DeepSeek。"""


class InputField(BaseModel):
    """工作助手需要用户提供的一项输入。"""

    key: str
    label: str
    description: str = ""
    required: bool = True


class AssistantDefinition(BaseModel):
    """一个工作助手的当前可执行定义。"""

    name: str = Field(min_length=1, max_length=80)
    description: str = ""
    goal: str = Field(min_length=1)
    input_fields: list[InputField] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    output_format: str = "Markdown"
    rules: list[str] = Field(default_factory=list)
    default_model: str = DEFAULT_MODEL


class AssistantVersion(BaseModel):
    """工作助手的一份历史版本。"""

    version: str
    definition: AssistantDefinition
    change_note: str = ""
    created_at: str


class AssistantRecord(BaseModel):
    """工作助手及其版本历史。"""

    id: str
    current_version: str
    current: AssistantDefinition
    versions: list[AssistantVersion] = Field(default_factory=list)
    created_at: str
    updated_at: str


class RunRecord(BaseModel):
    """一次工作助手运行记录。"""

    id: str
    assistant_id: str
    assistant_version: str
    model: str
    status: str
    input_text: str
    temporary_request: str = ""
    output: str = ""
    error: str | None = None
    created_at: str
    completed_at: str | None = None


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _assistant_id(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return f"{slug[:40] or 'assistant'}-{uuid.uuid4().hex[:8]}"


def _next_version(version: str) -> str:
    parts = version.split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return "1.1.0"
    return f"{parts[0]}.{int(parts[1]) + 1}.0"


def _json_object(text: str) -> dict[str, Any] | None:
    """从模型输出中提取 JSON 对象，兼容 Markdown 代码围栏。"""

    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def draft_prompt(description: str) -> str:
    return f"""你正在帮助一个不懂 AI 的公司员工定义一个可重复使用的工作助手。

用户对重复工作的描述：
{description.strip()}

请把描述整理成 JSON 对象，只输出 JSON，不要 Markdown 代码围栏。字段必须包含：
name（简短名称）、description（用途说明）、goal（工作目标）、input_fields（输入字段数组）。
每个输入字段包含 key、label、description、required；另外还要包含：
steps（工作步骤数组）、output_format（建议输出格式）、rules（规则数组）、
default_model（默认使用 deepseek-chat，除非用户明确指定其他 deepseek- 模型）。
不要添加用户没有提到的事实；信息不足时使用清晰、保守的通用表达。"""


def draft_definition(description: str, model: str) -> AssistantDefinition:
    """用 DeepSeek 将自然语言描述整理成助手草稿。"""

    if not description.strip():
        raise ValueError("请先描述你想重复处理的工作")
    result = execute_prompt(
        draft_prompt(description),
        base_url=DEFAULT_BASE_URL,
        api_key_env=DEFAULT_API_KEY_ENV,
        model=model,
        temperature=0.2,
        max_tokens=2000,
    )
    data = _json_object(result.content)
    if data is None:
        raise ValueError("模型没有返回可识别的助手草稿，请重试")
    try:
        return AssistantDefinition.model_validate(data)
    except Exception as exc:
        raise ValueError(f"助手草稿格式不完整：{exc}") from exc


class AssistantStore:
    """本地保存工作助手和运行记录。"""

    def __init__(self, project_dir: Path):
        self.root = project_dir / ".soloflow"
        self.assistants_dir = self.root / "assistants"
        self.runs_dir = self.root / "runs"

    def _path(self, assistant_id: str) -> Path:
        return self.assistants_dir / assistant_id / "assistant.json"

    def list(self) -> list[AssistantRecord]:
        records: list[AssistantRecord] = []
        if not self.assistants_dir.is_dir():
            return records
        for path in sorted(self.assistants_dir.glob("*/assistant.json")):
            try:
                records.append(
                    AssistantRecord.model_validate_json(path.read_text(encoding="utf-8"))
                )
            except (OSError, ValueError):
                continue
        return records

    def get(self, assistant_id: str) -> AssistantRecord:
        path = self._path(assistant_id)
        if not path.is_file():
            raise FileNotFoundError(f"找不到工作助手：{assistant_id}")
        return AssistantRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def _save(self, record: AssistantRecord) -> AssistantRecord:
        path = self._path(record.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(record.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return record

    def create(self, definition: AssistantDefinition) -> AssistantRecord:
        timestamp = _now()
        record = AssistantRecord(
            id=_assistant_id(definition.name),
            current_version="1.0.0",
            current=definition,
            versions=[
                AssistantVersion(
                    version="1.0.0",
                    definition=definition,
                    change_note="首次保存",
                    created_at=timestamp,
                )
            ],
            created_at=timestamp,
            updated_at=timestamp,
        )
        return self._save(record)

    def create_version(
        self, assistant_id: str, definition: AssistantDefinition, change_note: str = ""
    ) -> AssistantRecord:
        record = self.get(assistant_id)
        version = _next_version(record.current_version)
        timestamp = _now()
        record.current_version = version
        record.current = definition
        record.updated_at = timestamp
        record.versions.append(
            AssistantVersion(
                version=version,
                definition=definition,
                change_note=change_note or "用户确认长期修改",
                created_at=timestamp,
            )
        )
        return self._save(record)

    def save_run(self, run: RunRecord) -> RunRecord:
        run_dir = self.runs_dir / run.id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "run.json").write_text(
            json.dumps(run.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        if run.output:
            (run_dir / "result.md").write_text(run.output, encoding="utf-8")
        return run

    def run(
        self,
        assistant_id: str,
        input_text: str,
        model: str,
        temporary_request: str = "",
        privacy_confirmed: bool = False,
    ) -> RunRecord:
        if not privacy_confirmed:
            raise PrivacyConfirmationError("运行前必须确认必要内容将发送给 DeepSeek")
        if not input_text.strip():
            raise ValueError("请先填写本次任务内容")

        record = self.get(assistant_id)
        run = RunRecord(
            id=uuid.uuid4().hex,
            assistant_id=assistant_id,
            assistant_version=record.current_version,
            model=model,
            status="running",
            input_text=input_text,
            temporary_request=temporary_request,
            created_at=_now(),
        )
        self.save_run(run)
        prompt = _run_prompt(record.current, input_text, temporary_request)
        try:
            result = execute_prompt(
                prompt,
                base_url=DEFAULT_BASE_URL,
                api_key_env=DEFAULT_API_KEY_ENV,
                model=model,
                temperature=0.7,
                max_tokens=4096,
            )
        except Exception as exc:
            run.status = "failed"
            run.error = str(exc)
            run.completed_at = _now()
            self.save_run(run)
            raise
        run.status = "completed"
        run.output = result.content
        run.completed_at = _now()
        return self.save_run(run)


def _run_prompt(
    definition: AssistantDefinition, input_text: str, temporary_request: str = ""
) -> str:
    steps = "\n".join(f"{index}. {step}" for index, step in enumerate(definition.steps, 1))
    rules = "\n".join(f"- {rule}" for rule in definition.rules)
    temporary = temporary_request.strip() or "无"
    return f"""你是 SoloFlow 工作助手“{definition.name}”。

工作目标：
{definition.goal}

工作步骤：
{steps or "请根据工作目标整理出清晰结果。"}

必须遵守的规则：
{rules or "- 不编造输入中没有的信息。"}

本次临时要求（只影响本次任务，不修改长期助手）：
{temporary}

本次输入内容：
{input_text.strip()}

请按“{definition.output_format}”格式输出最终结果。"""
