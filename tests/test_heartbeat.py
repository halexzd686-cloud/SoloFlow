"""测试 Agent 心跳调度器。"""

from soloflow.core.heartbeat import (
    _delete_heartbeat_state,
    _format_interval,
    _is_process_running,
    _load_heartbeat_state,
    _parse_interval,
    _read_pid,
    _remove_pid,
    _save_heartbeat_state,
    _write_pid,
    list_heartbeats,
    start_heartbeat,
    stop_heartbeat,
)

# ── 已有测试: 间隔解析/格式化 ──


def test_parse_interval_seconds():
    assert _parse_interval("30s") == 30.0
    assert _parse_interval("0s") == 0.0


def test_parse_interval_minutes():
    assert _parse_interval("5m") == 300.0
    assert _parse_interval("30m") == 1800.0


def test_parse_interval_hours():
    assert _parse_interval("1h") == 3600.0
    assert _parse_interval("6h") == 21600.0


def test_parse_interval_days():
    assert _parse_interval("1d") == 86400.0


def test_parse_interval_with_space():
    assert _parse_interval("30 m") == 1800.0


def test_parse_interval_uppercase():
    assert _parse_interval("1H") == 3600.0


def test_parse_interval_invalid():
    result = _parse_interval("invalid")
    assert result == 3600.0


def test_format_interval():
    assert _format_interval(30) == "30s"
    assert _format_interval(1800) == "30m"
    assert _format_interval(3600) == "1h"
    assert _format_interval(86400) == "1d"


def test_format_interval_edge():
    assert _format_interval(59) == "59s"
    assert _format_interval(60) == "1m"
    assert _format_interval(3599) == "59m"
    assert _format_interval(3601) == "1h"


# ── 新增测试: PID 文件管理 ──


def test_pid_write_read_remove():
    """测试 PID 文件的写入、读取、删除循环。"""
    # 使用一个测试用的 name，避免与真实 heartbeat 冲突
    test_name = "_test_pid_xyz"
    _write_pid(test_name, 12345)

    pid = _read_pid(test_name)
    assert pid == 12345

    _remove_pid(test_name)
    assert _read_pid(test_name) is None


def test_read_pid_not_exists():
    """测试读取不存在的 PID 文件。"""
    assert _read_pid("_nonexistent_pid_xyz") is None


def test_is_process_running():
    """测试进程存活检查（当前进程应该在运行）。

    BUG-HB-001 回归测试：Windows 上 os.kill(pid, 0) 会杀死目标进程。
    此用例曾导致 pytest 进程被自身测试终止。修复后必须安全通过。
    """
    import os

    assert _is_process_running(os.getpid()) is True


def test_is_process_running_fake():
    """测试检查不存在的进程。"""
    # 使用一个极大的 PID，几乎不可能存在
    assert _is_process_running(99999999) is False


def test_is_process_running_child_process_lifecycle():
    """测试子进程从存活到退出的探活变化（回归 BUG-HB-001 的 Windows 误杀）。

    使用临时 subprocess 而非 pytest 自身，安全验证:
    - 存活时返回 True
    - 退出后返回 False
    """
    import subprocess
    import sys

    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        assert _is_process_running(proc.pid) is True
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    # 进程已退出，探活必须返回 False（且不抛异常、不误杀任何进程）
    assert _is_process_running(proc.pid) is False


# ── 新增测试: 心跳状态持久化 ──


def test_heartbeat_state_save_load_delete():
    """测试心跳状态的保存、加载、删除回路。"""
    test_name = "_test_state_xyz"
    state = {
        "agent_name": test_name,
        "interval": "1h",
        "run_count": 5,
        "last_run": "2026-08-07T12:00:00",
        "status": "running",
    }

    _save_heartbeat_state(test_name, state)
    loaded = _load_heartbeat_state(test_name)
    assert loaded is not None
    assert loaded["run_count"] == 5
    assert loaded["status"] == "running"

    _delete_heartbeat_state(test_name)
    assert _load_heartbeat_state(test_name) is None


