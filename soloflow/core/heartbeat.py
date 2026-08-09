"""Agent 心跳调度引擎。

让 Agent 从被动执行者升级为主动工作者。
按 Agent 定义的 heartbeat.interval 定时触发 trigger_prompt。

协议：
- 启用心跳: sf agent heartbeat start <name> [--daemon]
- 停止心跳: sf agent heartbeat stop <name>
- 查看状态: sf agent heartbeat list
- 恢复心跳: sf agent heartbeat resume
- 状态持久化到 .soloflow/heartbeats/<name>.json

Daemon 模式：
- --daemon 将心跳作为后台进程运行
- 输出写入 .soloflow/heartbeats/<name>.log
- PID 写入 .soloflow/heartbeats/<name>.pid
"""

import asyncio
import json
import os
import re
import signal
import sys
from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console
from rich.table import Table

from soloflow.core.agent_runner import run_agent
from soloflow.models.agent import AgentDefinition

console = Console()

HEARTBEAT_DIR = Path(".soloflow/heartbeats")

# 存储运行中的心跳任务 {agent_name: asyncio.Task}
_running_heartbeats: dict[str, asyncio.Task] = {}


def _parse_interval(interval: str) -> float:
    """解析时间间隔字符串为秒数。

    支持格式: "30s", "5m", "1h", "6h", "1d"
    """
    interval = interval.strip().lower()
    match = re.match(r"(\d+)\s*(s|m|h|d)", interval)
    if not match:
        console.print(f"[yellow]无法解析间隔 '{interval}'，使用默认 1h[/yellow]")
        return 3600.0

    value = int(match.group(1))
    unit = match.group(2)

    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return float(value * multipliers[unit])


def _format_interval(seconds: float) -> str:
    """将秒数格式化为可读字符串。"""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        return f"{int(seconds / 60)}m"
    elif seconds < 86400:
        return f"{int(seconds / 3600)}h"
    else:
        return f"{int(seconds / 86400)}d"


def _save_heartbeat_state(name: str, state: dict) -> None:
    """保存心跳状态到磁盘。"""
    HEARTBEAT_DIR.mkdir(parents=True, exist_ok=True)
    path = HEARTBEAT_DIR / f"{name}.json"
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_heartbeat_state(name: str) -> dict | None:
    """从磁盘加载心跳状态。"""
    path = HEARTBEAT_DIR / f"{name}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
    return None


def _delete_heartbeat_state(name: str) -> None:
    """删除心跳状态文件。"""
    path = HEARTBEAT_DIR / f"{name}.json"
    if path.exists():
        path.unlink()


async def _run_heartbeat_loop(agent: AgentDefinition, daemon: bool = False) -> None:
    """心跳主循环。

    在后台持续运行，按 interval 触发 agent 执行 trigger_prompt。

    Args:
        agent: Agent 定义。
        daemon: 是否为 daemon 模式（输出到日志文件而非 console）。
    """
    name = agent.name
    interval_sec = _parse_interval(agent.heartbeat.interval)

    state = _load_heartbeat_state(name) or {}
    run_count = state.get("run_count", 0)
    last_run = state.get("last_run")

    def _log(msg: str) -> None:
        """根据模式输出到 console 或日志文件。"""
        if daemon:
            log_path = HEARTBEAT_DIR / f"{name}.log"
            timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{timestamp}] {msg}\n")
        else:
            console.print(msg)

    _log(f"♥ Agent '{name}' 心跳已启动 (间隔: {_format_interval(interval_sec)})")

    if last_run:
        _log(f"  上次运行: {last_run}, 累计: {run_count} 次")

    # 写入 PID（daemon 模式）
    if daemon:
        _write_pid(name, os.getpid())

    loop = asyncio.get_running_loop()

    while True:
        try:
            await asyncio.sleep(interval_sec)

            now = datetime.now(UTC).isoformat()
            _log(f"♥ [{name}] 心跳触发")

            # 在线程池中执行阻塞的 run_agent，避免阻塞事件循环
            trigger = agent.heartbeat.trigger_prompt
            results = await loop.run_in_executor(None, run_agent, agent, trigger, 1, False)

            run_count += 1
            last_run = now

            # 保存状态
            _save_heartbeat_state(
                name,
                {
                    "agent_name": name,
                    "interval": agent.heartbeat.interval,
                    "run_count": run_count,
                    "last_run": last_run,
                    "last_result": results[0][:200] if results else "",
                    "status": "running",
                },
            )

            if results:
                preview = results[0][:500] + ("..." if len(results[0]) > 500 else "")
                _log(f"  输出: {preview}")

        except asyncio.CancelledError:
            _log(f"♥ Agent '{name}' 心跳已停止")
            _save_heartbeat_state(
                name,
                {
                    "agent_name": name,
                    "interval": agent.heartbeat.interval,
                    "run_count": run_count,
                    "last_run": last_run,
                    "stopped_at": datetime.now(UTC).isoformat(),
                    "status": "stopped",
                },
            )
            if daemon:
                _remove_pid(name)
            break
        except Exception as e:
            _log(f"心跳执行失败 [{name}]: {e}")
            # 继续循环，等下一轮


