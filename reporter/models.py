"""프로그램 전체에서 주고받는 '데이터 모양' 정의.

- Item    : 수집한 글/논문 하나
- Summary : AI가 쓴 요약 + 자세한 설명
- Report  : 하루치(또는 한 주치) 리포트 전체
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

from pydantic import BaseModel, Field


# ── AI 요약 ─────────────────────────────────────────────────────────
class GlossaryEntry(BaseModel):
    term: str = Field(description="전문용어")
    meaning: str = Field(description="초보자도 이해할 수 있는 한 줄 풀이")


class Summary(BaseModel):
    """항목 하나에 대한 '요약 + 자세한 설명'. (리포트만 읽어도 이해되게)"""

    title_ko: str = ""
    headline: list[str] = Field(default_factory=list)  # 한눈에 보기 (3줄)
    background: str = ""        # 배경
    changes: str = ""           # 무엇이 바뀌었나
    why_it_matters: str = ""    # 왜 중요한가
    paper_idea: str = ""        # (논문) 핵심 아이디어 — 비유로 쉽게
    paper_results: str = ""     # (논문) 실험 결과 요점
    paper_limits: str = ""      # (논문) 한계
    glossary: list[GlossaryEntry] = Field(default_factory=list)
    importance: Literal["상", "중", "하"] = "중"
    is_fallback: bool = False   # AI 없이 자동으로 만든 간단 요약이면 True


# ── 수집 항목 ───────────────────────────────────────────────────────
_TRACKING_PARAMS = re.compile(r"^(utm_|ref$|fbclid$|gclid$)")


def normalize_url(url: str) -> str:
    """같은 글인데 주소 끝이 조금 다른 경우(utm 꼬리표, 끝의 /)를 하나로 맞춰요."""
    parts = urlsplit(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if not _TRACKING_PARAMS.match(k)])
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, parts.fragment))


@dataclass
class Item:
    section_id: str
    source_name: str
    title: str
    url: str
    group: str = ""                     # 묶음 이름 (예: 기업명). 색상 태그·묶어 보기용
    published: datetime | None = None   # 발행 시각 (모르면 None)
    text: str = ""                      # 원문 일부 (요약 재료)
    authors: list[str] = field(default_factory=list)
    organizations: list[str] = field(default_factory=list)
    citations: int | None = None        # 인용수
    venue: str = ""                     # 학회/저널 (또는 arXiv 코멘트)
    upvotes: int | None = None          # Hugging Face 추천수
    paper_ids: dict[str, str] = field(default_factory=dict)  # {"arxiv": "...", "doi": "..."}
    tier: str = ""                      # 논문 구분: "new"(신규 주목) | "proven"(검증됨)
    tags: list[str] = field(default_factory=list)            # 일치한 키워드
    summary: Summary | None = None

    @property
    def uid(self) -> str:
        """중복 확인용 고유 번호. 논문은 arXiv 번호, 그 외는 정리된 주소 기준."""
        if self.paper_ids.get("arxiv"):
            key = "arxiv:" + self.paper_ids["arxiv"]
        elif self.paper_ids.get("doi"):
            key = "doi:" + self.paper_ids["doi"].lower()
        else:
            key = normalize_url(self.url)
        return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]

    def to_dict(self, text_limit: int = 2000) -> dict:
        return {
            "section_id": self.section_id,
            "source_name": self.source_name,
            "title": self.title,
            "url": self.url,
            "group": self.group,
            "published": self.published.isoformat() if self.published else None,
            "text": self.text[:text_limit],
            "authors": self.authors,
            "organizations": self.organizations,
            "citations": self.citations,
            "venue": self.venue,
            "upvotes": self.upvotes,
            "paper_ids": self.paper_ids,
            "tier": self.tier,
            "tags": self.tags,
            "summary": self.summary.model_dump() if self.summary else None,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Item":
        d = dict(d)
        if d.get("published"):
            d["published"] = datetime.fromisoformat(d["published"])
        if d.get("summary"):
            d["summary"] = Summary.model_validate(d["summary"])
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in known})


# ── 리포트 ─────────────────────────────────────────────────────────
@dataclass
class ReportSection:
    id: str
    title: str
    kind: str                       # "news" | "papers"
    items: list[Item] = field(default_factory=list)

    def groups(self) -> list[tuple[str, list[Item]]]:
        """news 섹션을 묶음(기업)별로 나눠서 돌려줘요. 순서는 처음 나온 순."""
        out: dict[str, list[Item]] = {}
        for it in self.items:
            out.setdefault(it.group or it.source_name, []).append(it)
        return list(out.items())

    def tier_items(self, tier: str) -> list[Item]:
        return [it for it in self.items if it.tier == tier]


@dataclass
class Trend:
    title: str
    explanation: str


@dataclass
class Report:
    topic: str
    title: str
    mode: str                       # "daily" | "weekly"
    date: date
    sections: list[ReportSection]
    one_liner: str = ""             # 오늘의 한 줄 요약
    highlights: list[str] = field(default_factory=list)   # 핵심 3줄 (카카오톡에도 사용)
    trends: list[Trend] = field(default_factory=list)     # 주간판: 이번 주 핵심 흐름
    web_url: str = ""               # 이 리포트의 웹 주소 (web 채널이 채움)
    archive_url: str = ""           # 지난 리포트 목록 주소
    label: str = ""                 # 표시 이름 (설정의 report_label, 예: "주간")

    @property
    def item_count(self) -> int:
        return sum(len(s.items) for s in self.sections)

    @property
    def is_empty(self) -> bool:
        return self.item_count == 0

    @property
    def mode_label(self) -> str:
        return self.label or ("주간 정리" if self.mode == "weekly" else "데일리")

    @property
    def slug(self) -> str:
        """파일 이름용: 2026-11-10-daily"""
        return f"{self.date.isoformat()}-{self.mode}"
