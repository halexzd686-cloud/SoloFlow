"""SoloFlow CLI 主入口。"""

import typer
from rich.console import Console
from rich.panel import Panel

from soloflow import __version__
from soloflow.cli import agent, flow, registry, skill

app = typer.Typer(
    name="soloflow",
    help="文件驱动的 AI Skill 管理系统",
    no_args_is_help=True,
)

console = Console()

# 注册子命令
app.add_typer(skill.app, name="skill", help="Skill 技能文件管理")
app.add_typer(agent.app, name="agent", help="Agent 智能体管理")
app.add_typer(flow.app, name="flow", help="Flow 工作流编排")
app.add_typer(registry.app, name="registry", help="Skill Registry 社区技能市场")


@app.command()
def dashboard():
    """启动 TUI 仪表盘（侘寂风）。"""
    from soloflow.tui.app import SoloFlowApp

    app = SoloFlowApp()
    app.run()


@app.command()
def mcp():
    """启动 MCP Server 模式（JSON-RPC over stdio）。

    让 Claude Code、Cursor、VS Code 等 AI 工具直接调用 SoloFlow 的 Skill/Flow/Agent。

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
def mcp_config():
    """查看/配置 MCP Server 的安全设置。

    包括 auth_token（访问认证）和 allowed_tools（工具白名单）。
    配置保存到 .soloflow/mcp.json。

    也支持环境变量:
      SOLOFLOW_MCP_TOKEN        认证 token
      SOLOFLOW_MCP_ALLOWED_TOOLS  允许的工具（逗号分隔）
    """
    from soloflow.mcp.server import (
        show_mcp_config,
    )

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

    console.print(
        "\n[dim]修改配置: sf mcp-config --set-token <token> --allow-tools tool1,tool2[/dim]"
    )
    console.print("[dim]清除限制: sf mcp-config --clear[/dim]")


@app.command()
def mcp_config_set(
    set_token: str = typer.Option(None, "--set-token", help="设置 auth token（环境变量优先）"),
    allow_tools: str = typer.Option(None, "--allow-tools", help="设置工具白名单（逗号分隔）"),
    clear: bool = typer.Option(False, "--clear", help="清除所有安全限制"),
):
    """修改 MCP Server 安全配置。"""
    from soloflow.mcp.server import save_mcp_config

    if clear:
        from soloflow.mcp.server import MCP_CONFIG_PATH

        if MCP_CONFIG_PATH.exists():
            MCP_CONFIG_PATH.unlink()
            console.print("[green]MCP 安全配置已清除 —— 所有调用放行[/green]")
        else:
            console.print("[dim]没有配置文件需要清除[/dim]")
        return

    allowed_list = None
    if allow_tools:
        allowed_list = [t.strip() for t in allow_tools.split(",") if t.strip()]

    path = save_mcp_config(auth_token=set_token or "", allowed_tools=allowed_list)
    console.print(f"[green][OK] MCP 配置已保存: {path}[/green]")

    if set_token:
        console.print(f"  Token 认证: 已启用 ({set_token[:8]}...)")
    if allowed_list:
        console.print(f"  工具白名单: {', '.join(allowed_list)}")


@app.command()
def version():
    """显示版本信息。"""
    console.print(f"[bold cyan]SoloFlow[/bold cyan] v{__version__}")
    console.print("[dim]文件驱动的 AI Skill 管理系统[/dim]")


@app.callback()
def callback(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="详细输出"),
    quiet: bool = typer.Option(False, "--quiet", "-q", help="静默模式"),
):
    """SoloFlow —— 封装、复用、迭代你的 AI 技能。

    将专家经验封装为可复用的 SKILL.md 文件，
    让 AI 按标准干活。
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet


if __name__ == "__main__":
    app()
