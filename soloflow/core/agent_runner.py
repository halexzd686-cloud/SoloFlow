"""Agent 执行器 —— 加载 Skill + 注入角色设定 + 执行任务。"""

import time

from rich.console import Console
from rich.panel import Panel

from soloflow.core.skill_loader import find_skill, load_skill
from soloflow.llm.client import call_llm, call_llm_stream
from soloflow.models.agent import AgentConfigOverride, AgentDefinition
from soloflow.models.skill import SkillConfig, SkillFile

console = Console()


def resolve_llm_config(
    config: AgentConfigOverride | None,
    fallback: SkillConfig,
) -> tuple[str, str, float, int]:
    """解析 Agent 的最终 LLM 配置（BUG-AGENT-001 修复）。

    语义: Agent config 中 None 的字段继承 fallback（Skill config），
    非 None 字段为显式覆盖 —— 不再用"等于默认值"猜测用户意图。

    Args:
        config: Agent 配置覆盖（可为 None）。
        fallback: 回退配置（通常是首个 Skill 的 config）。

    Returns:
        (model, provider, temperature, max_tokens)
    """
    cfg = config or AgentConfigOverride()
    return (
        cfg.model or fallback.model,
        cfg.provider or fallback.provider,
        cfg.temperature if cfg.temperature is not None else fallback.temperature,
        cfg.max_tokens if cfg.max_tokens is not None else fallback.max_tokens,
    )


def load_skills_for_agent(agent: AgentDefinition) -> list[tuple[str, SkillFile]]:
    """为 Agent 加载其绑定的所有 Skill。"""
    loaded = []
    for skill_name in agent.skills:
        try:
            skill_path = find_skill(skill_name)
            skill = load_skill(skill_path)
            loaded.append((skill_name, skill))
        except FileNotFoundError:
            console.print(
                f"[yellow]Warning: Skill '{skill_name}' not found for agent '{agent.name}'[/yellow]"
            )
    return loaded


def run_agent(
    agent: AgentDefinition,
    user_input: str,
    count: int = 1,
    dry_run: bool = False,
    stream: bool = False,
) -> list[str]:
    """让 Agent 执行任务。

    流程：
    1. 加载 Agent 绑定的所有 Skill
    2. 组合：Agent 角色设定 + Skill prompt + 用户任务
    3. 调用 LLM 执行（支持流式输出）

    Args:
        agent: Agent 定义。
        user_input: 用户任务。
        count: 生成版本数（流式模式下固定为 1）。
        dry_run: 仅预览。
        stream: 流式输出模式。
    """
    loaded_skills = load_skills_for_agent(agent)
    if not loaded_skills:
        console.print(f"[red]Agent '{agent.name}' has no valid skills loaded.[/red]")
        return []

    console.print(f"\n[bold]Agent: {agent.name}[/bold]")
    console.print(f"[dim]Skills: {', '.join(name for name, _ in loaded_skills)}[/dim]")

    # 组合完整 prompt
    prompt_parts = [agent.system_prompt]
    for skill_name, skill in loaded_skills:
        prompt_parts.append(f"\n---\n## Skill: {skill_name}\n{skill.full_prompt}")
    prompt_parts.append(f"\n---\n# Task\n{user_input}")
    full_prompt = "\n".join(prompt_parts)

    if dry_run:
        preview = full_prompt[:3000] + ("..." if len(full_prompt) > 3000 else "")
        console.print("\n[bold yellow]--- Dry Run ---[/bold yellow]")
        console.print(preview)
        return ["[DRY RUN]"]

    # LLM 配置：Agent config 覆盖 Skill config（None=继承，BUG-AGENT-001 修复）
    primary = loaded_skills[0][1]
    model, provider, temp, max_tok = resolve_llm_config(agent.config, primary.config)

    results = []
    effective_count = 1 if stream else count

    for i in range(effective_count):
        if effective_count > 1:
            console.print(f"\n[bold cyan]--- Version {i + 1}/{effective_count} ---[/bold cyan]")

        t0 = time.time()

        if stream:
            # ── 流式模式 ──
            console.print("[bold]>>> 输出:[/bold]\n")

            accumulated = []
            try:
                for chunk in call_llm_stream(
                    prompt=full_prompt,
                    model=model,
                    provider=provider,
                    temperature=temp,
                    max_tokens=max_tok,
                ):
                    accumulated.append(chunk)
                    console.print(chunk, end="", highlight=False)
            except RuntimeError as e:
                console.print(f"\n[red]执行失败: {e}[/red]")
                return []
            except ImportError as e:
                console.print(f"\n[red]依赖缺失: {e}[/red]")
                return []

            console.print()
            result = "".join(accumulated)
        else:
            # ── 非流式模式 ──
            try:
                result = call_llm(
                    prompt=full_prompt,
                    model=model,
                    provider=provider,
                    temperature=temp + (i * 0.1 if count > 1 else 0),
                    max_tokens=max_tok,
                    dry_run=dry_run,
                )
            except RuntimeError as e:
                console.print(f"[red]Error: {e}[/red]")
                return []
            except ImportError as e:
                console.print(f"[red]Error: {e}[/red]")
                return []

        elapsed = time.time() - t0
        results.append(result)

        if not stream:
            console.print(f"\n[dim]Time: {elapsed:.1f}s[/dim]")
            console.print(
                Panel(
                    result[:2000] + ("..." if len(result) > 2000 else ""),
                    title=f"Output {i + 1}/{effective_count}",
                    border_style="green",
                )
            )
        else:
            console.print(f"\n[dim]Time: {elapsed:.1f}s | {len(result)} chars[/dim]")

    return results
