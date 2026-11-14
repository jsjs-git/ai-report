"""RSS/Atom 피드 수집기 — 가장 안정적인 방식이에요.

설정 예:
  - name: OpenAI 뉴스
    group: OpenAI
    type: rss
    url: "https://openai.com/news/rss.xml"
    max_items: 20        # (선택) 최신 글 몇 개까지 볼지
"""

from __future__ import annotations

from datetime import datetime, timezone

import feedparser

from ..article import strip_html
from ..http import get
from ..models import Item


def collect(source: dict, section: dict, ctx) -> list[Item]:
    resp = get(ctx.client, source["url"])
    feed = feedparser.parse(resp.content)
    items: list[Item] = []
    for entry in feed.entries[: source.get("max_items", 20)]:
        link = entry.get("link")
        title = (entry.get("title") or "").strip()
        if not link or not title:
            continue
        items.append(
            Item(
                section_id=section["id"],
                source_name=source["name"],
                group=source.get("group", ""),
                title=title,
                url=link,
                published=_entry_time(entry),
                text=strip_html(entry.get("summary") or entry.get("description") or ""),
            )
        )
    return items


def _entry_time(entry) -> datetime | None:
    for key in ("published_parsed", "updated_parsed"):
        t = entry.get(key)
        if t:
            return datetime(*t[:6], tzinfo=timezone.utc)
    return None
