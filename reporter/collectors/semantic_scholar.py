"""Semantic Scholar 수집기 — 인용수가 많은 '검증된' 논문 + 인용수·학회 정보 보강.

설정 예:
  - name: Semantic Scholar
    type: semantic_scholar
    fields_of_study: ["Computer Science"]
    max_items: 20

섹션 filters.proven 의 lookback_days(기간)·min_citations(최소 인용수)를 함께 사용해요.
SEMANTIC_SCHOLAR_API_KEY 가 있으면 더 안정적이에요. (없어도 동작, 가끔 잠시 막힐 수 있음)
"""

from __future__ import annotations

import os
from datetime import timedelta

from ..article import parse_date
from ..http import get, request
from ..models import Item

BASE = "https://api.semanticscholar.org/graph/v1"
FIELDS = "title,url,abstract,citationCount,venue,publicationVenue,publicationDate,externalIds,authors"


def _headers() -> dict:
    key = os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
    return {"x-api-key": key} if key else {}


def build_query(keywords: list[str]) -> str:
    """Semantic Scholar 검색식: "구문" | 단어"""
    return " | ".join(f'"{k}"' if " " in k else k for k in keywords)


def collect(source: dict, section: dict, ctx) -> list[Item]:
    filters = section.get("filters", {})
    keywords = source.get("keywords") or filters.get("keywords") or []
    if not keywords:
        raise ValueError("semantic_scholar 소스에는 keywords가 필요해요.")
    proven = filters.get("proven", {})
    since = (ctx.now - timedelta(days=proven.get("lookback_days", 365))).date().isoformat()
    params = {
        "query": build_query(keywords),
        "fields": FIELDS,
        "minCitationCount": proven.get("min_citations", 50),
        "publicationDateOrYear": f"{since}:",
        "sort": "citationCount:desc",
    }
    if source.get("fields_of_study"):
        params["fieldsOfStudy"] = ",".join(source["fields_of_study"])
    resp = get(ctx.client, f"{BASE}/paper/search/bulk", params=params, headers=_headers())
    rows = (resp.json().get("data") or [])[: source.get("max_items", 20)]
    return [_to_item(row, source, section) for row in rows if row.get("title")]


def _to_item(row: dict, source: dict, section: dict) -> Item:
    ext = row.get("externalIds") or {}
    arxiv_id = ext.get("ArXiv")
    ids = {}
    if arxiv_id:
        ids["arxiv"] = arxiv_id
    if ext.get("DOI"):
        ids["doi"] = ext["DOI"]
    return Item(
        section_id=section["id"],
        source_name=source["name"],
        group="논문",
        title=" ".join(row["title"].split()),
        url=f"https://arxiv.org/abs/{arxiv_id}" if arxiv_id else row.get("url", ""),
        published=parse_date(row.get("publicationDate")),
        text=row.get("abstract") or "",
        authors=[a.get("name", "") for a in row.get("authors") or []][:20],
        citations=row.get("citationCount"),
        venue=_venue(row),
        paper_ids=ids,
    )


def _venue(row: dict) -> str:
    """학회/저널 이름. arXiv는 '게재'가 아니라 사전 공개라서 빈 값으로 둬요."""
    pv = row.get("publicationVenue") or {}
    venue = pv.get("name") or row.get("venue") or ""
    return "" if venue.lower() in ("arxiv.org", "arxiv") else venue


def enrich(items: list[Item], ctx) -> None:
    """arXiv·HF에서 온 논문에 인용수와 학회 정보를 채워요. (실패해도 그냥 넘어가요)"""
    targets = [it for it in items if it.paper_ids.get("arxiv") and it.citations is None]
    if not targets:
        return
    try:
        resp = request(
            ctx.client,
            "POST",
            f"{BASE}/paper/batch",
            params={"fields": "citationCount,venue,publicationVenue"},
            json={"ids": [f"ARXIV:{it.paper_ids['arxiv']}" for it in targets[:500]]},
            headers=_headers(),
        )
    except Exception as exc:
        ctx.log.warning("인용수 보강 실패 (건너뜀): %s", exc)
        return
    for it, row in zip(targets, resp.json()):
        if not row:
            continue
        it.citations = row.get("citationCount")
        venue = _venue(row)
        if venue:
            it.venue = f"{venue} · {it.venue}" if it.venue else venue
