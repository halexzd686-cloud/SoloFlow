"""Agent loading and execution on top of the shared Runner."""

from rich.console import Console

from soloflow.core.runner import render_prompt, run_prompt_versions
from soloflow.core.skill_loader import find_skill, load_skill
from soloflow.models.agent import AgentConfigOverride, AgentDefinition
from soloflow.models.skill import SkillConfig, SkillFile

console = Console()


def resolve_llm_config(
    config: AgentConfigOverride | None,
    fallback: SkillConfig,
) -> tuple[str, str, float, int]:
    """Apply explicit Agent values over the primary Skill configuration."""
    cfg = config or AgentConfigOverride()
    return (
        cfg.model or fallback.model,
        cfg.provider or fallback.provider,
        cfg.temperature if cfg.temperature is not None else fallback.temperature,
        cfg.max_tokens if cfg.max_tokens is not None else fallback.max_tokens,
    )


def load_skills_for_agent(agent: AgentDefinition) -> list[tuple[str, SkillFile]]:
    """Load every available Skill bound to an Agent."""
    loaded = []
    for skill_name in agent.skills:
        try:
            loaded.append((skill_name, load_skill(find_skill(skill_name))))
        except FileNotFoundError:
            console.print(
                f"[yellow]Warning: Skill '{skill_name}' not found for agent '{agent.name}'[/yellow]"
            )
    return loaded


def render_agent_prompt(
    agent: AgentDefinition,
    loaded_skills: list[tuple[str, SkillFile]],
    task: str,
) -> str:
    """Render an Agent role and its Skills through the shared prompt format."""
    sections = [agent.system_prompt]
    sections.extend(f"## Skill: {name}\n{skill.full_prompt}" for name, skill in loaded_skills)
    return render_prompt(sections, task)


def run_agent(
    agent: AgentDefinition,
    user_input: str,
    count: int = 1,
    dry_run: bool = False,
    stream: bool = False,
) -> list[str]:
    """Execute an Agent using the same prompt and model path as a Skill."""
    loaded_skills = load_skills_for_agent(agent)
    if not loaded_skills:
        console.print(f"[red]Agent '{agent.name}' has no valid skills loaded.[/red]")
        return []

    prompt = render_agent_prompt(agent, loaded_skills, user_input)
    if dry_run:
        preview = prompt[:3000] + ("..." if len(prompt) > 3000 else "")
        console.print("\n[bold yellow]--- Dry Run ---[/bold yellow]")
        console.print(preview)
        return ["[DRY RUN]"]

    primary = loaded_skills[0][1]
    model, provider, temperature, max_tokens = resolve_llm_config(agent.config, primary.config)
    return run_prompt_versions(
        prompt,
        label=agent.name,
        model=model,
        provider=provider,
        temperature=temperature,
        max_tokens=max_tokens,
        count=count,
        stream=stream,
    )
