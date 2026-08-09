"""Skill 执行器 —— 负责渲染 prompt 并调用 LLM。"""

import time

from rich.console import Console
from rich.panel import Panel

from soloflow.llm.client import call_llm, call_llm_stream
from soloflow.models.skill import SkillFile

console = Console()


def run_skill(
    skill: SkillFile,
    user_input: str,
    count: int = 1,
    dry_run: bool = False,
    stream: bool = False,
) -> list[str]:
    """用指定 Skill 执行任务。

    Args:
        skill: Skill 对象。
        user_input: 用户输入的任务描述。
        count: 生成多少个版本（抽卡模式）。
        dry_run: 仅渲染不调用。
        stream: 是否使用流式输出（逐 token 打印）。流式模式下 count 固定为 1。

    Returns:
        LLM 响应列表。
    """
    # 组合完整 prompt
    system_prompt = skill.full_prompt
    full_prompt = f"{system_prompt}\n\n---\n\n# Task\n\n{user_input}"

    results = []

    effective_count = 1 if stream else count

    for i in range(effective_count):
        if effective_count > 1:
            console.print(f"\n[bold cyan]── 版本 {i + 1}/{effective_count} ──[/bold cyan]")

        start = time.time()

        if stream:
            # ── 流式模式 ──
            console.print(f"[dim]Skill: {skill.meta.name} v{skill.meta.version}[/dim]")
            console.print("[bold]>>> 输出:[/bold]\n")

            accumulated = []
            try:
                for chunk in call_llm_stream(
                    prompt=full_prompt,
                    model=skill.config.model,
                    provider=skill.config.provider,
                    temperature=skill.config.temperature,
                    max_tokens=skill.config.max_tokens,
                ):
                    accumulated.append(chunk)
                    console.print(chunk, end="", highlight=False)
            except RuntimeError as e:
                console.print(f"\n[red]执行失败: {e}[/red]")
                return []
            except ImportError as e:
                console.print(f"\n[red]依赖缺失: {e}[/red]")
                return []

            console.print()  # 最后的换行
            result = "".join(accumulated)
        else:
            # ── 非流式模式 ──
            try:
                result = call_llm(
                    prompt=full_prompt,
                    model=skill.config.model,
                    provider=skill.config.provider,
                    temperature=skill.config.temperature if count == 1 else 0.7 + (i * 0.1),
                    max_tokens=skill.config.max_tokens,
                    dry_run=dry_run,
                )
            except RuntimeError as e:
                console.print(f"[red]执行失败: {e}[/red]")
                return []
            except ImportError as e:
                console.print(f"[red]依赖缺失: {e}[/red]")
                return []

        elapsed = time.time() - start
        results.append(result)

        # 显示结果（非流式模式下用 Panel 包裹）
        if not stream:
            console.print(f"\n[dim]耗时: {elapsed:.1f}s[/dim]")
            console.print(
                Panel(
                    result[:2000] + ("..." if len(result) > 2000 else ""),
                    title=f"输出 {i + 1}/{effective_count}",
                    border_style="green",
                )
            )
        else:
            console.print(f"\n[dim]耗时: {elapsed:.1f}s | {len(result)} 字符[/dim]")

    return results
