"""수집기 모음.

수집기는 모두 같은 모양의 함수예요:
    collect(source: dict, section: dict, ctx: CollectContext) -> list[Item]

새 수집 방식을 추가하려면:
  1) 이 폴더에 파일을 만들고 collect 함수를 작성
  2) 아래 COLLECTORS 에 이름을 등록
  3) 설정 파일에서 type: <이름> 으로 사용
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime

import httpx

from . import arxiv, github_releases, hf_papers, rss, sample, semantic_scholar, webpage


@dataclass
class CollectContext:
    client: httpx.Client
    now: datetime                       # 지금 시각 (UTC)
    log: logging.Logger = field(default_factory=lambda: logging.getLogger("reporter.collect"))


COLLECTORS = {
    "rss": rss.collect,
    "webpage": webpage.collect,
    "github_releases": github_releases.collect,
    "arxiv": arxiv.collect,
    "hf_papers": hf_papers.collect,
    "semantic_scholar": semantic_scholar.collect,
    "sample": sample.collect,
}
