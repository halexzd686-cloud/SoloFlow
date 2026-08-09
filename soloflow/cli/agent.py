"""Agent 子命令 —— sf agent *"""

import json
from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from soloflow.core.agent_runner import run_agent
from soloflow.core.assets import bundled_asset_dir
from soloflow.core.skill_loader import find_skill, load_skill
from soloflow.models.agent import AgentDefinition, AgentSoul

app = typer.Typer(help="Agent 智能体管理", no_args_is_help=True)
console = Console()

AGENT_CONFIG_DIR = Path(".soloflow/agents")


def _agent_search_dirs() -> list[Path]:
    """统一的 Agent 定义搜索目录（P2-001 修复，优先级从高到低）。

    - agents/         项目内置/示例 Agent
    - .               项目根（老用法）
    - .soloflow/agents 用户 Agent（sf agent create 的默认保存位置）
    - wheel 内置 Agent
    """
    return [Path("agents"), Path("."), AGENT_CONFIG_DIR, bundled_asset_dir("agents")]


def _load_agent(name: str) -> AgentDefinition:
    """按名称加载 Agent 定义。"""
    for d in _agent_search_dirs():
        for suffix in (".agent.yml", ".agent.yaml"):
            p = d / f"{name}{suffix}"
            if p.exists():
                data = yaml.safe_load(p.read_text(encoding="utf-8"))
                return AgentDefinition(**data)

    raise FileNotFoundError(f"Agent not found: {name}")


def _save_agent(agent: AgentDefinition) -> Path:
    """保存 Agent 定义到文件。"""
    AGENT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    path = AGENT_CONFIG_DIR / f"{agent.name}.agent.yml"
    # exclude_none: 避免 config 的 None 字段（=继承语义）写入 YAML
    data = agent.model_dump(exclude_defaults=True, exclude_none=True)
    path.write_text(yaml.dump(data, allow_unicode=True, default_flow_style=False), encoding="utf-8")
    return path


def _list_agents() -> list[dict]:
    """列出所有 Agent 定义（P2-001: 含 agents/ 目录，按名称去重保留最高优先级）。"""
    results: list[dict] = []
    seen: set[str] = set()
    for d in _agent_search_dirs():
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.agent.y*ml")):
            try:
                data = yaml.safe_load(f.read_text(encoding="utf-8"))
                name = data.get("name", f.stem.replace(".agent", ""))
                if name in seen:
                    continue  # 已由更高优先级目录提供
                seen.add(name)
                results.append(
                    {
                        "name": name,
                        "path": str(f),
                        "description": data.get("description", ""),
                        "skills": data.get("skills", []),
                    }
                )
            except Exception:
                continue
    return results


@app.command()
def create(
    name: str = typer.Argument(..., help="Agent 名称 (kebab-case)"),
    skills: str = typer.Option("", "--skills", "-s", help="绑定的 Skill 名称（逗号分隔）"),
    personality: str = typer.Option("", "--personality", "-p", help="性格描述"),
    description: str = typer.Option("", "--desc", "-d", help="Agent 职责描述"),
    dry_run: bool = typer.Option(False, "--dry-run", help="仅预览不写入"),
):
    """创建新 Agent。"""
    skill_list = [s.strip() for s in skills.split(",") if s.strip()]

    # 交互式输入
    if not description:
        description = typer.prompt("Agent 职责描述", default="通用助理")
    if not personality:
        personality = typer.prompt("性格描述", default="专业、高效、可靠")
    if not skill_list:
        console.print("[dim]可用 Skill:[/dim]")
        from soloflow.core.skill_loader import list_skills as ls

        for s in ls("skills"):
            console.print(f"  - {s['name']}: {s['description'][:60]}")
        skill_input = typer.prompt("绑定 Skill（逗号分隔）", default="content-writer")
        skill_list = [s.strip() for s in skill_input.split(",") if s.strip()]

    values_input = typer.prompt("核心价值观（逗号分隔）", default="诚实,效率,质量")
    values = [v.strip() for v in values_input.split(",") if v.strip()]

    rules_input = typer.prompt("Agent 规则（逗号分隔）", default="")
    rules = [r.strip() for r in rules_input.split(",") if r.strip()]

    agent = AgentDefinition(
        name=name,
        description=description,
        skills=skill_list,
        soul=AgentSoul(personality=personality, values=values),
        rules=rules,
    )

    if dry_run:
        console.print("\n[bold yellow]--- Preview ---[/bold yellow]")
        console.print(yaml.dump(agent.model_dump(exclude_defaults=True), allow_unicode=True))
        return

    path = _save_agent(agent)
    console.print(f"\n[green][OK] Agent created: {path}[/green]")
    console.print(f"[dim]Next: sf agent run {name} <task>[/dim]")


