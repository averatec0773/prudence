"""The `rumps` app: an icon, a dropdown of numbers, and three buttons.

No analysis logic lives here. Every number comes from `menubar.summary`, which reads
the store; every action shells out to the `prudence` CLI itself, the same one the
founder runs by hand, so the menu bar can never disagree with the terminal about what
a command does. `PRUDENCE_INTERNAL=1` marks the subprocess as Prudence's own, for the
hooks (task 9) to stay quiet around.
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from datetime import UTC, datetime

import rumps

from prudence.menubar.summary import today_summary, week_summary
from prudence.paths import database_file, reports_dir
from prudence.store import db

REFRESH_INTERVAL_SECONDS = 60
INGEST_INTERVAL_SECONDS = 30 * 60
TITLE = "P"
WINDOW = "7d"


class PrudenceApp(rumps.App):
    """Today's counts, the last ingest time, and a way to refresh, ingest and open."""

    def __init__(self) -> None:
        super().__init__(TITLE, quit_button=None)
        self.today_item = rumps.MenuItem("Today: -")
        self.week_item = rumps.MenuItem("This week: -")
        self.observation_item = rumps.MenuItem("Latest observation: -")
        self.ingest_item = rumps.MenuItem("Last ingest: -")
        self.menu = [
            self.today_item,
            self.week_item,
            self.observation_item,
            self.ingest_item,
            None,
            rumps.MenuItem("Ingest now", callback=self.ingest_now),
            rumps.MenuItem("Open latest table", callback=self.open_latest_table),
            rumps.MenuItem("Refresh", callback=self.refresh),
            None,
            rumps.MenuItem("Quit", callback=rumps.quit_application),
        ]
        self.refresh(None)
        rumps.Timer(self.refresh, REFRESH_INTERVAL_SECONDS).start()
        rumps.Timer(self._timed_ingest, INGEST_INTERVAL_SECONDS).start()

    def refresh(self, _arg: object) -> None:
        """Recompute today's and this week's numbers from the store. Reads only; never ingests."""
        if not database_file().exists():
            self.today_item.title = "Today: nothing ingested yet"
            self.week_item.title = "This week: nothing ingested yet"
            self.observation_item.title = "Latest observation: none yet"
            self.ingest_item.title = "Last ingest: never"
            return
        today = datetime.now().astimezone().date()
        connection = db.connect()
        try:
            summary = today_summary(connection, today)
            week = week_summary(connection, today)
        finally:
            connection.close()
        self.today_item.title = (
            f"Today: {summary.sessions} sessions, {summary.edits} edits, {summary.commits} commits"
        )
        self.week_item.title = f"This week: {_format_week(week.top_purposes)}"
        observation_text = _truncate(week.latest_observation)
        self.observation_item.title = f"Latest observation: {observation_text}"
        _set_tooltip(self.observation_item, week.latest_observation)
        self.ingest_item.title = f"Last ingest: {_format_ingest(summary.last_ingest)}"

    def ingest_now(self, _arg: object) -> None:
        threading.Thread(target=self._ingest, daemon=True).start()

    def _timed_ingest(self, _arg: object) -> None:
        self._ingest()

    def _ingest(self) -> None:
        """Run `prudence ingest` out of process, then refresh the counts it changed."""
        _run_cli("ingest")
        self.refresh(None)

    def open_latest_table(self, _arg: object) -> None:
        threading.Thread(target=self._open_latest_table, daemon=True).start()

    def _open_latest_table(self) -> None:
        """Write `prudence sessions --last 7d` to a Markdown file and open it."""
        result = _run_cli("sessions", "--last", WINDOW)
        output = result.stdout.strip() or result.stderr.strip() or "(no output)"
        generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
        path = reports_dir() / "sessions-latest.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"# Prudence: sessions, last {WINDOW}\n\nGenerated {generated}.\n\n```\n{output}\n```\n"
        )
        subprocess.run(["open", str(path)], check=False)


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    """`prudence <args>`, in the same Python environment this app runs in."""
    environment = dict(os.environ, PRUDENCE_INTERNAL="1")
    command = [sys.executable, "-c", "from prudence.cli import main; main()", *args]
    return subprocess.run(command, capture_output=True, text=True, env=environment, check=False)


def _format_ingest(last_seen: str | None) -> str:
    return f"{last_seen[:19]} UTC" if last_seen else "never"


def _format_week(top_purposes: tuple[tuple[str, float], ...]) -> str:
    """`development 88%, research 12%`, or a plain word when the week has no tokens yet."""
    if not top_purposes:
        return "no tokens yet"
    return ", ".join(f"{label} {share * 100:.0f}%" for label, share in top_purposes)


def _truncate(text: str | None, limit: int = 80) -> str:
    """The observation's own sentence, cut to `limit` characters with an ellipsis."""
    if not text:
        return "none yet"
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _set_tooltip(item: rumps.MenuItem, text: str | None) -> None:
    """The full sentence as a tooltip, when the underlying NSMenuItem allows it."""
    if not text:
        return
    try:
        item._menuitem.setToolTip_(text)
    except AttributeError:
        pass


def run() -> None:
    PrudenceApp().run()
