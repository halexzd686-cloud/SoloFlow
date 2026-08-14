"""SoloFlow 本地网页入口。

P0 只提供本地网页骨架和基础设置。真正的工作助手运行流程由后续阶段接入
现有 Runner 与文件处理层；工作助手应用层负责统一编排模型调用。
"""

# 内嵌 HTML/CSS/JavaScript 为了可读性保留长行。
# ruff: noqa: E501

from __future__ import annotations

import base64
import json
import os
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

import httpx

from soloflow.assistant_store import (
    AssistantDefinition,
    AssistantStore,
    PrivacyConfirmationError,
    PrivacyReviewError,
    draft_definition,
)
from soloflow.config import load_project_env
from soloflow.file_processing import FileAttachment, redact_text, scan_sensitive

DEFAULT_MODEL = "deepseek-v4-flash"
DEEPSEEK_MODEL_OPTIONS = ["deepseek-v4-flash", "deepseek-v4-pro"]
LEGACY_MODEL_ALIASES = {"deepseek-chat", "deepseek-reasoner"}
SETTINGS_RELATIVE_PATH = Path(".soloflow") / "config" / "settings.json"
PUBLIC_INPUT_EXTENSIONS = frozenset({".docx", ".xlsx", ".csv", ".pdf", ".txt", ".md"})


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _update_dotenv(path: Path, key: str, value: str) -> None:
    """更新项目 .env 中的单个键，不覆盖其他配置。"""

    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = existing.splitlines()
    replaced = False
    output: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"{key}="):
            output.append(f"{key}={value}")
            replaced = True
        else:
            output.append(line)
    if not replaced:
        if output and output[-1] != "":
            output.append("")
        output.append(f"{key}={value}")
    path.write_text("\n".join(output) + "\n", encoding="utf-8")


