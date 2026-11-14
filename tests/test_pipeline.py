"""체험판 주제로 전체 흐름을 실제로 돌려봐요. (인터넷·API 키 불필요)"""

import json

from reporter.config import load_topic
from reporter.pipeline import RunOptions, run


def _run(tmp_path, monkeypatch, **kw):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    opts = RunOptions(topic="demo", dry_run=True, data_dir=tmp_path / "data",
                      out_dir=tmp_path / "out", site_dir=tmp_path / "site", **kw)
    return run(opts)


def test_demo_dry_run_creates_all_previews(tmp_path, monkeypatch):
    result = _run(tmp_path, monkeypatch)
    assert result.report.item_count == 5
    assert set(result.results) == {"web", "email", "kakao"}
    assert all(v.startswith("성공") for v in result.results.values()), result.results

    out = tmp_path / "out"
    page = next((out / "site" / "demo" / "reports").glob("*-daily.html"))
    html = page.read_text(encoding="utf-8")
    assert "용어 풀이" in html and "검증된 논문" in html and "신규 주목" in html
    assert (out / "site" / "index.html").exists()
    assert (out / "site" / "demo" / "index.html").exists()

    kakao = json.loads(next(out.glob("demo-*-kakao.json")).read_text(encoding="utf-8"))
    assert len(kakao["text"]) <= 200
    assert kakao["link"]["web_url"].startswith("https://example.github.io/mailing_service/demo/reports/")

    email_html = next(out.glob("demo-*-email.html")).read_text(encoding="utf-8")
    assert "자세한 설명 읽기" in email_html


def test_two_stage_collect_then_send(tmp_path, monkeypatch):
    """collect → (Claude가 파일에 요약 작성) → send 흐름."""
    collected = _run(tmp_path, monkeypatch, stage="collect")
    pending = tmp_path / "out" / "demo-pending.json"
    data = json.loads(pending.read_text(encoding="utf-8"))
    assert "instructions" in data and "headline" in data["instructions"]
    assert collected.results == {}  # 수집 단계에서는 아무것도 보내지 않아요

    # Claude가 하는 일 흉내: 한 줄 요약·핵심 3줄과 첫 항목 요약을 채움
    data["one_liner"] = "이번 주 한 줄"
    data["highlights"] = ["하나", "둘", "셋"]
    data["sections"][0]["items"][0]["summary"]["title_ko"] = "Claude가 쓴 제목"
    data["sections"][0]["items"][1]["exclude"] = True  # 기술 소식이 아니라고 판단한 항목
    pending.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    sent = _run(tmp_path, monkeypatch, stage="send")
    assert sent.report.item_count == collected.report.item_count - 1
    assert sent.report.one_liner == "이번 주 한 줄"
    assert any(it.summary.title_ko == "Claude가 쓴 제목" for s in sent.report.sections for it in s.items)
    kakao = json.loads(next((tmp_path / "out").glob("demo-*-kakao.json")).read_text(encoding="utf-8"))
    assert "• 하나" in kakao["text"]


def test_include_rule_goes_into_instructions():
    from reporter.summarizer import writing_instructions
    cfg, _ = load_topic("ai_trends")
    text = writing_instructions(cfg)
    assert "항목 고르기" in text and '"exclude": true' in text and "상장" in text


def test_send_without_pending_file(tmp_path, monkeypatch):
    result = _run(tmp_path, monkeypatch, stage="send")
    assert "보낼 파일이 없어요" in result.message


def test_dry_run_does_not_mark_sent(tmp_path, monkeypatch):
    _run(tmp_path, monkeypatch)
    again = _run(tmp_path, monkeypatch)
    assert again.report.item_count == 5  # 미리보기는 기록하지 않으니 또 나와요


def test_mark_seen_then_nothing_new(tmp_path, monkeypatch):
    first = _run(tmp_path, monkeypatch, mark_seen=True)
    assert "이미 본 것" in first.message
    second = _run(tmp_path, monkeypatch)
    assert second.report.item_count == 0


def test_channel_toggle(tmp_path, monkeypatch):
    """YAML에서 꺼진 채널은 실행되지 않아요."""
    import reporter.pipeline as pipeline
    cfg, warnings = load_topic("demo")
    cfg["delivery"]["kakao"]["enabled"] = False
    cfg["delivery"]["email"]["enabled"] = False
    monkeypatch.setattr(pipeline, "load_topic", lambda name: (cfg, warnings))
    result = _run(tmp_path, monkeypatch)
    assert set(result.results) == {"web"}
