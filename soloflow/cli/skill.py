"""工作手册命令实现 —— sf playbook *（兼容 sf skill *）"""

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from soloflow.core.skill_loader import (
    find_skill,
    list_available_skills,
    load_skill,
    save_playbook,
    save_skill,
    validate_skill,
)
from soloflow.models.skill import (
    CoSTAR,
    SkillConfig,
    SkillFile,
    SkillMeta,
)

app = typer.Typer(help="工作手册管理（兼容旧版 Skill）", no_args_is_help=True)
console = Console()

SKILL_TEMPLATES = {
    "writer": {
        "name": "content-writer",
        "description": "按照特定风格撰写高质量长文",
        "context": "你是一位资深内容创作者，擅长深度长文写作。",
        "objective": "根据提供的主题和大纲，撰写一篇结构完整、有深度的文章。",
        "tags": ["writing", "content"],
        "body": """## Instructions

1. 理解输入的主题和受众
2. 构建清晰的文章结构（引言 → 正文 → 结论）
3. 使用真实案例和数据支撑观点
4. 确保语言流畅，避免 AI 味

## Quality Checklist

- [ ] 标题有吸引力
- [ ] 每段不超过 4 行
- [ ] 至少包含 2 个具体案例
- [ ] 结论有行动号召""",
    },
    "reviewer": {
        "name": "code-reviewer",
        "description": "按照团队标准进行代码审查",
        "context": "你是一位资深代码审查者，关注代码质量、安全性和可维护性。",
        "objective": "审查给定的代码变更，指出潜在问题并给出改进建议。",
        "tags": ["coding", "review"],
        "body": """## Instructions

1. 先理解代码变更的目的
2. 检查逻辑正确性和边界条件
3. 检查安全漏洞和性能问题
4. 给出具体、可执行的改进建议
5. 区分"必须修改"和"建议优化"

## Review Dimensions

- 正确性：逻辑是否正确
- 安全性：是否有注入、泄漏等风险
- 性能：是否有明显的性能问题
- 可读性：命名、结构是否清晰""",
    },
    "researcher": {
        "name": "market-researcher",
        "description": "深度市场调研与分析",
        "context": "你是一位资深市场研究分析师，擅长行业分析和竞争情报。",
        "objective": "针对给定主题进行深度调研，输出结构化分析报告。",
        "tags": ["research", "analysis"],
        "body": """## Instructions

1. 明确调研范围和关键问题
2. 从多维度收集信息（市场、竞争、趋势、用户）
3. 用数据支撑每个结论
4. 输出结构化的调研报告

## Report Structure

1. 执行摘要
2. 市场概况
3. 竞争格局
4. 趋势与机会
5. 建议与行动方案""",
    },
}


@app.command()
def init(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="工作手册名称 (kebab-case)"),
    template: str = typer.Option(
        "writer", "--from", "-f", help="模板: writer / reviewer / researcher"
    ),
    output: str | None = typer.Option(None, "--output", "-o", help="输出目录"),
    dry_run: bool = typer.Option(False, "--dry-run", help="仅预览，不写入文件"),
):
    """创建一个新的工作手册文件。"""
    is_playbook = "playbook" in ctx.command_path.split()
    output = output or ("./playbooks" if is_playbook else "./skills")
    if template not in SKILL_TEMPLATES:
        console.print(f"[red]未知模板: {template}[/red]")
        console.print(f"可用模板: {', '.join(SKILL_TEMPLATES.keys())}")
        raise typer.Exit(1)

    tpl = SKILL_TEMPLATES[template]

    console.print()
    console.print(
        Panel.fit("[bold cyan]SoloFlow - 工作手册创建向导[/bold cyan]", border_style="cyan")
    )

    # 收集基本信息
    console.print(f"\n[bold]工作手册名称:[/bold] {name}")
    desc = typer.prompt("简短描述", default=tpl["description"])
    author = typer.prompt("作者", default="unknown")
    tags_input = typer.prompt("标签 (逗号分隔)", default=",".join(tpl["tags"]))

    # CoSTAR 配置
    console.print("\n[bold cyan]── CoSTAR 提示词配置 ──[/bold cyan]")
    context = _multiline_prompt("Context (背景信息)", tpl["context"])
    objective = _multiline_prompt("Objective (目标)", tpl["objective"])
    style = typer.prompt("Style (风格)", default="")
    tone = typer.prompt("Tone (语气)", default="")
    audience = typer.prompt("Audience (受众)", default="")

    # 规则
    console.print("\n[bold cyan]── 规则（不可打破的约束）──[/bold cyan]")
    console.print("输入规则，每行一条。空行结束。")
    rules = _collect_lines()

    # Body
    console.print("\n[bold cyan]── Markdown Body（实际 prompt 模板）──[/bold cyan]")
    console.print("输入 Body 内容。输入 'EOF' 结束。")
    body = _collect_multiline()

    # 构建内部 SkillFile；对外文件名使用 Playbook。
    skill = SkillFile(
        meta=SkillMeta(
            name=name,
            version="0.1.0",
            author=author,
            description=desc,
            tags=[t.strip() for t in tags_input.split(",") if t.strip()],
        ),
        costar=CoSTAR(
            context=context,
            objective=objective,
            style=style,
            tone=tone,
            audience=audience,
        ),
        config=SkillConfig(),
        rules=rules,
        examples=[],
        tests=[],
        body=body if body.strip() else tpl["body"],
    )

    if dry_run:
        console.print("\n[bold yellow]── 预览 (dry-run) ──[/bold yellow]")
        console.print(Syntax(skill.full_prompt, "markdown", theme="monokai"))
        return

    # 保存
    out_path = Path(output) / name
    saved_path = save_playbook(skill, out_path) if is_playbook else save_skill(skill, out_path)

    console.print(f"\n[green][OK] 已创建工作手册: {saved_path}[/green]")
    console.print("[green][OK] 验证通过[/green]")
    console.print(f"[dim]Next: sf run {name} <task>[/dim]")


