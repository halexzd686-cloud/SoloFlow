"""SoloFlow TUI 主应用 —— 侘寂风仪表盘。"""

import logging
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Static

from soloflow import __version__
from soloflow.tui.modals import (
    FlowDetailModal,
    FlowInputModal,
    FlowResumeRequest,
    RegistryDetailModal,
    SkillDetailModal,
)
from soloflow.tui.theme import C, build_css
from soloflow.tui.widgets.flow_panel import FlowPanel, FlowStatusCard
from soloflow.tui.widgets.header_bar import HeaderBar
from soloflow.tui.widgets.registry_panel import RegistryItem, RegistryPanel
from soloflow.tui.widgets.skill_panel import SkillCard, SkillPanel

# GAP-TUI-003: 不再用 except: pass 静默吞异常，记录 debug log 便于排查
logger = logging.getLogger("soloflow.tui")


class SoloFlowApp(App):
    """SoloFlow Dashboard —— 侘寂 TUI。"""

    TITLE = "SoloFlow"
    SUB_TITLE = f"v{__version__}"

    # 布局断点（终端行数）
    BREAKPOINT_LARGE = 40  # >40 行：大屏，60/40 分割
    BREAKPOINT_MEDIUM = 28  # 28-40 行：中屏，75/25 分割
    # <28 行：小屏，Registry 可折叠

    _collapsed_registry: bool = False
    _current_rows: int = 0

    CSS = (
        build_css()
        + f"""
    #main-layout {{
        width: 1fr;
        height: 1fr;
    }}

    #left-column {{
        width: 1fr;
        min-width: 30;
        border-right: solid {C["divider"]};
        overflow-y: auto;
    }}

    #right-column {{
        width: 1fr;
        min-width: 30;
    }}

    #flows-section {{
        height: 3fr;
        min-height: 6;
        overflow-y: auto;
    }}

    #flows-section.expanded {{
        height: 1fr;
    }}

    #registry-section {{
        height: 2fr;
        min-height: 4;
        border-top: solid {C["divider"]};
        overflow-y: auto;
    }}

    #registry-section.collapsed {{
        height: 0;
        min-height: 0;
        display: none;
    }}

    #nav-bar {{
        dock: bottom;
        height: 3;
        background: {C["surface"]};
        padding: 0 1;
        border-top: solid {C["border"]};
    }}

    .nav-label {{
        color: {C["text_dim"]};
        padding: 0 1;
    }}

    .nav-key {{
        color: {C["accent"]};
        text-style: bold;
    }}
    """
    )

    BINDINGS = [
        Binding("r", "run_flow", "Run"),
        Binding("s", "focus_skills", "Skills"),
        Binding("f", "focus_flows", "Flows"),
        Binding("g", "focus_registry", "Registry"),
        Binding("slash", "search", "Search"),
        Binding("tab", "toggle_registry", "Fold", show=False),
        Binding("enter", "show_detail", "Detail", show=False),
        Binding("q", "quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield HeaderBar()
        with Horizontal(id="main-layout"):
            yield SkillPanel(id="left-column")
            with Vertical(id="right-column"):
                yield FlowPanel(id="flows-section")
                yield RegistryPanel(id="registry-section")
        with Horizontal(id="nav-bar"):
            for key, label in [
                ("s", "Skills"),
                ("f", "Flows"),
                ("g", "Registry"),
                ("tab", "Fold"),
                ("r", "Run"),
                ("enter", "Detail"),
                ("/", "Search"),
                ("q", "Quit"),
            ]:
                yield Static(f"[nav-key]{key}[/nav-key][nav-label]{label}[/nav-label]")

    def on_mount(self) -> None:
        """启动定时刷新——每 2 秒刷新 Flow 面板和 Header 状态。"""
        self.set_interval(2.0, self._refresh_dashboard)
        # 初始化布局
        self._apply_layout(self.size.height)

    def on_resize(self, event) -> None:
        """终端大小变化时自适应布局。"""
        rows = event.size.height
        if rows != self._current_rows:
            self._current_rows = rows
            self._apply_layout(rows)

    def _apply_layout(self, rows: int) -> None:
        """根据终端高度应用布局策略。

        - >= 40 行 (大屏): Flows 3fr / Registry 2fr (60/40)
        - 28-39 行 (中屏): Flows 4fr / Registry 1fr (80/20)
        - < 28 行 (小屏): 自动折叠 Registry
        """
        try:
            flows = self.query_one("#flows-section")
            registry = self.query_one("#registry-section")
        except Exception:
            return  # compose 阶段还未就绪

        if rows >= self.BREAKPOINT_LARGE:
            # 大屏：标准 60/40
            flows.styles.height = "3fr"
            registry.styles.height = "2fr"
            flows.remove_class("expanded")
            if self._collapsed_registry:
                # 用户之前手动折叠 → 尊重选择，但重置 fr
                registry.styles.height = "2fr"
            else:
                registry.remove_class("collapsed")
                registry.styles.height = "2fr"
        elif rows >= self.BREAKPOINT_MEDIUM:
            # 中屏：优先 Flows 75/25
            flows.styles.height = "3fr"
            registry.styles.height = "1fr"
            flows.remove_class("expanded")
            if self._collapsed_registry:
                registry.styles.height = "1fr"
            else:
                registry.remove_class("collapsed")
                registry.styles.height = "1fr"
        else:
            # 小屏：自动折叠 Registry
            flows.add_class("expanded")
            registry.add_class("collapsed")
            self._collapsed_registry = True

    def action_toggle_registry(self) -> None:
        """Tab 键：折叠/展开 Registry 面板。"""
        try:
            registry = self.query_one("#registry-section")
            flows = self.query_one("#flows-section")
        except Exception:
            return

        if self._collapsed_registry:
            # 展开：恢复到当前断点对应的比例
            rows = self.size.height
            if rows >= self.BREAKPOINT_LARGE:
                registry.styles.height = "2fr"
            else:
                registry.styles.height = "1fr"
            registry.remove_class("collapsed")
            flows.remove_class("expanded")
            self._collapsed_registry = False
            self.notify("Registry 面板已展开", title="Layout")
        else:
            # 折叠
            flows.add_class("expanded")
            registry.add_class("collapsed")
            self._collapsed_registry = True
            self.notify("Registry 面板已折叠 (Tab 恢复)", title="Layout")

    def _refresh_dashboard(self) -> None:
        """刷新仪表盘各面板。"""
        try:
            flow_panel = self.query_one("#flows-section", FlowPanel)
            flow_panel.refresh_flows()
        except Exception as e:  # GAP-TUI-003: 记录而不是静默
            logger.debug("refresh flows failed: %s", e)

        try:
            header = self.query_one(HeaderBar)
            header.refresh_stats()
        except Exception as e:
            logger.debug("refresh header failed: %s", e)

    # ── 焦点导航 ──

    def action_focus_skills(self) -> None:
        """s 键：聚焦 Skills 面板，自动选中第一个卡片。"""
        try:
            panel = self.query_one("#left-column", SkillPanel)
            panel.focus()
        except Exception as e:
            logger.debug("focus skills failed: %s", e)

    def action_focus_flows(self) -> None:
        """f 键：聚焦 Flows 面板，自动选中第一个卡片。"""
        try:
            panel = self.query_one("#flows-section", FlowPanel)
            panel.focus()
        except Exception as e:
            logger.debug("focus flows failed: %s", e)

    def action_focus_registry(self) -> None:
        """g 键：聚焦 Registry 面板，自动选中第一个条目。"""
        try:
            panel = self.query_one("#registry-section", RegistryPanel)
            panel.focus()
        except Exception as e:
            logger.debug("focus registry failed: %s", e)

    # ── Enter: 详情弹窗 ──

    def action_show_detail(self) -> None:
        """Enter 键：根据当前焦点 widget 类型弹出对应 Modal。"""
        focused = self.screen.focused

        if isinstance(focused, SkillCard):
            self.push_screen(SkillDetailModal(focused.skill_data))
        elif isinstance(focused, FlowStatusCard):
            self.push_screen(FlowDetailModal(focused.flow_data))
        elif isinstance(focused, RegistryItem):
            self.push_screen(RegistryDetailModal(focused.entry_data))

    # ── 消息处理：卡片内部 Enter 也会发出 DetailRequest ──

    def on_skill_card_detail_request(self, event: SkillCard.DetailRequest) -> None:
        event.stop()
        self.push_screen(SkillDetailModal(event.skill_data))

    def on_flow_status_card_detail_request(self, event: FlowStatusCard.DetailRequest) -> None:
        event.stop()
        self.push_screen(FlowDetailModal(event.flow_data))

    def on_registry_item_detail_request(self, event: RegistryItem.DetailRequest) -> None:
        event.stop()
        self.push_screen(RegistryDetailModal(event.entry_data))

    # ── R: 运行 Flow ──

    def action_run_flow(self) -> None:
        """R 键：运行当前聚焦的 Flow。"""
        focused = self.screen.focused
        if isinstance(focused, FlowStatusCard):
            flow_name = focused.flow_data.get("name", "")
            if flow_name:
                self._execute_flow(flow_name)
        else:
            self.notify("聚焦 Flow 卡片后按 R 运行", title="Run Flow")

    def on_flow_panel_run_request(self, event: FlowPanel.RunRequest) -> None:
        event.stop()
        flow_name = event.flow_name
        if flow_name:
            self._execute_flow(flow_name)

    def _execute_flow(self, flow_name: str) -> None:
        """执行 Flow。

        BUG-TUI-001/P1-001 修复: 只要 Flow 定义了 input_schema（含可选字段），
        就弹出动态输入表单让用户填写/确认输入；无 schema 直接运行。
        回调通过 closure 绑定 flow_name/flow_path，避免共享字段被并发覆盖。
        """
        flow_path = Path("flows") / f"{flow_name}.flow.yml"
        if not flow_path.exists():
            self.notify(f"Flow 文件不存在: {flow_path}", title="Error", severity="error")
            return

        try:
            from soloflow.core.flow_engine import load_flow

            flow = load_flow(flow_path)
        except Exception as e:
            logger.debug("load flow failed: %s", e)
            self.notify(f"Flow 加载失败: {e}", title="Error", severity="error")
            return

        # P2-006: schema 非空即弹表单（可选字段也能覆盖默认值）
        if flow.input_schema:
            self.push_screen(
                FlowInputModal(flow_name, flow.input_schema),
                # P1-001 修复: closure 绑定名称和路径，不用共享实例字段
                lambda result, _name=flow_name, _path=flow_path: self._handle_flow_input(
                    _name, _path, result
                ),
            )
            return

        self._start_flow_worker(flow_name, flow_path, inputs={})

    def _handle_flow_input(self, flow_name: str, flow_path: Path, result) -> None:
        """FlowInputModal 回调：result 为 dict 或 None（取消）。"""
        if result is None:
            self.notify("已取消运行 Flow", title="Run Flow")
            return
        self._start_flow_worker(flow_name, flow_path, inputs=result or {})

    def _start_flow_worker(self, flow_name: str, flow_path: Path, inputs: dict) -> None:
        """启动 Flow 执行 Worker（含输入参数）。"""
        self.notify(f"Running flow: {flow_name}...", title="Run Flow")
        self.run_worker(
            self._run_flow_worker(flow_name, flow_path, inputs),
            exclusive=False,
        )

    async def _run_flow_worker(self, flow_name: str, flow_path: Path, inputs: dict) -> None:
        """Worker: 在独立线程中运行 Flow 引擎。"""
        import asyncio as _asyncio

        from soloflow.core.flow_engine import load_flow, run_flow

        def _run():
            try:
                flow = load_flow(flow_path)
                run_flow(flow, inputs=inputs or {})
            except Exception as e:
                self.notify(str(e), title="Flow Error", severity="error")

        loop = _asyncio.get_running_loop()
        await loop.run_in_executor(None, _run)

    # ── Flow Resume ──

    def on_flow_resume_request(self, event: FlowResumeRequest) -> None:
        """处理来自 FlowDetailModal 的恢复请求。"""
        event.stop()
        run_id = event.run_id
        flow_name = event.flow_name
        self.notify(f"Resuming flow: {flow_name}...", title="Resume Flow")
        self.run_worker(self._resume_flow_worker(run_id, flow_name), exclusive=False)

    async def _resume_flow_worker(self, run_id: str, flow_name: str) -> None:
        """Worker: 在独立线程中恢复 Flow 执行。"""
        import asyncio as _asyncio

        from soloflow.core.flow_engine import resume_flow

        def _run():
            try:
                result = resume_flow(run_id)
                if result is None:
                    self.notify(
                        f"Flow '{flow_name}' 无可恢复的步骤", title="Resume", severity="warning"
                    )
                else:
                    self.notify(f"Flow '{flow_name}' 恢复执行完成", title="Resume")
            except Exception as e:
                self.notify(str(e), title="Resume Error", severity="error")

        loop = _asyncio.get_running_loop()
        await loop.run_in_executor(None, _run)

    # ── /: 搜索 ──

    def action_search(self) -> None:
        """/ 键：触发 Registry 搜索。"""
        try:
            panel = self.query_one("#registry-section", RegistryPanel)
            panel.focus()
            panel.action_start_search()
        except Exception:
            self.notify("Registry panel not available", title="Search")