def test_heartbeat_state_corrupted():
    """测试加载损坏的状态文件（应返回 None 不崩溃）。"""
    test_name = "_test_corrupt_xyz"
    from soloflow.core.heartbeat import HEARTBEAT_DIR

    HEARTBEAT_DIR.mkdir(parents=True, exist_ok=True)
    (HEARTBEAT_DIR / f"{test_name}.json").write_text("not json {{{")

    result = _load_heartbeat_state(test_name)
    assert result is None

    _delete_heartbeat_state(test_name)


# ── 新增测试: start/stop heartbeat (无 daemon) ──


def test_start_heartbeat_disabled_agent():
    """测试启用心跳被禁用的 Agent（应失败）。"""
    from soloflow.models.agent import AgentDefinition, AgentHeartbeat, AgentSoul

    agent = AgentDefinition(
        name="_test_disabled",
        description="Test agent",
        skills=["content-writer"],
        soul=AgentSoul(personality="test"),
        heartbeat=AgentHeartbeat(enabled=False, interval="1h", trigger_prompt="test"),
    )

    result = start_heartbeat(agent, daemon=False)
    assert result is False


def test_start_heartbeat_no_trigger_prompt():
    """测试启用心跳但缺少 trigger_prompt 的 Agent（应失败）。"""
    from soloflow.models.agent import AgentDefinition, AgentHeartbeat, AgentSoul

    agent = AgentDefinition(
        name="_test_no_trigger",
        description="Test agent",
        skills=["content-writer"],
        soul=AgentSoul(personality="test"),
        heartbeat=AgentHeartbeat(enabled=True, interval="1h", trigger_prompt=""),
    )

    result = start_heartbeat(agent, daemon=False)
    assert result is False


def test_stop_heartbeat_not_running():
    """测试停止未运行的心跳（应返回 False）。"""
    result = stop_heartbeat("_nonexistent_agent_xyz")
    assert result is False


# ── 新增测试: list_heartbeats ──


def test_list_heartbeats_does_not_crash():
    """测试列出心跳状态不崩溃。"""
    result = list_heartbeats()
    assert isinstance(result, list)


def test_daemon_script_is_valid_python(monkeypatch, tmp_path):
    """后台启动脚本必须可编译，并在子进程存活后才报告成功。"""
    import subprocess

    from soloflow.core import heartbeat as hb
    from soloflow.models.agent import AgentDefinition, AgentHeartbeat, AgentSoul

    captured = {}

    class FakeProcess:
        pid = 424242

        def wait(self, timeout):
            raise subprocess.TimeoutExpired("python", timeout)

    def fake_popen(command, **kwargs):
        captured["script"] = command[2]
        return FakeProcess()

    agent = AgentDefinition(
        name="daemon-probe",
        description="daemon test",
        skills=["hello-world"],
        soul=AgentSoul(personality="test"),
        heartbeat=AgentHeartbeat(enabled=True, interval="1d", trigger_prompt="probe"),
    )
    monkeypatch.setattr(hb, "HEARTBEAT_DIR", tmp_path / "heartbeats")
    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    assert hb._start_heartbeat_daemon(agent) is True
    compile(captured["script"], "<heartbeat-daemon>", "exec")


def test_list_heartbeats_reports_live_daemon(monkeypatch, tmp_path):
    """持久化状态为 running 且 PID 存活时，列表不得误报 stopped。"""
    from soloflow.core import heartbeat as hb

    monkeypatch.setattr(hb, "HEARTBEAT_DIR", tmp_path / "heartbeats")
    monkeypatch.setattr(hb, "_is_process_running", lambda pid: pid == 12345)
    hb._save_heartbeat_state(
        "live-daemon",
        {"agent_name": "live-daemon", "interval": "1d", "status": "running"},
    )
    hb._write_pid("live-daemon", 12345)

    beats = hb.list_heartbeats()

    assert beats == [
        {
            "agent_name": "live-daemon",
            "status": "running",
            "interval": "1d",
            "run_count": 0,
            "last_run": "—",
        }
    ]
