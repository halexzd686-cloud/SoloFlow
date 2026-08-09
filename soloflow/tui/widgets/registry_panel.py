"""Registry 面板 —— 右下角，社区 Skill 市场。"""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import Input, Static

from soloflow.tui.theme import C


class RegistryItem(Static):
    """单条 Registry 条目 —— 可聚焦。"""

    can_focus = True

    class DetailRequest(Message):
        """Enter 时向上发送。"""

        def __init__(self, entry_data: dict) -> None:
            self.entry_data = entry_data
            super().__init__()

    DEFAULT_CSS = f"""
    RegistryItem {{
        padding: 0 2;
        height: 1;
    }}
    RegistryItem:hover {{ background: {C["highlight"]}; }}
    RegistryItem:focus {{ background: {C["highlight"]}; border: solid {C["accent"]}; }}
    RegistryItem .reg-name {{ color: {C["text"]}; }}
    RegistryItem .reg-count {{ color: {C["text_muted"]}; }}
    RegistryItem .reg-badge {{ color: {C["accent"]}; text-style: italic; }}
    """

    BINDINGS = [
        Binding("enter", "show_detail", "Detail", show=False),
    ]

    def __init__(self, entry_data: dict):
        super().__init__()
        self.entry_data = entry_data
        self.ename = entry_data.get("name", "")
        self.edownloads = entry_data.get("downloads", 0)
        self.eis_new = entry_data.get("is_new", False)
        badge = " [reg-badge]{新着}[/reg-badge]" if self.eis_new else ""
        self.update(
            f"· [reg-name]{self.ename}[/reg-name]  [reg-count]{self.edownloads:,} ↓[/reg-count]{badge}"  # noqa: E501
        )

    def action_show_detail(self) -> None:
        self.post_message(self.DetailRequest(self.entry_data))


class RegistryPanel(VerticalScroll):
    """社区 Registry 面板 —— ↑↓ 导航 + / 搜索。"""

    BINDINGS = [
        Binding("up", "cursor_up", show=False),
        Binding("down", "cursor_down", show=False),
        Binding("slash", "start_search", "Search", show=False),
    ]

    DEFAULT_CSS = f"""
    RegistryPanel {{
        background: {C["bg"]};
        padding: 0 1;
    }}
    RegistryPanel .panel-title {{
        color: {C["accent"]};
        text-style: bold;
        padding: 1 2;
        height: 3;
    }}
    RegistryPanel .panel-subtitle {{
        color: {C["text_muted"]};
        padding: 0 2;
    }}
    RegistryPanel .section-label {{
        color: {C["text_dim"]};
        text-style: italic;
        padding: 1 2;
    }}
    #registry-search {{
        margin: 0 2;
        height: 3;
        display: none;
    }}
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._search_input = Input(placeholder="Search registry...", id="registry-search")

    def compose(self) -> ComposeResult:
        yield Static("[panel-title]|  Registry[/panel-title]")
        yield Static("[panel-subtitle]skillの市庭[/panel-subtitle]")
        yield self._search_input
        yield Static("[section-label]今日の新着[/section-label]")
        entries = _load_registry()
        for e in entries:
            yield RegistryItem(e)
        if not entries:
            yield Static("[reg-count]  (registry 未接続)[/reg-count]")

    def on_focus(self) -> None:
        """面板获得焦点时自动聚焦第一个条目。"""
        cards = self._get_cards()
        if cards:
            cards[0].focus()

    def _get_cards(self) -> list[RegistryItem]:
        return list(self.query(RegistryItem))

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

    def action_start_search(self) -> None:
        """显示搜索输入框并聚焦。"""
        self._search_input.styles.display = "block"
        self._search_input.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """搜索框内容变化时实时过滤。"""
        if event.input.id != "registry-search":
            return
        query = event.value.lower()
        for item in self.query(RegistryItem):
            if isinstance(item, RegistryItem):
                if query:
                    match = query in item.ename.lower()
                    item.display = match
                else:
                    item.display = True

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """搜索提交后隐藏搜索框，聚焦第一个可见结果。"""
        if event.input.id != "registry-search":
            return
        self._search_input.styles.display = "none"
        self._search_input.value = ""
        # 恢复所有条目可见
        for item in self.query(RegistryItem):
            if isinstance(item, RegistryItem):
                item.display = True
        cards = self._get_cards()
        if cards:
            cards[0].focus()


def _load_registry() -> list[dict]:
    """加载 Registry 条目数据。"""
    try:
        from soloflow.core.registry import load_registry_index

        entries = load_registry_index()
        if entries:
            return [
                {"name": e.name, "downloads": e.downloads, "is_new": i == 0}
                for i, e in enumerate(entries[:6])
            ]
    except Exception:
        pass
    return [
        {"name": "twitter-thread-writer", "downloads": 1200, "is_new": False},
        {"name": "resume-optimizer", "downloads": 892, "is_new": False},
        {"name": "course-outline-designer", "downloads": 567, "is_new": False},
        {"name": "weekly-report-generator", "downloads": 445, "is_new": False},
        {"name": "api-doc-writer", "downloads": 42, "is_new": True},
    ]
