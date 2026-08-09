"""详情弹窗 Modal —— Skill 详情 + Flow 详情 + Registry 详情 + Flow 输入表单。"""

from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Static

from soloflow.tui.theme import C


class SkillDetailModal(ModalScreen[None]):
    """Skill 完整详情弹窗。"""

    DEFAULT_CSS = f"""
    SkillDetailModal {{
        align: center middle;
    }}
    SkillDetailModal > VerticalScroll {{
        width: 70%;
        height: 80%;
        background: {C["surface"]};
        border: solid {C["border"]};
        padding: 1 2;
    }}
    SkillDetailModal .modal-title {{
        color: {C["accent"]};
        text-style: bold;
        padding: 0 1;
    }}
    SkillDetailModal .modal-section {{
        color: {C["accent"]};
        text-style: bold;
        padding: 1 0 0 0;
    }}
    SkillDetailModal .modal-text {{
        color: {C["text"]};
        padding: 0 1;
    }}
    SkillDetailModal .modal-dim {{
        color: {C["text_dim"]};
        padding: 0 1;
    }}
    SkillDetailModal .modal-muted {{
        color: {C["text_muted"]};
        padding: 0 1;
    }}
    #modal-close {{
        margin: 1 0;
        width: 20;
    }}
    """

    def __init__(self, skill_data: dict) -> None:
        super().__init__()
        self.skill_data = skill_data

    def compose(self) -> ComposeResult:
        sd = self.skill_data
        name = sd.get("name", "unknown")
        version = sd.get("version", "0.1.0")
        desc = sd.get("description", "")
        tags = sd.get("tags", [])
        path = sd.get("path", "")
        stars = sd.get("stars", 0)
        calls = sd.get("calls", 0)
        iters = sd.get("iterations", 0)

        with VerticalScroll():
            yield Static(
                f"[modal-title]{name}[/modal-title]  [modal-muted]v{version}[/modal-muted]"
            )
            yield Static(f"[modal-dim]{desc}[/modal-dim]")

            if tags:
                yield Static(f"[modal-muted]Tags: {', '.join(tags)}[/modal-muted]")

            yield Static("")  # spacer

            yield Static("[modal-section]Stats[/modal-section]")
            sv = "★" * int(stars) + "☆" * (5 - int(stars))
            yield Static(f"[modal-text]{sv}    {calls:,} calls    {iters} iterations[/modal-text]")

            yield Static("[modal-section]Location[/modal-section]")
            yield Static(f"[modal-muted]{path}[/modal-muted]")

            # 尝试加载完整的 SkillFile
            try:
                from soloflow.core.skill_loader import find_skill, load_skill

                skill_name = sd.get("skill_name") or sd.get("name", "")
                skill_path = find_skill(skill_name)
                skill = load_skill(skill_path)

                if skill.costar.context:
                    yield Static("[modal-section]Context[/modal-section]")
                    yield Static(f"[modal-text]{skill.costar.context[:300]}[/modal-text]")

                if skill.costar.objective:
                    yield Static("[modal-section]Objective[/modal-section]")
                    yield Static(f"[modal-text]{skill.costar.objective[:300]}[/modal-text]")

                if skill.costar.style:
                    yield Static("[modal-section]Style[/modal-section]")
                    yield Static(f"[modal-text]{skill.costar.style[:200]}[/modal-text]")

                if skill.costar.tone:
                    yield Static("[modal-section]Tone[/modal-section]")
                    yield Static(f"[modal-text]{skill.costar.tone[:200]}[/modal-text]")

                if skill.costar.audience:
                    yield Static("[modal-section]Audience[/modal-section]")
                    yield Static(f"[modal-text]{skill.costar.audience[:200]}[/modal-text]")

                if skill.rules:
                    yield Static("[modal-section]Rules[/modal-section]")
                    for r in skill.rules[:10]:
                        yield Static(f"[modal-text]  - {r}[/modal-text]")

                yield Static("[modal-section]Instructions (body)[/modal-section]")
                body_preview = skill.body[:800]
                yield Static(
                    f"[modal-text]{body_preview}{'...' if len(skill.body) > 800 else ''}[/modal-text]"  # noqa: E501
                )

                if skill.config.model:
                    yield Static("[modal-section]LLM Config[/modal-section]")
                    yield Static(
                        f"[modal-muted]model={skill.config.model}  provider={skill.config.provider}  "  # noqa: E501
                        f"temp={skill.config.temperature}  max_tokens={skill.config.max_tokens}[/modal-muted]"  # noqa: E501
                    )

                if skill.iteration.version > 0:
                    yield Static("[modal-section]Iteration[/modal-section]")
                    score = skill.iteration.score or "—"
                    yield Static(
                        f"[modal-text]v{skill.iteration.version}  score={score}[/modal-text]"
                    )

            except Exception:
                yield Static("[modal-section]Info[/modal-section]")
                yield Static("[modal-muted]Full skill file could not be loaded.[/modal-muted]")

            yield Button("Close", variant="primary", id="modal-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "modal-close":
            self.dismiss()


class FlowDetailModal(ModalScreen[None]):
    """Flow 完整详情弹窗。"""

    DEFAULT_CSS = f"""
    FlowDetailModal {{
        align: center middle;
    }}
    FlowDetailModal > VerticalScroll {{
        width: 70%;
        height: 80%;
        background: {C["surface"]};
        border: solid {C["border"]};
        padding: 1 2;
    }}
    FlowDetailModal .modal-title {{
        color: {C["accent"]};
        text-style: bold;
        padding: 0 1;
    }}
    FlowDetailModal .modal-section {{
        color: {C["accent"]};
        text-style: bold;
        padding: 1 0 0 0;
    }}
    FlowDetailModal .modal-text {{
        color: {C["text"]};
        padding: 0 1;
    }}
    FlowDetailModal .modal-dim {{
        color: {C["text_dim"]};
        padding: 0 1;
    }}
    FlowDetailModal .modal-muted {{
        color: {C["text_muted"]};
        padding: 0 1;
    }}
    FlowDetailModal .modal-done {{
        color: {C["success"]};
    }}
    FlowDetailModal .modal-running {{
        color: {C["warning"]};
        text-style: bold;
    }}
    FlowDetailModal .modal-failed {{
        color: {C["error"]};
    }}
    FlowDetailModal .modal-skipped {{
        color: {C["text_muted"]};
    }}
    FlowDetailModal .modal-resume-hint {{
        color: {C["warning"]};
        text-style: bold;
        padding: 1 1;
    }}
    #modal-close {{
        margin: 1 0;
        width: 20;
    }}
    #modal-resume {{
        margin: 1 0;
        width: 26;
    }}
    """

    def __init__(self, flow_data: dict) -> None:
        super().__init__()
        self.flow_data = flow_data

    def compose(self) -> ComposeResult:
        fd = self.flow_data
        name = fd.get("name", "unknown")
        version = fd.get("version", "0.1.0")
        desc = fd.get("description", "")
        progress = fd.get("progress", 0)
        duration = fd.get("duration", "---")
        tokens = fd.get("tokens", "---")
        cost = fd.get("cost", "---")
        run_data = fd.get("run_data")
        run_id = fd.get("run_id", "")
        can_resume = fd.get("can_resume", False)

        with VerticalScroll():
            yield Static(
                f"[modal-title]{name}[/modal-title]  [modal-muted]v{version}[/modal-muted]"
            )
            yield Static(f"[modal-dim]{desc}[/modal-dim]")

            yield Static("")  # spacer

            # 运行概要
            yield Static("[modal-section]Run Summary[/modal-section]")
            bw = 36
            f_val = max(0, min(int(progress / 100 * bw), bw))
            bar = "▓" * f_val + "░" * (bw - f_val)
            yield Static(f"[modal-text]{bar}  {progress}%[/modal-text]")
            yield Static(f"[modal-muted]{duration}    {tokens} token    {cost}[/modal-muted]")

            # 可恢复提示
            if can_resume:
                yield Static(
                    f"[modal-resume-hint]⚠ 此 Flow 上次运行未完成 (run: {run_id[:16]}...)，可以恢复执行[/modal-resume-hint]"  # noqa: E501
                )

            # 步骤管线
            yield Static("[modal-section]Steps[/modal-section]")
            steps = fd.get("steps", [])
            for step in steps:
                sname = step.get("name", "?")
                status = step.get("status", 0)
                if status == 1:
                    yield Static(f"  [modal-done]✓ {sname} (done)[/modal-done]")
                elif status == 2:
                    yield Static(f"  [modal-running]⟳ {sname} (running)[/modal-running]")
                elif status == 3:
                    yield Static(f"  [modal-failed]✗ {sname} (failed)[/modal-failed]")
                else:
                    yield Static(f"  [modal-skipped]○ {sname} (pending)[/modal-skipped]")

            # Flow 定义详情
            flow_def = fd.get("flow_definition")
            if flow_def:
                try:
                    from soloflow.core.flow_engine import _topological_sort

                    yield Static("[modal-section]DAG Levels[/modal-section]")
                    levels = _topological_sort(flow_def.steps)
                    for i, level in enumerate(levels, 1):
                        yield Static(f"[modal-dim]  Level {i}: {' | '.join(level)}[/modal-dim]")

                    yield Static("[modal-section]Step Details[/modal-section]")
                    for step in flow_def.steps:
                        skill_info = step.skill
                        if step.agent:
                            skill_info += f" (agent: {step.agent})"
                        deps = ", ".join(step.depends_on) if step.depends_on else "none"
                        yield Static(
                            f"[modal-text]{step.id}:[/modal-text] "
                            f"[modal-dim]{skill_info}  ← deps: {deps}[/modal-dim]"
                        )
                        if step.description:
                            yield Static(f"[modal-muted]    {step.description[:80]}[/modal-muted]")
                except Exception:
                    pass

            # 运行日志（最近一次）
            if run_data:
                yield Static("[modal-section]Last Run Log[/modal-section]")
                run_status = run_data.get("status", "?")
                yield Static(f"[modal-dim]Status: {run_status}[/modal-dim]")
                for sid, sr in run_data.get("steps", {}).items():
                    s_status = sr.get("status", "?")
                    s_dur = sr.get("duration", 0)
                    s_err = sr.get("error", "")
                    line = f"  {sid}: {s_status} ({s_dur:.1f}s)"
                    if s_err:
                        line += f" — {s_err[:60]}"
                    yield Static(f"[modal-muted]{line}[/modal-muted]")

            # 操作按钮
            if can_resume:
                yield Button("Resume Flow", variant="warning", id="modal-resume")
            yield Button("Close", variant="primary", id="modal-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "modal-close":
            self.dismiss()
        elif event.button.id == "modal-resume":
            run_id = self.flow_data.get("run_id", "")
            flow_name = self.flow_data.get("name", "")
            self.post_message(FlowResumeRequest(run_id, flow_name))
            self.dismiss()


class FlowResumeRequest(Static):
    """Flow 恢复请求消息 —— 从 FlowDetailModal 传到 SoloFlowApp。"""

    def __init__(self, run_id: str, flow_name: str) -> None:
        self.run_id = run_id
        self.flow_name = flow_name
        super().__init__()


class RegistryDetailModal(ModalScreen[None]):
    """Registry 条目详情弹窗。"""

    DEFAULT_CSS = f"""
    RegistryDetailModal {{
        align: center middle;
    }}
    RegistryDetailModal > Vertical {{
        width: 50%;
        height: auto;
        max-height: 60%;
        background: {C["surface"]};
        border: solid {C["border"]};
        padding: 2 3;
    }}
    RegistryDetailModal .modal-title {{
        color: {C["accent"]};
        text-style: bold;
        padding: 0 1;
    }}
    RegistryDetailModal .modal-section {{
        color: {C["accent"]};
        text-style: bold;
        padding: 1 0 0 0;
    }}
    RegistryDetailModal .modal-text {{
        color: {C["text"]};
        padding: 0 1;
    }}
    RegistryDetailModal .modal-dim {{
        color: {C["text_dim"]};
        padding: 0 1;
    }}
    #modal-close {{
        margin: 1 0;
        width: 20;
    }}
    """

    def __init__(self, entry_data: dict) -> None:
        super().__init__()
        self.entry_data = entry_data

    def compose(self) -> ComposeResult:
        ed = self.entry_data
        name = ed.get("name", "unknown")
        downloads = ed.get("downloads", 0)
        is_new = ed.get("is_new", False)

        with Vertical():
            yield Static(f"[modal-title]{name}[/modal-title]")
            if is_new:
                yield Static("[modal-dim]🆕 New arrival[/modal-dim]")
            yield Static("[modal-section]Downloads[/modal-section]")
            yield Static(f"[modal-text]{downloads:,}[/modal-text]")
            yield Static("[modal-section]Install[/modal-section]")
            yield Static(f"[modal-dim]sf registry install {name}[/modal-dim]")
            yield Button("Close", variant="primary", id="modal-close")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "modal-close":
            self.dismiss()


class FlowInputModal(ModalScreen[dict]):
    """Flow 输入表单 Modal（BUG-TUI-001 修复）。

    根据 flow.input_schema 动态生成输入字段：
    - 展示字段说明、必填状态、类型
    - 默认值预填
    - 提交后返回 {key: value} 字典
    """

    DEFAULT_CSS = f"""
    FlowInputModal {{
        align: center middle;
    }}
    FlowInputModal > Vertical {{
        width: 60;
        height: auto;
        max-height: 90%;
        background: {C["surface"]};
        border: solid {C["border"]};
        padding: 1 2;
    }}
    FlowInputModal .modal-title {{
        color: {C["accent"]};
        text-style: bold;
        padding: 0 1;
    }}
    FlowInputModal .modal-dim {{
        color: {C["text_dim"]};
        padding: 0 1;
    }}
    FlowInputModal .input-label {{
        color: {C["text"]};
        padding: 1 1 0 1;
    }}
    FlowInputModal .input-required {{
        color: {C["error"]};
    }}
    FlowInputModal Input {{
        margin: 0 1;
    }}
    FlowInputModal #modal-run {{
        margin: 1 0 0 1;
        width: 16;
    }}
    FlowInputModal #modal-cancel {{
        margin: 1 0 0 1;
        width: 16;
    }}
    """

    def __init__(self, flow_name: str, input_schema: dict) -> None:
        super().__init__()
        self.flow_name = flow_name
        self.input_schema = input_schema or {}

    def compose(self) -> ComposeResult:
        yield Static(f"[modal-title]Run Flow: {self.flow_name}[/modal-title]")
        with Vertical():
            if not self.input_schema:
                yield Static("[modal-dim]此 Flow 无需输入参数[/modal-dim]")
            for key, spec in self.input_schema.items():
                if not isinstance(spec, dict):
                    spec = {}
                label = spec.get("description", key)
                required = spec.get("required", False)
                req_mark = " *" if required else ""
                yield Static(
                    f"[input-label]{label}[/input-label]"
                    f"[input-required]{req_mark}[/input-required]"
                    f" [modal-dim]({key}, {spec.get('type', 'string')})[/modal-dim]"
                )
                default = spec.get("default", "")
                yield Input(
                    value=str(default) if default is not None else "",
                    placeholder=key,
                    id=f"input-{key}",
                )
            yield Static("")  # spacer
            yield Button("Run", variant="primary", id="modal-run")
            yield Button("Cancel", variant="default", id="modal-cancel")

    def _collect_inputs(self) -> dict:
        """收集表单值。

        P2-006 修复: 与 CLI 共用 parse_input_value（支持 array、
        非法 boolean 不再静默变 False），行为一致。
        未填写的字段不提交（引擎使用默认值）。
        """
        from soloflow.core.flow_engine import parse_input_value

        inputs = {}
        for key, spec in self.input_schema.items():
            widget = self.query_one(f"#input-{key}", Input)
            value = widget.value.strip()
            if value == "":
                continue  # 未填写的字段不提交
            try:
                inputs[key] = parse_input_value(value, spec)
            except ValueError:
                inputs[key] = value  # 转换失败保留字符串，交给引擎校验报错
        return inputs

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "modal-run":
            self.dismiss(self._collect_inputs())
        elif event.button.id == "modal-cancel":
            self.dismiss(None)
