"""리포트를 HTML로 꾸며요. (templates/ 양식 + themes/ 디자인)"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import ROOT
from .models import Report
from .theme import Theme

TEMPLATES_DIR = ROOT / "templates"
_WEEKDAYS = "월화수목금토일"


class Renderer:
    def __init__(self, theme: Theme, timezone: str = "Asia/Seoul", templates_dir: Path | None = None):
        self.theme = theme
        self.tz = ZoneInfo(timezone)
        self.env = Environment(
            loader=FileSystemLoader(str(templates_dir or TEMPLATES_DIR)),
            autoescape=select_autoescape(enabled_extensions=("html", "j2"), default_for_string=True),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        self.env.globals.update(
            t=theme.data,
            theme=theme,
            group_color=theme.group_color,
        )
        self.env.filters.update(kdate=self.kdate, kdate_short=self.kdate_short, short=_short)

    # ── 날짜 표기 ──────────────────────────────────────────────────
    def _local(self, value) -> date:
        if isinstance(value, datetime):
            return value.astimezone(self.tz).date() if value.tzinfo else value.date()
        return value

    def kdate(self, value) -> str:
        d = self._local(value)
        return f"{d.year}년 {d.month}월 {d.day}일 {_WEEKDAYS[d.weekday()]}요일"

    def kdate_short(self, value) -> str:
        """'11월 14일'. 올해가 아니면 '2025년 11월 26일'처럼 연도를 붙여요."""
        d = self._local(value)
        if d.year != datetime.now(self.tz).year:
            return f"{d.year}년 {d.month}월 {d.day}일"
        return f"{d.month}월 {d.day}일"

    # ── 페이지 만들기 ──────────────────────────────────────────────
    def render_report(self, report: Report, channel: str = "web", detail: str = "full") -> str:
        """channel: web | email,  detail: full | short | brief"""
        template = self.env.get_template("weekly.html.j2" if report.mode == "weekly" else "daily.html.j2")
        return template.render(
            report=report,
            channel=channel,
            detail=detail,
            week_start=report.date - timedelta(days=6),
            preheader=report.one_liner,
            generated_at=datetime.now(self.tz).strftime("%Y-%m-%d %H:%M 생성"),
        )

    def render_archive(self, topic_title: str, description: str, entries: list[dict], home_url: str = "") -> str:
        return self.env.get_template("archive.html.j2").render(
            channel="web", topic_title=topic_title, description=description,
            entries=entries, home_url=home_url, preheader="",
        )

    def render_home(self, topics: list[dict]) -> str:
        return self.env.get_template("home.html.j2").render(channel="web", topics=topics, preheader="")


def _short(text: str, limit: int = 60) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"
