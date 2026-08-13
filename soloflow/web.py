"""SoloFlow 本地网页入口。

P0 只提供本地网页骨架和基础设置。真正的工作助手运行流程由后续阶段接入
现有 Runner 与文件处理层；工作助手应用层负责统一编排模型调用。
"""

# 内嵌 HTML/CSS/JavaScript 为了可读性保留长行。
# ruff: noqa: E501

from __future__ import annotations

import json
import os
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse

from soloflow.assistant_store import (
    AssistantDefinition,
    AssistantStore,
    PrivacyConfirmationError,
    PrivacyReviewError,
    draft_definition,
)
from soloflow.config import load_project_env
from soloflow.file_processing import FileAttachment

DEFAULT_MODEL = "deepseek-chat"
SETTINGS_RELATIVE_PATH = Path(".soloflow") / "config" / "settings.json"


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
        return {
            "api_key_configured": bool(os.getenv("DEEPSEEK_API_KEY")),
            "default_model": values.get("default_model", DEFAULT_MODEL),
        }

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

    def draft_assistant(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not payload.get("privacy_confirmed"):
            raise PrivacyConfirmationError("生成助手草稿前必须确认描述会发送给 DeepSeek")
        model = str(payload.get("model") or self.settings()["default_model"]).strip()
        definition = draft_definition(str(payload.get("description", "")), model)
        return definition.model_dump(mode="json")

    def create_assistant(self, payload: dict[str, Any]) -> dict[str, Any]:
        definition = AssistantDefinition.model_validate(payload.get("definition", {}))
        return self.assistants.create(definition).model_dump(mode="json")

    def trial_assistant(self, assistant_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        model = str(payload.get("model") or self.settings()["default_model"]).strip()
        attachments = [
            FileAttachment.from_payload(item)
            for item in payload.get("attachments", [])
            if isinstance(item, dict)
        ]
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


HOME_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SoloFlow 工作助手</title>
  <style>
    :root { color-scheme: light; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }
    body { margin: 0; background: #f5f7fb; color: #172033; }
    header { background: #14213d; color: #fff; padding: 28px max(24px, calc((100% - 1040px) / 2)); }
    main { max-width: 1040px; margin: 0 auto; padding: 28px 24px 56px; }
    .eyebrow { color: #8ea7d8; font-size: 13px; letter-spacing: .08em; text-transform: uppercase; }
    h1, h2 { margin: 8px 0 12px; }
    h1 { font-size: clamp(28px, 5vw, 44px); }
    h2 { font-size: 22px; }
    p { line-height: 1.7; }
    .intro { max-width: 720px; color: #d8e2f5; margin-bottom: 0; }
    .bar { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin: 24px 0; }
    .card-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }
    .card, .panel { background: #fff; border: 1px solid #e2e7f0; border-radius: 14px; padding: 20px; box-shadow: 0 5px 18px rgba(24, 41, 76, .05); }
    .card h3 { margin: 0 0 8px; }
    .card p { color: #5b667a; font-size: 14px; min-height: 48px; }
    button { border: 0; border-radius: 9px; padding: 10px 15px; background: #3468d4; color: #fff; cursor: pointer; font-size: 14px; }
    button.secondary { background: #e9eef9; color: #23447d; }
    button:disabled { opacity: .55; cursor: not-allowed; }
    .status { display: inline-flex; align-items: center; gap: 8px; border-radius: 999px; background: #eef3ff; color: #3156a3; padding: 8px 12px; font-size: 13px; }
    .status.ok { background: #eaf8ef; color: #237545; }
    .notice { margin-top: 22px; padding: 14px 16px; border-left: 4px solid #e0a62d; background: #fff8e7; color: #6b5317; }
    dialog { width: min(520px, calc(100% - 48px)); border: 0; border-radius: 14px; padding: 0; box-shadow: 0 18px 70px rgba(0,0,0,.25); }
    dialog::backdrop { background: rgba(11, 20, 39, .48); }
    form { padding: 24px; }
    label { display: block; margin: 14px 0 6px; font-weight: 600; font-size: 14px; }
    input { box-sizing: border-box; width: 100%; border: 1px solid #cbd4e3; border-radius: 8px; padding: 11px; font-size: 15px; }
    .actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px; }
    .muted { color: #6b7689; font-size: 14px; }
    textarea { box-sizing: border-box; width: 100%; min-height: 112px; resize: vertical; border: 1px solid #cbd4e3; border-radius: 8px; padding: 11px; font: inherit; line-height: 1.5; }
    .field-row { margin: 14px 0; }
    .field-row label { margin-top: 0; }
    .output { white-space: pre-wrap; background: #f7f9fc; border-radius: 8px; padding: 16px; min-height: 80px; overflow-wrap: anywhere; }
    .assistant-item { display: flex; justify-content: space-between; gap: 14px; align-items: center; border-top: 1px solid #e5eaf2; padding: 12px 0; }
    .assistant-item:first-child { border-top: 0; }
    .hidden { display: none; }
  </style>
</head>
<body>
  <header>
    <div class="eyebrow">SoloFlow 本地工作助手</div>
    <h1>把重复工作，变成自己的工作助手</h1>
    <p class="intro">先从一个你每周都会做的工作开始。后续你可以用自然语言告诉 SoloFlow 规则，并把确认后的方法保存下来反复使用。</p>
  </header>
  <main>
    <div class="bar">
      <div>
        <h2>从示例开始</h2>
        <div class="muted">先用自然语言定义一项重复工作，再试运行并保存为自己的工作助手。</div>
      </div>
      <button class="secondary" id="settings-button">设置 DeepSeek</button>
    </div>
    <div class="card-grid">
      <article class="card"><h3>周报整理</h3><p>把本周完成、未完成、问题和下周计划整理成固定格式。</p><button disabled>即将支持</button></article>
      <article class="card"><h3>表格汇总</h3><p>根据多份数据表整理出适合汇报的结果。</p><button disabled>即将支持</button></article>
      <article class="card"><h3>会议内容整理</h3><p>提取会议结论、待办事项、负责人和截止时间。</p><button disabled>即将支持</button></article>
      <article class="card"><h3>销售跟进整理</h3><p>把零散的客户跟进记录整理成统一的汇报内容。</p><button disabled>即将支持</button></article>
    </div>
    <div class="panel" style="margin-top: 24px">
      <h2>开始使用前</h2>
      <p id="key-status" class="status">正在检查 DeepSeek 配置…</p>
      <p class="notice">运行工作助手时，必要内容会发送到你配置的 DeepSeek 模型。正式运行前，SoloFlow 会先提示你检查材料是否敏感。</p>
    </div>
    <div class="panel" style="margin-top: 24px">
      <h2>创建工作助手</h2>
      <p class="muted">用平时说话的方式描述一项你反复做的工作。SoloFlow 会先整理成草稿，你确认后再保存。</p>
      <div class="field-row"><label for="assistant-description">我想重复处理的工作</label><textarea id="assistant-description" placeholder="例如：我每周要提交周报，包含本周完成、未完成、遇到的问题和下周计划，语气要简洁、适合给领导看。"></textarea></div>
      <div class="field-row"><label for="draft-model">本次使用模型</label><input id="draft-model" value="deepseek-chat" placeholder="deepseek-chat"></div>
      <label><input id="draft-privacy" type="checkbox"> 我确认这段工作描述可以发送给 DeepSeek，且可能产生 API 费用。</label>
      <div class="actions"><button id="draft-button">生成助手草稿</button></div>
      <p id="draft-message" class="muted"></p>
      <div id="draft-panel" class="hidden">
        <h3>确认助手内容</h3>
        <div class="field-row"><label for="draft-name">助手名称</label><input id="draft-name"></div>
        <div class="field-row"><label for="draft-description">用途说明</label><textarea id="draft-description"></textarea></div>
        <div class="field-row"><label for="draft-goal">工作目标</label><textarea id="draft-goal"></textarea></div>
        <div class="field-row"><label for="draft-steps">工作步骤（每行一步）</label><textarea id="draft-steps"></textarea></div>
        <div class="field-row"><label for="draft-rules">注意事项（每行一条）</label><textarea id="draft-rules"></textarea></div>
        <div class="field-row"><label for="draft-format">最终输出格式</label><input id="draft-format"></div>
        <div class="field-row"><label for="draft-inputs">需要用户填写的内容（每行一项）</label><textarea id="draft-inputs"></textarea></div>
        <div class="actions"><button class="secondary" id="cancel-draft-button">放弃草稿</button><button id="save-assistant-button">保存为工作助手</button></div>
      </div>
    </div>
    <div class="panel" style="margin-top: 24px">
      <h2>我的工作助手</h2>
      <div id="assistant-list" class="muted">还没有保存的工作助手。</div>
      <div id="run-panel" class="hidden">
        <h3 id="run-title"></h3>
        <p id="run-version" class="muted"></p>
        <div class="field-row"><label for="run-input">本次要处理的内容</label><textarea id="run-input" placeholder="粘贴本周工作记录，或输入这次要整理的内容。"></textarea></div>
        <div class="field-row"><label for="run-files">上传材料（可选，单个文件不超过 20 MB）</label><input id="run-files" type="file" multiple accept=".docx,.xlsx,.csv,.pdf,.txt,.md,.png,.jpg,.jpeg"><div id="file-hints" class="muted">支持 Word、Excel、CSV、PDF、文本和普通图片；扫描件与 OCR 暂不支持。</div></div>
        <div class="field-row"><label for="temporary-request">本次临时要求（可选，不会自动修改助手）</label><textarea id="temporary-request" placeholder="例如：这次把问题部分写得更适合给领导看。"></textarea></div>
        <div class="field-row"><label for="run-model">本次使用模型</label><input id="run-model" value="deepseek-chat"></div>
        <div class="field-row"><label for="output-formats">结果文件格式（可多选）</label><select id="output-formats" multiple size="4"><option value="md">Markdown</option><option value="docx">Word（.docx）</option><option value="xlsx">Excel（.xlsx）</option><option value="pdf">PDF（.pdf）</option></select><div class="muted">请至少选择一种最终格式；选择多个格式时会同时提供单独下载和 ZIP 打包下载。</div></div>
        <label><input id="run-privacy" type="checkbox"> 我确认本次内容可以发送给 DeepSeek，并已检查是否包含敏感信息。</label>
        <div class="actions"><button id="run-button">试运行</button><button class="secondary" id="save-version-button" disabled>将本次要求保存为新版本</button></div>
        <p id="run-message" class="muted"></p>
        <div id="privacy-review" class="notice hidden"><strong>发送前检查</strong><div id="privacy-findings"></div><div class="actions"><button id="redact-and-run-button">按建议脱敏并继续</button><button class="secondary" id="manual-review-button">我手动修改后重新上传</button></div></div>
        <h3>结果预览</h3>
        <div id="run-output" class="output">运行后将在这里显示结果。</div>
        <div id="artifact-list" class="muted"></div>
      </div>
    </div>
  </main>
  <dialog id="settings-dialog">
    <form method="dialog" id="settings-form">
      <h2>DeepSeek 设置</h2>
      <p class="muted">API Key 只保存在当前项目本机的 .env 文件中，不会进入工作助手分享文件。</p>
      <label for="api-key">DeepSeek API Key（已有配置可留空）</label>
      <input id="api-key" name="api_key" type="password" autocomplete="off" placeholder="sk-…">
      <label for="default-model">默认模型</label>
      <input id="default-model" name="default_model" value="deepseek-chat" placeholder="deepseek-chat">
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

    function lines(value) {
      return value.split('\\\\n').map(item => item.trim()).filter(Boolean);
    }

    function showMessage(target, text, error = false) {
      target.textContent = text;
      target.style.color = error ? '#b33636' : '';
    }

    async function loadSettings() {
      const response = await fetch('/api/settings');
      const data = await response.json();
      status.textContent = data.api_key_configured ? `DeepSeek 已配置 · 默认模型：${data.default_model}` : '还没有配置 DeepSeek API Key';
      status.className = data.api_key_configured ? 'status ok' : 'status';
      document.querySelector('#default-model').value = data.default_model;
      document.querySelector('#draft-model').value = data.default_model;
      document.querySelector('#run-model').value = data.default_model;
    }

    async function loadAssistants() {
      const response = await fetch('/api/assistants');
      const assistants = await response.json();
      const container = document.querySelector('#assistant-list');
      if (!assistants.length) { container.textContent = '还没有保存的工作助手。'; return; }
      container.innerHTML = assistants.map(item => `<div class="assistant-item"><div><strong>${item.current.name}</strong><div class="muted">${item.current.description || item.current.goal} · v${item.current_version}</div></div><button class="secondary" data-assistant-id="${item.id}">使用</button></div>`).join('');
      container.querySelectorAll('[data-assistant-id]').forEach(button => button.addEventListener('click', () => selectAssistant(button.dataset.assistantId)));
    }

    async function selectAssistant(id) {
      const response = await fetch(`/api/assistants/${id}`);
      currentAssistant = await response.json();
      document.querySelector('#run-panel').classList.remove('hidden');
      document.querySelector('#run-title').textContent = currentAssistant.current.name;
      document.querySelector('#run-version').textContent = `当前版本：v${currentAssistant.current_version} · ${currentAssistant.current.description || currentAssistant.current.goal}`;
      document.querySelector('#run-model').value = currentAssistant.current.default_model;
      document.querySelector('#run-output').textContent = '运行后将在这里显示结果。';
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
      await loadSettings();
      setTimeout(() => dialog.close(), 500);
    });

    document.querySelector('#draft-button').addEventListener('click', async () => {
      const message = document.querySelector('#draft-message');
      const confirmed = document.querySelector('#draft-privacy').checked;
      if (!confirmed) { showMessage(message, '请先确认工作描述可以发送给 DeepSeek。', true); return; }
      showMessage(message, '正在整理助手草稿，请稍候…');
      const response = await fetch('/api/assistant-drafts', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({
        description: document.querySelector('#assistant-description').value,
        model: document.querySelector('#draft-model').value,
        privacy_confirmed: confirmed
      })});
      const data = await response.json();
      if (!response.ok) { showMessage(message, data.error || '生成草稿失败', true); return; }
      showMessage(message, '草稿已生成，请检查并修改后保存。');
      populateDraft(data);
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
    async function readFilePayload(file) {
      return await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve({ filename: file.name, content_base64: String(reader.result).split(',')[1] || '' });
        reader.onerror = () => reject(new Error(`无法读取文件：${file.name}`));
        reader.readAsDataURL(file);
      });
    }

    async function selectedFilePayloads() {
      return await Promise.all(Array.from(document.querySelector('#run-files').files || []).map(readFilePayload));
    }

    async function runSelectedAssistant(options = {}) {
      const message = document.querySelector('#run-message');
      const confirmed = document.querySelector('#run-privacy').checked;
      if (!confirmed) { showMessage(message, '请先确认本次内容可以发送给 DeepSeek，并检查敏感信息。', true); return; }
      showMessage(message, '正在本地检查材料并运行工作助手，请稍候…');
      const temporary = document.querySelector('#temporary-request').value;
      const formats = Array.from(document.querySelector('#output-formats').selectedOptions).map(option => option.value);
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
          document.querySelector('#privacy-findings').innerHTML = `<p>${data.error}</p><ul>${(data.findings || []).map(item => `<li>${item.label}（${item.masked_sample}）：${item.suggestion}</li>`).join('')}</ul>`;
        }
        showMessage(message, data.error || '运行失败', true);
        return;
      }
      document.querySelector('#privacy-review').classList.add('hidden');
      lastTemporaryRequest = temporary.trim();
      document.querySelector('#run-output').textContent = data.output || '模型没有返回内容。';
      document.querySelector('#save-version-button').disabled = !lastTemporaryRequest;
      const artifactList = document.querySelector('#artifact-list');
      artifactList.innerHTML = `<p>结果文件：</p><ul>${(data.artifacts || []).map(item => `<li><a href="/api/runs/${data.id}/artifacts/${encodeURIComponent(item.name)}" download>${item.name}</a></li>`).join('')}</ul>`;
      showMessage(message, `本次任务已完成，运行记录已保存在本机（${data.id}）。`);
    }

    document.querySelector('#run-button').addEventListener('click', () => runSelectedAssistant());
    document.querySelector('#redact-and-run-button').addEventListener('click', () => runSelectedAssistant({redact: true}));
    document.querySelector('#manual-review-button').addEventListener('click', () => {
      document.querySelector('#privacy-review').classList.add('hidden');
      showMessage(document.querySelector('#run-message'), '请手动修改内容或文件后重新上传，再次点击运行。');
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

    loadSettings().catch(() => { status.textContent = '无法读取本地设置'; });
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
            elif path == "/api/assistants":
                self._json_response(
                    HTTPStatus.OK,
                    [item.model_dump(mode="json") for item in state.assistants.list()],
                )
            elif path.startswith("/api/assistants/"):
                assistant_id = path.removeprefix("/api/assistants/").strip("/")
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
            except RuntimeError as exc:
                self._json_response(HTTPStatus.BAD_GATEWAY, {"error": f"DeepSeek 请求失败：{exc}"})
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