# ── PID 文件管理 ──


def _write_pid(name: str, pid: int) -> None:
    """写入 PID 文件。"""
    HEARTBEAT_DIR.mkdir(parents=True, exist_ok=True)
    pid_path = HEARTBEAT_DIR / f"{name}.pid"
    pid_path.write_text(str(pid))


def _read_pid(name: str) -> int | None:
    """读取 PID 文件。"""
    pid_path = HEARTBEAT_DIR / f"{name}.pid"
    if pid_path.exists():
        try:
            return int(pid_path.read_text().strip())
        except (ValueError, OSError):
            return None
    return None


def _remove_pid(name: str) -> None:
    """删除 PID 文件。"""
    pid_path = HEARTBEAT_DIR / f"{name}.pid"
    if pid_path.exists():
        pid_path.unlink()


def _is_process_running(pid: int) -> bool:
    """检查指定 PID 的进程是否在运行。

    平台差异（重要）：
    - Unix: os.kill(pid, 0) 信号 0 只做存在性检查，不会影响目标进程。
    - Windows: os.kill 不是信号语义，会直接调用 TerminateProcess 杀死目标进程！
      必须改用 OpenProcess + GetExitCodeProcess 做只读探活，绝不能 os.kill。

    这是 BUG-HB-001 的修复：此前 Windows 上探活会误杀 daemon 甚至 pytest 自身。
    """
    if sys.platform == "win32":
        return _is_process_running_windows(pid)
    try:
        os.kill(pid, 0)  # 信号 0 只检查进程是否存在
        return True
    except (OSError, ProcessLookupError):
        return False


def _is_process_running_windows(pid: int) -> bool:
    """Windows 专用探活：OpenProcess + GetExitCodeProcess（只读，不杀进程）。"""
    import ctypes
    from ctypes import wintypes

    # Win32 API 常量名（惯例大写，N806 豁免）
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000  # noqa: N806
    STILL_ACTIVE = 259  # noqa: N806
    ERROR_ACCESS_DENIED = 5  # noqa: N806
    ERROR_INVALID_PARAMETER = 87  # noqa: N806

    # use_last_error=True 才能用 ctypes.get_last_error() 读取 Win32 错误码
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]

    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        last_error = ctypes.get_last_error()
        # 拒绝访问 = 进程存在但权限不足 → 按"在运行"处理（存在性语义）
        if last_error == ERROR_ACCESS_DENIED:
            return True
        # 参数无效 = 不存在该 PID 的进程
        if last_error == ERROR_INVALID_PARAMETER:
            return False
        return False
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        # STILL_ACTIVE 表示进程仍在运行；否则已退出
        return exit_code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


# ── Daemon 模式 ──


def _daemonize() -> None:
    """将当前进程转为后台 daemon（Unix 风格 double-fork）。

    在 Windows 上，使用简单的进程 detach 替代。
    """
    if sys.platform == "win32":
        # Windows: 无法真正 fork，使用 CREATE_NEW_PROCESS_GROUP
        # 由调用方通过 subprocess.Popen + creationflags 处理
        return

    # Unix double-fork
    try:
        if os.fork() > 0:
            sys.exit(0)  # 父进程退出
    except OSError:
        sys.exit(1)

    os.setsid()  # 创建新会话

    try:
        if os.fork() > 0:
            sys.exit(0)  # 第一个子进程退出
    except OSError:
        sys.exit(1)

    # 重定向标准流到 /dev/null
    sys.stdout.flush()
    sys.stderr.flush()
    with open(os.devnull) as devnull:
        os.dup2(devnull.fileno(), sys.stdin.fileno())
    with open(os.devnull, "a") as devnull:
        os.dup2(devnull.fileno(), sys.stdout.fileno())
        os.dup2(devnull.fileno(), sys.stderr.fileno())


