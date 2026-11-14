"""전체 흐름: 수집 → 중복 제거 → 걸러내기 → AI 요약 → 리포트 → 발송

주제가 바뀌어도 이 흐름은 그대로예요. 무엇을 모을지는 topics/*.yaml 이 정해요.
"""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from . import ROOT, filters
from .article import fetch_article
from .collectors import COLLECTORS, CollectContext, semantic_scholar
from .collectors.webpage import looks_generic
from .config import load_env, load_topic
from .delivery import DeliveryContext, deliver_all, enabled_channels
from .http import make_client
from .models import Item, Report, ReportSection
from .renderer import Renderer
from .state import State
from .summarizer import Summarizer, writing_instructions
from .theme import load_theme

log = logging.getLogger("reporter")

_IMPORTANCE_RANK = {"상": 0, "중": 1, "하": 2}


@dataclass
class RunOptions:
    topic: str
    mode: str = "daily"              # daily | weekly
    dry_run: bool = False            # True면 실제로 보내지 않고 out/ 에 미리보기만 저장
    no_summary: bool = False         # True면 AI 요약 없이 진행
    mark_seen: bool = False          # True면 지금 있는 글을 '이미 본 것'으로 기록만 (첫 실행용)
    stage: str = "all"               # all(한 번에) | collect(수집 후 파일 저장) | send(파일 읽어 발송)
    data_dir: Path | None = None
    out_dir: Path | None = None
    site_dir: Path | None = None
    now: datetime | None = None


@dataclass
class RunResult:
    report: Report | None
    results: dict[str, str] = field(default_factory=dict)
    message: str = ""

    @property
    def failed(self) -> bool:
        return any(v.startswith("실패") for v in self.results.values())


def run(opts: RunOptions) -> RunResult:
    load_env()
    cfg, warnings = load_topic(opts.topic)
    for w in warnings:
        log.warning("설정 참고: %s", w)

    now = opts.now or datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo(cfg["timezone"])).date()
    renderer = Renderer(load_theme(cfg["theme"]), cfg["timezone"])
    summarizer = Summarizer(cfg, force_disable=opts.no_summary)
    out_dir = Path(opts.out_dir or ROOT / "out")
    site_dir = Path(opts.site_dir or ROOT / "docs")
    pending = out_dir / f"{cfg['topic']}-pending.json"

    with State(cfg["topic"], opts.data_dir) as state, make_client() as client:
        if opts.stage == "send":
            if not pending.exists():
                return RunResult(None, message=f"보낼 파일이 없어요: {pending} (먼저 --stage collect 실행)")
            report, selected = load_pending(pending, cfg, summarizer)
        elif opts.mode == "weekly":
            report = build_weekly(cfg, state, summarizer, today)
            selected: list[Item] = []
        else:
            report, selected, skipped = build_daily(cfg, state, summarizer, client, now, today, opts)
            if opts.mark_seen:
                state.mark_skipped(selected + skipped)
                return RunResult(None, message=f"현재 글 {len(selected) + len(skipped)}건을 '이미 본 것'으로 기록했어요. (발송 안 함)")
            if not opts.dry_run:
                state.mark_skipped(skipped)

        if report.is_empty and cfg.get("skip_if_empty", True):
            pending.unlink(missing_ok=True)  # 지난번 파일이 잘못 발송되지 않게
            return RunResult(report, message="새 소식이 없어서 이번에는 보내지 않아요.")

        if opts.stage == "collect":
            write_pending(pending, report, cfg)
            return RunResult(report, message=f"수집 완료 {report.item_count}건 → {pending}")

        if not enabled_channels(cfg):
            return RunResult(report, message="켜진 발송 채널이 없어요. (설정의 delivery 확인)")

        ctx = DeliveryContext(cfg=cfg, renderer=renderer, dry_run=opts.dry_run, out_dir=out_dir, site_dir=site_dir)
        results = deliver_all(report, ctx)

        # 모든 채널이 성공해야 '보낸 것'으로 기록 (하나라도 실패하면 같은 파일로 다시 보낼 수 있게)
        if not opts.dry_run and selected and all(v.startswith("성공") for v in results.values()):
            state.mark_sent(selected, report.date)
            if opts.stage == "send":
                pending.replace(pending.with_suffix(".done.json"))  # 같은 파일을 두 번 보내지 않게
        return RunResult(report, results)


