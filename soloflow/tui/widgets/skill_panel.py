"""Skill 面板 —— 左侧卡片列表。"""

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.message import Message
from textual.widgets import Static

from soloflow.tui.theme import C


class SkillCard(Static):
    """单个 Skill 卡片 —— 可聚焦，Enter 弹出详情。"""

    can_focus = True

    class DetailRequest(Message):
        """按下 Enter 时向上发送，携带完整 Skill 数据。"""

        def __init__(self, skill_data: dict) -> None:
            self.skill_data = skill_data
            super().__init__()

    DEFAULT_CSS = f"""
    SkillCard {{
        background: {C["surface"]};
        border: solid {C["border"]};
        padding: 1 2;
        margin: 1 1;
        height: 4;
    }}
    SkillCard:hover {{ border: solid {C["border_focus"]}; }}
    SkillCard:focus {{ border: solid {C["accent"]}; background: {C["highlight"]}; }}
    SkillCard .skill-header {{ color: {C["text"]}; text-style: bold; }}
    SkillCard .skill-version {{ color: {C["text_muted"]}; }}
    SkillCard .skill-desc {{ color: {C["text_dim"]}; padding: 0 1; }}
    SkillCard .skill-stats {{ color: {C["text_muted"]}; padding: 0 1; }}
    SkillCard .skill-stars {{ color: {C["warning"]}; }}
    """

    BINDINGS = [
        Binding("enter", "show_detail", "Detail", show=False),
    ]

    def __init__(self, skill_data: dict):
        super().__init__()
        self.skill_data = skill_data
        self.sname = skill_data.get("name", "unknown")
        self.sver = skill_data.get("version", "0.1.0")
        self.sdesc = skill_data.get("description", "")[:60]
        self.stars = skill_data.get("stars", 4.5)
        self.calls = skill_data.get("calls", 0)
        self.iters = skill_data.get("iterations", 0)

    def on_mount(self) -> None:
        sv = "★" * int(self.stars) + "☆" * (5 - int(self.stars))
        self.update(
            f"[skill-header]{self.sname}[/skill-header]"
            f"  [skill-version]v{self.sver}[/skill-version]\n"
            f" [skill-desc]{self.sdesc}[/skill-desc]\n"
            f" [skill-stats]"
            f"[skill-stars]{sv}[/skill-stars]"
            f"    {self.calls:,}回    {self.iters}回反復"
            f"[/skill-stats]"
        )

    def action_show_detail(self) -> None:
        self.post_message(self.DetailRequest(self.skill_data))


class SkillPanel(VerticalScroll):
    """Skill 列表面板 —— ↑↓ 导航卡片。"""

    BINDINGS = [
        Binding("up", "cursor_up", show=False),
        Binding("down", "cursor_down", show=False),
    ]

    DEFAULT_CSS = f"""
    SkillPanel {{
        background: {C["bg"]};
        padding: 0 1;
    }}
    SkillPanel .panel-title {{
        color: {C["accent"]};
        text-style: bold;
        padding: 1 2;
        height: 3;
    }}
    SkillPanel .panel-subtitle {{
        color: {C["text_muted"]};
        padding: 0 2;
    }}
    """

    def compose(self) -> ComposeResult:
        yield Static("[panel-title]|  Skills[/panel-title]")
        yield Static("[panel-subtitle]skillの森[/panel-subtitle]")
        for s in _load_skills():
            yield SkillCard(s)
        if not _load_skills():
            yield Static("[skill-stats]  Skill が見つかりません[/skill-stats]")

    def on_focus(self) -> None:
        """面板获得焦点时自动聚焦第一个卡片。"""
        cards = self._get_cards()
        if cards:
            cards[0].focus()

    def _get_cards(self) -> list[SkillCard]:
        return list(self.query(SkillCard))

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


def _load_skills() -> list[dict]:
    """加载 Skill 列表，返回富数据供卡片渲染和详情弹窗。"""
    try:
        from soloflow.core.skill_loader import list_skills

        skills = list_skills("skills")
        enriched = []
        for s in skills:
            enriched.append(
                {
                    "name": s.get("name", "unknown"),
                    "version": s.get("version", "0.1.0"),
                    "description": s.get("description", ""),
                    "tags": s.get("tags", []),
                    "path": s.get("path", ""),
                    "stars": 4.5,
                    "calls": 0,
                    "iterations": 0,
                    "skill_name": s.get("name", "unknown"),
                }
            )
        return enriched
    except Exception:
        return []