class WebAppState:
    """本地网页所需的应用状态。"""

    def __init__(self, project_dir: Path | None = None):
        self.project_dir = (project_dir or Path.cwd()).resolve()
        self.settings_path = self.project_dir / SETTINGS_RELATIVE_PATH
        load_project_env(self.project_dir)
        self.assistants = AssistantStore(self.project_dir)

    def settings(self) -> dict[str, Any]:
        values = _read_json(self.settings_path)
        default_model = values.get("default_model", DEFAULT_MODEL)
        if default_model in LEGACY_MODEL_ALIASES:
            default_model = DEFAULT_MODEL
            _write_json(self.settings_path, {"default_model": default_model})
        return {
            "api_key_configured": bool(os.getenv("DEEPSEEK_API_KEY")),
            "default_model": default_model,
        }

    def models(self) -> list[str]:
        """返回当前 DeepSeek 可用的最新模型，失败时使用安全内置列表。"""

        configured = os.getenv("DEEPSEEK_API_KEY")
        if not configured:
            return DEEPSEEK_MODEL_OPTIONS.copy()
        import httpx

        try:
            response = httpx.get(
                "https://api.deepseek.com/models",
                headers={"Authorization": f"Bearer {configured}"},
                timeout=8.0,
            )
            response.raise_for_status()
            data = response.json()
            model_ids = [
                str(item.get("id", "")).strip()
                for item in data.get("data", [])
                if isinstance(item, dict)
            ]
            latest = [model_id for model_id in model_ids if "v4" in model_id.lower()]
            if latest:
                return list(dict.fromkeys(latest))[:4]
        except (httpx.HTTPError, OSError, ValueError, TypeError):
            pass
        return DEEPSEEK_MODEL_OPTIONS.copy()

    def save_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        model = str(payload.get("default_model", DEFAULT_MODEL)).strip() or DEFAULT_MODEL
        if not model.startswith("deepseek-"):
            raise ValueError("模型名称必须以 deepseek- 开头")

        api_key = str(payload.get("api_key", "")).strip()
        if api_key:
            _update_dotenv(self.project_dir / ".env", "DEEPSEEK_API_KEY", api_key)
            os.environ["DEEPSEEK_API_KEY"] = api_key

        _write_json(self.settings_path, {"default_model": model})
        return self.settings()

    @staticmethod
    def _attachments_from_payload(payload: dict[str, Any]) -> list[FileAttachment]:
        attachments: list[FileAttachment] = []
        for item in payload.get("attachments", []):
            if not isinstance(item, dict):
                continue
            filename = Path(str(item.get("filename", ""))).name
            extension = Path(filename).suffix.lower()
            if extension not in PUBLIC_INPUT_EXTENSIONS and extension in {".png", ".jpg", ".jpeg"}:
                raise ValueError(
                    "图片直接上传暂未开放；当前仅支持 Word、Excel、CSV、PDF 和文本文件"
                )
            attachments.append(FileAttachment.from_payload(item))
        return attachments

    def draft_assistant(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not payload.get("privacy_confirmed"):
            raise PrivacyConfirmationError("生成助手草稿前必须确认描述和附件会发送给 DeepSeek")
        model = str(payload.get("model") or self.settings()["default_model"]).strip()
        attachments = self._attachments_from_payload(payload)
        description = str(payload.get("description", ""))
        findings = scan_sensitive(description) + [
            finding for attachment in attachments for finding in attachment.findings
        ]
        if findings and not payload.get("redact") and not payload.get("privacy_override"):
            raise PrivacyReviewError(findings)
        if payload.get("redact"):
            description = redact_text(description)
            for attachment in attachments:
                attachment.text = redact_text(attachment.text)
        definition = draft_definition(description, model, attachments)
        return definition.model_dump(mode="json")

    def create_assistant(self, payload: dict[str, Any]) -> dict[str, Any]:
        definition = AssistantDefinition.model_validate(payload.get("definition", {}))
        return self.assistants.create(definition).model_dump(mode="json")

    def trial_assistant(self, assistant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        model = str(payload.get("model") or self.settings()["default_model"]).strip()
        attachments = self._attachments_from_payload(payload)
        run = self.assistants.run(
            assistant_id,
            str(payload.get("input_text", "")),
            model,
            temporary_request=str(payload.get("temporary_request", "")),
            privacy_confirmed=bool(payload.get("privacy_confirmed")),
            attachments=attachments,
            output_formats=[str(item) for item in payload.get("output_formats", ["md"])],
            redact=bool(payload.get("redact")),
            privacy_override=bool(payload.get("privacy_override")),
        )
        return run.model_dump(mode="json")

    def create_version(self, assistant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        definition = AssistantDefinition.model_validate(payload.get("definition", {}))
        record = self.assistants.create_version(
            assistant_id, definition, str(payload.get("change_note", ""))
        )
        return record.model_dump(mode="json")

    def export_assistant(self, assistant_id: str) -> dict[str, Any]:
        return self.assistants.export_package(assistant_id).model_dump(mode="json")

    def import_assistant(self, payload: dict[str, Any]) -> dict[str, Any]:
        encoded = str(payload.get("package_base64", "")).strip()
        if not encoded:
            raise ValueError("请先选择 .sfassistant 工作助手文件")
        try:
            raw = base64.b64decode(encoded, validate=True)
            package = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("工作助手文件无法读取，请选择 SoloFlow 导出的文件") from exc
        if not isinstance(package, dict):
            raise ValueError("工作助手文件格式不正确")
        return self.assistants.import_package(package).model_dump(mode="json")

    def delete_run(self, run_id: str) -> dict[str, Any]:
        self.assistants.delete_run(run_id)
        return {"deleted": True, "run_id": run_id}

    def delete_assistant_history(self, assistant_id: str) -> dict[str, Any]:
        count = self.assistants.delete_assistant_history(assistant_id)
        return {"deleted": True, "assistant_id": assistant_id, "count": count}


HOME_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SoloFlow 工作助手</title>
  <style>
    :root { color-scheme: light; font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", "PingFang SC", "Microsoft YaHei", sans-serif; --ink: #2e3834; --muted: #75827d; --muted-2: #98a7a1; --line: #e1ebe6; --line-strong: #cedfd8; --paper: #fbfdfc; --paper-soft: #f5faf7; --canvas: #edf1ef; --mint: #9acfbc; --mint-deep: #5b9d85; --mint-soft: #e2f2ec; --mint-pale: #f0f8f4; --success: #6aaa8f; --warm: #cfb580; --danger: #a85e51; }
    * { box-sizing: border-box; }
    html { scroll-behavior: smooth; }
    body { margin: 0; min-width: 320px; background: var(--canvas); color: var(--ink); -webkit-font-smoothing: antialiased; }
    header { border-bottom: 1px solid var(--line); background: var(--canvas); padding: 0 max(28px, calc((100% - 1160px) / 2)); }
    main { width: min(1160px, calc(100% - 56px)); margin: 0 auto; padding: 44px 0 84px; }
    h1, h2, h3, p { margin-top: 0; }
    h1 { margin-bottom: 0; font-size: 20px; letter-spacing: -.04em; }
    h2 { margin-bottom: 8px; font-size: 22px; letter-spacing: -.035em; }
    h3 { margin-bottom: 7px; font-size: 15px; }
    p { line-height: 1.7; }
    .header-bar { display: flex; justify-content: space-between; align-items: center; gap: 20px; max-width: 1160px; margin: 0 auto; border-bottom: 1px solid var(--line); padding: 24px 0 20px; }
    .brand { display: inline-flex; align-items: center; gap: 10px; color: var(--ink); text-decoration: none; }
    .brand-mark { display: grid; place-items: center; width: 26px; height: 26px; border: 1px solid var(--mint); border-radius: 8px; color: var(--mint-deep); background: var(--mint-soft); }
    .brand-mark::before { content: ""; width: 8px; height: 8px; border: 2px solid currentColor; border-radius: 50%; }
    .eyebrow { color: var(--ink); font-size: 15px; font-weight: 750; letter-spacing: -.025em; }
    .hero-copy, .intro { display: none; }
    .hero-start { width: min(760px, 100%); margin: 68px auto 0; border: 1px solid var(--line-strong); border-radius: 16px; padding: 27px; background: var(--paper); box-shadow: 0 20px 55px rgba(56, 67, 47, .08); }
    .hero-start::before { content: ""; display: block; height: 3px; margin: -28px 0 25px; border-radius: 0 0 4px 4px; background: var(--mint); }
    .card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; margin-bottom: 20px; }
    .card-subtitle { margin-top: 5px; color: var(--muted); font-size: 12px; line-height: 1.55; }
    .field-label, .hero-start > label { display: block; margin: 0 0 8px; color: var(--ink); font-size: 12px; font-weight: 700; }
    .description-box { overflow: hidden; border: 1px solid var(--line-strong); border-radius: 10px; background: var(--paper-soft); transition: border-color .18s ease, box-shadow .18s ease; }
    .description-box:focus-within { border-color: var(--mint-deep); box-shadow: 0 0 0 3px rgba(91, 157, 133, .13); }
    .hero-start textarea { display: block; width: 100%; min-height: 116px; resize: vertical; border: 0; border-radius: 0; padding: 13px 14px 9px; outline: 0; color: var(--ink); background: transparent; font: inherit; font-size: 14px; line-height: 1.65; }
    textarea::placeholder { color: var(--muted-2); }
    .description-tools { display: flex; align-items: center; justify-content: space-between; gap: 10px; border-top: 1px solid var(--line); padding: 8px 11px 9px 14px; color: var(--muted-2); font-size: 11px; }
    .upload-button { display: inline-flex; align-items: center; gap: 6px; border: 0; border-radius: 6px; padding: 5px 7px; color: var(--mint-deep); background: transparent; cursor: pointer; font-size: 11px; font-weight: 650; }
    .upload-button:hover { background: var(--mint-pale); }
    .upload-icon { width: 15px; height: 15px; border: 1.4px solid currentColor; border-radius: 4px; position: relative; }
    .upload-icon::before { content: ""; position: absolute; left: 6px; top: 3px; width: 1.4px; height: 7px; background: currentColor; }
    .upload-icon::after { content: ""; position: absolute; left: 3px; top: 6px; width: 7px; height: 1.4px; background: currentColor; }
    #assistant-files { display: none; }
    .hero-start .muted { margin-top: 8px; color: var(--muted-2); font-size: 11px; }
    .template-grid { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 17px !important; }
    .template-card { min-height: 0; border: 1px solid var(--line); border-radius: 7px; padding: 8px 10px; text-align: left; color: var(--muted); background: var(--paper); box-shadow: none; cursor: pointer; font-size: 11px; }
    .template-card:hover, .template-card:focus-visible { border-color: #b9ded0; color: var(--mint-deep); background: var(--mint-pale); transform: none; }
    .template-card h3 { margin: 0; font-size: 11px; font-weight: 600; }
    .template-card p { display: none; }
    .hero-start .field-row { margin: 18px 0 0; }
    .hero-start .field-row label { margin: 0 0 8px; color: var(--ink); }
    .hero-start .field-row select { margin-top: 0; }
    .hero-start .field-row:has(select) { display: grid; grid-template-columns: 1fr; }
    .hero-start .field-row:has(select) label { grid-column: 1; }
    .consent { display: flex; align-items: flex-start; gap: 10px; margin-top: 18px; border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; color: var(--muted); background: var(--paper-soft); font-size: 11px; line-height: 1.7; }
    .consent span { flex: 1; }
    .consent input, .format-option input { flex: 0 0 auto; width: 16px; height: 16px; margin: 2px 0 0; accent-color: var(--mint-deep); }
    button { border: 0; border-radius: 9px; padding: 10px 15px; color: var(--paper); background: var(--mint-deep); cursor: pointer; font-size: 14px; font-weight: 650; transition: transform .16s ease, box-shadow .16s ease, background .16s ease; }
    button:hover:not(:disabled), button:focus-visible { box-shadow: 0 8px 18px rgba(91, 157, 133, .16); transform: translateY(-1px); }
    button.secondary { color: var(--mint-deep); background: var(--mint-pale); border: 1px solid var(--line-strong); }
    button.ghost { border: 1px solid var(--line-strong); border-radius: 8px; padding: 9px 12px; color: var(--mint-deep); background: rgba(255,255,255,.4); }
    button:disabled { opacity: .55; cursor: not-allowed; }
    #draft-button { display: flex; justify-content: space-between; align-items: center; width: 100%; margin-top: 18px; border: 1px solid var(--mint-deep); padding: 12px 14px; color: var(--paper); background: var(--mint-deep); }
    .hero-start .actions { display: block; margin-top: 0; }
    .status { display: inline-flex; align-items: center; gap: 8px; border-radius: 999px; padding: 8px 12px; color: var(--muted); background: var(--mint-pale); font-size: 13px; }
    .status.ok { color: var(--success); background: var(--mint-soft); }
    .notice { border-left: 3px solid var(--mint); padding: 13px 15px; color: var(--muted); background: var(--mint-pale); font-size: 13px; line-height: 1.6; }
    .main-section { margin-top: 28px; }
    .process-rail { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0; margin: 0 auto 30px; border: 1px solid var(--line); border-radius: 13px; overflow: hidden; background: var(--paper); box-shadow: 0 8px 22px rgba(56, 67, 47, .035); }
    .process-step { position: relative; min-height: 137px; padding: 21px 24px; background: var(--paper); }
    .process-step + .process-step { border-left: 1px solid var(--line); }
    .process-step:not(:last-child)::after { content: ""; position: absolute; top: 34px; right: -18px; z-index: 1; width: 34px; height: 1px; background: var(--line-strong); }
    .process-step strong { display: block; margin: 16px 0 7px; font-size: 14px; }
    .process-step > span:last-child { display: block; max-width: 220px; color: var(--muted); font-size: 11px; line-height: 1.6; }
    .step-number { display: inline-grid; place-items: center; width: 23px; height: 23px; margin: 0; border: 1px solid #bedfd3; border-radius: 50%; color: var(--mint-deep); background: var(--mint-pale); font-size: 10px; font-weight: 750; }
    .panel { border: 1px solid var(--line); border-radius: 13px; padding: 24px; background: var(--paper); box-shadow: 0 8px 22px rgba(56, 67, 47, .035); }
    .setup-strip { display: grid; grid-template-columns: minmax(0, 1fr) minmax(300px, 1.1fr); align-items: center; gap: 22px; }
    .setup-strip .notice { margin: 0; }
    .section-heading { display: flex; justify-content: space-between; align-items: end; gap: 16px; margin-bottom: 16px; }
    .section-heading h2 { margin-bottom: 6px; }
    .card-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }
    label { display: block; margin: 14px 0 6px; color: var(--ink); font-weight: 650; font-size: 13px; }
    input, select { width: 100%; border: 1px solid var(--line-strong); border-radius: 8px; padding: 10px; color: var(--ink); background: var(--paper); font: inherit; font-size: 14px; }
    textarea { width: 100%; min-height: 112px; resize: vertical; border: 1px solid var(--line-strong); border-radius: 8px; padding: 11px; color: var(--ink); background: var(--paper); font: inherit; line-height: 1.5; }
    textarea:focus, input:focus, select:focus { outline: 3px solid rgba(91, 157, 133, .13); border-color: var(--mint-deep); }
    .actions { display: flex; justify-content: flex-end; flex-wrap: wrap; gap: 10px; margin-top: 20px; }
    .muted { color: var(--muted); font-size: 13px; }
    .field-row { margin: 14px 0; }
    .field-row label { margin-top: 0; }
    #assistant-import + .muted { margin-top: 9px; line-height: 1.75; }
    .output { min-height: 100px; overflow-wrap: anywhere; white-space: pre-wrap; border: 1px solid var(--line); border-radius: 10px; padding: 18px; background: var(--paper-soft); }
    .artifact-box { margin-top: 16px; border: 1px solid #d2e8df; border-radius: 10px; padding: 16px; background: var(--mint-pale); }
    .artifact-box a { color: var(--mint-deep); font-weight: 650; }
    .assistant-item { display: flex; justify-content: space-between; gap: 14px; align-items: center; border-top: 1px solid var(--line); padding: 16px 0; }
    .assistant-item:first-child { border-top: 0; }
    .assistant-item .actions { margin-top: 0; }
    .format-options { display: flex; flex-wrap: wrap; gap: 10px; }
    .format-option { display: inline-flex; align-items: center; gap: 7px; margin: 0; border: 1px solid var(--line); border-radius: 8px; padding: 9px 12px; color: var(--ink); background: var(--paper-soft); font-weight: 500; }
    .file-input, #assistant-import, #run-files { padding: 10px 12px; background: var(--paper-soft); border-color: var(--line-strong); color: var(--ink); }
    .file-input::file-selector-button, #assistant-import::file-selector-button, #run-files::file-selector-button { margin-right: 12px; border: 0; border-radius: 7px; padding: 8px 12px; color: var(--mint-deep); background: var(--mint-soft); cursor: pointer; }
    #assistant-import, #run-files { min-height: 46px; }
    .empty-state { padding: 18px 0; color: var(--muted); }
    dialog { width: min(520px, calc(100% - 44px)); border: 1px solid var(--line-strong); border-radius: 15px; padding: 0; background: var(--paper); box-shadow: 0 25px 65px rgba(56, 67, 47, .2); }
    dialog::backdrop { background: rgba(48, 56, 52, .24); backdrop-filter: blur(5px); }
    dialog form { padding: 24px; }
    .hidden { display: none; }
    @media (max-width: 760px) {
      header { padding: 0 18px; }
      main { width: calc(100% - 36px); padding: 28px 0 52px; }
      .header-bar, .section-heading, .setup-strip { display: block; }
      .header-bar button { margin-top: 16px; }
      .hero-start { margin-top: 44px; padding: 18px; }
      .hero-start::before { margin: -19px 0 18px; }
      .card-head { display: block; }
      .process-rail { grid-template-columns: 1fr; }
      .process-step { min-height: 0; padding: 18px 20px 19px 56px; }
      .process-step + .process-step { border-top: 1px solid var(--line); border-left: 0; }
      .process-step:not(:last-child)::after { top: auto; right: auto; bottom: -1px; left: 56px; width: 32px; }
      .process-step .step-number { position: absolute; top: 19px; left: 20px; }
      .process-step strong { margin-top: 0; }
      .process-step > span:last-child { max-width: none; }
      .assistant-item { display: block; }
      .assistant-item .actions { justify-content: flex-start; margin-top: 12px; }
    }
    @media (max-width: 460px) {
      .process-rail { margin-bottom: 22px; }
      .hero-start { border-radius: 13px; }
      .hero-start .field-row { display: block; }
      .setup-strip, .panel { padding: 18px; }
      .section-heading { margin-bottom: 13px; }
    }
    @media (prefers-reduced-motion: reduce) { *, *::before, *::after { scroll-behavior: auto !important; transition: none !important; } }
  </style>
</head>
<body>
  <header>
    <div class="header-bar">
      <a class="brand" href="/" aria-label="SoloFlow 首页">
        <span class="brand-mark" aria-hidden="true"></span>
        <span class="eyebrow">SoloFlow 本地工作助手</span>
      </a>
      <button class="ghost" id="settings-button">设置 DeepSeek</button>
    </div>
    <div class="hero-start">
      <div class="card-head">
        <div>
          <h1>创建一个工作助手</h1>
          <p class="card-subtitle">用平时说话的方式描述，或者直接上传手上的材料。</p>
        </div>
      </div>
      <label for="assistant-description">我想让 SoloFlow 帮我……</label>
      <div class="description-box">
        <textarea id="assistant-description" placeholder="例如：我每周要提交周报，包含本周完成、未完成、遇到的问题和下周计划，语气简洁，适合给领导看。"></textarea>
        <div class="description-tools">
          <span>支持 Word、Excel、PDF、文本</span>
          <label class="upload-button" for="assistant-files"><span class="upload-icon" aria-hidden="true"></span>添加材料</label>
        </div>
      </div>
      <input id="assistant-files" class="file-input" type="file" multiple accept=".docx,.xlsx,.csv,.pdf,.txt,.md">
      <div class="muted">当前支持 Word、Excel、CSV、PDF 和文本文件；图片暂未开放。</div>
      <div class="template-grid">
        <button type="button" class="template-card" data-template-description="我每周要提交周报，包含本周完成、未完成、遇到的问题和下周计划，语气简洁，适合给领导看。"><h3>周报整理</h3><p>把一周的工作记录整理成固定格式。</p></button>
        <button type="button" class="template-card" data-template-description="我需要把会议记录整理成会议纪要，包含会议结论、待办事项、负责人和截止时间，不能补充原文没有的信息。"><h3>会议纪要</h3><p>提取结论、待办和负责人。</p></button>
        <button type="button" class="template-card" data-template-description="我经常要把多份 Excel 或 CSV 数据汇总成一份适合汇报的结果，保留关键数字并标注异常。"><h3>表格汇总</h3><p>汇总多份数据并标出异常。</p></button>
        <button type="button" class="template-card" data-template-description="我每周要整理客户跟进记录，按照客户、当前进展、下一步行动和需要协助的问题输出销售跟进汇报。"><h3>销售跟进</h3><p>把零散记录变成跟进汇报。</p></button>
      </div>
      <div class="field-row">
        <label for="draft-model">本次使用模型</label>
        <select id="draft-model" data-model-select><option value="deepseek-v4-flash">DeepSeek V4 Flash（推荐）</option><option value="deepseek-v4-pro">DeepSeek V4 Pro</option></select>
      </div>
      <label class="consent"><input id="draft-privacy" type="checkbox"> <span>我知道描述和上传的材料会发送给 DeepSeek。<strong>我已检查内容是否敏感。</strong></span></label>
      <div class="actions"><button id="draft-button"><span>定制我的Work伙伴</span><span aria-hidden="true">→</span></button></div>
      <p id="draft-message" class="muted"></p>
      <div id="draft-privacy-review" class="notice hidden"><strong>发送前检查</strong><div id="draft-findings"></div><div class="actions"><button id="draft-redact-button">按建议脱敏并生成</button><button class="secondary" id="draft-manual-button">我修改后再上传</button></div></div>
    </div>
  </header>
  <main>
    <div class="process-rail" aria-label="使用流程">
      <div class="process-step"><span class="step-number">1</span><strong>描述工作</strong><span>用平时说话的方式告诉 SoloFlow</span></div>
      <div class="process-step"><span class="step-number">2</span><strong>确认方法</strong><span>检查并修改工作助手草稿</span></div>
      <div class="process-step"><span class="step-number">3</span><strong>生成结果</strong><span>上传材料并下载交付文件</span></div>
    </div>
    <section class="panel setup-strip main-section">
      <div><h2>使用前确认</h2><p class="muted">SoloFlow 在本机保存助手、运行记录和生成文件；只有必要内容会发送给你选择的 DeepSeek 模型。</p><p id="key-status" class="status">正在检查 DeepSeek 配置…</p></div>
      <div class="notice">每次运行前，你都可以检查材料是否敏感，再决定是否发送给 DeepSeek。API Key 只保存在当前项目本机。</div>
    </section>
    <section id="draft-panel" class="panel main-section hidden">
      <div class="section-heading"><div><h2>第 2 步：确认工作方法</h2><p class="muted">这是 SoloFlow 根据你的描述整理出的草稿。请先检查，再保存为自己的工作助手。</p></div></div>
      <div class="field-row"><label for="draft-name">助手名称</label><input id="draft-name"></div>
      <div class="field-row"><label for="draft-description">用途说明</label><textarea id="draft-description"></textarea></div>
      <div class="field-row"><label for="draft-goal">工作目标</label><textarea id="draft-goal"></textarea></div>
      <div class="field-row"><label for="draft-steps">工作步骤（每行一步）</label><textarea id="draft-steps"></textarea></div>
      <div class="field-row"><label for="draft-rules">注意事项（每行一条）</label><textarea id="draft-rules"></textarea></div>
      <div class="field-row"><label for="draft-format">最终输出格式</label><input id="draft-format"></div>
      <div class="field-row"><label for="draft-inputs">需要用户填写的内容（每行一项）</label><textarea id="draft-inputs"></textarea></div>
      <div class="actions"><button class="secondary" id="cancel-draft-button">放弃草稿</button><button id="save-assistant-button">保存为工作助手</button></div>
    </section>
    <section class="panel main-section">
      <div class="section-heading"><div><h2>我的工作助手</h2><p class="muted">保存后，你可以反复使用，也可以导出给同事作为个人副本。</p></div></div>
      <div class="field-row"><label for="assistant-import">导入同事分享的工作助手</label><input id="assistant-import" type="file" accept=".sfassistant,.json"><div class="muted">导入后会创建新的个人副本，不会带入对方的 API Key、原始材料、运行记录和结果文件。</div></div>
      <div class="actions"><button class="secondary" id="import-assistant-button">导入个人副本</button></div>
      <p id="assistant-message" class="muted"></p>
      <div id="assistant-list" class="empty-state">还没有保存的工作助手。先在页面顶部描述一项重复工作。</div>
      <div id="run-panel" class="run-panel hidden">
        <div class="section-heading"><div><h2 id="run-title"></h2><p id="run-version" class="muted"></p></div></div>
        <div class="field-row"><label for="run-input">第 3 步：填写本次要处理的内容</label><textarea id="run-input" placeholder="粘贴本周工作记录，或输入这次要整理的内容。"></textarea></div>
        <div class="field-row"><label for="run-files">上传材料（可选，单个文件不超过 20 MB）</label><input id="run-files" type="file" multiple accept=".docx,.xlsx,.csv,.pdf,.txt,.md"><div id="file-hints" class="muted">支持 Word、Excel、CSV、PDF 和文本文件；图片、扫描件与 OCR 暂未开放。</div></div>
        <div class="field-row"><label for="temporary-request">本次临时要求（可选，不会自动修改助手）</label><textarea id="temporary-request" placeholder="例如：这次把问题部分写得更适合给领导看。"></textarea></div>
        <div class="field-row"><label for="run-model">本次使用模型</label><select id="run-model" data-model-select><option value="deepseek-v4-flash">DeepSeek V4 Flash（推荐）</option><option value="deepseek-v4-pro">DeepSeek V4 Pro</option></select></div>
        <div class="field-row"><label>你希望下载哪些格式？</label><div id="output-formats" class="format-options"><label class="format-option"><input type="checkbox" name="output-format" value="md"> Markdown</label><label class="format-option"><input type="checkbox" name="output-format" value="docx"> Word</label><label class="format-option"><input type="checkbox" name="output-format" value="xlsx"> Excel</label><label class="format-option"><input type="checkbox" name="output-format" value="pdf"> PDF</label></div><div class="muted">可以选择多个格式；选择多个时还会提供 ZIP 打包下载。</div></div>
        <label class="consent"><input id="run-privacy" type="checkbox"> <span>我确认本次内容可以发送给 DeepSeek，并已检查是否包含敏感信息。</span></label>
        <div class="actions"><button id="run-button">生成本次结果</button><button class="secondary" id="save-version-button" disabled>把本次要求保存为规则</button></div>
        <p id="run-message" class="muted"></p>
        <div id="privacy-review" class="notice hidden"><strong>发送前检查</strong><div id="privacy-findings"></div><div class="actions"><button id="redact-and-run-button">按建议脱敏并继续</button><button class="secondary" id="manual-review-button">我手动修改后重新上传</button></div></div>
        <h3>最终结果</h3>
        <div id="run-output" class="output">生成后会在这里显示结果预览。</div>
        <div id="artifact-list" class="artifact-box"></div>
        <div class="actions"><button class="secondary hidden" id="delete-run-button">删除本次运行记录</button></div>
      </div>
    </section>
  </main>
  <dialog id="settings-dialog">
    <form method="dialog" id="settings-form">
      <h2>DeepSeek 设置</h2>
      <p class="muted">API Key 只保存在当前项目本机的 .env 文件中，不会进入工作助手分享文件。</p>
      <label for="api-key">DeepSeek API Key（已有配置可留空）</label>
      <input id="api-key" name="api_key" type="password" autocomplete="off" placeholder="sk-…">
      <label for="default-model">默认模型</label>
      <input id="default-model" name="default_model" value="deepseek-v4-flash" placeholder="deepseek-v4-flash">
      <div class="actions"><button type="button" class="secondary" id="cancel-button">取消</button><button type="submit">保存设置</button></div>
      <p id="settings-message" class="muted"></p>
    </form>
  </dialog>
  <script>
    const dialog = document.querySelector('#settings-dialog');
    const status = document.querySelector('#key-status');
    const message = document.querySelector('#settings-message');
    let currentDraft = null;
    let currentAssistant = null;
    let lastTemporaryRequest = '';
    let lastRunId = '';

    function lines(value) {
      return value.split('\\\\n').map(item => item.trim()).filter(Boolean);
    }

    function showMessage(target, text, error = false) {
      target.textContent = text;
      target.style.color = error ? '#b33636' : '';
    }

    function escapeHtml(value) {
      return String(value).replace(/[&<>"']/g, character => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));
    }

    async function loadSettings() {
      const response = await fetch('/api/settings');
      const data = await response.json();
      status.textContent = data.api_key_configured ? `DeepSeek 已配置 · 默认模型：${data.default_model}` : '还没有配置 DeepSeek API Key';
      status.className = data.api_key_configured ? 'status ok' : 'status';
      document.querySelector('#default-model').value = data.default_model;
      return data;
    }

    function modelLabel(model) {
      if (model === 'deepseek-v4-flash') return 'DeepSeek V4 Flash（推荐）';
      if (model === 'deepseek-v4-pro') return 'DeepSeek V4 Pro';
      return model;
    }

    async function loadModels(preferred = '') {
      const response = await fetch('/api/models');
      const data = await response.json();
      const models = Array.isArray(data.models) && data.models.length ? data.models : ['deepseek-v4-flash', 'deepseek-v4-pro'];
      document.querySelectorAll('[data-model-select]').forEach(select => {
        const current = preferred || select.value;
        select.innerHTML = models.map(model => `<option value="${escapeHtml(model)}">${escapeHtml(modelLabel(model))}</option>`).join('');
        select.value = models.includes(current) ? current : models[0];
      });
    }

    async function loadAssistants() {
      const response = await fetch('/api/assistants');
      const assistants = await response.json();
      const container = document.querySelector('#assistant-list');
      if (!assistants.length) { container.classList.add('empty-state'); container.textContent = '还没有保存的工作助手。先在页面顶部描述一项重复工作。'; return; }
      container.classList.remove('empty-state');
      container.innerHTML = assistants.map(item => `<div class="assistant-item"><div><strong>${escapeHtml(item.current.name)}</strong><div class="muted">${escapeHtml(item.current.description || item.current.goal)} · v${escapeHtml(item.current_version)}</div></div><div class="actions"><button class="secondary" data-use-assistant-id="${escapeHtml(item.id)}">使用</button><button class="secondary" data-export-assistant-id="${escapeHtml(item.id)}">导出</button><button class="secondary" data-history-assistant-id="${escapeHtml(item.id)}">清空历史</button></div></div>`).join('');
      container.querySelectorAll('[data-use-assistant-id]').forEach(button => button.addEventListener('click', () => selectAssistant(button.dataset.useAssistantId)));
      container.querySelectorAll('[data-export-assistant-id]').forEach(button => button.addEventListener('click', () => downloadAssistant(button.dataset.exportAssistantId)));
      container.querySelectorAll('[data-history-assistant-id]').forEach(button => button.addEventListener('click', () => deleteAssistantHistory(button.dataset.historyAssistantId)));
    }

    async function downloadAssistant(id) {
      const response = await fetch(`/api/assistants/${id}/export`);
      if (!response.ok) { showMessage(document.querySelector('#assistant-message'), '导出失败，请稍后重试。', true); return; }
      const blob = await response.blob();
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'soloflow-assistant.sfassistant';
      link.click();
      URL.revokeObjectURL(link.href);
      showMessage(document.querySelector('#assistant-message'), '工作助手文件已下载，可以发给同事。');
    }

    async function deleteAssistantHistory(id) {
      if (!window.confirm('确定删除这个工作助手的全部本地运行记录和生成文件吗？此操作不可恢复。')) return;
      const response = await fetch(`/api/assistants/${id}/history`, { method: 'DELETE' });
      const data = await response.json();
      if (!response.ok) { showMessage(document.querySelector('#assistant-message'), data.error || '删除历史失败', true); return; }
      showMessage(document.querySelector('#assistant-message'), `已删除 ${data.count || 0} 条本地运行记录及其文件。`);
    }

    async function selectAssistant(id) {
      const response = await fetch(`/api/assistants/${id}`);
      currentAssistant = await response.json();
      document.querySelector('#run-panel').classList.remove('hidden');
      document.querySelector('#run-title').textContent = currentAssistant.current.name;
      document.querySelector('#run-version').textContent = `当前版本：v${currentAssistant.current_version} · ${currentAssistant.current.description || currentAssistant.current.goal}`;
      document.querySelector('#run-model').value = currentAssistant.current.default_model;
      document.querySelector('#run-output').textContent = '生成后会在这里显示结果预览。';
      document.querySelector('#artifact-list').textContent = '';
      document.querySelector('#artifact-list').classList.add('hidden');
      document.querySelectorAll('input[name="output-format"]').forEach(input => { input.checked = false; });
      document.querySelector('#delete-run-button').classList.add('hidden');
      lastRunId = '';
      document.querySelector('#save-version-button').disabled = true;
      document.querySelector('#run-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function populateDraft(definition) {
      currentDraft = definition;
      document.querySelector('#draft-name').value = definition.name || '';
      document.querySelector('#draft-description').value = definition.description || '';
      document.querySelector('#draft-goal').value = definition.goal || '';
      document.querySelector('#draft-steps').value = (definition.steps || []).join('\\\\n');
      document.querySelector('#draft-rules').value = (definition.rules || []).join('\\\\n');
      document.querySelector('#draft-format').value = definition.output_format || 'Markdown';
      const fields = (definition.input_fields || []).map(item => item.label).join('\\\\n');
      document.querySelector('#draft-inputs').value = fields;
      document.querySelector('#draft-panel').classList.remove('hidden');
    }

    function readDraftForm() {
      return { ...currentDraft,
        name: document.querySelector('#draft-name').value.trim(),
        description: document.querySelector('#draft-description').value.trim(),
        goal: document.querySelector('#draft-goal').value.trim(),
        steps: lines(document.querySelector('#draft-steps').value),
        rules: lines(document.querySelector('#draft-rules').value),
        output_format: document.querySelector('#draft-format').value.trim() || 'Markdown',
        input_fields: lines(document.querySelector('#draft-inputs').value).map((label, index) => ({
          key: (currentDraft.input_fields[index] || {}).key || `input-${index + 1}`,
          label,
          description: (currentDraft.input_fields[index] || {}).description || '',
          required: (currentDraft.input_fields[index] || {}).required !== false
        }))
      };
    }

    document.querySelectorAll('[data-template-description]').forEach(button => button.addEventListener('click', () => {
      document.querySelector('#assistant-description').value = button.dataset.templateDescription;
      showMessage(document.querySelector('#draft-message'), `已填入“${button.querySelector('h3').textContent}”示例，你可以继续修改。`);
      document.querySelector('#assistant-description').focus();
    }));

    document.querySelector('#settings-button').addEventListener('click', () => { message.textContent = ''; dialog.showModal(); });
    document.querySelector('#cancel-button').addEventListener('click', () => dialog.close());
    document.querySelector('#settings-form').addEventListener('submit', async (event) => {
      event.preventDefault();
      const response = await fetch('/api/settings', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
        api_key: document.querySelector('#api-key').value,
        default_model: document.querySelector('#default-model').value
      })});
      const data = await response.json();
      if (!response.ok) { message.textContent = data.error || '保存失败'; return; }
      message.textContent = '设置已保存';
      document.querySelector('#api-key').value = '';
      const settings = await loadSettings();
      await loadModels(settings.default_model);
      setTimeout(() => dialog.close(), 500);
    });

    async function readFilePayload(file) {
      return await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve({ filename: file.name, content_base64: String(reader.result).split(',')[1] || '' });
        reader.onerror = () => reject(new Error(`无法读取文件：${file.name}`));
        reader.readAsDataURL(file);
      });
    }

    async function selectedAssistantFilePayloads() {
      return await Promise.all(Array.from(document.querySelector('#assistant-files').files || []).map(readFilePayload));
    }

    async function draftAssistant(options = {}) {
      const message = document.querySelector('#draft-message');
      const confirmed = document.querySelector('#draft-privacy').checked;
      if (!confirmed) { showMessage(message, '请先确认描述和材料可以发送给 DeepSeek。', true); return; }
      showMessage(message, '正在生成工作助手，请稍候…');
      const response = await fetch('/api/assistant-drafts', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
        description: document.querySelector('#assistant-description').value,
        attachments: await selectedAssistantFilePayloads(),
        model: document.querySelector('#draft-model').value,
        privacy_confirmed: confirmed,
        redact: Boolean(options.redact),
        privacy_override: Boolean(options.privacyOverride)
      })});
      const data = await response.json();
      if (!response.ok) {
        if (data.code === 'privacy_review') {
          document.querySelector('#draft-privacy-review').classList.remove('hidden');
          document.querySelector('#draft-findings').innerHTML = `<p>${escapeHtml(data.error)}</p><ul>${(data.findings || []).map(item => `<li>${escapeHtml(item.label)}（${escapeHtml(item.masked_sample)}）：${escapeHtml(item.suggestion)}</li>`).join('')}</ul>`;
        }
        showMessage(message, data.error || '生成工作助手失败', true);
        return;
      }
      document.querySelector('#draft-privacy-review').classList.add('hidden');
      showMessage(message, '草稿已生成，请检查并修改后保存。');
      populateDraft(data);
    }

    document.querySelector('#draft-button').addEventListener('click', () => draftAssistant());
    document.querySelector('#draft-redact-button').addEventListener('click', () => draftAssistant({redact: true}));
    document.querySelector('#draft-manual-button').addEventListener('click', () => {
      document.querySelector('#draft-privacy-review').classList.add('hidden');
      showMessage(document.querySelector('#draft-message'), '请修改描述或重新上传材料，再生成工作助手。');
    });
    document.querySelector('#cancel-draft-button').addEventListener('click', () => {
      currentDraft = null;
      document.querySelector('#draft-panel').classList.add('hidden');
    });
    document.querySelector('#save-assistant-button').addEventListener('click', async () => {
      const message = document.querySelector('#draft-message');
      const response = await fetch('/api/assistants', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ definition: readDraftForm() }) });
      const data = await response.json();
      if (!response.ok) { showMessage(message, data.error || '保存失败', true); return; }
      currentDraft = null;
      document.querySelector('#draft-panel').classList.add('hidden');
      showMessage(message, '工作助手已保存，可以在“我的工作助手”中运行。');
      await loadAssistants();
      await selectAssistant(data.id);
    });
    document.querySelector('#import-assistant-button').addEventListener('click', async () => {
      const input = document.querySelector('#assistant-import');
      const message = document.querySelector('#assistant-message');
      const file = input.files[0];
      if (!file) { showMessage(message, '请先选择 .sfassistant 工作助手文件。', true); return; }
      showMessage(message, '正在导入工作助手…');
      try {
        const payload = await readFilePayload(file);
        const response = await fetch('/api/assistants/import', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ package_base64: payload.content_base64 }) });
        const data = await response.json();
        if (!response.ok) { showMessage(message, data.error || '导入失败', true); return; }
        input.value = '';
        showMessage(message, '已导入为新的个人副本。');
        await loadAssistants();
        await selectAssistant(data.id);
      } catch (error) {
        showMessage(message, error.message || '导入失败', true);
      }
    });

    async function selectedFilePayloads() {
      return await Promise.all(Array.from(document.querySelector('#run-files').files || []).map(readFilePayload));
    }

    async function runSelectedAssistant(options = {}) {
      const message = document.querySelector('#run-message');
      const confirmed = document.querySelector('#run-privacy').checked;
      if (!confirmed) { showMessage(message, '请先确认本次内容可以发送给 DeepSeek，并检查敏感信息。', true); return; }
      showMessage(message, '正在本地检查材料并运行工作助手，请稍候…');
      const temporary = document.querySelector('#temporary-request').value;
      const formats = Array.from(document.querySelectorAll('input[name="output-format"]:checked')).map(input => input.value);
      if (!formats.length) { showMessage(message, '请先选择最终结果需要的文件格式。', true); return; }
      const response = await fetch(`/api/assistants/${currentAssistant.id}/trial`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
        input_text: document.querySelector('#run-input').value,
        attachments: await selectedFilePayloads(),
        temporary_request: temporary,
        model: document.querySelector('#run-model').value,
        output_formats: formats,
        privacy_confirmed: confirmed,
        redact: Boolean(options.redact),
        privacy_override: Boolean(options.privacyOverride)
      })});
      const data = await response.json();
      if (!response.ok) {
        if (data.code === 'privacy_review') {
          document.querySelector('#privacy-review').classList.remove('hidden');
          document.querySelector('#privacy-findings').innerHTML = `<p>${escapeHtml(data.error)}</p><ul>${(data.findings || []).map(item => `<li>${escapeHtml(item.label)}（${escapeHtml(item.masked_sample)}）：${escapeHtml(item.suggestion)}</li>`).join('')}</ul>`;
        }
        showMessage(message, data.error || '运行失败', true);
        return;
      }
      document.querySelector('#privacy-review').classList.add('hidden');
      lastTemporaryRequest = temporary.trim();
      lastRunId = data.id;
      document.querySelector('#run-output').textContent = data.output || '模型没有返回内容。';
      document.querySelector('#save-version-button').disabled = !lastTemporaryRequest;
      const artifactList = document.querySelector('#artifact-list');
      artifactList.innerHTML = `<strong>可下载文件</strong><ul>${(data.artifacts || []).map(item => `<li><a href="/api/runs/${data.id}/artifacts/${encodeURIComponent(item.name)}" download>${escapeHtml(item.name)}</a></li>`).join('')}</ul>`;
      artifactList.classList.remove('hidden');
      document.querySelector('#delete-run-button').classList.remove('hidden');
      showMessage(message, `本次任务已完成，运行记录已保存在本机（${data.id}）。`);
    }

    document.querySelector('#run-button').addEventListener('click', () => runSelectedAssistant());
    document.querySelector('#redact-and-run-button').addEventListener('click', () => runSelectedAssistant({redact: true}));
    document.querySelector('#manual-review-button').addEventListener('click', () => {
      document.querySelector('#privacy-review').classList.add('hidden');
      showMessage(document.querySelector('#run-message'), '请手动修改内容或文件后重新上传，再次点击运行。');
    });
    document.querySelector('#delete-run-button').addEventListener('click', async () => {
      const message = document.querySelector('#run-message');
      if (!lastRunId || !window.confirm('确定删除本次运行记录和生成文件吗？此操作不可恢复。')) return;
      const response = await fetch(`/api/runs/${lastRunId}`, { method: 'DELETE' });
      const data = await response.json();
      if (!response.ok) { showMessage(message, data.error || '删除失败', true); return; }
      document.querySelector('#run-output').textContent = '本次运行记录已删除。';
      document.querySelector('#artifact-list').textContent = '';
      document.querySelector('#artifact-list').classList.add('hidden');
      document.querySelector('#delete-run-button').classList.add('hidden');
      lastRunId = '';
      showMessage(message, '本次运行记录和生成文件已从本机删除。');
    });
    document.querySelector('#save-version-button').addEventListener('click', async () => {
      if (!currentAssistant || !lastTemporaryRequest) return;
      const definition = { ...currentAssistant.current, rules: [...(currentAssistant.current.rules || []), lastTemporaryRequest] };
      const response = await fetch(`/api/assistants/${currentAssistant.id}/versions`, { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ definition, change_note: lastTemporaryRequest }) });
      const data = await response.json();
      if (!response.ok) { showMessage(document.querySelector('#run-message'), data.error || '保存新版本失败', true); return; }
      currentAssistant = data;
      lastTemporaryRequest = '';
      document.querySelector('#save-version-button').disabled = true;
      document.querySelector('#run-version').textContent = `当前版本：v${data.current_version} · ${data.current.description || data.current.goal}`;
      showMessage(document.querySelector('#run-message'), `已保存为新版本 v${data.current_version}。`);
      await loadAssistants();
    });

    loadSettings().then(settings => loadModels(settings.default_model)).catch(() => { status.textContent = '无法读取本地设置'; });
    loadAssistants().catch(() => { document.querySelector('#assistant-list').textContent = '无法读取本地工作助手'; });
  </script>
