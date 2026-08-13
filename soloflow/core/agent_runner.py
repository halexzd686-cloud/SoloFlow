"""Agent discovery, persistence, and execution on top of the shared Runner."""

from pathlib import Path

import yaml
from rich.console import Console

from soloflow.core.assets import asset_name, find_asset, list_asset_paths
from soloflow.core.runner import render_prompt, run_prompt_versions
from soloflow.core.skill_loader import find_skill, load_skill
from soloflow.models.agent import AgentConfigOverride, AgentDefinition
from soloflow.models.skill import SkillConfig, SkillFile

console = Console()


def load_agent(name: str | Path) -> AgentDefinition:
    """Load an Agent through the shared asset discovery order."""
    path = find_asset("agent", name)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return AgentDefinition(**data)


def save_agent(
    agent: AgentDefinition,
    output: str | Path = "agents",
    *,
    use_playbooks: bool = False,
) -> Path:
    """Save an Agent definition in the requested project directory."""
    output_dir = Path(output)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{agent.name}.agent.yml"
    data = agent.model_dump(exclude_defaults=True, exclude_none=True)
    if use_playbooks and "skills" in data:
        data["playbooks"] = data.pop("skills")
    path.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False),
        encoding="utf-8",
    )
    return path


def list_agents() -> list[dict]:
    """List Agents once through the shared asset discovery order."""
    results: list[dict] = []
    for source, path in list_asset_paths("agent"):
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            results.append(
                {
                    "name": data.get("name", asset_name("agent", path)),
                    "path": str(path),
                    "description": data.get("description", ""),
                    "skills": data.get("skills", data.get("playbooks", [])),
                    "source": source,
                }
            )
        except Exception:
            continue
    return results


def resolve_llm_config(
    config: AgentConfigOverride | None,
    fallback: SkillConfig,
) -> tuple[str, str, str, float, int]:
    """Apply explicit Agent values over the primary Skill configuration."""
    cfg = config or AgentConfigOverride()
    return (
        cfg.base_url or fallback.base_url,
        cfg.api_key_env or fallback.api_key_env,
        cfg.model or fallback.model,
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
    base_url, api_key_env, model, temperature, max_tokens = resolve_llm_config(
        agent.config, primary.config
    )
    return run_prompt_versions(
        prompt,
        label=agent.name,
        base_url=base_url,
        api_key_env=api_key_env,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        count=count,
        stream=stream,
    )
