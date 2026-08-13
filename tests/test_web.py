"""本地网页 P0 入口测试。"""

import json
import threading
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

import pytest

from soloflow.assistant_store import (
    AssistantDefinition,
    AssistantStore,
    InputField,
    PrivacyConfirmationError,
    PrivacyReviewError,
)
from soloflow.llm.client import LLMResult
from soloflow.web import create_server


def test_web_home_and_health(tmp_path):
    server = create_server(tmp_path, port=0)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        with urlopen(f"http://127.0.0.1:{server.server_port}/") as response:
            body = response.read().decode("utf-8")
            assert response.status == 200
            assert "把重复工作，变成自己的工作助手" in body

        with urlopen(f"http://127.0.0.1:{server.server_port}/api/health") as response:
            assert json.loads(response.read()) == {"status": "ok", "service": "soloflow-web"}
    finally:
        server.shutdown()
        server_thread.join(timeout=2)
        server.server_close()


def test_web_settings_save_key_and_model(tmp_path, monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    server = create_server(tmp_path, port=0)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        payload = json.dumps({"api_key": "test-key", "default_model": "deepseek-reasoner"}).encode()
        request = Request(
            f"http://127.0.0.1:{server.server_port}/api/settings",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request) as response:
            result = json.loads(response.read())
            assert response.status == 200
            assert result == {"api_key_configured": True, "default_model": "deepseek-reasoner"}

        assert (tmp_path / ".env").read_text(encoding="utf-8") == "DEEPSEEK_API_KEY=test-key\n"
        settings = json.loads(
            (tmp_path / ".soloflow/config/settings.json").read_text(encoding="utf-8")
        )
        assert settings == {"default_model": "deepseek-reasoner"}
    finally:
        server.shutdown()
        server_thread.join(timeout=2)
        server.server_close()


def test_assistant_store_creates_versions_and_runs_locally(tmp_path, monkeypatch):
    store = AssistantStore(tmp_path)
    definition = AssistantDefinition(
        name="周报整理",
        description="整理每周工作内容",
        goal="生成结构化周报",
        input_fields=[InputField(key="work", label="本周工作")],
        steps=["整理完成事项", "整理问题和计划"],
        output_format="Markdown",
        rules=["不编造信息"],
        default_model="deepseek-chat",
    )
    record = store.create(definition)
    assert record.current_version == "1.0.0"
    assert store.get(record.id).current.name == "周报整理"

    monkeypatch.setattr(
        "soloflow.assistant_store.execute_prompt",
        lambda *args, **kwargs: LLMResult(content="# 周报\n已完成：整理数据"),
    )
    with pytest.raises(PrivacyConfirmationError):
        store.run(record.id, "本周完成了数据整理", "deepseek-chat")

    run = store.run(
        record.id,
        "本周完成了数据整理",
        "deepseek-chat",
        temporary_request="语气简洁",
        privacy_confirmed=True,
    )
    assert run.status == "completed"
    assert run.output.startswith("# 周报")
    assert (tmp_path / ".soloflow/runs" / run.id / "result.md").exists()

    updated = store.create_version(
        record.id,
        definition.model_copy(update={"rules": ["不编造信息", "适合给领导阅读"]}),
        "增加领导阅读要求",
    )
    assert updated.current_version == "1.1.0"
    assert len(updated.versions) == 2


def test_web_draft_requires_privacy_confirmation(tmp_path):
    server = create_server(tmp_path, port=0)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        payload = json.dumps({"description": "整理周报", "privacy_confirmed": False}).encode()
        request = Request(
            f"http://127.0.0.1:{server.server_port}/api/assistant-drafts",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(Exception) as error:
            urlopen(request)
        assert "409" in str(error.value)
    finally:
        server.shutdown()
        server_thread.join(timeout=2)
        server.server_close()


def test_run_requires_privacy_review_and_creates_multiple_artifacts(tmp_path, monkeypatch):
    store = AssistantStore(tmp_path)
    definition = AssistantDefinition(
        name="隐私检查测试",
        goal="整理输入",
        output_format="Markdown",
    )
    record = store.create(definition)
    monkeypatch.setattr(
        "soloflow.assistant_store.execute_prompt",
        lambda *args, **kwargs: LLMResult(content="# 结果\n已完成"),
    )
    with pytest.raises(PrivacyReviewError):
        store.run(
            record.id,
            "客户电话 13800138000",
            "deepseek-chat",
            privacy_confirmed=True,
        )
    run = store.run(
        record.id,
        "客户电话 13800138000",
        "deepseek-chat",
        privacy_confirmed=True,
        redact=True,
        output_formats=["md", "txt"],
    )
    assert run.status == "completed"
    assert {item.name for item in run.artifacts} == {
        "隐私检查测试.md",
        "隐私检查测试.txt",
        "结果文件.zip",
    }
    redacted = list((tmp_path / ".soloflow/runs" / run.id / "redacted").glob("*.txt"))
    assert not redacted


def test_web_trial_returns_privacy_review_and_downloadable_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "soloflow.assistant_store.execute_prompt",
        lambda *args, **kwargs: LLMResult(content="# 周报\n已完成数据汇总"),
    )
    server = create_server(tmp_path, port=0)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"

    def post(path, value):
        request = Request(
            base_url + path,
            data=json.dumps(value).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        return urlopen(request)

    try:
        with post(
            "/api/assistants", {"definition": {"name": "周报", "goal": "整理周报"}}
        ) as response:
            assistant = json.loads(response.read())
        run_payload = {
            "input_text": "本周客户电话 13800138000",
            "attachments": [],
            "model": "deepseek-chat",
            "output_formats": ["md", "txt"],
            "privacy_confirmed": True,
        }
        try:
            post(f"/api/assistants/{assistant['id']}/trial", run_payload)
        except HTTPError as error:
            assert error.code == 409
            assert json.loads(error.read())["code"] == "privacy_review"
        else:
            raise AssertionError("敏感信息未触发隐私复核")

        run_payload["redact"] = True
        with post(f"/api/assistants/{assistant['id']}/trial", run_payload) as response:
            run = json.loads(response.read())
        artifact = next(item for item in run["artifacts"] if item["name"].endswith(".txt"))
        with urlopen(
            f"{base_url}/api/runs/{run['id']}/artifacts/{quote(artifact['name'])}"
        ) as response:
            assert response.status == 200
            assert response.read()
    finally:
        server.shutdown()
        server_thread.join(timeout=2)
        server.server_close()