@app.command()
def validate(
    path: str = typer.Argument(..., help="工作手册文件路径或目录"),
    strict: bool = typer.Option(False, "--strict", "-s", help="严格模式"),
):
    """校验工作手册文件格式。"""
    skill_path = Path(path)
    try:
        skill = load_skill(skill_path)
    except FileNotFoundError as e:
        console.print(f"[red]X {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]X 解析失败: {e}[/red]")
        raise typer.Exit(1)

    issues = validate_skill(skill, strict=strict)

    console.print(f"\n[bold]工作手册: {skill.meta.name} v{skill.meta.version}[/bold]")

    if not issues:
        console.print("[green][OK] 格式校验通过[/green]")
        console.print(
            f"  Context: {'[OK]' if skill.costar.context else '○'} | "
            f"Objective: {'[OK]' if skill.costar.objective else '○'} | "
            f"Rules: {len(skill.rules)} | "
            f"Examples: {len(skill.examples)}"
        )
    else:
        console.print("[red]X 校验发现问题:[/red]")
        for issue in issues:
            console.print(f"  [yellow]• {issue}[/yellow]")
        raise typer.Exit(1)


@app.command("list")
def list_cmd(
    local: bool = typer.Option(False, "--local", "-l", help="仅列出项目工作手册"),
    global_: bool = typer.Option(False, "--global", "-g", help="仅列出全局工作手册"),
):
    """列出所有可用的工作手册。"""
    table = Table(title="Playbooks / 工作手册", show_header=True, header_style="bold cyan")
    table.add_column("名称", style="cyan")
    table.add_column("版本")
    table.add_column("描述")
    table.add_column("标签")
    table.add_column("来源")

    skills = list_available_skills(
        include_project=not global_,
        include_global=not local,
        include_bundled=not local and not global_,
    )
    for s in skills:
        table.add_row(
            s["name"],
            s["version"],
            s["description"][:60] + "..." if len(s["description"]) > 60 else s["description"],
            ", ".join(s["tags"]),
            s["source"],
        )

    if len(table.rows) == 0:
        console.print("[dim]没有找到工作手册。使用 sf playbook init 创建一个。[/dim]")
        return

    console.print(table)


