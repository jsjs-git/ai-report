from datetime import timedelta

from reporter import filters
from reporter.models import Item
from reporter.pipeline import merge_duplicates

PAPER_FILTERS = {
    "keywords": ["agent harness", "prompting"],
    "new": {"lookback_days": 7, "min_upvotes": 10, "labs": ["Anthropic"], "max_items": 5},
    "proven": {"lookback_days": 365, "min_citations": 50, "venues": ["NeurIPS", "ICLR"], "max_items": 2},
}


def paper(now, days_old=1, **kw):
    base = dict(section_id="papers", source_name="arXiv", title="An agent harness study",
                url=f"https://arxiv.org/abs/{kw.pop('aid', '1')}", published=now - timedelta(days=days_old))
    base.update(kw)
    return Item(**base)


def test_keyword_hits_case_insensitive_and_word_start(now):
    it = Item(section_id="s", source_name="x", title="New Prompting tricks", url="u", text="said hello")
    assert filters.keyword_hits(it, ["prompting"]) == ["prompting"]
    assert filters.keyword_hits(it, ["AI"]) == []  # 'said' 안의 ai는 무시


def test_new_paper_by_upvotes(now):
    assert filters.classify_paper(paper(now, upvotes=12), PAPER_FILTERS, now) == "new"
    assert filters.classify_paper(paper(now, upvotes=3), PAPER_FILTERS, now) is None


def test_new_paper_by_lab_or_accepted_venue(now):
    assert filters.classify_paper(paper(now, organizations=["Anthropic"]), PAPER_FILTERS, now) == "new"
    assert filters.classify_paper(paper(now, venue="Accepted at ICLR 2027"), PAPER_FILTERS, now) == "new"


def test_venue_matching_rules():
    venues = ["NeurIPS", "ICLR", "ACL", "Nature", "Science"]
    assert filters.venue_match("Accepted at NeurIPS 2026", venues) == "NeurIPS"
    assert filters.venue_match("Findings of ACL 2026", venues) == "ACL"
    assert filters.venue_match("Nature", venues) == "Nature"
    assert filters.venue_match("Neural Information Processing Systems", venues) == "NeurIPS"
    assert filters.venue_match("To be published on Annual Review Biomedical Data Science", venues) is None
    assert filters.venue_match("Nature Machine Intelligence", venues) is None
    assert filters.venue_match("Accepted at the XYZ Workshop at NeurIPS", venues) is None


def test_under_review_is_not_accepted(now):
    assert filters.venue_match("Under review at NeurIPS", ["NeurIPS"]) is None
    assert filters.classify_paper(paper(now, venue="Submitted to NeurIPS"), PAPER_FILTERS, now) is None


def test_proven_paper_by_citations(now):
    assert filters.classify_paper(paper(now, days_old=100, citations=80), PAPER_FILTERS, now) == "proven"
    assert filters.classify_paper(paper(now, days_old=400, citations=80), PAPER_FILTERS, now) is None


def test_select_papers_caps_each_tier(now):
    items = [paper(now, aid=str(i), upvotes=20 + i) for i in range(8)]
    items += [paper(now, aid=f"p{i}", days_old=200, citations=100 + i) for i in range(5)]
    section = {"kind": "papers", "filters": PAPER_FILTERS}
    chosen = filters.select(section, items, now)
    assert [it.tier for it in chosen].count("new") == 5
    assert [it.tier for it in chosen].count("proven") == 2
    assert chosen[0].upvotes == 27  # 추천수 높은 순


def test_select_news_lookback_and_order(now):
    def news(h, title):
        return Item(section_id="n", source_name="s", title=title, url=f"https://e.com/{title}",
                    published=now - timedelta(hours=h))
    items = [news(5, "b"), news(1, "a"), news(100, "old")]
    chosen = filters.select({"kind": "news", "filters": {"lookback_days": 2}}, items, now)
    assert [it.title for it in chosen] == ["a", "b"]


def test_select_news_max_per_group(now):
    items = [Item(section_id="n", source_name="s", group=g, title=f"{g}{h}", url=f"https://e.com/{g}{h}",
                  published=now - timedelta(hours=h)) for h, g in enumerate("GGGGA", start=1)]
    chosen = filters.select({"kind": "news", "filters": {"lookback_days": 7, "max_per_group": 2}}, items, now)
    assert [it.title for it in chosen] == ["G1", "G2", "A5"]


def test_separate_count_source_skips_group_limit(now):
    items = [Item(section_id="n", source_name="블로그", group="A", title=f"blog{h}", url=f"https://e.com/b{h}",
                  published=now - timedelta(hours=h)) for h in (1, 2, 3)]
    items += [Item(section_id="n", source_name="릴리스 노트", group="A", title=f"rel{h}", url=f"https://e.com/r{h}",
                   published=now - timedelta(hours=h)) for h in (4, 5)]
    section = {"kind": "news", "filters": {"lookback_days": 7, "max_per_group": 2},
               "sources": [{"name": "블로그"}, {"name": "릴리스 노트", "separate_count": True}]}
    assert [it.title for it in filters.select(section, items, now)] == ["blog1", "blog2", "rel4", "rel5"]


def test_merge_duplicates_fills_blanks(now):
    a = paper(now, aid="2611.1", source_name="arXiv", venue="Accepted at ICLR", paper_ids={"arxiv": "2611.1"})
    b = paper(now, aid="2611.1", source_name="HF", upvotes=40, paper_ids={"arxiv": "2611.1"},
              organizations=["Meta"])
    merged = merge_duplicates([a, b])
    assert len(merged) == 1
    assert merged[0].upvotes == 40 and "ICLR" in merged[0].venue and merged[0].organizations == ["Meta"]


def test_paper_needs_title_hit_or_two_keywords(now):
    f = {**PAPER_FILTERS, "keywords": ["agent harness", "prompting", "tool use"], "min_keyword_hits": 2}
    section = {"kind": "papers", "filters": f}
    only_one_in_abstract = paper(now, aid="a", title="Fast video rendering", text="we also try prompting", upvotes=50)
    two_in_abstract = paper(now, aid="b", title="A new method", text="prompting and tool use", upvotes=50)
    title_hit = paper(now, aid="c", title="Prompting at scale", text="", upvotes=50)
    chosen = {it.title for it in filters.select(section, [only_one_in_abstract, two_in_abstract, title_hit], now)}
    assert chosen == {"A new method", "Prompting at scale"}


def test_source_exclude_title():
    items = [Item(section_id="s", source_name="x", title=t, url=f"https://e.com/{i}")
             for i, t in enumerate(["Introducing GPT-9", "How Acme ships faster with OpenAI", "Shield helps teams with OpenAI"])]
    src = {"type": "rss", "exclude_title": r"(with|using) (OpenAI|ChatGPT)$|^How .+ (uses|ships)\b"}
    assert [it.title for it in filters.source_keyword_filter(items, src)] == ["Introducing GPT-9"]


def test_generic_link_text_detected():
    from reporter.collectors.webpage import looks_generic
    assert looks_generic("FEATURED") and looks_generic("Learn More")
    assert not looks_generic("Introducing a new open model for agents")


def test_uid_ignores_tracking_params():
    a = Item(section_id="s", source_name="x", title="t", url="https://e.com/post/?utm_source=x")
    b = Item(section_id="s", source_name="y", title="t", url="https://E.com/post")
    assert a.uid == b.uid