def start_heartbeat(agent: AgentDefinition, daemon: bool = False) -> bool:
    """启动 Agent 的心跳。

    Args:
        agent: 已加载的 Agent 定义（heartbeat.enabled 必须为 True）。
        daemon: True 将心跳作为后台守护进程运行。

    Returns:
        True 表示成功启动，False 表示失败。
    """
    name = agent.name

    if not agent.heartbeat.enabled:
        console.print(f"[yellow]Agent '{name}' 未启用心跳[/yellow]")
        return False

    if not agent.heartbeat.trigger_prompt.strip():
        console.print(f"[red]Agent '{name}' 的心跳缺少 trigger_prompt[/red]")
        return False

    # 检查是否已在运行（daemon 模式通过 PID 文件）
    if daemon:
        existing_pid = _read_pid(name)
        if existing_pid and _is_process_running(existing_pid):
            console.print(f"[yellow]Agent '{name}' 心跳已在运行中 (PID: {existing_pid})[/yellow]")
            return False
    else:
        if name in _running_heartbeats:
            task = _running_heartbeats[name]
            if not task.done():
                console.print(f"[yellow]Agent '{name}' 心跳已在运行中[/yellow]")
                return False
            del _running_heartbeats[name]

    # ── Daemon 模式：通过子进程启动 ──
    if daemon:
        return _start_heartbeat_daemon(agent)

    # ── 嵌入式模式：在当前进程中创建 asyncio 任务 ──
    # 清除旧的停止状态
    old_state = _load_heartbeat_state(name)
    if old_state and "stopped_at" in old_state:
        _delete_heartbeat_state(name)

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    task = loop.create_task(_run_heartbeat_loop(agent, daemon=False))
    _running_heartbeats[name] = task

    _save_heartbeat_state(
        name,
        {
            "agent_name": name,
            "interval": agent.heartbeat.interval,
            "run_count": 0,
            "started_at": datetime.now(UTC).isoformat(),
            "status": "running",
        },
    )

    return True


