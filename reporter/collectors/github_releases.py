"""GitHub 릴리스 수집기 — SDK·도구의 새 버전 소식.

설정 예:
  - name: Claude Code 릴리스
    group: Anthropic
    type: github_releases
    repo: anthropics/claude-code
    max_items: 5
    include_prereleases: false   # (선택) 시험판 포함 여부

GITHUB_API_TOKEN(또는 GITHUB_TOKEN) 환경변수가 있으면 조회 한도가 늘어나요. (없어도 동작)
"""

from __future__ import annotations

import os

from ..article import parse_date
from ..http import get
from ..models import Item


def collect(source: dict, section: dict, ctx) -> list[Item]:
    repo = source["repo"]
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_API_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = get(
        ctx.client,
        f"https://api.github.com/repos/{repo}/releases",
        params={"per_page": source.get("max_items", 5)},
        headers=headers,
    )
    items: list[Item] = []
    for rel in resp.json():
        if rel.get("draft") or (rel.get("prerelease") and not source.get("include_prereleases")):
            continue
        tag = rel.get("tag_name") or ""
        name = (rel.get("name") or "").strip()
        title = f"{repo} {tag}" + (f" — {name}" if name and name != tag else "")
        items.append(
            Item(
                section_id=section["id"],
                source_name=source["name"],
                group=source.get("group", ""),
                title=title,
                url=rel.get("html_url") or f"https://github.com/{repo}/releases",
                published=parse_date(rel.get("published_at")),
                text=(rel.get("body") or "")[:8000],
            )
        )
    return items
