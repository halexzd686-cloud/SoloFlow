"""TUI 仪表盘自动化测试（GAP-TUI-002）。

使用 Textual 的 run_test 无头模式，验证:
- 启动无 CSS 错误
- 面板渲染 / 键盘导航
- Flow 输入表单（BUG-TUI-001）
- 布局折叠
"""

import pytest


@pytest.mark.asyncio
async def test_tui_starts_without_errors():
    """GAP-TUI-002: 启动无异常、无 CSS 错误。"""
    from soloflow.tui.app import SoloFlowApp

    app = SoloFlowApp()
    async with app.run_test(size=(120, 40)) as pilot:
        # 主界面元素存在
        assert app.query_one("#main-layout") is not None
        assert app.query_one("#flows-section") is not None
        assert app.query_one("#registry-section") is not None
        await pilot.pause()


@pytest.mark.asyncio
async def test_tui_focus_navigation():
    """GAP-TUI-002: s/f/g 键切换面板焦点。"""
    from soloflow.tui.app import SoloFlowApp

    app = SoloFlowApp()
    async with app.run_test(size=(120, 40)) as pilot:
        # 按 s 聚焦 Skills
        await pilot.press("s")
        await pilot.pause()
        assert app.screen.focused is not None

        # 按 f 聚焦 Flows
        await pilot.press("f")
        await pilot.pause()
        assert app.screen.focused is not None

        # 按 g 聚焦 Registry
        await pilot.press("g")
        await pilot.pause()
        assert app.screen.focused is not None


@pytest.mark.asyncio
async def test_tui_flow_input_modal_opens():
    """BUG-TUI-001: 含必填输入的 Flow 会弹出输入表单。"""
    import tempfile
    from pathlib import Path

    from soloflow.tui.app import SoloFlowApp

    # 构造一个带必填输入的临时 Flow
    with tempfile.TemporaryDirectory() as tmp:
        import os

        import yaml

        orig = os.getcwd()
        os.chdir(tmp)
        try:
            Path("flows").mkdir()
            (Path("flows") / "needs-input.flow.yml").write_text(
                yaml.dump(
                    {
                        "name": "needs-input",
                        "version": "1.0.0",
                        "description": "Flow with required input",
                        "input_schema": {
                            "topic": {"type": "string", "required": True, "description": "主题"},
                        },
                        "steps": [{"id": "a", "skill": "content-writer"}],
                    },
                    allow_unicode=True,
                ),
                encoding="utf-8",
            )

            app = SoloFlowApp()
            # P1-001 修复: 纯交互测试必须 mock worker，否则点击 Run 会启动真实
            # Flow worker（chdir 到 tmp 后找不到 content-writer）→ "Unexpected error"
            # 被吞掉造成假绿。worker 参数断言由 test_tui_flow_input_passes_correct_args 覆盖。
            from unittest.mock import patch

            from textual.widgets import Input

            from soloflow.tui.modals import FlowInputModal

            async with app.run_test(size=(120, 40)) as pilot:
                with patch.object(app, "_start_flow_worker"):
                    # 直接触发 _execute_flow → 应弹出 FlowInputModal
                    app._execute_flow("needs-input")
                    await pilot.pause()
                    await pilot.pause()

                    # push_screen 后当前 screen 就是 FlowInputModal 本身
                    assert isinstance(app.screen, FlowInputModal)

                    # 表单字段存在
                    topic_input = app.screen.query_one("#input-topic", Input)
                    topic_input.value = "AI 测试"
                    await pilot.pause()

                    # 点击 Run 按钮提交（modal 关闭，返回主界面）
                    await pilot.click("#modal-run")
                    await pilot.pause()
                    await pilot.pause()
                    assert not isinstance(app.screen, FlowInputModal)
        finally:
            os.chdir(orig)


