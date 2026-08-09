"""顶部状态栏 —— SoloFlow 标识 + 统计概览。"""

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Static

from soloflow import __version__
from soloflow.tui.theme import C


class HeaderBar(Horizontal):
    """侘寂风顶部栏。"""

    DEFAULT_CSS = f"""
    HeaderBar {{
        height: 3;
        background: {C["surface"]};
        padding: 0 2;
        border-bottom: solid {C["border"]};
    }}
    HeaderBar .brand {{
        color: {C["accent"]};
        text-style: bold;
        width: 16;
    }}
    HeaderBar .brand-version {{
        color: {C["text_muted"]};
    }}
    HeaderBar .stat-value {{
        color: {C["accent"]};
        text-style: bold;
    }}
    HeaderBar .stat-label {{
        color: {C["text_dim"]};
    }}
    HeaderBar .sep {{
        color: {C["divider"]};
        width: 3;
    }}
    """

    def compose(self) -> ComposeResult:
        yield Static(
            f"[brand]SoloFlow[/brand] [brand-version]v{__version__}[/brand-version]",
            classes="brand",
            id="header-brand",
        )
        yield Static("", classes="sep")
        sc, ac, fc = self._count_skills(), self._count_agents(), self._count_flows()
        for val, label, wid in [
            (sc, "Skills", "stat-skills"),
            (ac, "Agents", "stat-agents"),
            (fc, "Flows", "stat-flows"),
        ]:
            yield Static(f"[stat-value]{val}[/stat-value]", classes="stat-value", id=wid)
            yield Static(f"[stat-label]{label}[/stat-label]", classes="stat-label")
            yield Static("|", classes="sep")

    def refresh_stats(self) -> None:
        """刷新计数统计。

        注意: 不覆盖 Textual 的 Widget.refresh()（签名不兼容，会破坏布局）。
        """
        try:
            sc = self._count_skills()
            ac = self._count_agents()
            fc = self._count_flows()
            for wid, val in [("stat-skills", sc), ("stat-agents", ac), ("stat-flows", fc)]:
                try:
                    widget = self.query_one(f"#{wid}", Static)
                    widget.update(f"[stat-value]{val}[/stat-value]")
                except Exception:
                    pass
        except Exception:
            pass

    @staticmethod
    def _count_skills() -> int:
        try:
            from soloflow.core.skill_loader import list_skills

            return len(list_skills("skills"))
        except Exception:
            return 0

    @staticmethod
    def _count_agents() -> int:
        # P2-001: 与 CLI 共用统一的搜索目录
        try:
            from soloflow.cli.agent import _agent_search_dirs

            return sum(
                len(list(d.glob("*.agent.y*ml"))) for d in _agent_search_dirs() if d.is_dir()
            )
        except Exception:
            return 0

    @staticmethod
    def _count_flows() -> int:
        try:
            from pathlib import Path

            return len(list(Path("flows").glob("*.flow.y*ml")))
        except Exception:
            return 0
