"""걸러내기 — 기간·키워드·인용수·학회 기준으로 보낼 항목을 골라요.

설정(섹션 filters)에서 쓰는 값:
  news   : lookback_days, keywords, max_items
  papers : keywords, new{lookback_days, min_upvotes, labs, max_items},
           proven{lookback_days, min_citations, venues, max_items}
"""

from __future__ import annotations

import re
from datetime import datetime

from .models import Item

# 학회 이름이 코멘트에 있어도 '심사 중/제출함/워크숍'이면 본 학회 채택으로 보지 않아요.
_NOT_ACCEPTED = re.compile(r"under review|submitted|in submission|rejected|preprint|workshop", re.I)

# Semantic Scholar는 학회를 정식 이름으로 알려줘요 → 약칭과 짝지어 둬요
VENUE_ALIASES = {
    "NeurIPS": ["Neural Information Processing Systems", "NIPS"],
    "ICLR": ["International Conference on Learning Representations"],
    "ICML": ["International Conference on Machine Learning"],
    "ACL": ["Annual Meeting of the Association for Computational Linguistics"],
    "EMNLP": ["Empirical Methods in Natural Language Processing"],
    "NAACL": ["North American Chapter of the Association for Computational Linguistics"],
    "CVPR": ["Computer Vision and Pattern Recognition"],
    "AAAI": ["AAAI Conference on Artificial Intelligence"],
    "TMLR": ["Trans. Mach. Learn. Res.", "Transactions on Machine Learning Research"],
}
# 약칭 앞에 올 수 있는 말 (예: "Accepted at NeurIPS", "Findings of ACL", "NeurIPS 2026")
_VENUE_BEFORE = r"(?:^|\b(?:at|in|to|on|of|by|for|the)\s+|[(\[:,;·]\s*)"
# 약칭 뒤: 끝/숫자/문장부호는 OK, 대문자로 시작하는 다른 단어가 이어지면 다른 이름 (예: Nature Machine …)
_VENUE_AFTER = r"(?=$|[\s\d'’.,;:)\]·-])(?!\s+[A-Z][a-z])"


# ── 기본 도구 ───────────────────────────────────────────────────────
def keyword_hits(item: Item, keywords: list[str]) -> list[str]:
    """제목+본문에 들어 있는 키워드 목록. (대소문자 무시, 단어 앞부분 기준)"""
    if not keywords:
        return []
    haystack = f"{item.title}\n{item.text}".lower()
    hits = []
    for k in keywords:
        if re.search(r"(?<![a-z0-9])" + re.escape(k.lower()), haystack):
            hits.append(k)
    return hits


def paper_keyword_ok(item: Item, keywords: list[str], min_hits: int) -> list[str] | None:
    """논문 관련성 판단: 제목에 키워드가 있거나, 서로 다른 키워드가 min_hits개 이상 있으면 통과.
    통과하면 일치한 키워드 목록, 아니면 None."""
    if not keywords:
        return []
    hits = keyword_hits(item, keywords)
    title_hits = keyword_hits(Item(section_id="", source_name="", title=item.title, url=""), keywords)
    if title_hits or len(hits) >= min_hits:
        return hits
    return None


def age_days(item: Item, now: datetime) -> float | None:
    if item.published is None:
        return None
    return (now - item.published).total_seconds() / 86400


def within_days(item: Item, days: float, now: datetime) -> bool:
    """기간 안이면 True. 날짜를 모르면 일단 통과(이미 보낸 기록으로 중복을 막아요)."""
    age = age_days(item, now)
    return age is None or age <= days


def venue_match(venue_text: str, venues: list[str]) -> str | None:
    """학회/저널 이름이 들어 있으면 그 이름을 돌려줘요."""
    if not venue_text or not venues or _NOT_ACCEPTED.search(venue_text):
        return None
    for v in venues:
        # 1) 약칭/짧은 이름: 앞뒤 문맥까지 확인 ("Data Science"를 Science로 착각하지 않게)
        if re.search(_VENUE_BEFORE + re.escape(v) + _VENUE_AFTER, venue_text):
            return v
        # 2) 정식 이름: 그대로 들어 있으면 OK
        if any(alias.lower() in venue_text.lower() for alias in VENUE_ALIASES.get(v, [])):
            return v
    return None


