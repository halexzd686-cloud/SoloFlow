"""Flow 面板 —— 右上，展示 Flow 列表及运行状态。"""

import json
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import Static

from soloflow.core.flow_engine import load_flow
from soloflow.tui.theme import C

FLOWS_DIR = Path("flows")
RUNS_DIR = Path(".soloflow/runs")


def _load_recent_runs() -> dict[str, dict]:
    """加载最近的 Flow 运行状态。"""
    runs: dict[str, dict] = {}
    if not RUNS_DIR.is_dir():
        return runs

    for run_file in sorted(RUNS_DIR.glob("run-*.json"), reverse=True):
        try:
            data = json.loads(run_file.read_text(encoding="utf-8"))
            flow_name = data.get("flow_name", "")
            if flow_name and flow_name not in runs:
                runs[flow_name] = data
        except (json.JSONDecodeError, KeyError):
            continue
    return runs


def _load_flows() -> list[dict]:
    """从 flows/ 目录加载真实 Flow 定义并合并运行状态。"""
    if not FLOWS_DIR.is_dir():
        return []

    recent_runs = _load_recent_runs()
    results = []

    for flow_file in sorted(FLOWS_DIR.glob("*.flow.y*ml")):
        try:
            flow = load_flow(flow_file)
        except Exception:
            continue

        run_state = recent_runs.get(flow.name)

        # 构建步骤状态列表
        steps_status = []
        for step in flow.steps:
            status = 0
            if run_state:
                step_result = run_state.get("steps", {}).get(step.id)
                if step_result:
                    if step_result.get("status") == "done":
                        status = 1
                    elif step_result.get("status") == "running":
                        status = 2
                    elif step_result.get("status") == "failed":
                        status = 3
            steps_status.append({"name": step.id, "status": status})

        # 计算进度
        if run_state:
            total_steps = len(flow.steps)
            done_steps = sum(
                1 for sr in run_state.get("steps", {}).values() if sr.get("status") == "done"
            )
            progress = int(done_steps / total_steps * 100) if total_steps > 0 else 0
            duration = f"{run_state.get('total_duration', 0):.1f}s"
            tokens = f"{run_state.get('total_tokens', 0):,}"
            cost = f"{run_state.get('total_tokens', 0) * 0.000002:.2f}"
        else:
            progress = 0
            duration = "---"
            tokens = "---"
            cost = "---"

        # 获取 run_id 以便恢复
        run_id = run_state.get("run_id", "") if run_state else ""

        # 判断是否有可恢复的运行（failed/partial 状态）
        can_resume = bool(run_state and run_state.get("status") in ("failed", "partial") and run_id)

        results.append(
            {
                "name": flow.name,
                "version": flow.version,
                "description": flow.description,
                "steps": steps_status,
                "progress": progress,
                "duration": duration,
                "tokens": tokens,
                "cost": cost,
                "flow_definition": flow,
                "run_data": run_state,
                "run_id": run_id,
                "can_resume": can_resume,
            }
        )

    return results


class FlowStatusCard(Static):
    """Flow 状态卡片 —— 可聚焦，Enter 弹出详情。"""

    can_focus = True

    class DetailRequest(Message):
        """Enter 时向上发送详情请求。"""

        def __init__(self, flow_data: dict) -> None:
            self.flow_data = flow_data
            super().__init__()

    DEFAULT_CSS = f"""
    FlowStatusCard {{
        background: {C["surface"]};
        border: solid {C["border"]};
        padding: 1 2;
        margin: 1 1;
        height: 5;
    }}
    FlowStatusCard:hover {{ border: solid {C["border_focus"]}; }}
    FlowStatusCard:focus {{ border: solid {C["accent"]}; background: {C["highlight"]}; }}
    FlowStatusCard .flow-name {{ color: {C["text"]}; text-style: bold; }}
    FlowStatusCard .flow-pipeline {{ color: {C["text_dim"]}; padding: 0 1; }}
    FlowStatusCard .flow-done {{ color: {C["success"]}; }}
    FlowStatusCard .flow-running {{ color: {C["warning"]}; text-style: bold; }}
    FlowStatusCard .flow-failed {{ color: {C["error"]}; }}
    FlowStatusCard .flow-pending {{ color: {C["text_muted"]}; }}
    FlowStatusCard .flow-bar {{ color: {C["success"]}; padding: 0 1; }}
    FlowStatusCard .flow-meta {{ color: {C["text_muted"]}; padding: 0 1; }}
    """

    BINDINGS = [
        Binding("enter", "show_detail", "Detail", show=False),
    ]

    def __init__(self, flow_data: dict):
        super().__init__()
        self.flow_data = flow_data
        self.fname = flow_data.get("name", "")
        self.fsteps = flow_data.get("steps", [])
        self.fprogress = flow_data.get("progress", 0)
        self.fduration = flow_data.get("duration", "")
        self.ftokens = flow_data.get("tokens", "")
        self.fcost = flow_data.get("cost", "")

    def on_mount(self) -> None:
        can_resume = self.flow_data.get("can_resume", False)
        resume_marker = " [flow-failed]◀[/flow-failed]" if can_resume else ""
        parts = []
        for i, s in enumerate(self.fsteps):
            status = s.get("status", 0)
            n = s.get("name", "?")
            if status == 1:
                parts.append(f"[flow-done]{n}[/flow-done]")
            elif status == 2:
                parts.append(f"[flow-running]{n}[/flow-running]")
            elif status == 3:
                parts.append(f"[flow-failed]{n}[/flow-failed]")
            else:
                parts.append(f"[flow-pending]{n}[/flow-pending]")
            if i < len(self.fsteps) - 1:
                parts.append("[flow-pending]--[/flow-pending]")
        pipeline = "".join(parts)
        bw = 36
        f = max(0, min(int(self.fprogress / 100 * bw), bw))
        bar = "▓" * f + "░" * (bw - f)
        self.update(
            f"[flow-name]{self.fname}{resume_marker}[/flow-name]\n"
            f" [flow-pipeline]{pipeline}[/flow-pipeline]\n"
            f" [flow-bar]{bar}  {self.fprogress}%[/flow-bar]\n"
            f" [flow-meta]{self.fduration}    {self.ftokens} token    {self.fcost}[/flow-meta]"
        )

    def action_show_detail(self) -> None:
        self.post_message(self.DetailRequest(self.flow_data))