# ── 데일리 ─────────────────────────────────────────────────────────
def build_daily(cfg, state, summarizer, client, now, today, opts) -> tuple[Report, list[Item], list[Item]]:
    ctx = CollectContext(client=client, now=now)
    sections: list[ReportSection] = []
    selected_all: list[Item] = []
    skipped_all: list[Item] = []

    for sec in cfg["sections"]:
        kind = sec.get("kind", "news")
        log.info("▶ %s 수집", sec["title"])
        raw = collect_section(sec, ctx)
        items = state.filter_new(merge_duplicates(raw))
        log.info("  새 항목 %d건 (이미 본 항목 제외)", len(items))

        if kind == "news" and not opts.mark_seen:
            items, skipped = prepare_news(items, sec, cfg, ctx)
            skipped_all += skipped
        elif sec.get("filters", {}).get("enrich_citations") and not opts.mark_seen:
            semantic_scholar.enrich(items, ctx)

        if opts.mark_seen:
            selected = items  # 첫 실행: 거르지 않고 전부 '본 것'으로
        else:
            selected = filters.select(sec, items, now)
            log.info("  리포트에 실을 항목 %d건", len(selected))
        sections.append(ReportSection(sec["id"], sec["title"], kind, selected))
        selected_all += selected

    report = Report(topic=cfg["topic"], title=cfg["title"], mode="daily", date=today, sections=sections,
                    label=cfg.get("report_label", ""))
    if opts.mark_seen or not selected_all or opts.stage == "collect":
        return report, selected_all, skipped_all  # collect 단계: 요약은 Claude가 파일에 직접 채워요
    summarize_report(report, cfg, summarizer)
    return report, selected_all, skipped_all


def summarize_report(report: Report, cfg: dict, summarizer: Summarizer) -> None:
    """요약이 빈 항목을 채우고, 중요도 순으로 정렬하고, 한 줄 요약·핵심 3줄을 만들어요."""
    items = [it for s in report.sections for it in s.items]
    log.info("▶ AI 요약 (%d건)%s", len(items), "" if summarizer.enabled else " — 간단 요약 모드")
    summarizer.summarize_items(items, {s["id"]: s.get("kind", "news") for s in cfg["sections"]})
    for section in report.sections:  # 같은 묶음 안에서는 중요한 것부터
        section.items.sort(key=lambda it: _IMPORTANCE_RANK.get(it.summary.importance, 1) if it.summary else 1)
    if not (report.one_liner and report.highlights):
        report.one_liner, report.highlights = summarizer.digest(_by_importance(items))


