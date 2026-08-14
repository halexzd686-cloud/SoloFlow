"""SoloFlow CLI 主入口。"""

import typer
from rich.console import Console
from rich.panel import Panel

from soloflow import __version__
from soloflow.cli import agent, flow, skill
from soloflow.cli.encoding import configure_output_encoding
from soloflow.config import load_project_env

app = typer.Typer(
    name="soloflow",
    help="文件驱动的 AI 工作手册管理系统",
    no_args_is_help=True,
)

# Windows 传统终端可能仍使用 GBK；统一让 CLI 的中文输出走 UTF-8。
configure_output_encoding()
console = Console()

# 对外推荐 Playbook；Skill 作为隐藏的旧命令保留，避免破坏已有脚本。
app.add_typer(skill.app, name="playbook", help="工作手册管理")
app.add_typer(skill.app, name="skill", help="旧版 Skill 命令（兼容）", hidden=True)
app.add_typer(agent.app, name="agent", help="Agent 智能体管理")
app.add_typer(flow.app, name="flow", help="Flow 工作流编排")


@app.command("web")
def web(
    host: str = typer.Option("127.0.0.1", help="本地网页监听地址"),
    port: int = typer.Option(8765, min=1, max=65535, help="本地网页端口"),
    open_browser: bool = typer.Option(True, "--open/--no-open", help="启动后是否自动打开浏览器"),
):
    """启动 SoloFlow 本地网页。

    默认会自动打开浏览器；如果只想启动服务，可以使用 --no-open。
    """
    from soloflow.web import serve

    serve(host=host, port=port, open_browser=open_browser)


@app.command("run")
def run_skill_shortcut(
    skill_name: str = typer.Argument(..., help="工作手册名称或路径"),
    task: str = typer.Argument(None, help="任务描述"),
    input_file: str = typer.Option(None, "--file", "-f", help="从文件读取任务"),
    count: int = typer.Option(1, "--count", "-n", help="生成几个版本"),
    model: str | None = typer.Option(None, "--model", help="临时覆盖工作手册的 DeepSeek 模型"),
    dry_run: bool = typer.Option(False, "--dry-run", help="仅预览，不调用模型"),
    stream: bool = typer.Option(False, "--stream", "-s", help="流式输出"),
):
    """运行一个工作手册（推荐入口）。"""
    skill.run(
        skill_name=skill_name,
        prompt=task,
        input_file=input_file,
        count=count,
        model=model,
        dry_run=dry_run,
        stream=stream,
    )


@app.command()
def mcp():
    """启动 MCP Server 模式（JSON-RPC over stdio）。

    让 Claude Code、Cursor、VS Code 等 AI 工具直接调用 SoloFlow 的工作手册、Flow 和 Agent。

    配置方式 —— 在 .claude/settings.json 或 claude_desktop_config.json 中添加：

    ```json
    {
      "mcpServers": {
        "soloflow": {
          "command": "uv",
          "args": ["run", "sf", "mcp"],
          "cwd": "/path/to/your/project"
        }
      }
    }
    ```
    """
    # stderr 用于日志（不影响 stdio 协议）
    import sys

    from soloflow.mcp.server import run_stdio_server

    print(f"SoloFlow MCP Server v{__version__}", file=sys.stderr)
    print("JSON-RPC 2.0 over stdio — waiting for client...", file=sys.stderr)

    try:
        run_stdio_server()
    except KeyboardInterrupt:
        pass


@app.command()
def mcp_config(
    set_token: str = typer.Option(None, "--set-token", help="设置 auth token（环境变量优先）"),
    allow_tools: str = typer.Option(None, "--allow-tools", help="设置工具白名单（逗号分隔）"),
    clear: bool = typer.Option(False, "--clear", help="清除所有安全限制"),
):
    """查看/配置 MCP Server 的安全设置。

    包括 auth_token（访问认证）和 allowed_tools（工具白名单）。
    配置保存到 .soloflow/mcp.json。

    也支持环境变量:
      SOLOFLOW_MCP_TOKEN        认证 token
      SOLOFLOW_MCP_ALLOWED_TOOLS  允许的工具（逗号分隔）
    """
    from soloflow.mcp.server import MCP_CONFIG_PATH, save_mcp_config, show_mcp_config

    if clear:
        if MCP_CONFIG_PATH.exists():
            MCP_CONFIG_PATH.unlink()
            console.print("[green]MCP 安全配置已清除[/green]")
        else:
            console.print("[dim]没有配置文件需要清除[/dim]")
        return

    allowed_list = None
    if allow_tools:
        allowed_list = [tool.strip() for tool in allow_tools.split(",") if tool.strip()]

    if set_token is not None or allow_tools is not None:
        path = save_mcp_config(auth_token=set_token or "", allowed_tools=allowed_list)
        console.print(f"[green][OK] MCP 配置已保存: {path}[/green]")
        return

    config = show_mcp_config()
    console.print(Panel.fit("[bold cyan]MCP Server 安全配置[/bold cyan]", border_style="cyan"))
    console.print(f"配置文件: {config['config_file']}")
    console.print(f"配置文件存在: {'是' if config['config_exists'] else '否'}")
    console.print(
        f"Token 认证: {'[green]已启用[/green]' if config['auth_enabled'] else '[dim]未启用（所有调用放行）[/dim]'}"  # noqa: E501
    )
    if config["auth_token_masked"]:
        console.print(f"Token: {config['auth_token_masked']}")

    tools = config["allowed_tools"]
    if tools is None:
        console.print(f"工具白名单: [dim]未限制（{config['total_tools']} 个工具全部可用）[/dim]")
    else:
        console.print(f"工具白名单: [yellow]{len(tools)}/{config['total_tools']} 个工具[/yellow]")
        for t in tools:
            console.print(f"  - {t}")

    console.print("\n[dim]修改: sf mcp-config --set-token <token> --allow-tools tool1,tool2[/dim]")
    console.print("[dim]清除限制: sf mcp-config --clear[/dim]")


@app.command()
def version():
    """显示版本信息。"""
    console.print(f"[bold cyan]SoloFlow[/bold cyan] v{__version__}")
    console.print("[dim]文件驱动的 AI 工作手册管理系统[/dim]")


@app.callback()
def callback(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="详细输出"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="静默模式"),
):
    """SoloFlow —— 把 AI 工作方法保存成可复用的工作手册。

    将专家经验封装为可复用的 PLAYBOOK.md 文件，
    让 AI 按标准完成任务。
    """
    load_project_env()
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet


if __name__ == "__main__":
    app()
