"""LLM 统一调用层。

基于 LiteLLM 封装，支持 OpenAI / Anthropic / 国产模型统一调用。
支持普通调用和流式输出两种模式。

GAP-LLM-001 修复: call_llm_full() 返回结构化 LLMResult，
包含 token usage / model / request_id，不再只返回字符串。
"""

import os
import time
from collections.abc import Callable, Generator

from pydantic import BaseModel, Field
from rich.console import Console

console = Console()

SUPPORTED_PROVIDER = "deepseek"
SUPPORTED_MODEL = "deepseek-v4-flash"

# 可重试的异常类名关键词（GAP-LLM-003: 限流 / 超时 / 连接 / 服务端错误可重试）
_RETRYABLE_ERROR_KEYWORDS = (
    "ratelimit",
    "timeout",
    "connection",
    "server",
    "internal",
    "apierror",
    "badgateway",
    "serviceunavailable",
)


def _is_retryable_error(exc: Exception) -> bool:
    """判断异常是否值得重试（限流/超时/网络/5xx）。"""
    exc_name = type(exc).__name__.lower()
    return any(k in exc_name for k in _RETRYABLE_ERROR_KEYWORDS)


class LLMResult(BaseModel):
    """LLM 调用的结构化结果（GAP-LLM-001）。

    usage 数据供 Flow 引擎累计 total_tokens、TUI 展示成本等。
    """

    content: str = Field(default="", description="模型响应文本")
    prompt_tokens: int = Field(default=0, description="输入 token 数")
    completion_tokens: int = Field(default=0, description="输出 token 数")
    total_tokens: int = Field(default=0, description="总 token 数")
    model: str = Field(default="", description="实际使用的模型")
    provider: str = Field(default="", description="提供商")
    request_id: str | None = Field(default=None, description="请求 ID")


def _extract_usage(response) -> tuple[int, int, int]:
    """从 LiteLLM 响应中提取 (prompt_tokens, completion_tokens, total_tokens)。

    兼容对象属性与字典两种形态。
    """
    usage = getattr(response, "usage", None)
    if not usage:
        return 0, 0, 0
    if isinstance(usage, dict):
        return (
            int(usage.get("prompt_tokens", 0) or 0),
            int(usage.get("completion_tokens", 0) or 0),
            int(usage.get("total_tokens", 0) or 0),
        )
    return (
        int(getattr(usage, "prompt_tokens", 0) or 0),
        int(getattr(usage, "completion_tokens", 0) or 0),
        int(getattr(usage, "total_tokens", 0) or 0),
    )


def _get_api_key(provider: str) -> str | None:
    """获取当前唯一支持的 DeepSeek API Key。"""
    if provider.lower() != SUPPORTED_PROVIDER:
        return None
    return os.environ.get("DEEPSEEK_API_KEY")


def _validate_target(provider: str, model: str) -> None:
    """拒绝非 DeepSeek V4 Flash 目标，避免意外调用其他付费 API。"""
    if provider.lower() != SUPPORTED_PROVIDER or model.lower() != SUPPORTED_MODEL:
        raise RuntimeError(
            f"当前版本仅支持 {SUPPORTED_PROVIDER}/{SUPPORTED_MODEL}，收到 {provider}/{model}。"
        )


def call_llm_full(
    prompt: str,
    model: str = "deepseek-v4-flash",
    provider: str = "deepseek",
    temperature: float = 0.7,
    max_tokens: int = 4096,
    dry_run: bool = False,
    max_retries: int = 2,
    timeout: float = 120.0,
) -> LLMResult:
    """调用 LLM 并返回结构化结果（GAP-LLM-001）。

    GAP-LLM-003 增强:
    - 重试与指数退避（限流/超时/网络/5xx 类错误，默认 2 次重试）
    - 超时参数透传给 LiteLLM

    Args:
        prompt: 完整的系统提示词 + 用户任务。
        model: 模型名称。
        provider: LLM 提供商。
        temperature: 温度参数。
        max_tokens: 最大输出 token 数。
        dry_run: 仅显示 prompt，不实际调用。
        max_retries: 可重试错误的最大重试次数（0 表示不重试）。
        timeout: 单次调用超时秒数。

    Returns:
        LLMResult 含 content + token usage + model + request_id。
    """
    _validate_target(provider, model)

    if dry_run:
        console.print("[yellow]Dry run —— 不调用 LLM[/yellow]")
        return LLMResult(content="[DRY RUN]", provider=provider, model=model)

    api_key = _get_api_key(provider)
    if not api_key:
        raise RuntimeError(
            "未设置 DeepSeek API Key。请选择一种方式配置：\n"
            "1. 在当前目录创建 .env，写入 DEEPSEEK_API_KEY=你的密钥\n"
            "2. 设置环境变量 DEEPSEEK_API_KEY（PowerShell: "
            '$env:DEEPSEEK_API_KEY="你的密钥"）\n'
            "获取密钥：https://platform.deepseek.com/；也可使用 --dry-run 零费用预览。"
        )

    try:
        from litellm import completion
    except ImportError:
        raise ImportError("需要安装 litellm: pip install litellm")

    # 构建模型标识
    model_id = f"{provider}/{model}"

    console.print(f"\n[dim]调用 {model_id} ...[/dim]")

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = completion(
                model=model_id,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
                api_key=api_key,
                timeout=timeout,
            )

            content = response.choices[0].message.content
            prompt_tokens, completion_tokens, total_tokens = _extract_usage(response)

            # 显示 token 用量
            if total_tokens:
                console.print(
                    f"[dim]Token: {prompt_tokens} in / {completion_tokens} out "
                    f"(total {total_tokens})[/dim]"
                )

            return LLMResult(
                content=content,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                model=getattr(response, "model", model) or model,
                provider=provider,
                request_id=getattr(response, "id", None),
            )
        except Exception as e:
            last_error = e
            if attempt < max_retries and _is_retryable_error(e):
                delay = 2**attempt  # 指数退避: 1s, 2s, 4s...
                console.print(
                    f"[yellow]调用失败 ({type(e).__name__}: {e})，"
                    f"{delay}s 后重试 ({attempt + 1}/{max_retries})[/yellow]"
                )
                time.sleep(delay)
                continue
            raise

    assert last_error is not None
    raise last_error