# ── 두 단계 실행: collect → (Claude가 요약 작성) → send ─────────────────
def write_pending(path: Path, report: Report, cfg: dict) -> None:
    data = {
        "_설명": "instructions 대로 각 item의 summary와 맨 위 one_liner·highlights를 채운 뒤 --stage send 로 발송해요.",
        "topic": report.topic,
        "date": report.date.isoformat(),
        "instructions": writing_instructions(cfg),
        "one_liner": "",
        "highlights": [],
        "sections": [
            {"id": s.id, "title": s.title, "kind": s.kind, "items": [it.to_dict(text_limit=8000) for it in s.items]}
            for s in report.sections
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_pending(path: Path, cfg: dict, summarizer: Summarizer) -> tuple[Report, list[Item]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    # "exclude": true 표시된 항목(기술 소식이 아닌 것 등)은 빼고 보내요
    sections = [ReportSection(s["id"], s["title"], s["kind"],
                              [Item.from_dict(d) for d in s["items"] if not d.get("exclude")])
                for s in data["sections"]]
    report = Report(topic=cfg["topic"], title=cfg["title"], mode="daily", date=date.fromisoformat(data["date"]),
                    sections=sections, label=cfg.get("report_label", ""),
                    one_liner=data.get("one_liner", ""), highlights=data.get("highlights", [])[:3])
    summarize_report(report, cfg, summarizer)  # 비어 있는 요약만 채워요 (Claude가 쓴 건 그대로)
    return report, [it for s in sections for it in s.items]


def collect_section(sec: dict, ctx: CollectContext) -> list[Item]:
    items: list[Item] = []
    for src in sec.get("sources", []):
        if src.get("enabled", True) is False:
            continue
        name = src.get("name", src["type"])
        try:
            got = COLLECTORS[src["type"]](src, sec, ctx)
            got = filters.source_keyword_filter(got, src)
            log.info("  · %s: %d건", name, len(got))
            items += got
        except Exception as exc:  # 한 소스가 실패해도 나머지는 계속
            log.warning("  · %s 수집 실패 (건너뜀): %s", name, exc)
    return items


def merge_duplicates(items: list[Item]) -> list[Item]:
    """같은 글(같은 주소·같은 논문 번호)이 여러 소스에서 오면 하나로 합쳐요. 빈 칸은 서로 채워요."""
    merged: dict[str, Item] = {}
    for it in items:
        cur = merged.get(it.uid)
        if cur is None:
            merged[it.uid] = it
            continue
        for attr in ("published", "citations", "upvotes", "summary"):
            if getattr(cur, attr) is None and getattr(it, attr) is not None:
                setattr(cur, attr, getattr(it, attr))
        if len(it.text) > len(cur.text):
            cur.text = it.text
        if it.venue and it.venue not in cur.venue:
            cur.venue = f"{cur.venue} · {it.venue}" if cur.venue else it.venue
        cur.organizations = sorted(set(cur.organizations) | set(it.organizations))
        cur.authors = cur.authors or it.authors
    return list(merged.values())


def prepare_news(items: list[Item], sec: dict, cfg: dict, ctx: CollectContext) -> tuple[list[Item], list[Item]]:
    """소식 항목 다듬기: 너무 오래된 글은 빼고, 본문·날짜가 없는 글은 글 페이지에서 가져와요.
    돌려주는 값: (남은 항목, 오래돼서 넘긴 항목)"""
    lookback = sec.get("filters", {}).get("lookback_days", 2)
    sources = {s.get("name"): s for s in sec.get("sources", [])}
    max_chars = int(cfg["summary"].get("max_input_chars", 15000))

    fresh, skipped = [], []
    for it in items:
        (fresh if filters.within_days(it, lookback, ctx.now) else skipped).append(it)

    need_fetch = [it for it in fresh if it.published is None or len(it.text) < 800]

    def fetch(it: Item) -> None:
        try:
            text, published, title = fetch_article(ctx.client, it.url, max_chars)
            if len(text) > len(it.text):
                it.text = text
            it.published = it.published or published
            if title and looks_generic(it.title):
                it.title = title  # 목록의 링크 문구 대신 글의 진짜 제목
        except Exception as exc:
            log.debug("본문 가져오기 실패 %s: %s", it.url, exc)

    if need_fetch:
        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(fetch, need_fetch))

    kept = []
    for it in fresh:
        src = sources.get(it.source_name, {})
        if it.published is None and src.get("require_date"):
            skipped.append(it)          # 날짜 없는 페이지(분류 목록 등)는 제외
        elif not filters.within_days(it, lookback, ctx.now):
            skipped.append(it)          # 글을 열어 보니 오래된 글
        else:
            kept.append(it)
    return kept, skipped


# ── 주간 ──────────────────────────────────────────────────────────
def build_weekly(cfg, state, summarizer, today) -> Report:
    start = today - timedelta(days=6)
    items = state.items_between(start, today)
    log.info("▶ 주간 정리: %s ~ %s, 지난 리포트 항목 %d건", start, today, len(items))
    wcfg = cfg.get("weekly", {})
    min_rank = _IMPORTANCE_RANK.get(wcfg.get("min_importance", "중"), 1)
    per_section = int(wcfg.get("max_items_per_section", 8))

    sections = []
    chosen: list[Item] = []
    for sec in cfg["sections"]:
        sec_items = [it for it in items if it.section_id == sec["id"]
                     and _IMPORTANCE_RANK.get(it.summary.importance if it.summary else "중", 1) <= min_rank]
        sec_items = _by_importance(sec_items)[:per_section]
        sections.append(ReportSection(sec["id"], sec["title"], sec.get("kind", "news"), sec_items))
        chosen += sec_items

    report = Report(topic=cfg["topic"], title=cfg["title"], mode="weekly", date=today, sections=sections)
    if chosen:
        report.one_liner, report.highlights, report.trends = summarizer.weekly(chosen)
    return report


def _by_importance(items: list[Item]) -> list[Item]:
    return sorted(items, key=lambda it: _IMPORTANCE_RANK.get(it.summary.importance, 1) if it.summary else 1)
