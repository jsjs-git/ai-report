"""카카오톡 채널 — '나에게 보내기'로 핵심 3줄 + [웹 리포트 보기] 버튼을 보내요.

사용하는 카카오 API
  - 토큰 갱신 : POST https://kauth.kakao.com/oauth/token  (grant_type=refresh_token)
  - 나에게 보내기: POST https://kapi.kakao.com/v2/api/talk/memo/default/send  (기본 텍스트 템플릿)

필요한 비밀값: KAKAO_REST_API_KEY, (사용 시) KAKAO_CLIENT_SECRET, 리프레시 토큰
버튼 링크 주소의 도메인은 카카오 개발자 사이트 > 내 앱 > 플랫폼 > Web 에 등록해야 동작해요.

설정 예:
  kakao:
    enabled: true
    summary_lines: 3
    button_title: "웹 리포트 보기"
"""

from __future__ import annotations

import json
import os

import httpx

from ..errors import DeliveryError, KakaoAuthError
from ..http import make_client
from ..models import Report
from ..token_store import TokenStore

TOKEN_URL = "https://kauth.kakao.com/oauth/token"
MEMO_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
TEXT_LIMIT = 200  # 텍스트 템플릿 글자 수 제한


# ── 메시지 만들기 ──────────────────────────────────────────────────
def build_text(report: Report, lines: int = 3, limit: int = TEXT_LIMIT) -> str:
    """'[제목] 날짜' + 핵심 n줄. 글자 수 제한을 넘으면 각 줄을 고르게 줄여요."""
    label = f" {report.label}" if report.label else (" 주간" if report.mode == "weekly" else "")
    head = f"[{report.title}] {report.date.month}/{report.date.day}{label}"
    bullets = [b for b in report.highlights[:lines] if b] or ([report.one_liner] if report.one_liner else [])
    if not bullets:
        return head[:limit]

    def compose(items: list[str]) -> str:
        return head + "\n" + "\n".join(f"• {b}" for b in items)

    text = compose(bullets)
    if len(text) > limit:
        overhead = len(head) + 1 + len(bullets) * 3  # 줄바꿈 + "• "
        per_line = max(8, (limit - overhead) // len(bullets))
        bullets = [b if len(b) <= per_line else b[: per_line - 1] + "…" for b in bullets]
        text = compose(bullets)
    return text[:limit]


def build_template(report: Report, ch: dict) -> dict:
    url = report.web_url or report.archive_url
    if not url and report.sections:
        first = next((it for s in report.sections for it in s.items), None)
        url = first.url if first else ""
    return {
        "object_type": "text",
        "text": build_text(report, int(ch.get("summary_lines", 3))),
        "link": {"web_url": url, "mobile_web_url": url},
        "button_title": ch.get("button_title", "웹 리포트 보기")[:14],
    }


# ── 카카오 API ────────────────────────────────────────────────────
def refresh_access_token(client: httpx.Client, rest_api_key: str, refresh_token: str,
                         client_secret: str | None = None) -> tuple[str, str | None, int | None]:
    """리프레시 토큰으로 새 액세스 토큰을 받아요.
    돌려주는 값: (액세스 토큰, 새 리프레시 토큰 또는 None, 새 리프레시 토큰 유효기간(초) 또는 None)"""
    data = {"grant_type": "refresh_token", "client_id": rest_api_key, "refresh_token": refresh_token}
    if client_secret:
        data["client_secret"] = client_secret
    resp = client.post(TOKEN_URL, data=data)
    if resp.status_code >= 400:
        try:
            err = resp.json()
        except ValueError:
            err = {}
        raise KakaoAuthError(
            f"토큰 갱신 실패 ({resp.status_code} {err.get('error', '')}: {err.get('error_description', '')}). "
            "리프레시 토큰이 만료됐을 수 있어요."
        )
    body = resp.json()
    return body["access_token"], body.get("refresh_token"), body.get("refresh_token_expires_in")


def send_memo(client: httpx.Client, access_token: str, template: dict) -> None:
    resp = client.post(
        MEMO_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        data={"template_object": json.dumps(template, ensure_ascii=False)},
    )
    if resp.status_code == 401:
        raise KakaoAuthError("액세스 토큰이 거부됐어요. 재인증이 필요해요.")
    if resp.status_code == 403:
        raise KakaoAuthError("'카카오톡 메시지 전송(talk_message)' 동의가 필요해요. 재인증 시 동의해 주세요.")
    if resp.status_code >= 400:
        raise DeliveryError(f"카카오톡 전송 실패 ({resp.status_code}): {resp.text[:200]}")
    if resp.json().get("result_code") != 0:
        raise DeliveryError(f"카카오톡 전송 결과가 이상해요: {resp.text[:200]}")


# ── 채널 진입점 ────────────────────────────────────────────────────
def send(report: Report, ch: dict, ctx, client: httpx.Client | None = None,
         store: TokenStore | None = None) -> str:
    template = build_template(report, ch)
    if ctx.dry_run:
        path = ctx.out_dir / f"{report.topic}-{report.slug}-kakao.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(template, ensure_ascii=False, indent=2), encoding="utf-8")
        preview = template["text"].replace("\n", " / ")
        return f"미리보기 저장 → {path}  ({len(template['text'])}자: {preview})"

    rest_key = os.environ.get("KAKAO_REST_API_KEY")
    if not rest_key:
        raise DeliveryError("KAKAO_REST_API_KEY 가 필요해요. (.env 확인)")
    store = store or TokenStore()
    own_client = client is None
    client = client or make_client()
    try:
        access, new_refresh, expires = refresh_access_token(
            client, rest_key, store.load_refresh(), os.environ.get("KAKAO_CLIENT_SECRET") or None
        )
        store.save(access_token=access, refresh_token=new_refresh, refresh_expires_in=expires)
        if new_refresh:
            ctx.log.info("카카오 리프레시 토큰이 새로 발급되어 저장했어요.")
        send_memo(client, access, template)
    finally:
        if own_client:
            client.close()
    return "나에게 보내기 완료"