</body>
</html>
"""


def create_server(project_dir: Path | None = None, host: str = "127.0.0.1", port: int = 8765):
    """创建本地网页服务器，供 CLI 和测试复用。"""

    state = WebAppState(project_dir)

    class Handler(BaseHTTPRequestHandler):
        def _send(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json_response(self, status: HTTPStatus, payload: Any) -> None:
            self._send(status, _json_bytes(payload), "application/json; charset=utf-8")

        def _download(self, body: bytes, filename: str, content_type: str) -> None:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header(
                "Content-Disposition",
                f"attachment; filename=soloflow-download; filename*=UTF-8''{quote(filename)}",
            )
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _read_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 50 * 1024 * 1024:
                raise ValueError("请求内容过大（上限 50 MB）")
            raw = self.rfile.read(length)
            data = json.loads(raw.decode("utf-8")) if raw else {}
            if not isinstance(data, dict):
                raise ValueError("请求内容必须是 JSON 对象")
            return data

        def do_GET(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/":
                self._send(HTTPStatus.OK, HOME_PAGE.encode("utf-8"), "text/html; charset=utf-8")
            elif path == "/api/health":
                self._json_response(HTTPStatus.OK, {"status": "ok", "service": "soloflow-web"})
            elif path == "/api/settings":
                self._json_response(HTTPStatus.OK, state.settings())
            elif path == "/api/models":
                self._json_response(HTTPStatus.OK, {"models": state.models()})
            elif path == "/api/assistants":
                self._json_response(
                    HTTPStatus.OK,
                    [item.model_dump(mode="json") for item in state.assistants.list()],
                )
            elif path.startswith("/api/assistants/"):
                parts = path.strip("/").split("/")
                if len(parts) == 4 and parts[0:2] == ["api", "assistants"] and parts[3] == "export":
                    try:
                        package = state.export_assistant(parts[2])
                    except FileNotFoundError as exc:
                        self._json_response(HTTPStatus.NOT_FOUND, {"error": str(exc)})
                        return
                    self._download(
                        _json_bytes(package),
                        "soloflow-assistant.sfassistant",
                        "application/json; charset=utf-8",
                    )
                    return
                if len(parts) != 3 or parts[0:2] != ["api", "assistants"]:
                    self._json_response(HTTPStatus.NOT_FOUND, {"error": "接口不存在"})
                    return
                assistant_id = parts[2]
                try:
                    self._json_response(
                        HTTPStatus.OK, state.assistants.get(assistant_id).model_dump(mode="json")
                    )
                except FileNotFoundError as exc:
                    self._json_response(HTTPStatus.NOT_FOUND, {"error": str(exc)})
            elif path.startswith("/api/runs/"):
                parts = path.strip("/").split("/")
                if len(parts) != 5 or parts[0:2] != ["api", "runs"] or parts[3] != "artifacts":
                    self._json_response(HTTPStatus.NOT_FOUND, {"error": "结果文件不存在"})
                    return
                run_dir = state.assistants.runs_dir / parts[2]
                artifact_path = (run_dir / "artifacts" / unquote(parts[4])).resolve()
                if not artifact_path.is_file() or not artifact_path.is_relative_to(
                    run_dir.resolve()
                ):
                    self._json_response(HTTPStatus.NOT_FOUND, {"error": "结果文件不存在"})
                    return
                body = artifact_path.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(body)))
                self.send_header(
                    "Content-Disposition",
                    "attachment; filename=soloflow-result; "
                    f"filename*=UTF-8''{quote(artifact_path.name)}",
                )
                self.end_headers()
                self.wfile.write(body)
            else:
                self._json_response(HTTPStatus.NOT_FOUND, {"error": "页面不存在"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            try:
                payload = self._read_body()
                if path == "/api/settings":
                    result = state.save_settings(payload)
                elif path == "/api/assistant-drafts":
                    result = state.draft_assistant(payload)
                elif path == "/api/assistants/import":
                    result = state.import_assistant(payload)
                elif path == "/api/assistants":
                    result = state.create_assistant(payload)
                elif path.startswith("/api/assistants/"):
                    parts = path.strip("/").split("/")
                    if len(parts) != 4 or parts[0:2] != ["api", "assistants"]:
                        self._json_response(HTTPStatus.NOT_FOUND, {"error": "接口不存在"})
                        return
                    assistant_id, action = parts[2], parts[3]
                    if action == "trial":
                        result = state.trial_assistant(assistant_id, payload)
                    elif action == "versions":
                        result = state.create_version(assistant_id, payload)
                    else:
                        self._json_response(HTTPStatus.NOT_FOUND, {"error": "接口不存在"})
                        return
                else:
                    self._json_response(HTTPStatus.NOT_FOUND, {"error": "接口不存在"})
                    return
            except FileNotFoundError as exc:
                self._json_response(HTTPStatus.NOT_FOUND, {"error": str(exc)})
                return
            except PrivacyReviewError as exc:
                self._json_response(
                    HTTPStatus.CONFLICT,
                    {
                        "code": "privacy_review",
                        "error": str(exc),
                        "findings": [item.model_dump(mode="json") for item in exc.findings],
                    },
                )
                return
            except PrivacyConfirmationError as exc:
                self._json_response(HTTPStatus.CONFLICT, {"error": str(exc)})
                return
            except (OSError, ValueError, json.JSONDecodeError) as exc:
                self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                if status_code == 401:
                    error_code = "deepseek_auth_error"
                    message = "DeepSeek API Key 无效或已过期，请在设置中重新配置。"
                elif status_code == 429:
                    error_code = "deepseek_rate_limit"
                    message = "DeepSeek 请求过于频繁或余额不足，请稍后重试并检查账户状态。"
                else:
                    error_code = "deepseek_http_error"
                    message = f"DeepSeek 请求失败（HTTP {status_code}），请稍后重试。"
                self._json_response(
                    HTTPStatus.BAD_GATEWAY,
                    {"code": error_code, "error": message},
                )
                return
            except httpx.HTTPError as exc:
                self._json_response(
                    HTTPStatus.BAD_GATEWAY,
                    {"code": "deepseek_network_error", "error": f"DeepSeek 网络请求失败：{exc}"},
                )
                return
            self._json_response(HTTPStatus.OK, result)

        def do_DELETE(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            try:
                parts = path.strip("/").split("/")
                if len(parts) == 3 and parts[0:2] == ["api", "runs"]:
                    result = state.delete_run(parts[2])
                elif (
                    len(parts) == 4
                    and parts[0:2] == ["api", "assistants"]
                    and parts[3] == "history"
                ):
                    result = state.delete_assistant_history(parts[2])
                else:
                    self._json_response(HTTPStatus.NOT_FOUND, {"error": "接口不存在"})
                    return
            except (FileNotFoundError, OSError, ValueError) as exc:
                self._json_response(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
                return
            self._json_response(HTTPStatus.OK, result)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


def serve(
    project_dir: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
) -> None:
    """启动本地网页并持续运行，直到用户按 Ctrl+C。"""

    server = create_server(project_dir=project_dir, host=host, port=port)
    address = f"http://{host}:{server.server_port}"
    print(f"SoloFlow 本地网页已启动：{address}")
    print("关闭网页服务请按 Ctrl+C。")
    if open_browser:
        threading.Timer(0.2, webbrowser.open, args=(address,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSoloFlow 本地网页已关闭。")
    finally:
        server.server_close()
