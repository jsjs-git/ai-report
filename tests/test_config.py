import pytest

from reporter.config import TOPICS_DIR, list_topics, load_topic, validate
from reporter.errors import ConfigError


@pytest.mark.parametrize("path", sorted(TOPICS_DIR.glob("*.yaml")), ids=lambda p: p.name)
def test_all_topic_files_are_valid(path):
    """topics/ 의 모든 설정 파일(양식 포함)이 문제없이 읽혀야 해요."""
    cfg, _ = load_topic(str(path))
    assert cfg["sections"]


def test_list_topics_hides_template():
    names = list_topics()
    assert "ai_trends" in names and "_template" not in names


def test_env_expansion(monkeypatch):
    monkeypatch.setenv("REPORT_EMAIL_TO", "me@test.com")
    monkeypatch.setenv("REPORT_BASE_URL", "https://x.github.io/r/")
    cfg, _ = load_topic("ai_trends")
    assert cfg["delivery"]["email"]["to"] == ["me@test.com"]
    assert cfg["delivery"]["web"]["base_url"] == "https://x.github.io/r/"


def test_defaults_are_filled():
    cfg, _ = load_topic("demo")
    assert cfg["timezone"] == "Asia/Seoul"
    assert cfg["summary"]["detail_level"] == "detailed"


def test_unknown_source_type_is_rejected():
    cfg = {"topic": "x", "title": "x", "delivery": {},
           "sections": [{"id": "a", "title": "A", "sources": [{"type": "nope"}]}]}
    with pytest.raises(ConfigError, match="nope"):
        validate(cfg)


def test_kakao_without_web_warns():
    cfg = {"topic": "x", "title": "x",
           "sections": [{"id": "a", "title": "A", "sources": [{"type": "rss", "url": "u"}]}],
           "delivery": {"kakao": {"enabled": True}, "web": {"enabled": False}}}
    warnings = validate(cfg)
    assert any("카카오" in w for w in warnings)