@pytest.mark.asyncio
async def test_tui_flow_input_passes_correct_args():
    """P1-001 回归: 输入 Modal 提交后 Worker 收到正确的 flow name/path/inputs。

    不再只断言 Modal 关闭——必须验证 _start_flow_worker 的调用参数。
    """
    import tempfile
    from pathlib import Path
    from unittest.mock import patch

    import yaml

    from soloflow.tui.app import SoloFlowApp

    with tempfile.TemporaryDirectory() as tmp:
        import os

        orig = os.getcwd()
        os.chdir(tmp)
        try:
            Path("flows").mkdir()
            (Path("flows") / "needs-input.flow.yml").write_text(
                yaml.dump(
                    {
                        "name": "needs-input",
                        "version": "1.0.0",
                        "description": "Flow with required input",
                        "input_schema": {
                            "topic": {"type": "string", "required": True, "description": "主题"},
                            "count": {"type": "integer", "default": 3},
                        },
                        "steps": [{"id": "a", "skill": "content-writer"}],
                    },
                    allow_unicode=True,
                ),
                encoding="utf-8",
            )

            app = SoloFlowApp()
            captured = []

            with patch.object(
                app,
                "_start_flow_worker",
                side_effect=lambda *a, **kw: captured.append((a, kw)),
            ):
                async with app.run_test(size=(120, 40)) as pilot:
                    app._execute_flow("needs-input")
                    await pilot.pause()
                    await pilot.pause()

                    from textual.widgets import Input

                    # 填写 topic（integer count 留空走默认值）
                    topic_input = app.screen.query_one("#input-topic", Input)
                    topic_input.value = "AI 测试"
                    await pilot.pause()

                    await pilot.click("#modal-run")
                    await pilot.pause()
                    await pilot.pause()

            # P1-001: 必须恰好调用一次，且参数正确
            assert len(captured) == 1, f"_start_flow_worker 应被调用 1 次，实际 {len(captured)}"
            (args, kwargs) = captured[0]
            assert args[0] == "needs-input"
            assert args[1] == Path("flows") / "needs-input.flow.yml"
            # count 默认值 3 预填后一并提交（integer 类型转换生效）
            assert kwargs["inputs"] == {"topic": "AI 测试", "count": 3}
        finally:
            os.chdir(orig)


@pytest.mark.asyncio
async def test_tui_flow_optional_schema_opens_modal():
    """P2-006: 只有可选字段的 Flow 也弹出输入表单（可覆盖默认值）。"""
    import tempfile
    from pathlib import Path

    import yaml

    from soloflow.tui.app import SoloFlowApp

    with tempfile.TemporaryDirectory() as tmp:
        import os

        orig = os.getcwd()
        os.chdir(tmp)
        try:
            Path("flows").mkdir()
            (Path("flows") / "optional-only.flow.yml").write_text(
                yaml.dump(
                    {
                        "name": "optional-only",
                        "version": "1.0.0",
                        "description": "Flow with only optional inputs",
                        "input_schema": {
                            "style": {"type": "string", "default": "professional"},
                        },
                        "steps": [{"id": "a", "skill": "content-writer"}],
                    },
                    allow_unicode=True,
                ),
                encoding="utf-8",
            )

            app = SoloFlowApp()
            async with app.run_test(size=(120, 40)) as pilot:
                app._execute_flow("optional-only")
                await pilot.pause()
                await pilot.pause()

                from soloflow.tui.modals import FlowInputModal

                assert isinstance(app.screen, FlowInputModal)
        finally:
            os.chdir(orig)


@pytest.mark.asyncio
async def test_tui_tab_folds_registry():
    """GAP-TUI-002: Tab 键折叠/展开 Registry 面板。

    Tab 同时也是 Textual 默认的焦点循环键，测试直接调用 action
    验证折叠逻辑（按键绑定由 Binding 声明保证）。
    """
    from soloflow.tui.app import SoloFlowApp

    app = SoloFlowApp()
    async with app.run_test(size=(120, 40)) as pilot:
        registry = app.query_one("#registry-section")
        assert not app._collapsed_registry

        # 触发 Tab 绑定的 action
        app.action_toggle_registry()
        await pilot.pause()
        assert app._collapsed_registry is True
        assert "collapsed" in registry.classes

        app.action_toggle_registry()
        await pilot.pause()
        assert app._collapsed_registry is False
        assert "collapsed" not in registry.classes


@pytest.mark.asyncio
async def test_tui_resize_small_folds_registry():
    """GAP-TUI-002: 小终端自动折叠 Registry。"""
    from soloflow.tui.app import SoloFlowApp

    app = SoloFlowApp()
    async with app.run_test(size=(100, 24)) as pilot:
        # 24 行 < BREAKPOINT_MEDIUM(28) → 自动折叠
        assert app._collapsed_registry is True
        await pilot.pause()
