"""SoloFlow 本地网页入口。

P0 只提供本地网页骨架和基础设置。真正的工作助手运行流程由后续阶段接入
现有 Runner 与文件处理层；本模块不直接实现模型调用。
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
from urllib.parse import urlparse

from soloflow.config import load_project_env

DEFAULT_MODEL = "deepseek-chat"
SETTINGS_RELATIVE_PATH = Path(".soloflow") / "config" / "settings.json"


def _json_bytes(payload: dict[str, Any]) -> bytes:
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
    """本地网页所需的最小应用状态。"""

    def __init__(self, project_dir: Path | None = None):
        self.project_dir = (project_dir or Path.cwd()).resolve()
        self.settings_path = self.project_dir / SETTINGS_RELATIVE_PATH
        load_project_env(self.project_dir)

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
        <div class="muted">这是 P0 网页入口，工作助手创建和文件处理将在后续版本接入。</div>
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
    async function loadSettings() {
      const response = await fetch('/api/settings');
      const data = await response.json();
      status.textContent = data.api_key_configured ? `DeepSeek 已配置 · 默认模型：${data.default_model}` : '还没有配置 DeepSeek API Key';
      status.className = data.api_key_configured ? 'status ok' : 'status';
      document.querySelector('#default-model').value = data.default_model;
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
    loadSettings().catch(() => { status.textContent = '无法读取本地设置'; });
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

        def _json_response(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            self._send(status, _json_bytes(payload), "application/json; charset=utf-8")

        def _read_body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length > 1024 * 1024:
                raise ValueError("请求内容过大")
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
            else:
                self._json_response(HTTPStatus.NOT_FOUND, {"error": "页面不存在"})

        def do_POST(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path != "/api/settings":
                self._json_response(HTTPStatus.NOT_FOUND, {"error": "接口不存在"})
                return
            try:
                result = state.save_settings(self._read_body())
            except (OSError, ValueError, json.JSONDecodeError) as exc:
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
