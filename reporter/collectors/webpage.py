"""웹페이지 수집기 — RSS가 없는 사이트용.

두 가지 방식이 있어요.

1) mode: links (기본) — 목록 페이지에서 '글 주소 모양'에 맞는 링크를 뽑아요.
  - name: Anthropic 뉴스
    type: webpage
    url: "https://www.anthropic.com/news"
    link_pattern: "^https://www\\.anthropic\\.com/news/[a-z0-9-]+$"   # 글 주소 모양 (정규식)
    exclude_pattern: "/news/(announcements|product)$"                   # (선택) 빼고 싶은 주소
    require_date: true      # (선택) 글 페이지에서 날짜를 못 찾으면 제외
    max_items: 10

2) mode: headings — 한 페이지에 날짜별 제목이 쌓이는 '변경 기록(릴리스 노트)' 페이지용.
  - name: Claude 개발자 릴리스 노트
    type: webpage
    mode: headings
    url: "https://platform.claude.com/docs/en/release-notes/overview"
    heading_id_pattern: "^[a-z]+-\\d{1,2}-\\d{4}$"   # 제목 id 모양 (예: november-5-2026)
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from ..article import parse_date
from ..http import get
from ..models import Item

_SPACES = re.compile(r"\s+")
# 제목이 아니라 버튼·라벨인 링크 문구 (이런 건 제목으로 쓰지 않아요)
GENERIC_LINK_TEXT = re.compile(
    r"^(featured|learn more|read more|read the (post|blog|story)|more|continue reading|자세히( 보기)?|더 ?보기)$", re.I
)


def looks_generic(title: str) -> bool:
    return not title or len(title) < 12 or bool(GENERIC_LINK_TEXT.match(title.strip()))


def collect(source: dict, section: dict, ctx) -> list[Item]:
    resp = get(ctx.client, source["url"])
    soup = BeautifulSoup(resp.text, "html.parser")
    if source.get("mode") == "headings":
        return _collect_headings(soup, source, section)
    return _collect_links(soup, source, section)


def _clean(text: str, limit: int = 200) -> str:
    text = _SPACES.sub(" ", text or "").strip()
    return text[:limit]


def _collect_links(soup: BeautifulSoup, source: dict, section: dict) -> list[Item]:
    if not source.get("link_pattern"):
        raise ValueError(f"'{source['name']}' 소스에 link_pattern(글 주소 모양)이 필요해요.")
    pattern = re.compile(source["link_pattern"])
    exclude = re.compile(source["exclude_pattern"]) if source.get("exclude_pattern") else None

    found: dict[str, str] = {}  # 주소 → 제목 (페이지에 나온 순서 유지)
    for a in soup.find_all("a", href=True):
        url = urljoin(source["url"], a["href"]).split("#")[0]
        if not pattern.search(url) or (exclude and exclude.search(url)):
            continue
        heading = a.find(["h1", "h2", "h3", "h4"])
        title = _clean(heading.get_text(" ") if heading else a.get_text(" "))
        if GENERIC_LINK_TEXT.match(title):
            title = ""
        # 같은 글로 가는 링크가 여러 개면 가장 제목다운(긴) 문구를 써요
        if url not in found or len(title) > len(found[url]):
            found[url] = title

    items: list[Item] = []
    for url, title in list(found.items())[: source.get("max_items", 10)]:
        if not title:
            title = url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ").title()
        items.append(
            Item(
                section_id=section["id"],
                source_name=source["name"],
                group=source.get("group", ""),
                title=title,
                url=url,
                published=None,  # 목록에는 날짜가 없어서, 나중에 글 페이지에서 확인해요
            )
        )
    return items


def _collect_headings(soup: BeautifulSoup, source: dict, section: dict) -> list[Item]:
    id_pattern = re.compile(source.get("heading_id_pattern", ".+"))
    headings = [h for h in soup.find_all(["h2", "h3"], id=True) if id_pattern.search(h["id"])]
    items: list[Item] = []
    for h in headings[: source.get("max_items", 5)]:
        heading_text = _clean(h.get_text(" "))
        parts: list[str] = []
        for el in h.find_all_next(["h2", "h3", "p", "li", "pre"]):
            if el.name in ("h2", "h3"):
                break
            if el.name == "li" and el.find("p"):
                continue  # 안쪽 <p>에서 이미 읽어요
            parts.append(_clean(el.get_text(" "), 1000))
            if sum(len(p) for p in parts) > 6000:
                break
        items.append(
            Item(
                section_id=section["id"],
                source_name=source["name"],
                group=source.get("group", ""),
                title=f"{source['name']} — {heading_text}",
                url=f"{source['url']}#{h['id']}",
                published=parse_date(heading_text),
                text="\n".join(parts),
            )
        )
    return items
