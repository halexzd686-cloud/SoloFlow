"""Registry 子命令 —— sf registry *"""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from soloflow.core.registry import (
    install_skill,
    list_registry_skills,
    publish_skill,
    search_registry,
    update_registry,
    validate_registry_entry,
)

app = typer.Typer(help="Skill Registry 社区技能市场", no_args_is_help=True)
console = Console()


@app.command()
def update():
    """更新本地 registry 缓存（从 GitHub 拉取最新索引）。"""
    update_registry()
    entries = list_registry_skills()
    console.print(f"[dim]{len(entries)} skills available in registry.[/dim]")


@app.command()
def search(
    keyword: str = typer.Argument(..., help="搜索关键词"),
):
    """搜索 registry 中的 Skill。

    Examples:
        sf registry search writing
        sf registry search code-review
        sf registry search marketing
    """
    console.print(f"[dim]Searching for: {keyword}[/dim]")

    results = search_registry(keyword)

    if not results:
        console.print(f"[yellow]No skills matching '{keyword}' found.[/yellow]")
        console.print("[dim]Try updating the registry first: sf registry update[/dim]")
        return

    table = Table(title=f"Search Results: '{keyword}'", header_style="bold cyan")
    table.add_column("Name", style="cyan")
    table.add_column("Version")
    table.add_column("Author")
    table.add_column("Downloads")
    table.add_column("Description")

    for e in results:
        table.add_row(
            e.name,
            e.version,
            e.author,
            str(e.downloads),
            e.description[:60] + "..." if len(e.description) > 60 else e.description,
        )

    console.print(table)
    console.print(
        f"\n[dim]Found {len(results)} skill(s). Install with: sf registry install <name>[/dim]"
    )


@app.command()
def install(
    name: str = typer.Argument(..., help="Skill 名称"),
    target: str = typer.Option(
        "local", "--target", "-t", help="安装目标: local（全局）或 project（当前项目）"
    ),
    version: str = typer.Option(
        None, "--version", "-v", help="指定安装版本（如 1.2.0），不指定则安装最新版"
    ),
    fallback_latest: bool = typer.Option(
        False, "--fallback-latest", help="指定版本不存在时允许回退到最新版（默认严格失败）"
    ),
):
    """从 registry 安装一个 Skill。

    BUG-REG-002: 指定版本时必须精确安装该版本；版本不存在则失败，
    除非显式传 --fallback-latest。

    Examples:
        sf registry install awesome-writer
        sf registry install code-reviewer --target project
        sf registry install twitter-writer --version 1.2.0
        sf registry install twitter-writer --version 9.9.9 --fallback-latest
    """
    console.print(f"[dim]Installing '{name}'...[/dim]")
    if version:
        console.print(f"[dim]Requested version: {version}[/dim]")

    result = install_skill(name, target=target, version=version, fallback_latest=fallback_latest)
    if result:
        console.print(f"\n[dim]Installed. Use: sf skill run {name} <task>[/dim]")


@app.command()
def publish(
    name: str = typer.Argument(..., help="要发布的 Skill 名称"),
    submit: bool = typer.Option(False, "--submit", "-s", help="自动提交 PR 到社区 Registry"),
    message: str = typer.Option("", "--message", "-m", help="PR 描述信息"),
    fork: str = typer.Option("", "--fork", help="Fork 目标 (user/repo)，默认官方 registry"),
):
    """打包一个 Skill 准备分享，可选自动提交到社区 Registry。

    --submit 模式会自动：
    1. 打包 Skill 文件
    2. 生成 Registry 条目
    3. Fork/Clone 社区 Registry
    4. 添加 Skill + 更新索引
    5. 通过 gh CLI 创建 PR

    Examples:
        sf registry publish my-skill                  # 仅打包
        sf registry publish my-skill --submit         # 打包 + 自动PR
        sf registry publish my-skill -s -m "v2.0 重磅升级"
    """
    result = publish_skill(name, submit=submit, message=message, fork_name=fork)
    if result:
        console.print("\n[dim]Ready to share![/dim]")


@app.command()
def validate_entry(
    name: str = typer.Argument(None, help="Skill 名称（从 SKILL.md 生成条目并校验）"),
    file: str = typer.Option(None, "--file", "-f", help="直接校验 YAML 条目文件"),
):
    """校验 Registry 条目格式。"""
    if file:
        import yaml

        try:
            data = yaml.safe_load(Path(file).read_text(encoding="utf-8"))
            entries = data.get("skills", [data]) if isinstance(data, dict) else data
        except Exception as e:
            console.print(f"[red]Failed to parse {file}: {e}[/red]")
            raise typer.Exit(1)
    elif name:
        from soloflow.core.skill_loader import find_skill, load_skill

        try:
            skill_path = find_skill(name)
            _ = load_skill(skill_path)
        except FileNotFoundError:
            console.print(f"[red]Skill '{name}' not found.[/red]")
            raise typer.Exit(1)

        from soloflow.core.registry import _generate_registry_entry

        entries = [_generate_registry_entry(_, name)]
    else:
        console.print("[red]Provide a skill name or --file path.[/red]")
        raise typer.Exit(1)

    all_ok = True
    for entry in entries:
        issues = validate_registry_entry(entry)
        name_str = entry.get("name", "unknown")
        if not issues:
            console.print(f"[green][OK] {name_str} — 格式校验通过[/green]")
        else:
            all_ok = False
            console.print(f"[red]X {name_str} — {len(issues)} 个问题:[/red]")
            for issue in issues:
                console.print(f"  [yellow]• {issue}[/yellow]")

    if not all_ok:
        raise typer.Exit(1)


@app.command("list")
def list_cmd():
    """列出 registry 中所有可用的 Skill。"""
    entries = list_registry_skills()

    if not entries:
        console.print("[yellow]Registry is empty or not available.[/yellow]")
        console.print("[dim]Run 'sf registry update' to fetch the registry index.[/dim]")
        return

    table = Table(title=f"Community Registry ({len(entries)} skills)", header_style="bold cyan")
    table.add_column("Name", style="cyan")
    table.add_column("Version")
    table.add_column("Author")
    table.add_column("Tags")
    table.add_column("Description")

    for e in entries:
        table.add_row(
            e.name,
            e.version,
            e.author,
            ", ".join(e.tags[:3]),
            e.description[:60] + "..." if len(e.description) > 60 else e.description,
        )

    console.print(table)
    console.print("\n[dim]Install with: sf registry install <name>[/dim]")
