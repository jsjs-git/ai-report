"""Hugging Face '오늘의 논문' 수집기 — 연구자들이 추천(upvote)한 논문.

설정 예:
  - name: Hugging Face 오늘의 논문
    type: hf_papers
    days: 3          # 최근 며칠치 목록을 볼지
"""

from __future__ import annotations

from datetime import timedelta

from ..article import parse_date
from ..http import get
from ..models import Item

API_URL = "https://huggingface.co/api/daily_papers"


def collect(source: dict, section: dict, ctx) -> list[Item]:
    items: dict[str, Item] = {}
    for offset in range(max(1, int(source.get("days", 1)))):
        day = (ctx.now - timedelta(days=offset)).date().isoformat()
        try:
            resp = get(ctx.client, API_URL, params={"date": day})
        except Exception as exc:  # 특정 날짜 목록이 없을 수 있어요 (주말 등)
            ctx.log.debug("HF %s 목록 없음: %s", day, exc)
            continue
        for row in resp.json():
            paper = row.get("paper") or {}
            pid = paper.get("id")
            if not pid or pid in items:
                continue
            items[pid] = Item(
                section_id=section["id"],
                source_name=source["name"],
                group="논문",
                title=" ".join((paper.get("title") or row.get("title") or "").split()),
                url=f"https://arxiv.org/abs/{pid}",
                published=parse_date(paper.get("publishedAt") or row.get("publishedAt")),
                text=" ".join((paper.get("summary") or row.get("summary") or "").split()),
                authors=[a.get("name", "") for a in paper.get("authors", []) if not a.get("hidden")][:20],
                organizations=_orgs(paper, row),
                upvotes=paper.get("upvotes"),
                paper_ids={"arxiv": pid},
            )
    return list(items.values())


def _orgs(paper: dict, row: dict) -> list[str]:
    """소속 기관 이름 (있으면). 데이터 모양이 바뀌어도 오류가 나지 않게 조심해서 읽어요."""
    out = []
    for org in (paper.get("organization"), row.get("organization")):
        if isinstance(org, dict):
            out += [v for k, v in org.items() if k in ("name", "fullname") and isinstance(v, str)]
        elif isinstance(org, str):
            out.append(org)
    return sorted(set(out))