@app.command("list")
def list_cmd():
    """列出所有 Agent。"""
    agents = _list_agents()
    if not agents:
        console.print("[dim]No agents found. Use sf agent create to create one.[/dim]")
        return

    table = Table(title="Agents", header_style="bold cyan")
    table.add_column("Name", style="cyan")
    table.add_column("Description")
    table.add_column("Skills")
    table.add_column("Source")

    for a in agents:
        table.add_row(
            a["name"],
            a["description"][:60] + "..." if len(a["description"]) > 60 else a["description"],
            ", ".join(a["skills"]),
            "bundled" if str(bundled_asset_dir("agents")) in a["path"] else "project/user",
        )

    console.print(table)


@app.command()
def show(
    name: str = typer.Argument(..., help="Agent 名称"),
    json_output: bool = typer.Option(False, "--json", help="JSON 格式输出"),
):
    """查看 Agent 详情。"""
    try:
        agent = _load_agent(name)
    except FileNotFoundError:
        console.print(f"[red]Agent not found: {name}[/red]")
        raise typer.Exit(1)

    if json_output:
        console.print_json(json.dumps(agent.model_dump(), ensure_ascii=False, indent=2))
        return

    console.print(Panel.fit(f"[bold cyan]{agent.name}[/bold cyan]", subtitle=agent.description))

    console.print(f"\n[bold]Soul:[/bold] {agent.soul.personality}")
    if agent.soul.values:
        console.print(f"[bold]Values:[/bold] {', '.join(agent.soul.values)}")
    console.print(f"[bold]Skills:[/bold] {', '.join(agent.skills) if agent.skills else 'none'}")
    if agent.rules:
        console.print("[bold]Rules:[/bold]")
        for r in agent.rules:
            console.print(f"  - {r}")

    # 显示加载的 Skill 详情
    if agent.skills:
        console.print("\n[bold]Loaded Skills:[/bold]")
        for skill_name in agent.skills:
            try:
                sp = find_skill(skill_name)
                s = load_skill(sp)
                console.print(
                    f"  [cyan]{skill_name}[/cyan] v{s.meta.version}: {s.meta.description[:80]}"
                )
            except FileNotFoundError:
                console.print(f"  [red]{skill_name}[/red] — not found")


@app.command()
def run(
    agent_name: str = typer.Argument(..., help="Agent 名称"),
    task: str = typer.Argument(None, help="任务描述"),
    count: int = typer.Option(1, "--count", "-n", help="生成几个版本"),
    dry_run: bool = typer.Option(False, "--dry-run", help="仅预览 prompt"),
    stream: bool = typer.Option(False, "--stream", "-s", help="流式输出（逐 token 实时打印）"),
):
    """让 Agent 执行任务。

    --stream 模式实时逐 token 输出。流式模式下 --count 固定为 1。

    Examples:
        sf agent run my-agent "review this code"
        sf agent run my-agent "写一篇文章" --stream
    """
    try:
        agent = _load_agent(agent_name)
    except FileNotFoundError:
        console.print(f"[red]Agent not found: {agent_name}[/red]")
        raise typer.Exit(1)

    if not task:
        task = typer.prompt("任务描述")

    run_agent(agent, task, count=count, dry_run=dry_run, stream=stream)
