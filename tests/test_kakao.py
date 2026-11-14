import json
from types import SimpleNamespace

import httpx
import pytest

from reporter.delivery import kakao
from reporter.errors import KakaoAuthError
from reporter.token_store import TokenStore


def test_text_fits_limit_and_has_three_lines(sample_report):
    sample_report.highlights = ["아주 긴 핵심 문장입니다 " * 10] * 3
    text = kakao.build_text(sample_report, lines=3)
    assert len(text) <= kakao.TEXT_LIMIT
    assert text.count("\n• ") == 3
    assert text.startswith("[테스트 리포트] 11/10")


def test_template_uses_web_url_and_button(sample_report):
    sample_report.web_url = "https://me.github.io/r/test/reports/2026-11-10-daily.html"
    tpl = kakao.build_template(sample_report, {"button_title": "웹 리포트 보기"})
    assert tpl["object_type"] == "text"
    assert tpl["link"]["web_url"] == sample_report.web_url
    assert tpl["button_title"] == "웹 리포트 보기"


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_refresh_saves_new_refresh_token(tmp_path, monkeypatch, sample_report):
    monkeypatch.setenv("KAKAO_REST_API_KEY", "key")
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    store = TokenStore(tmp_path / "tok.json")
    store.save(refresh_token="old-refresh")
    sent = {}

    def handler(request: httpx.Request):
        if "oauth/token" in str(request.url):
            assert b"refresh_token=old-refresh" in request.content
            return httpx.Response(200, json={"access_token": "acc", "refresh_token": "new-refresh",
                                             "refresh_token_expires_in": 5184000})
        sent["template"] = json.loads(httpx.QueryParams(request.content.decode())["template_object"])
        assert request.headers["Authorization"] == "Bearer acc"
        return httpx.Response(200, json={"result_code": 0})

    ctx = SimpleNamespace(dry_run=False, log=SimpleNamespace(info=lambda *a: None))
    kakao.send(sample_report, {}, ctx, client=_client(handler), store=store)
    assert store.load_refresh() == "new-refresh"
    assert sent["template"]["text"].startswith("[테스트 리포트]")


def test_refresh_keeps_old_token_when_none_returned(tmp_path, monkeypatch, sample_report):
    monkeypatch.setenv("KAKAO_REST_API_KEY", "key")
    store = TokenStore(tmp_path / "tok.json")
    store.save(refresh_token="keep-me")

    def handler(request):
        if "oauth/token" in str(request.url):
            return httpx.Response(200, json={"access_token": "acc"})
        return httpx.Response(200, json={"result_code": 0})

    ctx = SimpleNamespace(dry_run=False, log=SimpleNamespace(info=lambda *a: None))
    kakao.send(sample_report, {}, ctx, client=_client(handler), store=store)
    assert store.load_refresh() == "keep-me"


def test_expired_refresh_raises_auth_error(tmp_path, monkeypatch, sample_report):
    monkeypatch.setenv("KAKAO_REST_API_KEY", "key")
    store = TokenStore(tmp_path / "tok.json")
    store.save(refresh_token="expired")

    def handler(request):
        return httpx.Response(401, json={"error": "invalid_grant", "error_description": "expired"})

    ctx = SimpleNamespace(dry_run=False, log=SimpleNamespace(info=lambda *a: None))
    with pytest.raises(KakaoAuthError):
        kakao.send(sample_report, {}, ctx, client=_client(handler), store=store)


def test_missing_token_raises_auth_error(tmp_path, monkeypatch):
    monkeypatch.delenv("KAKAO_REFRESH_TOKEN", raising=False)
    with pytest.raises(KakaoAuthError):
        TokenStore(tmp_path / "none.json").load_refresh()
