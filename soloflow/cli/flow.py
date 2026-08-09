"""Flow 子命令 —— sf flow *"""

from pathlib import Path

import typer
import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from soloflow.core.flow_engine import (
    _topological_sort,
    load_flow,
    run_flow,
    validate_flow,
)
from soloflow.models.flow import FlowDefinition, FlowStep

app = typer.Typer(help="Flow 工作流编排", no_args_is_help=True)
console = Console()

FLOWS_DIR = Path("flows")


@app.command()
def init(
    name: str = typer.Argument(..., help="Flow 名称 (kebab-case)"),
    output: str = typer.Option("./flows", "--output", "-o", help="输出目录"),
    dry_run: bool = typer.Option(False, "--dry-run", help="仅预览"),
):
    """创建一个新的 Flow 文件。"""
    console.print()
    console.print(
        Panel.fit(
            "[bold cyan]SoloFlow - Flow Creation[/bold cyan]",
            border_style="cyan",
        )
    )

    description = typer.prompt("Flow 描述", default=f"{name} workflow")
    console.print(f"\nFlow: [bold]{name}[/bold] — {description}")

    # 收集步骤
    console.print("\n[bold cyan]--- Steps ---[/bold cyan]")
    console.print("Add steps to your flow. Press Enter on empty name to finish.\n")

    steps = []
    step_num = 1
    while True:
        console.print(f"[bold]Step {step_num}:[/bold]")
        sid = typer.prompt("  ID", default=f"step-{step_num}")
        if not sid.strip():
            break

        skill = typer.prompt("  Skill name", default="content-writer")
        desc = typer.prompt("  Description", default="")
        deps = typer.prompt("  Depends on (comma-separated IDs)", default="")

        step = FlowStep(
            id=sid,
            skill=skill,
            description=desc,
            depends_on=[d.strip() for d in deps.split(",") if d.strip()],
        )
        steps.append(step)
        console.print(f"  [green][OK] Added: {sid}[/green]\n")
        step_num += 1

    if not steps:
        console.print("[red]No steps defined. Aborted.[/red]")
        raise typer.Exit(1)

    flow = FlowDefinition(
        name=name,
        description=description,
        steps=steps,
    )

    # 校验
    issues = validate_flow(flow)
    if issues:
        console.print("\n[yellow]Validation warnings:[/yellow]")
        for i in issues:
            console.print(f"  - {i}")
        if any("circular" in i.lower() for i in issues):
            console.print("[red]Cannot proceed with circular dependency.[/red]")
            raise typer.Exit(1)

    if dry_run:
        console.print("\n[bold yellow]--- Preview ---[/bold yellow]")
        console.print(yaml.dump(flow.model_dump(), allow_unicode=True, default_flow_style=False))
        return

    # 保存
    out_path = Path(output) / f"{name}.flow.yml"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        yaml.dump(
            flow.model_dump(exclude_defaults=True),
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    console.print(f"\n[green][OK] Flow created: {out_path}[/green]")
    console.print(f"[dim]Next: sf flow run {name}[/dim]")


@app.command()
def validate(
    path: str = typer.Argument(..., help="Flow 文件路径"),
):
    """校验 Flow 定义。"""
    try:
        flow = load_flow(path)
    except FileNotFoundError:
        console.print(f"[red]Flow not found: {path}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Parse error: {e}[/red]")
        raise typer.Exit(1)

    issues = validate_flow(flow)

    console.print(f"\n[bold]Flow: {flow.name} v{flow.version}[/bold]")
    console.print(f"Steps: {len(flow.steps)}")

    if not issues:
        levels = _topological_sort(flow.steps)
        console.print(f"Levels: {len(levels)}")
        for i, level in enumerate(levels, 1):
            console.print(f"  Level {i}: {' → '.join(level)}")
        console.print("[green][OK] Validation passed[/green]")
    else:
        console.print("[red]Validation failed:[/red]")
        for issue in issues:
            console.print(f"  [yellow]- {issue}[/yellow]")
        raise typer.Exit(1)


@app.command("list")
def list_cmd():
    """列出所有 Flow。"""
    if not FLOWS_DIR.is_dir():
        console.print("[dim]No flows found. Create one with sf flow init.[/dim]")
        return

    table = Table(title="Flows", header_style="bold cyan")
    table.add_column("Name", style="cyan")
    table.add_column("Version")
    table.add_column("Steps")
    table.add_column("Description")

    for f in sorted(FLOWS_DIR.glob("*.flow.y*ml")):
        try:
            flow = load_flow(f)
            table.add_row(
                flow.name,
                flow.version,
                str(len(flow.steps)),
                flow.description[:60] + "..." if len(flow.description) > 60 else flow.description,
            )
        except Exception:
            table.add_row(f.stem, "?", "?", "[red]Parse error[/red]")

    console.print(table)


@app.command()
def show(
    name: str = typer.Argument(..., help="Flow 名称或路径"),
    dag: bool = typer.Option(False, "--dag", help="显示依赖图"),
):
    """查看 Flow 详情。"""
    path = Path(name)
    if not path.exists():
        path = FLOWS_DIR / f"{name}.flow.yml"

    try:
        flow = load_flow(path)
    except FileNotFoundError:
        console.print(f"[red]Flow not found: {name}[/red]")
        raise typer.Exit(1)

    console.print(
        Panel.fit(
            f"[bold cyan]{flow.name}[/bold cyan] v{flow.version}",
            subtitle=flow.description,
        )
    )

    if dag:
        levels = _topological_sort(flow.steps)
        console.print("\n[bold]Execution Plan (DAG):[/bold]")
        for i, level in enumerate(levels, 1):
            console.print(f"  Level {i}: {' | '.join(level)}")

    # 步骤列表
    table = Table(title="Steps", header_style="bold")
    table.add_column("ID", style="cyan")
    table.add_column("Skill")
    table.add_column("Depends On")
    table.add_column("Description")

    for step in flow.steps:
        table.add_row(
            step.id,
            step.skill,
            ", ".join(step.depends_on) or "-",
            step.description[:50],
        )

    console.print(table)


@app.command()
def run(
    name: str = typer.Argument(..., help="Flow 名称或路径"),
    input_values: list[str] = typer.Option(
        None, "--input", "-i", help="输入参数 key=value（可多次指定）"
    ),
    parallel: int = typer.Option(5, "--parallel", "-p", help="最大并行步骤数"),
    dry_run: bool = typer.Option(False, "--dry-run", help="仅显示执行计划"),
    stream: bool = typer.Option(
        False, "--stream", "-s", help="流式输出（逐 token 实时打印每个步骤）"
    ),
):
    """执行 Flow。

    --stream 模式逐 token 实时输出每个步骤的结果。
    流式模式下步骤顺序执行以避免输出交错。

    Examples:
        sf flow run blog-pipeline -i topic="AI trends"
        sf flow run code-review --stream -i repo_path=./src
    """
    path = Path(name)
    if not path.exists():
        path = FLOWS_DIR / f"{name}.flow.yml"

    try:
        flow = load_flow(path)
    except FileNotFoundError:
        console.print(f"[red]Flow not found: {name}[/red]")
        raise typer.Exit(1)

    # 解析输入参数（P2-002: 按 schema type 转换，-i count=3 得到 int 3）
    from soloflow.core.flow_engine import parse_input_value

    inputs = {}
    if input_values:
        for iv in input_values:
            if "=" in iv:
                k, v = iv.split("=", 1)
                k = k.strip()
                spec = flow.input_schema.get(k, {}) if flow.input_schema else {}
                try:
                    inputs[k] = parse_input_value(v.strip(), spec)
                except ValueError as e:
                    console.print(f"[red]输入参数错误 ({k}): {e}[/red]")
                    raise typer.Exit(1)

    # P1-002: 流式模式串行由引擎统一规范化（run_flow 内部处理），CLI 不再重复
    try:
        run_flow(flow, inputs=inputs, max_parallel=parallel, dry_run=dry_run, stream=stream)
    except ValueError as e:
        # P1-002: max_parallel 非法值（0/负数）显示友好错误并非零退出
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


@app.command()
def resume(
    run_id: str = typer.Argument(..., help="运行 ID（如 run-a1b2c3d4e5f6）"),
    dry_run: bool = typer.Option(False, "--dry-run", help="仅预览不执行"),
    stream: bool = typer.Option(False, "--stream", "-s", help="流式输出"),
):
    """从断点恢复 Flow 执行。

    列出可恢复的运行: sf flow runs

    Examples:
        sf flow resume run-a1b2c3d4e5f6
        sf flow resume run-a1b2c3d4e5f6 --stream
    """
    from soloflow.core.flow_engine import resume_flow

    result = resume_flow(run_id, dry_run=dry_run, stream=stream)
    if result is None:
        raise typer.Exit(1)


@app.command("runs")
def list_runs():
    """列出所有 Flow 运行记录（可从中断点恢复）。"""
    from soloflow.core.flow_engine import RUNS_DIR, _list_runnable_ids

    if not RUNS_DIR.is_dir() or not any(RUNS_DIR.iterdir()):
        console.print("[dim]没有运行记录。执行 sf flow run <name> 后会自动保存。[/dim]")
        return

    console.print("[bold]Flow 运行记录:[/bold]")
    console.print(f"[dim]目录: {RUNS_DIR}[/dim]")
    _list_runnable_ids()