def lab_match(item: Item, labs: list[str]) -> str | None:
    text = " ".join(item.organizations).lower()
    for lab in labs or []:
        if lab.lower() in text:
            return lab
    return None


def classify_paper(item: Item, filters: dict, now: datetime) -> str | None:
    """논문을 'new'(신규 주목) / 'proven'(검증됨) / None(제외) 으로 나눠요."""
    new = filters.get("new", {})
    proven = filters.get("proven", {})
    age = age_days(item, now)
    age = 0 if age is None else age

    if new and age <= new.get("lookback_days", 7):
        if (item.upvotes or 0) >= new.get("min_upvotes", 10):
            return "new"
        if lab_match(item, new.get("labs", [])):
            return "new"
        if venue_match(item.venue, proven.get("venues", [])):
            return "new"  # 갓 나왔지만 이미 주요 학회 채택

    if proven and age <= proven.get("lookback_days", 365):
        if (item.citations or 0) >= proven.get("min_citations", 50):
            return "proven"
        if venue_match(item.venue, proven.get("venues", [])):
            return "proven"
    return None


# ── 섹션별 선택 ─────────────────────────────────────────────────────
def select(section: dict, items: list[Item], now: datetime) -> list[Item]:
    f = section.get("filters", {})
    keywords = f.get("keywords") or []
    if section.get("kind") == "papers":
        return _select_papers(f, items, keywords, now)
    # separate_count: true 인 소스(예: 릴리스 노트)는 회사당 제한(max_per_group)에 세지 않아요
    separate = {s.get("name") for s in section.get("sources", []) if s.get("separate_count")}
    return _select_news(f, items, keywords, now, separate)


def _select_news(f: dict, items: list[Item], keywords: list[str], now: datetime,
                 separate: set[str] = frozenset()) -> list[Item]:
    out = []
    for it in items:
        if not within_days(it, f.get("lookback_days", 2), now):
            continue
        hits = keyword_hits(it, keywords)
        if keywords and not hits:
            continue
        it.tags = hits
        out.append(it)
    # 최신 글 먼저 (날짜 모르는 글은 뒤로)
    out.sort(key=lambda it: it.published.timestamp() if it.published else 0, reverse=True)
    per_group = f.get("max_per_group")  # 한 묶음(회사)이 칸을 독차지하지 않게
    if per_group:
        counts: dict[str, int] = {}
        kept = []
        for it in out:
            if it.source_name in separate:
                kept.append(it)
                continue
            counts[it.group] = counts.get(it.group, 0) + 1
            if counts[it.group] <= per_group:
                kept.append(it)
        out = kept
    return out[: f.get("max_items", 15)]


def _select_papers(f: dict, items: list[Item], keywords: list[str], now: datetime) -> list[Item]:
    by_tier: dict[str, list[Item]] = {"new": [], "proven": []}
    min_hits = int(f.get("min_keyword_hits", 2))
    for it in items:
        hits = paper_keyword_ok(it, keywords, min_hits)
        if hits is None:
            continue
        tier = classify_paper(it, f, now)
        if not tier:
            continue
        it.tier, it.tags = tier, hits
        by_tier[tier].append(it)
    by_tier["new"].sort(key=lambda it: (it.upvotes or 0, len(it.tags)), reverse=True)
    by_tier["proven"].sort(key=lambda it: it.citations or 0, reverse=True)
    new_max = f.get("new", {}).get("max_items", 5)
    proven_max = f.get("proven", {}).get("max_items", 2)
    return by_tier["new"][:new_max] + by_tier["proven"][:proven_max]


def source_keyword_filter(items: list[Item], source: dict) -> list[Item]:
    """소스별 거르기.
    - keywords      : 그 단어가 들어간 글만 남기기 (예: 개발자 블로그 중 AI 글만)
    - exclude_title : 제목이 이 모양(정규식)이면 빼기 (예: 고객 사례 글)"""
    if source.get("exclude_title"):
        pattern = re.compile(source["exclude_title"], re.I)
        items = [it for it in items if not pattern.search(it.title)]
    kws = source.get("keywords") or []
    if not kws or source.get("type") in ("arxiv", "semantic_scholar"):
        return items  # 논문 소스는 검색어로 이미 사용했어요
    return [it for it in items if keyword_hits(it, kws)]
