"""Single prompt rendering and model execution path for all assets."""

import time
from collections.abc import Callable

from rich.console import Console
from rich.panel import Panel

from soloflow.live_view import live_skill
from soloflow.llm.client import LLMResult, chat
from soloflow.models.skill import SkillFile

console = Console()


def render_prompt(instruction_sections: list[str], task: str) -> str:
    """Combine non-empty instruction sections and one user task."""
    sections = [section.strip() for section in instruction_sections if section.strip()]
    sections.append(f"# Task\n\n{task.strip()}")
    return "\n\n---\n\n".join(sections)


def render_skill_prompt(skill: SkillFile, task: str) -> str:
    """Render one Skill and task through the shared prompt format."""
    return render_prompt([skill.full_prompt], task)


def execute_prompt(
    prompt: str,
    *,
    base_url: str,
    api_key_env: str,
    model: str,
    temperature: float,
    max_tokens: int,
    dry_run: bool = False,
    stream: bool = False,
    timeout: float = 120.0,
    max_retries: int = 2,
    on_chunk: Callable[[str], None] | None = None,
) -> LLMResult:
    """Execute one rendered prompt through the only model call boundary."""
    return chat(
        [{"role": "user", "content": prompt}],
        base_url=base_url,
        api_key_env=api_key_env,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        dry_run=dry_run,
        stream=stream,
        on_chunk=on_chunk,
        timeout=timeout,
        max_retries=max_retries,
    )


def run_prompt_versions(
    prompt: str,
    *,
    label: str,
    base_url: str,
    api_key_env: str,
    model: str,
    temperature: float,
    max_tokens: int,
    count: int = 1,
    dry_run: bool = False,
    stream: bool = False,
) -> list[str]:
    """Execute and display one or more versions of the same rendered prompt."""
    results: list[str] = []
    effective_count = 1 if stream else count

    for index in range(effective_count):
        if effective_count > 1:
            console.print(f"\n[bold cyan]── 版本 {index + 1}/{effective_count} ──[/bold cyan]")
        started = time.time()
        try:
            if stream:
                console.print("[bold]>>> 输出:[/bold]\n")
                response = execute_prompt(
                    prompt,
                    base_url=base_url,
                    api_key_env=api_key_env,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                    on_chunk=lambda chunk: console.print(chunk, end="", highlight=False),
                )
                console.print()
            else:
                with live_skill(label) as view:
                    response = execute_prompt(
                        prompt,
                        base_url=base_url,
                        api_key_env=api_key_env,
                        model=model,
                        temperature=temperature + (index * 0.1 if count > 1 else 0),
                        max_tokens=max_tokens,
                        dry_run=dry_run,
                    )
                    view.complete(response.content)
        except (RuntimeError, ImportError) as error:
            console.print(f"[red]执行失败: {error}[/red]")
            return []

        result = response.content
        results.append(result)
        elapsed = time.time() - started
        if not stream:
            console.print(
                Panel(
                    result[:2000] + ("..." if len(result) > 2000 else ""),
                    title=f"输出 {index + 1}/{effective_count} · {elapsed:.1f}s",
                    border_style="green",
                )
            )
        else:
            console.print(f"\n[dim]耗时: {elapsed:.1f}s | {len(result)} 字符[/dim]")

    return results


def run_skill(
    skill: SkillFile,
    user_input: str,
    count: int = 1,
    model: str | None = None,
    dry_run: bool = False,
    stream: bool = False,
) -> list[str]:
    """Render and execute one Skill through the shared Runner.

    ``model`` is a one-run override and never mutates the Playbook file.
    """
    return run_prompt_versions(
        render_skill_prompt(skill, user_input),
        label=skill.meta.name,
        base_url=skill.config.base_url,
        api_key_env=skill.config.api_key_env,
        model=model.strip() if model and model.strip() else skill.config.model,
        temperature=skill.config.temperature,
        max_tokens=skill.config.max_tokens,
        count=count,
        dry_run=dry_run,
        stream=stream,
    )
