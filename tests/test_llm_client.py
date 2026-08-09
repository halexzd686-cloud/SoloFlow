"""测试 LLM 调用层（GAP-LLM-001/002 回归）。

所有测试通过 mock litellm 完成，不发起真实网络调用。
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from soloflow.llm.client import LLMResult, call_llm, call_llm_full, call_llm_stream


def _fake_completion_response(
    content: str = "hello world",
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
    model: str = "deepseek-v4-flash",
    request_id: str = "req-123",
) -> SimpleNamespace:
    """构造一个模拟的 LiteLLM completion 响应对象。"""
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
        ),
        model=model,
        id=request_id,
    )


# ── call_llm_full: 结构化结果 ──


def test_call_llm_full_returns_structured_result():
    """GAP-LLM-001: 返回 LLMResult 含 content + usage + model + request_id。"""
    with (
        patch("soloflow.llm.client._get_api_key", return_value="sk-test"),
        patch("litellm.completion", return_value=_fake_completion_response()),
    ):
        result = call_llm_full(prompt="test")

    assert isinstance(result, LLMResult)
    assert result.content == "hello world"
    assert result.prompt_tokens == 10
    assert result.completion_tokens == 5
    assert result.total_tokens == 15
    assert result.model == "deepseek-v4-flash"
    assert result.request_id == "req-123"
    assert result.provider == "deepseek"


def test_call_llm_full_usage_dict_form():
    """GAP-LLM-001: usage 为 dict 形态也能解析。"""
    resp = _fake_completion_response()
    resp.usage = {"prompt_tokens": 20, "completion_tokens": 7, "total_tokens": 27}

    with (
        patch("soloflow.llm.client._get_api_key", return_value="sk-test"),
        patch("litellm.completion", return_value=resp),
    ):
        result = call_llm_full(prompt="test")

    assert result.total_tokens == 27
    assert result.prompt_tokens == 20


def test_call_llm_full_no_usage():
    """GAP-LLM-001: 响应无 usage 时不崩溃，token 为 0。"""
    resp = _fake_completion_response()
    resp.usage = None

    with (
        patch("soloflow.llm.client._get_api_key", return_value="sk-test"),
        patch("litellm.completion", return_value=resp),
    ):
        result = call_llm_full(prompt="test")

    assert result.total_tokens == 0
    assert result.content == "hello world"


def test_call_llm_backward_compat():
    """GAP-LLM-001: call_llm 仍返回纯字符串（向后兼容）。"""
    with (
        patch("soloflow.llm.client._get_api_key", return_value="sk-test"),
        patch("litellm.completion", return_value=_fake_completion_response()),
    ):
        content = call_llm(prompt="test")

    assert content == "hello world"
    assert isinstance(content, str)


def test_call_llm_missing_api_key():
    """缺少 API Key 时给出 .env、环境变量和获取地址。"""
    with patch("soloflow.llm.client._get_api_key", return_value=None):
        with pytest.raises(RuntimeError) as exc_info:
            call_llm_full(prompt="test")

    message = str(exc_info.value)
    assert "DEEPSEEK_API_KEY=你的密钥" in message
    assert '$env:DEEPSEEK_API_KEY="你的密钥"' in message
    assert "https://platform.deepseek.com/" in message
    assert "--dry-run" in message


@pytest.mark.parametrize(
    ("provider", "model"),
    [("unsupported", "deepseek-v4-flash"), ("deepseek", "unsupported-model")],
)
def test_call_llm_rejects_unsupported_target(provider, model):
    """当前版本在读取密钥和发起网络请求前拒绝非指定目标。"""
    with patch("litellm.completion") as mock_completion:
        with pytest.raises(RuntimeError, match="仅支持 deepseek/deepseek-v4-flash"):
            call_llm_full(prompt="test", provider=provider, model=model)
        mock_completion.assert_not_called()


def test_call_llm_dry_run():
    """dry_run 不调用 LLM，返回占位结果。"""
    with patch("litellm.completion") as mock_completion:
        result = call_llm_full(prompt="test", dry_run=True)
        mock_completion.assert_not_called()

    assert result.content == "[DRY RUN]"
    assert result.total_tokens == 0
    assert result.provider == "deepseek"
    assert result.model == "deepseek-v4-flash"


# ── GAP-LLM-003: 重试 / 退避 / 超时 ──


class _RateLimitError(Exception):
    """模拟 litellm 限流异常。"""


class _AuthError(Exception):
    """模拟不可重试的认证错误。"""


def test_call_llm_full_retries_on_rate_limit():
    """GAP-LLM-003: 限流错误自动重试，最终成功。"""
    from soloflow.llm.client import _is_retryable_error

    assert _is_retryable_error(_RateLimitError("rate limit"))

    attempts = {"n": 0}

    def flaky_completion(**kwargs):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise _RateLimitError("rate limit exceeded")
        return _fake_completion_response(content="ok")

    with (
        patch("soloflow.llm.client._get_api_key", return_value="sk-test"),
        patch("litellm.completion", side_effect=flaky_completion),
        patch("soloflow.llm.client.time.sleep") as mock_sleep,
    ):
        result = call_llm_full(prompt="test", max_retries=3)

    assert result.content == "ok"
    assert attempts["n"] == 3
    # 指数退避: 1s + 2s
    assert [c.args[0] for c in mock_sleep.call_args_list] == [1, 2]


def test_call_llm_full_retries_exhausted():
    """GAP-LLM-003: 重试耗尽后抛出最后一次异常。"""
    attempts = {"n": 0}

    def always_fail(**kwargs):
        attempts["n"] += 1
        raise _RateLimitError("rate limit forever")

    with (
        patch("soloflow.llm.client._get_api_key", return_value="sk-test"),
        patch("litellm.completion", side_effect=always_fail),
        patch("soloflow.llm.client.time.sleep"),
    ):
        with pytest.raises(_RateLimitError):
            call_llm_full(prompt="test", max_retries=2)

    assert attempts["n"] == 3  # 1 次初始 + 2 次重试


def test_call_llm_full_no_retry_on_auth_error():
    """GAP-LLM-003: 不可重试错误（认证失败）立即抛出，不重试。"""
    from soloflow.llm.client import _is_retryable_error

    assert not _is_retryable_error(_AuthError("invalid key"))

    attempts = {"n": 0}

    def always_auth_fail(**kwargs):
        attempts["n"] += 1
        raise _AuthError("invalid api key")

    with (
        patch("soloflow.llm.client._get_api_key", return_value="sk-test"),
        patch("litellm.completion", side_effect=always_auth_fail),
        patch("soloflow.llm.client.time.sleep") as mock_sleep,
    ):
        with pytest.raises(_AuthError):
            call_llm_full(prompt="test", max_retries=2)

    assert attempts["n"] == 1  # 不重试
    mock_sleep.assert_not_called()


def test_call_llm_full_passes_timeout():
    """GAP-LLM-003: timeout 参数透传给 LiteLLM。"""
    with (
        patch("soloflow.llm.client._get_api_key", return_value="sk-test"),
        patch("litellm.completion", return_value=_fake_completion_response()) as mock_completion,
    ):
        call_llm_full(prompt="test", timeout=45.0)

    assert mock_completion.call_args.kwargs["timeout"] == 45.0


# ── call_llm_stream: 流式 + usage 回调 ──


def _fake_stream_response(chunks_text, usage=None):
    """构造模拟流式 chunk 序列。"""
    chunks = []
    for text in chunks_text:
        chunks.append(
            SimpleNamespace(
                choices=[SimpleNamespace(delta=SimpleNamespace(content=text))],
                usage=None,
            )
        )
    if usage:
        # 最后一个 chunk 携带 usage
        chunks.append(
            SimpleNamespace(
                choices=[],
                usage=SimpleNamespace(
                    prompt_tokens=usage[0],
                    completion_tokens=usage[1],
                    total_tokens=usage[0] + usage[1],
                ),
            )
        )
    return iter(chunks)


def test_call_llm_stream_yields_chunks():
    """流式输出逐个 chunk 产出。"""
    with (
        patch("soloflow.llm.client._get_api_key", return_value="sk-test"),
        patch("litellm.completion", return_value=_fake_stream_response(["Hel", "lo ", "world"])),
    ):
        parts = list(call_llm_stream(prompt="test"))

    assert parts == ["Hel", "lo ", "world"]


def test_call_llm_stream_on_usage_callback():
    """GAP-LLM-001: 流式结束通过 on_usage 回调提供真实 usage（非 chunk 数）。"""
    captured = []

    with (
        patch("soloflow.llm.client._get_api_key", return_value="sk-test"),
        patch(
            "litellm.completion", return_value=_fake_stream_response(["Hel", "lo"], usage=(30, 12))
        ),
    ):
        parts = list(
            call_llm_stream(
                prompt="test",
                on_usage=lambda r: captured.append(r),
            )
        )

    assert parts == ["Hel", "lo"]
    assert len(captured) == 1
    usage = captured[0]
    assert isinstance(usage, LLMResult)
    # 真实 usage 30/12，而不是 chunk 数 2
    assert usage.prompt_tokens == 30
    assert usage.completion_tokens == 12
    assert usage.total_tokens == 42


def test_call_llm_stream_no_usage():
    """流式响应无 usage 时回调收到全 0 结果，不崩溃。"""
    captured = []

    with (
        patch("soloflow.llm.client._get_api_key", return_value="sk-test"),
        patch("litellm.completion", return_value=_fake_stream_response(["x"])),
    ):
        list(call_llm_stream(prompt="test", on_usage=lambda r: captured.append(r)))

    assert len(captured) == 1
    assert captured[0].total_tokens == 0


# ── Flow 引擎 token 累计 ──


def test_flow_engine_accumulates_tokens(monkeypatch, tmp_path):
    """GAP-LLM-001: Flow 步骤的 tokens 累计到 FlowResult.total_tokens。"""
    from unittest.mock import patch as mpatch

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

    def fake_call_llm_full(prompt, **kwargs):
        # 每个步骤返回不同 token 数
        if "PROMPT_a" in prompt:
            return LLMResult(content="A", total_tokens=100)
        return LLMResult(content="B", total_tokens=250)

    with (
        mpatch("soloflow.core.flow_engine._build_step_prompt", fake_build_step_prompt),
        mpatch("soloflow.core.flow_engine.execute_prompt", fake_call_llm_full),
    ):
        result = run_flow(flow)

    assert result.status == "done"
    assert result.steps["a"].tokens == 100
    assert result.steps["b"].tokens == 250
    assert result.total_tokens == 350
