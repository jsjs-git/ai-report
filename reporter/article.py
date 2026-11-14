"""글 페이지에서 본문과 발행 날짜를 뽑아요. (요약 재료 + 날짜 확인용)"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from bs4 import BeautifulSoup

from .http import get

_MONTHS = (
    r"Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?"
    r"|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?"
)
_TEXT_DATE = re.compile(rf"\b({_MONTHS})\.? (\d{{1,2}}), (\d{{4}})\b")


def parse_date(value: str | None) -> datetime | None:
    """여러 모양의 날짜 문자열을 datetime(UTC)으로 바꿔요. 모르면 None."""
    if not value:
        return None
    value = value.strip()
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%d %B %Y"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    m = _TEXT_DATE.search(value)
    if m:
        month = m.group(1)[:3]
        try:
            return datetime.strptime(f"{month} {m.group(2)} {m.group(3)}", "%b %d %Y").replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def extract_date(soup: BeautifulSoup) -> datetime | None:
    """페이지 안의 날짜 정보를 순서대로 찾아봐요."""
    for attrs in (
        {"property": "article:published_time"},
        {"name": "article:published_time"},
        {"itemprop": "datePublished"},
        {"name": "date"},
        {"name": "publish-date"},
    ):
        tag = soup.find("meta", attrs=attrs)
        if tag and (dt := parse_date(tag.get("content"))):
            return dt
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        for obj in data if isinstance(data, list) else [data]:
            if isinstance(obj, dict) and (dt := parse_date(obj.get("datePublished"))):
                return dt
    tag = soup.find("time", attrs={"datetime": True})
    if tag and (dt := parse_date(tag["datetime"])):
        return dt
    return None


def extract_text(soup: BeautifulSoup) -> str:
    """메뉴·광고 등을 빼고 본문 글만 뽑아요."""
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside", "form", "svg"]):
        tag.decompose()
    container = soup.find("article") or soup.find("main") or soup.body or soup
    lines = [ln.strip() for ln in container.get_text("\n").splitlines()]
    return "\n".join(ln for ln in lines if ln)


def extract_title(soup: BeautifulSoup) -> str:
    """글의 진짜 제목 (공유용 og:title → <title> 순서)."""
    tag = soup.find("meta", attrs={"property": "og:title"}) or soup.find("meta", attrs={"name": "twitter:title"})
    if tag and tag.get("content"):
        return " ".join(tag["content"].split())
    if soup.title and soup.title.string:
        return " ".join(soup.title.string.split())
    return ""


def fetch_article(client, url: str, max_chars: int = 15000) -> tuple[str, datetime | None, str]:
    """글 페이지를 읽어서 (본문, 발행일, 제목)을 돌려줘요."""
    resp = get(client, url)
    soup = BeautifulSoup(resp.text, "html.parser")
    published = extract_date(soup)
    title = extract_title(soup)
    text = extract_text(soup)
    if published is None:
        # 날짜 정보가 숨어 있지 않은 페이지: 본문 앞부분의 "October 8, 2026" 같은 표기를 찾아봐요
        m = _TEXT_DATE.search(text[:3000])
        if m:
            published = parse_date(m.group(0))
    if len(text) > max_chars:
        text = text[:max_chars] + "\n…(원문이 길어 앞부분만 포함)"
    return text, published, title


def strip_html(html: str) -> str:
    if not html:
        return ""
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
