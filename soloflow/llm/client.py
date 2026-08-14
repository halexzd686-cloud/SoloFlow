"""DeepSeek-only client for the OpenAI-compatible Chat Completions API."""

import json
import os
import time
from collections.abc import Callable
from typing import Any

import httpx
from pydantic import BaseModel, Field
from rich.console import Console

console = Console()

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_API_KEY_ENV = "DEEPSEEK_API_KEY"
DEFAULT_MODEL = "deepseek-v4-flash"


class LLMResult(BaseModel):
    """Text and usage returned by one model call."""

    content: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    request_id: str | None = Field(default=None, description="API request ID")


def _validate_target(base_url: str, api_key_env: str, model: str) -> str:
    """Keep the provider boundary while allowing every DeepSeek model name."""
    normalized_url = base_url.rstrip("/")
    if (
        normalized_url != DEFAULT_BASE_URL
        or api_key_env != DEFAULT_API_KEY_ENV
        or not model.strip().startswith("deepseek-")
    ):
        raise RuntimeError(
            "当前版本仅支持 DeepSeek 官方接口与 DEEPSEEK_API_KEY，model 必须是 DeepSeek 模型名；"
            f"收到 base_url={normalized_url!r}, api_key_env={api_key_env!r}, model={model!r}。"
        )
    return normalized_url


def _get_api_key(api_key_env: str) -> str | None:
    return os.environ.get(api_key_env)


def _usage(data: dict | None) -> tuple[int, int, int]:
    usage = data or {}
    return (
        int(usage.get("prompt_tokens", 0) or 0),
        int(usage.get("completion_tokens", 0) or 0),
        int(usage.get("total_tokens", 0) or 0),
    )


def _is_retryable_error(error: Exception) -> bool:
    if isinstance(error, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code == 429 or error.response.status_code >= 500
    return False


def _missing_key_error(api_key_env: str) -> RuntimeError:
    return RuntimeError(
        "未设置 DeepSeek API Key。请选择一种方式配置：\n"
        f"1. 在当前目录创建 .env，写入 {api_key_env}=你的密钥\n"
        f'2. 设置环境变量 {api_key_env}（PowerShell: $env:{api_key_env}="你的密钥"）\n'
        "获取密钥：https://platform.deepseek.com/；也可使用 --dry-run 零费用预览。"
    )


def _stream_result(
    client: httpx.Client,
    url: str,
    headers: dict[str, str],
    payload: dict,
    model: str,
    on_chunk: Callable[[str], None] | None,
) -> LLMResult:
    chunks: list[str] = []
    usage = (0, 0, 0)
    request_id: str | None = None
    actual_model = model
    with client.stream("POST", url, headers=headers, json=payload) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("data:"):
                continue
            raw = line.removeprefix("data:").strip()
            if not raw or raw == "[DONE]":
                continue
            data = json.loads(raw)
            request_id = data.get("id", request_id)
            actual_model = data.get("model", actual_model)
            if data.get("usage"):
                usage = _usage(data["usage"])
            choices = data.get("choices") or []
            chunk = choices[0].get("delta", {}).get("content") if choices else None
            if chunk:
                chunks.append(chunk)
                if on_chunk:
                    on_chunk(chunk)
    return LLMResult(
        content="".join(chunks),
        prompt_tokens=usage[0],
        completion_tokens=usage[1],
        total_tokens=usage[2],
        model=actual_model,
        request_id=request_id,
    )


def chat(
    messages: list[dict[str, Any]],
    *,
    base_url: str = DEFAULT_BASE_URL,
    api_key_env: str = DEFAULT_API_KEY_ENV,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    dry_run: bool = False,
    stream: bool = False,
    on_chunk: Callable[[str], None] | None = None,
    timeout: float = 120.0,
    max_retries: int = 2,
) -> LLMResult:
    """Call a validated DeepSeek model through one project-wide boundary."""
    base_url = _validate_target(base_url, api_key_env, model)
    model = model.strip()
    if dry_run:
        return LLMResult(content="[DRY RUN]", model=model)

    api_key = _get_api_key(api_key_env)
    if not api_key:
        raise _missing_key_error(api_key_env)

    url = f"{base_url}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    if stream:
        payload["stream_options"] = {"include_usage": True}

    for attempt in range(max_retries + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                if stream:
                    return _stream_result(client, url, headers, payload, model, on_chunk)
                response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                prompt_tokens, completion_tokens, total_tokens = _usage(data.get("usage"))
                return LLMResult(
                    content=data["choices"][0]["message"]["content"] or "",
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    model=data.get("model", model),
                    request_id=data.get("id"),
                )
        except Exception as error:
            if attempt >= max_retries or not _is_retryable_error(error):
                raise
            delay = 2**attempt
            console.print(f"[yellow]DeepSeek 调用失败，{delay}s 后重试[/yellow]")
            time.sleep(delay)

    raise RuntimeError("DeepSeek 调用未返回结果")