def _start_heartbeat_daemon(agent: AgentDefinition) -> bool:
    """在后台守护进程中启动心跳。

    Windows: 使用 subprocess.Popen 在独立进程中运行
    Unix: 使用 start_new_session
    """
    import subprocess

    name = agent.name
    project_root = os.getcwd()
    python = sys.executable

    # 构建内联启动脚本
    script_lines = [
        "import asyncio, sys",
        f"sys.path.insert(0, {project_root!r})",
        f"sys.path.insert(0, {str(Path(__file__).parent.parent)!r})",
        "from soloflow.core.heartbeat import _run_heartbeat_loop",
        "from soloflow.cli.agent import _load_agent",
        "async def _main():",
        f"    agent = _load_agent({name!r})",
        "    await _run_heartbeat_loop(agent, daemon=True)",
        "asyncio.run(_main())",
    ]
    script = "; ".join(script_lines)

    try:
        if sys.platform == "win32":
            proc = subprocess.Popen(
                [python, "-c", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
                if hasattr(subprocess, "CREATE_NO_WINDOW")
                else 0,
            )
        else:
            proc = subprocess.Popen(
                [python, "-c", script],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )

        _write_pid(name, proc.pid)
        _save_heartbeat_state(
            name,
            {
                "agent_name": name,
                "interval": agent.heartbeat.interval,
                "run_count": 0,
                "started_at": datetime.now(UTC).isoformat(),
                "status": "running",
            },
        )

        console.print(
            f"[green]♥ Agent '{name}' 心跳已在后台启动[/green] "
            f"(PID: {proc.pid}, 间隔: {agent.heartbeat.interval})"
        )
        console.print(f"[dim]日志: {HEARTBEAT_DIR / name}.log[/dim]")
        console.print(f"[dim]停止: sf agent heartbeat stop {name}[/dim]")
        return True

    except Exception as e:
        console.print(f"[red]无法启动 daemon: {e}[/red]")
        return False


def stop_heartbeat(name: str) -> bool:
    """停止 Agent 的心跳。

    支持嵌入式模式和 daemon 模式：
    - 嵌入式：取消 asyncio Task
    - Daemon：通过 PID 文件杀死进程

    Returns:
        True 表示成功停止，False 表示未在运行。
    """
    # 先尝试取消嵌入式任务
    if name in _running_heartbeats:
        task = _running_heartbeats[name]
        if not task.done():
            task.cancel()
            del _running_heartbeats[name]
            console.print(f"[green]♥ Agent '{name}' 心跳已停止[/green]")
            return True
        del _running_heartbeats[name]

    # 尝试通过 PID 文件停止 daemon 进程
    pid = _read_pid(name)
    if pid and _is_process_running(pid):
        try:
            if sys.platform == "win32":
                os.kill(pid, signal.SIGTERM)
            else:
                os.kill(pid, signal.SIGTERM)
            _remove_pid(name)

            # 更新状态
            state = _load_heartbeat_state(name) or {}
            state["status"] = "stopped"
            state["stopped_at"] = datetime.now(UTC).isoformat()
            _save_heartbeat_state(name, state)

            console.print(f"[green]♥ Agent '{name}' 后台心跳已停止 (PID: {pid})[/green]")
            return True
        except OSError as e:
            console.print(f"[red]无法停止进程 {pid}: {e}[/red]")
            return False

    # 清理残留 PID 文件
    if pid:
        _remove_pid(name)

    console.print(f"[yellow]Agent '{name}' 心跳未在运行[/yellow]")
    return False


def resume_heartbeats() -> list[str]:
    """恢复之前运行中的心跳（daemon 进程重启后调用）。

    扫描 .soloflow/heartbeats/ 目录，找到状态为 "running" 的心跳，
    检查对应进程是否还活着，如果不在了就重新启动。

    Returns:
        已恢复的 Agent 名称列表。
    """
    if not HEARTBEAT_DIR.is_dir():
        return []

    resumed = []
    for state_file in sorted(HEARTBEAT_DIR.glob("*.json")):
        name = state_file.stem
        state = _load_heartbeat_state(name)

        if not state or state.get("status") != "running":
            continue

        # 检查进程是否还在运行
        pid = _read_pid(name)
        if pid and _is_process_running(pid):
            console.print(f"[dim]Agent '{name}' 心跳仍在运行 (PID: {pid})[/dim]")
            continue

        # 进程不在了，尝试恢复
        console.print(f"[yellow]Agent '{name}' 心跳已中断，尝试恢复...[/yellow]")
        _remove_pid(name)

        try:
            from soloflow.cli.agent import _load_agent

            agent = _load_agent(name)

            if not agent.heartbeat.enabled:
                console.print(f"[dim]Agent '{name}' 心跳已被禁用，跳过恢复[/dim]")
                _save_heartbeat_state(name, {**state, "status": "stopped"})
                continue

            # 以 daemon 模式重启
            ok = _start_heartbeat_daemon(agent)
            if ok:
                resumed.append(name)
            else:
                console.print(f"[red]恢复 Agent '{name}' 失败[/red]")
        except FileNotFoundError:
            console.print(f"[yellow]Agent '{name}' 定义文件不存在，跳过[/yellow]")
            _save_heartbeat_state(name, {**state, "status": "stopped"})
        except Exception as e:
            console.print(f"[red]恢复 Agent '{name}' 时出错: {e}[/red]")

    return resumed


def list_heartbeats() -> list[dict]:
    """列出所有心跳状态。

    Returns:
        心跳状态列表（运行中 + 历史）。
    """
    results = []

    # 运行中的心跳
    for name, task in _running_heartbeats.items():
        state = _load_heartbeat_state(name) or {}
        results.append(
            {
                "agent_name": name,
                "status": "running" if not task.done() else "stopped",
                "interval": state.get("interval", "?"),
                "run_count": state.get("run_count", 0),
                "last_run": state.get("last_run", "—"),
            }
        )

    # 历史心跳（已停止、不在运行列表中）
    if HEARTBEAT_DIR.is_dir():
        for f in sorted(HEARTBEAT_DIR.glob("*.json")):
            name = f.stem
            if name in _running_heartbeats:
                continue  # 已在上面列出
            try:
                state = json.loads(f.read_text(encoding="utf-8"))
                results.append(
                    {
                        "agent_name": name,
                        "status": "stopped",
                        "interval": state.get("interval", "?"),
                        "run_count": state.get("run_count", 0),
                        "last_run": state.get("last_run", "—"),
                    }
                )
            except Exception:
                continue

    return results


def show_heartbeat_status() -> None:
    """以 Rich 表格显示心跳状态。"""
    beats = list_heartbeats()
    if not beats:
        console.print("[dim]没有心跳记录。用 sf agent heartbeat start <name> 启动。[/dim]")
        return

    table = Table(title="♥ Agent Heartbeats", header_style="bold cyan")
    table.add_column("Agent", style="cyan")
    table.add_column("Status")
    table.add_column("Interval")
    table.add_column("Runs")
    table.add_column("Last Run")

    for b in beats:
        status_style = "green" if b["status"] == "running" else "dim"
        last_run = b["last_run"]
        if last_run and last_run != "—":
            last_run = last_run[:19]
        table.add_row(
            b["agent_name"],
            f"[{status_style}]{b['status']}[/{status_style}]",
            b["interval"],
            str(b["run_count"]),
            last_run,
        )

    console.print(table)
