"""面向普通用户的工作助手应用层。

这一层把网页表单转换为可保存、可版本化、可运行的工作助手定义，
并复用现有 Runner 的模型调用边界。
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from soloflow.artifacts import ArtifactRecord, write_artifacts, write_zip
from soloflow.core.runner import execute_prompt
from soloflow.file_processing import (
    FileAttachment,
    SensitiveFinding,
    attachment_content,
    redact_text,
    scan_sensitive,
)
from soloflow.llm.client import DEFAULT_API_KEY_ENV, DEFAULT_BASE_URL, DEFAULT_MODEL


class PrivacyConfirmationError(ValueError):
    """用户尚未确认将必要内容发送给 DeepSeek。"""


class PrivacyReviewError(ValueError):
    """本地检查发现敏感信息，需要用户选择脱敏或重新上传。"""

    def __init__(self, findings: list[SensitiveFinding]):
        self.findings = findings
        super().__init__("检测到可能的敏感信息，请选择按建议脱敏或手动修改后重新上传")


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


class AssistantPackage(BaseModel):
    """可分享的工作助手文件，不包含本地运行数据。"""

    kind: str = "soloflow-assistant"
    schema_version: int = 1
    exported_at: str
    source_version: str
    definition: AssistantDefinition
    versions: list[AssistantVersion] = Field(default_factory=list)


class RunRecord(BaseModel):
    """一次工作助手运行记录。"""

    id: str
    assistant_id: str
    assistant_version: str
    model: str
    status: str
    input_text: str
    temporary_request: str = ""
    input_files: list[str] = Field(default_factory=list)
    privacy_findings: list[SensitiveFinding] = Field(default_factory=list)
    artifacts: list[ArtifactRecord] = Field(default_factory=list)
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


def draft_prompt(description: str, attachment_text: str = "") -> str:
    description = description.strip() or (
        "用户没有提供文字描述，请根据附件内容判断这项重复工作的目标和处理方式。"
    )
    attachment_section = (
        f"\n\n用户上传的材料内容：\n{attachment_text}" if attachment_text.strip() else ""
    )
    return f"""你正在帮助一个不懂 AI 的公司员工定义一个可重复使用的工作助手。

用户对重复工作的描述：
{description}{attachment_section}

