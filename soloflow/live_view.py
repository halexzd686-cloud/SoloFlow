"""Rich live views for Skill and Flow execution."""

import json
import time
from contextlib import contextmanager
from pathlib import Path

from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text

TERMINAL_STATUSES = {"done", "failed", "partial", "dry_run"}
STATUS_MARKS = {
    "pending": ("○", "dim"),
    "done": ("✓", "green"),
    "failed": ("×", "red"),
    "skipped": ("−", "yellow"),
}


class SkillLiveView:
    """Render one Skill call while the model is working."""

    def __init__(self, skill_name: str):
        self.skill_name = skill_name
        self.started_at = time.monotonic()
        self.status = "running"
        self.output_chars = 0

    def complete(self, output: str) -> None:
        self.status = "done"
        self.output_chars = len(output)

    def fail(self) -> None:
        self.status = "failed"

    def __rich__(self):
        elapsed = time.monotonic() - self.started_at
        if self.status == "running":
            body = Spinner("dots", text=f"调用 DeepSeek · {elapsed:.1f}s")
            border = "cyan"
        elif self.status == "done":
            body = Text(f"完成 · {elapsed:.1f}s · {self.output_chars} 字符", style="green")
            border = "green"
        else:
            body = Text(f"失败 · {elapsed:.1f}s", style="red")
            border = "red"
        return Panel(body, title=f"Skill · {self.skill_name}", border_style=border)


@contextmanager
def live_skill(skill_name: str):
    """Show a live Skill panel for the duration of one model call."""
    view = SkillLiveView(skill_name)
    with Live(view, refresh_per_second=4, transient=False):
        try:
            yield view
        except Exception:
            view.fail()
            raise


class FlowRunView:
    """Read and render one persisted Flow run without mutating it."""

    def __init__(self, run_id: str, runs_dir: Path):
        self.run_id = run_id
        self.run_file = runs_dir / f"{run_id}.json"

    def read_state(self) -> dict:
        try:
            return json.loads(self.run_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return {}

    def __rich__(self):
        state = self.read_state()
        if not state:
            return Panel(
                Text(f"等待运行状态：{self.run_id}", style="yellow"),
                title="Flow",
                border_style="yellow",
            )

        table = Table(show_header=True, header_style="bold cyan", expand=True)
        table.add_column("步骤")
        table.add_column("Skill")
        table.add_column("依赖")
        table.add_column("状态", width=14)
        table.add_column("耗时", justify="right")
        table.add_column("Tokens", justify="right")

        for step_id, step in state.get("steps", {}).items():
            status = step.get("status", "pending")
            if status == "running":
                status_cell = Spinner("dots", text="running")
            else:
                mark, style = STATUS_MARKS.get(status, ("?", "white"))
                status_cell = Text(f"{mark} {status}", style=style)
            table.add_row(
                step_id,
                str(step.get("skill", "-")),
                ", ".join(step.get("depends_on", [])) or "-",
                status_cell,
                f"{float(step.get('duration', 0) or 0):.1f}s",
                str(step.get("tokens", 0) or 0),
            )

        status = state.get("status", "running")
        summary = Text.assemble(
            (f"状态: {status}", "bold"),
            f"  ·  总耗时: {float(state.get('total_duration', 0) or 0):.1f}s",
            f"  ·  Tokens: {state.get('total_tokens', 0) or 0}",
        )
        border = "green" if status == "done" else "yellow" if status == "running" else "red"
        return Panel(
            Group(summary, table),
            title=f"Flow · {state.get('flow_name', '?')} · {self.run_id}",
            border_style=border,
        )


@contextmanager
def live_flow(run_id: str, runs_dir: Path):
    """Show a live Flow panel while the caller executes the run."""
    view = FlowRunView(run_id, runs_dir)
    with Live(view, refresh_per_second=4, transient=False):
        yield view


def watch_flow(run_id: str, runs_dir: Path, refresh_interval: float = 0.25) -> dict:
    """Attach to a persisted Flow run until it reaches a terminal status."""
    view = FlowRunView(run_id, runs_dir)
    if not view.run_file.exists():
        raise FileNotFoundError(f"运行记录不存在: {run_id}")

    with Live(view, refresh_per_second=4, transient=False):
        while True:
            state = view.read_state()
            if state.get("status") in TERMINAL_STATUSES:
                return state
            time.sleep(refresh_interval)