@app.command()
def show(
    name: str = typer.Argument(..., help="工作手册名称或路径"),
    json: bool = typer.Option(False, "--json", help="JSON 格式输出"),
    rendered: bool = typer.Option(False, "--rendered", "-r", help="显示渲染后的完整 prompt"),
):
    """查看工作手册详情。"""
    try:
        skill_path = find_skill(name)
        skill = load_skill(skill_path)
    except FileNotFoundError:
        console.print(f"[red]工作手册不存在: {name}[/red]")
        raise typer.Exit(1)

    if json:
        console.print_json(skill.model_dump_json(indent=2))
        return

    # 美化输出
    console.print(
        Panel.fit(
            f"[bold cyan]{skill.meta.name}[/bold cyan] v{skill.meta.version}",
            subtitle=f"作者: {skill.meta.author}",
        )
    )
    console.print(f"[dim]{skill.meta.description}[/dim]")
    if skill.meta.tags:
        console.print(f"标签: {', '.join(skill.meta.tags)}")

    if rendered:
        console.print("\n[bold]── 渲染后的完整 Prompt ──[/bold]")
        console.print(Syntax(skill.full_prompt, "markdown", theme="monokai"))
    else:
        console.print("\n[bold]CoSTAR:[/bold]")
        console.print(
            f"  Context: {skill.costar.context[:80]}..."
            if len(skill.costar.context) > 80
            else f"  Context: {skill.costar.context}"
        )
        console.print(
            f"  Objective: {skill.costar.objective[:80]}..."
            if len(skill.costar.objective) > 80
            else f"  Objective: {skill.costar.objective}"
        )
        console.print(f"  Rules: {len(skill.rules)} 条")
        console.print(f"  Examples: {len(skill.examples)} 个")
        console.print(f"  Body: {len(skill.body)} 字符")


@app.command()
def run(
    skill_name: str = typer.Argument(..., help="工作手册名称或路径"),
    prompt: str = typer.Argument(None, help="输入任务描述"),
    input_file: str = typer.Option(None, "--file", "-f", help="从文件读取输入"),
    count: int = typer.Option(1, "--count", "-n", help="生成几个版本 (抽卡模式)"),
    model: str | None = typer.Option(None, "--model", help="临时覆盖工作手册的 DeepSeek 模型"),
    dry_run: bool = typer.Option(False, "--dry-run", help="仅显示 prompt，不调用 LLM"),
    stream: bool = typer.Option(False, "--stream", "-s", help="流式输出（逐 token 实时打印）"),
):
    """用工作手册执行任务。

    --stream 模式实时逐 token 输出，适合长任务。
    流式模式下 --count 固定为 1。

    Examples:
        sf playbook run writer "写一篇AI文章"
        sf playbook run writer "写一篇文章" --stream
        sf playbook run reviewer --file diff.txt -n 3
    """
    try:
        spath = find_skill(skill_name)
        skill = load_skill(spath)
    except FileNotFoundError:
        console.print(f"[red]工作手册不存在: {skill_name}[/red]")
        raise typer.Exit(1)

    # 获取输入
    if input_file:
        user_input = Path(input_file).read_text(encoding="utf-8")
    elif prompt:
        user_input = prompt
    else:
        user_input = typer.prompt("输入任务描述")

    console.print(f"\n[dim]使用工作手册: {skill.meta.name} v{skill.meta.version}[/dim]")
    effective_model = model.strip() if model and model.strip() else skill.config.model
    console.print(f"[dim]模型: {effective_model} | 温度: {skill.config.temperature}[/dim]")

    if stream:
        console.print("[dim]模式: 流式输出[/dim]")

    if dry_run:
        console.print("\n[bold yellow]── Dry Run: 渲染后的 Prompt ──[/bold yellow]")
        combined = f"{skill.full_prompt}\n\n# Task\n{user_input}"
        console.print(Syntax(combined, "markdown", theme="monokai"))
        return

    # 实际执行
    from soloflow.core.runner import run_skill

    run_skill(skill, user_input, count=count, model=model, stream=stream)


# ── 辅助函数 ──


def _multiline_prompt(label: str, default: str = "") -> str:
    """多行输入提示（单行输入）。"""
    console.print(f"[bold]{label}[/bold]")
    if default:
        console.print(
            f"[dim]默认: {default[:100]}...[/dim]"
            if len(default) > 100
            else f"[dim]默认: {default}[/dim]"
        )
    result = typer.prompt("", default=default, show_default=False)
    return result


def _collect_lines() -> list[str]:
    """收集多行输入，空行结束。"""
    lines = []
    while True:
        line = typer.prompt("", default="", show_default=False)
        if not line.strip():
            break
        lines.append(line)
    return lines


def _collect_multiline() -> str:
    """收集多行文本，输入 'EOF' 结束。"""
    lines = []
    console.print("[dim](输入 EOF 结束)[/dim]")
    while True:
        line = typer.prompt("", default="", show_default=False)
        if line.strip().upper() == "EOF":
            break
        lines.append(line)
    return "\n".join(lines)