请把描述整理成 JSON 对象，只输出 JSON，不要 Markdown 代码围栏。字段必须包含：
name（简短名称）、description（用途说明）、goal（工作目标）、input_fields（输入字段数组）。
每个输入字段包含 key、label、description、required；另外还要包含：
steps（工作步骤数组）、output_format（建议输出格式）、rules（规则数组）、
default_model（默认使用 deepseek-v4-flash，除非用户明确指定其他 deepseek- 模型）。
不要添加用户没有提到的事实；信息不足时使用清晰、保守的通用表达。"""


def draft_definition(
    description: str,
    model: str,
    attachments: list[FileAttachment] | None = None,
) -> AssistantDefinition:
    """用 DeepSeek 根据文字和附件整理成助手草稿。"""

    attachments = attachments or []
    if not description.strip() and not attachments:
        raise ValueError("请先描述你想重复处理的工作，或上传一份材料")
    attachment_prompt = attachment_content(attachments, model)
    prompt = draft_prompt(
        description, attachment_prompt if isinstance(attachment_prompt, str) else ""
    )
    model_content: str | list[dict[str, Any]]
    if isinstance(attachment_prompt, str):
        model_content = prompt
    else:
        model_content = [{"type": "text", "text": prompt}, *attachment_prompt]
    result = execute_prompt(
        model_content,
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

    def export_package(self, assistant_id: str) -> AssistantPackage:
        """导出助手方法和版本历史，不导出运行记录、附件或本地配置。"""

        record = self.get(assistant_id)
        return AssistantPackage(
            exported_at=_now(),
            source_version=record.current_version,
            definition=record.current,
            versions=record.versions,
        )

    def import_package(self, payload: dict[str, Any]) -> AssistantRecord:
        """从分享文件创建新的个人副本，始终生成新的本地 ID。"""

        package = AssistantPackage.model_validate(payload)
        if package.kind != "soloflow-assistant":
            raise ValueError("不是 SoloFlow 工作助手文件")
        if package.schema_version != 1:
            raise ValueError(f"不支持的工作助手文件版本：{package.schema_version}")

        timestamp = _now()
        versions = list(package.versions)
        if not any(item.version == package.source_version for item in versions):
            versions.append(
                AssistantVersion(
                    version=package.source_version,
                    definition=package.definition,
                    change_note="从共享文件导入",
                    created_at=timestamp,
                )
            )
        record = AssistantRecord(
            id=_assistant_id(package.definition.name),
            current_version=package.source_version,
            current=package.definition,
            versions=versions,
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

    def delete_run(self, run_id: str) -> None:
        """删除一次运行的本地记录、原始附件和生成文件。"""

        runs_root = self.runs_dir.resolve()
        run_dir = (self.runs_dir / run_id).resolve()
        if run_dir.parent != runs_root or not run_dir.is_dir():
            raise FileNotFoundError(f"找不到运行记录：{run_id}")
        shutil.rmtree(run_dir)

    def delete_assistant_history(self, assistant_id: str) -> int:
        """删除指定助手的全部本地运行记录，返回删除数量。"""

        self.get(assistant_id)
        deleted = 0
        if not self.runs_dir.is_dir():
            return deleted
        for run_dir in self.runs_dir.iterdir():
            run_path = run_dir / "run.json"
            if not run_dir.is_dir() or not run_path.is_file():
                continue
            try:
                run = RunRecord.model_validate_json(run_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if run.assistant_id == assistant_id:
                shutil.rmtree(run_dir)
                deleted += 1
        return deleted

    def run(
        self,
        assistant_id: str,
        input_text: str,
        model: str,
        temporary_request: str = "",
        privacy_confirmed: bool = False,
        attachments: list[FileAttachment] | None = None,
        output_formats: list[str] | None = None,
        redact: bool = False,
        privacy_override: bool = False,
    ) -> RunRecord:
        if not input_text.strip():
            input_text = ""

        attachments = attachments or []
        findings = scan_sensitive(input_text) + [
            finding for attachment in attachments for finding in attachment.findings
        ]
        if findings and not redact and not privacy_override:
            raise PrivacyReviewError(findings)
        if not privacy_confirmed:
            raise PrivacyConfirmationError("运行前必须确认必要内容将发送给 DeepSeek")
        if not input_text.strip() and not attachments:
            raise ValueError("请先填写本次任务内容或上传文件")

        if redact:
            input_text = redact_text(input_text)
            for attachment in attachments:
                attachment.text = redact_text(attachment.text)

        record = self.get(assistant_id)
        run = RunRecord(
            id=uuid.uuid4().hex,
            assistant_id=assistant_id,
            assistant_version=record.current_version,
            model=model,
            status="running",
            input_text=input_text,
            temporary_request=temporary_request,
            input_files=[attachment.filename for attachment in attachments],
            privacy_findings=findings,
            created_at=_now(),
        )
        self.save_run(run)
        run_dir = self.runs_dir / run.id
        input_dir = run_dir / "inputs"
        redacted_dir = run_dir / "redacted"
        for attachment in attachments:
            if attachment.data_base64:
                import base64

                input_dir.mkdir(parents=True, exist_ok=True)
                (input_dir / attachment.filename).write_bytes(
                    base64.b64decode(attachment.data_base64)
                )
            if redact and attachment.text:
                redacted_dir.mkdir(parents=True, exist_ok=True)
                (redacted_dir / f"{Path(attachment.filename).stem}.txt").write_text(
                    attachment.text, encoding="utf-8"
                )

        prompt = _run_prompt(record.current, input_text, temporary_request)
        attachment_prompt = attachment_content(attachments, model)
        if isinstance(attachment_prompt, str):
            if attachment_prompt.strip():
                prompt = f"{prompt}\n\n附件内容：\n{attachment_prompt}"
            model_content: str | list[dict[str, Any]] = prompt
        else:
            model_content = [{"type": "text", "text": prompt}, *attachment_prompt]
        try:
            result = execute_prompt(
                model_content,
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
        artifacts = write_artifacts(
            run_dir / "artifacts",
            record.current.name,
            result.content,
            output_formats or ["md"],
        )
        if len(artifacts) > 1:
            artifacts.append(write_zip(run_dir / "artifacts", artifacts))
        run.artifacts = artifacts
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
