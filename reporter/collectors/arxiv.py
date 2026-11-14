"""arXiv 수집기 — 갓 나온 논문.

설정 예:
  - name: arXiv
    type: arxiv
    categories: [cs.CL, cs.AI, cs.LG]   # arXiv 분류
    max_results: 100
    keywords: [...]                     # (선택) 없으면 섹션 filters.keywords 사용

arXiv 코멘트(예: "Accepted at NeurIPS 2026")는 venue 칸에 넣어서 학회 채택 여부 판단에 써요.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import feedparser

from ..http import get
from ..models import Item

API_URL = "https://export.arxiv.org/api/query"
_VERSION = re.compile(r"v\d+$")


def build_query(categories: list[str], keywords: list[str]) -> str:
    query = " OR ".join(f"cat:{c}" for c in categories) or "cat:cs.AI"
    if keywords:
        kw = " OR ".join(f'abs:"{k}"' if " " in k else f"abs:{k}" for k in keywords)
        query = f"({query}) AND ({kw})"
    return query


def collect(source: dict, section: dict, ctx) -> list[Item]:
    keywords = source.get("keywords") or section.get("filters", {}).get("keywords") or []
    params = {
        "search_query": build_query(source.get("categories", []), keywords),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": source.get("max_results", 100),
    }
    resp = get(ctx.client, API_URL, params=params)
    feed = feedparser.parse(resp.content)
    items: list[Item] = []
    for e in feed.entries:
        arxiv_id = _VERSION.sub("", (e.get("id") or "").rsplit("/abs/", 1)[-1])
        if not arxiv_id:
            continue
        published = None
        if e.get("published_parsed"):
            published = datetime(*e.published_parsed[:6], tzinfo=timezone.utc)
        items.append(
            Item(
                section_id=section["id"],
                source_name=source["name"],
                group="논문",
                title=" ".join((e.get("title") or "").split()),
                url=f"https://arxiv.org/abs/{arxiv_id}",
                published=published,
                text=" ".join((e.get("summary") or "").split()),
                authors=[a.get("name", "") for a in e.get("authors", [])][:20],
                venue=(e.get("arxiv_comment") or "").strip(),
                paper_ids={"arxiv": arxiv_id},
            )
        )
    return items