class FlowPanel(VerticalScroll):
    """Flow 列表面板 —— ↑↓ 导航 + R 运行。"""

    class RunRequest(Message):
        """R 键触发运行请求。"""

        def __init__(self, flow_name: str) -> None:
            self.flow_name = flow_name
            super().__init__()

    BINDINGS = [
        Binding("up", "cursor_up", show=False),
        Binding("down", "cursor_down", show=False),
        Binding("r", "run_selected", "Run Flow", show=False),
    ]

    DEFAULT_CSS = f"""
    FlowPanel {{
        background: {C["bg"]};
        padding: 0 1;
    }}
    FlowPanel .panel-title {{
        color: {C["accent"]};
        text-style: bold;
        padding: 1 2;
        height: 3;
    }}
    FlowPanel .panel-subtitle {{
        color: {C["text_muted"]};
        padding: 0 2;
    }}
    """

    def compose(self) -> ComposeResult:
        yield Static("[panel-title]|  Flows[/panel-title]")
        yield Static("[panel-subtitle]flowの流れ[/panel-subtitle]")
        flows = _load_flows()
        for f in flows:
            yield FlowStatusCard(f)
        if not flows:
            yield Static("[flow-pending]  実行中の Flow はありません[/flow-pending]")

    def on_focus(self) -> None:
        """面板获得焦点时自动聚焦第一个卡片。"""
        cards = self._get_cards()
        if cards:
            cards[0].focus()

    def _get_cards(self) -> list[FlowStatusCard]:
        return list(self.query(FlowStatusCard))

    def action_cursor_up(self) -> None:
        cards = self._get_cards()
        if not cards:
            return
        focused = self.screen.focused
        if focused in cards:
            idx = cards.index(focused)
            if idx > 0:
                cards[idx - 1].focus()
        else:
            cards[-1].focus()

    def action_cursor_down(self) -> None:
        cards = self._get_cards()
        if not cards:
            return
        focused = self.screen.focused
        if focused in cards:
            idx = cards.index(focused)
            if idx < len(cards) - 1:
                cards[idx + 1].focus()
        else:
            cards[0].focus()

    def action_run_selected(self) -> None:
        """R 键：触发当前聚焦 Flow 的运行。"""
        focused = self.screen.focused
        if isinstance(focused, FlowStatusCard):
            flow_name = focused.flow_data.get("name", "")
            self.post_message(self.RunRequest(flow_name))

    def refresh_flows(self) -> None:
        """刷新 Flow 列表，保留焦点。"""
        previously_focused = self.screen.focused
        focused_name = None
        if isinstance(previously_focused, FlowStatusCard):
            focused_name = previously_focused.flow_data.get("name")

        # 移除旧卡片
        for child in list(self.query(FlowStatusCard)):
            child.remove()

        # 重新挂载
        for f in _load_flows():
            self.mount(FlowStatusCard(f))

        # 恢复焦点
        if focused_name:
            for card in self.query(FlowStatusCard):
                if isinstance(card, FlowStatusCard) and card.flow_data.get("name") == focused_name:
                    card.focus()
                    break
