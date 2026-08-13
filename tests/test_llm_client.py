"""DeepSeek client tests use httpx.MockTransport and never access the network."""

import json
from unittest.mock import patch

import httpx
import pytest

from soloflow.llm.client import LLMResult, chat

_REAL_HTTPX_CLIENT = httpx.Client
_MESSAGES = [{"role": "user", "content": "test"}]


def _response(
    request: httpx.Request,
    *,
    content: str = "hello world",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
    usage: bool = True,
) -> httpx.Response:
    data = {
        "id": "req-123",
        "model": "deepseek-v4-flash",
        "choices": [{"message": {"content": content}}],
    }
    if usage:
        data["usage"] = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        }
    return httpx.Response(200, json=data, request=request)


def _client_patch(handler, constructor_calls: list[dict] | None = None):
    transport = httpx.MockTransport(handler)

    def create_client(**kwargs):
        if constructor_calls is not None:
            constructor_calls.append(kwargs)
        return _REAL_HTTPX_CLIENT(transport=transport, **kwargs)

    return patch("soloflow.llm.client.httpx.Client", side_effect=create_client)


def test_chat_returns_structured_result_and_sends_expected_request():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers["Authorization"]
        captured["payload"] = json.loads(request.content)
        return _response(request)

    with (
        patch("soloflow.llm.client._get_api_key", return_value="sk-test"),
        _client_patch(handler),
    ):
        result = chat(_MESSAGES)

    assert result == LLMResult(
        content="hello world",
        prompt_tokens=10,
        completion_tokens=5,
        total_tokens=15,
        model="deepseek-v4-flash",
        request_id="req-123",
    )
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["authorization"] == "Bearer sk-test"
    assert captured["payload"]["messages"] == _MESSAGES
    assert captured["payload"]["model"] == "deepseek-v4-flash"
    assert captured["payload"]["stream"] is False


def test_chat_handles_missing_usage():
    with (
        patch("soloflow.llm.client._get_api_key", return_value="sk-test"),
        _client_patch(lambda request: _response(request, usage=False)),
    ):
        result = chat(_MESSAGES)

    assert result.content == "hello world"
    assert result.total_tokens == 0


def test_chat_missing_api_key_has_actionable_message():
    with patch("soloflow.llm.client._get_api_key", return_value=None):
        with pytest.raises(RuntimeError) as exc_info:
            chat(_MESSAGES)

    message = str(exc_info.value)
    assert "DEEPSEEK_API_KEY=你的密钥" in message
    assert '$env:DEEPSEEK_API_KEY="你的密钥"' in message
    assert "https://platform.deepseek.com/" in message
    assert "--dry-run" in message


@pytest.mark.parametrize(
    "overrides",
    [
        {"base_url": "https://example.com"},
        {"api_key_env": "OTHER_API_KEY"},
        {"model": "unsupported-model"},
    ],
)
def test_chat_rejects_non_deepseek_target_before_reading_key(overrides):
    with patch("soloflow.llm.client._get_api_key") as get_key:
        with pytest.raises(RuntimeError, match="仅支持 DeepSeek 官方接口"):
            chat(_MESSAGES, **overrides)
        get_key.assert_not_called()


@pytest.mark.parametrize("model", ["deepseek-chat", "deepseek-reasoner", "deepseek-v3.2"])
def test_chat_accepts_supported_deepseek_model_names(model):
    captured_payload: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_payload.update(json.loads(request.content))
        return _response(request)

    with (
        patch("soloflow.llm.client._get_api_key", return_value="sk-test"),
        _client_patch(handler),
    ):
        chat(_MESSAGES, model=model)

    assert captured_payload["model"] == model


def test_chat_dry_run_reads_no_key_and_makes_no_request():
    with (
        patch("soloflow.llm.client._get_api_key") as get_key,
        patch("soloflow.llm.client.httpx.Client") as client,
    ):
        result = chat(_MESSAGES, dry_run=True)

    get_key.assert_not_called()
    client.assert_not_called()
    assert result == LLMResult(content="[DRY RUN]", model="deepseek-v4-flash")