def call_llm(
    prompt: str,
    model: str = "deepseek-v4-flash",
    provider: str = "deepseek",
    temperature: float = 0.7,
    max_tokens: int = 4096,
    dry_run: bool = False,
) -> str:
    """调用 LLM 执行任务（返回纯文本，向后兼容）。

    Args:
        prompt: 完整的系统提示词 + 用户任务。
        model: 模型名称。
        provider: LLM 提供商。
        temperature: 温度参数。
        max_tokens: 最大输出 token 数。
        dry_run: 仅显示 prompt，不实际调用。

    Returns:
        LLM 响应文本。
    """
    return call_llm_full(
        prompt=prompt,
        model=model,
        provider=provider,
        temperature=temperature,
        max_tokens=max_tokens,
        dry_run=dry_run,
    ).content


def call_llm_stream(
    prompt: str,
    model: str = "deepseek-v4-flash",
    provider: str = "deepseek",
    temperature: float = 0.7,
    max_tokens: int = 4096,
    on_usage: Callable[[LLMResult], None] | None = None,
    timeout: float = 120.0,
) -> Generator[str, None, None]:
    """流式调用 LLM，逐个 token 输出。

    GAP-LLM-001 修复: 结束时通过 on_usage 回调提供真实 usage 汇总
    （从流式响应的 usage 字段提取），不再把 chunk 数当 token 数。

    用法:
        for chunk in call_llm_stream(prompt, ..., on_usage=cb):
            print(chunk, end="", flush=True)

    Args:
        prompt: 完整的系统提示词 + 用户任务。
        model: 模型名称。
        provider: LLM 提供商。
        temperature: 温度参数。
        max_tokens: 最大输出 token 数。
        on_usage: 可选回调，流式结束时收到 LLMResult（含真实 usage）。

    Yields:
        每次 yield 一段增量文本。
    """
    _validate_target(provider, model)

    api_key = _get_api_key(provider)
    if not api_key:
        raise RuntimeError(
            "未设置 DeepSeek API Key。请选择一种方式配置：\n"
            "1. 在当前目录创建 .env，写入 DEEPSEEK_API_KEY=你的密钥\n"
            "2. 设置环境变量 DEEPSEEK_API_KEY（PowerShell: "
            '$env:DEEPSEEK_API_KEY="你的密钥"）\n'
            "获取密钥：https://platform.deepseek.com/。"
        )

    try:
        from litellm import completion
    except ImportError:
        raise ImportError("需要安装 litellm: pip install litellm")

    model_id = f"{provider}/{model}"

    console.print(f"\n[dim]流式调用 {model_id} ...[/dim]")

    response = completion(
        model=model_id,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
        max_tokens=max_tokens,
        api_key=api_key,
        stream=True,
        timeout=timeout,
    )

    usage_result = LLMResult(provider=provider, model=model)
    for chunk in response:
        # 流式响应最后一个 chunk 常携带 usage
        if hasattr(chunk, "usage") and chunk.usage:
            p, c, t = _extract_usage(chunk)
            usage_result = LLMResult(
                content="",
                prompt_tokens=p,
                completion_tokens=c,
                total_tokens=t,
                model=getattr(chunk, "model", model) or model,
                provider=provider,
                request_id=getattr(chunk, "id", None),
            )
        if hasattr(chunk, "choices") and chunk.choices:
            delta = chunk.choices[0].delta
            if hasattr(delta, "content") and delta.content:
                yield delta.content

    if usage_result.total_tokens:
        console.print(
            f"[dim]流式输出完成 "
            f"({usage_result.prompt_tokens} in / {usage_result.completion_tokens} out)[/dim]"
        )
    else:
        console.print("[dim]流式输出完成（未提供 usage）[/dim]")

    if on_usage:
        on_usage(usage_result)
