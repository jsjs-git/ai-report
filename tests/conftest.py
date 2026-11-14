import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from reporter.models import Item, Report, ReportSection, Summary  # noqa: E402


@pytest.fixture
def now():
    return datetime(2026, 11, 10, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def sample_report():
    s = Summary(
        title_ko="테스트 제목",
        headline=["첫째 줄이에요.", "둘째 줄이에요.", "셋째 줄이에요."],
        background="배경 설명", changes="바뀐 점", why_it_matters="중요한 이유",
        glossary=[{"term": "하네스", "meaning": "AI와 도구를 연결하는 틀"}],
        importance="상",
    )
    news = Item(section_id="updates", source_name="소스", group="Anthropic", title="Title",
                url="https://example.com/a", summary=s)
    paper = Item(section_id="papers", source_name="arXiv", group="논문", title="Paper", tier="new",
                 url="https://arxiv.org/abs/0000.00001", upvotes=30, paper_ids={"arxiv": "0000.00001"},
                 summary=s.model_copy(update={"paper_idea": "비유 설명"}))
    from datetime import date
    return Report(
        topic="test", title="테스트 리포트", mode="daily", date=date(2026, 11, 10),
        sections=[ReportSection("updates", "업데이트", "news", [news]),
                  ReportSection("papers", "논문", "papers", [paper])],
        one_liner="한 줄 요약", highlights=["핵심 하나", "핵심 둘", "핵심 셋"],
    )