def test_chat_retries_rate_limit_with_exponential_backoff():
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 3:
            return httpx.Response(429, request=request)
        return _response(request, content="ok")

    with (
        patch("soloflow.llm.client._get_api_key", return_value="sk-test"),
        _client_patch(handler),
        patch("soloflow.llm.client.time.sleep") as sleep,
    ):
        result = chat(_MESSAGES, max_retries=3)

    assert result.content == "ok"
    assert attempts["count"] == 3
    assert [call.args[0] for call in sleep.call_args_list] == [1, 2]


def test_chat_does_not_retry_auth_failure():
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(401, request=request)

    with (
        patch("soloflow.llm.client._get_api_key", return_value="sk-test"),
        _client_patch(handler),
        patch("soloflow.llm.client.time.sleep") as sleep,
    ):
        with pytest.raises(httpx.HTTPStatusError):
            chat(_MESSAGES, max_retries=2)

    assert attempts["count"] == 1
    sleep.assert_not_called()


def test_chat_passes_timeout_to_httpx_client():
    constructor_calls: list[dict] = []
    with (
        patch("soloflow.llm.client._get_api_key", return_value="sk-test"),
        _client_patch(lambda request: _response(request), constructor_calls),
    ):
        chat(_MESSAGES, timeout=45.0)

    assert constructor_calls == [{"timeout": 45.0}]


def test_chat_streams_chunks_and_collects_usage():
    events = [
        {
            "id": "req-stream",
            "model": "deepseek-v4-flash",
            "choices": [{"delta": {"content": "Hel"}}],
        },
        {"choices": [{"delta": {"content": "lo"}}]},
        {
            "choices": [],
            "usage": {"prompt_tokens": 30, "completion_tokens": 12, "total_tokens": 42},
        },
    ]
    body = "".join(f"data: {json.dumps(event)}\n\n" for event in events) + "data: [DONE]\n\n"
    captured_chunks: list[str] = []
    captured_payload: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_payload.update(json.loads(request.content))
        return httpx.Response(200, text=body, request=request)

    with (
        patch("soloflow.llm.client._get_api_key", return_value="sk-test"),
        _client_patch(handler),
    ):
        result = chat(_MESSAGES, stream=True, on_chunk=captured_chunks.append)

    assert captured_chunks == ["Hel", "lo"]
    assert result.content == "Hello"
    assert result.total_tokens == 42
    assert result.request_id == "req-stream"
    assert captured_payload["stream_options"] == {"include_usage": True}


def test_flow_engine_accumulates_tokens(monkeypatch, tmp_path):
    """Flow steps preserve usage returned by the shared Runner boundary."""
    from soloflow.core.flow_engine import run_flow
    from soloflow.models.flow import FlowDefinition, FlowStep

    monkeypatch.chdir(tmp_path)
    flow = FlowDefinition(
        name="token-accum",
        steps=[
            FlowStep(id="a", skill="content-writer"),
            FlowStep(id="b", skill="code-reviewer", depends_on=["a"]),
        ],
    )

    def fake_build_step_prompt(step, context):
        return f"PROMPT_{step.id}"

    def fake_execute_prompt(prompt, **kwargs):
        if "PROMPT_a" in prompt:
            return LLMResult(content="A", total_tokens=100)
        return LLMResult(content="B", total_tokens=250)

    with (
        patch("soloflow.core.flow_engine._build_step_prompt", fake_build_step_prompt),
        patch("soloflow.core.flow_engine.execute_prompt", fake_execute_prompt),
    ):
        result = run_flow(flow)

    assert result.status == "done"
    assert result.steps["a"].tokens == 100
    assert result.steps["b"].tokens == 250
    assert result.total_tokens == 350
