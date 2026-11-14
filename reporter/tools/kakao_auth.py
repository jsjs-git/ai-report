"""카카오 처음 인증 도구 — 딱 한 번만 실행하면 돼요.

    python -m reporter.tools.kakao_auth

하는 일
  1) 브라우저에서 카카오 로그인·동의 화면을 열어요. (로그인과 동의는 직접 해 주세요)
  2) 동의가 끝나면 카카오가 이 컴퓨터(localhost)로 '인증 코드'를 돌려줘요.
  3) 인증 코드를 토큰으로 바꿔서 .secrets/kakao_token.json 에 저장해요.

미리 할 일 (README 6장)
  - .env 에 KAKAO_REST_API_KEY 입력
  - 카카오 개발자 사이트에서 Redirect URI 로 http://localhost:5000/callback 등록
  - 동의 항목에서 '카카오톡 메시지 전송(talk_message)' 설정
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode, urlparse

from ..config import load_env
from ..http import make_client
from ..token_store import TOKEN_FILE, TokenStore

AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
TOKEN_URL = "https://kauth.kakao.com/oauth/token"


def main() -> None:
    load_env()
    parser = argparse.ArgumentParser(description="카카오톡 '나에게 보내기' 처음 인증")
    parser.add_argument("--timeout", type=int, default=300, help="로그인을 기다리는 최대 시간(초)")
    parser.add_argument("--show", action="store_true", help="발급된 리프레시 토큰을 화면에 표시 (GitHub Secret 입력용)")
    args = parser.parse_args()

    rest_key = os.environ.get("KAKAO_REST_API_KEY")
    if not rest_key:
        sys.exit("✗ .env 파일에 KAKAO_REST_API_KEY 를 먼저 넣어 주세요. (README 6장)")
    redirect_uri = os.environ.get("KAKAO_REDIRECT_URI", "http://localhost:5000/callback")
    parsed = urlparse(redirect_uri)
    if parsed.hostname not in ("localhost", "127.0.0.1"):
        sys.exit("✗ 이 도구는 Redirect URI가 http://localhost:<포트>/... 형태일 때만 동작해요.")

    result: dict = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 (http.server 규칙)
            q = parse_qs(urlparse(self.path).query)
            if urlparse(self.path).path != parsed.path:
                self.send_response(404)
                self.end_headers()
                return
            result["code"] = (q.get("code") or [""])[0]
            result["error"] = (q.get("error_description") or q.get("error") or [""])[0]
            ok = bool(result["code"])
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "인증 완료! 이 창을 닫고 터미널로 돌아가세요." if ok else f"인증 실패: {result['error']}"
            self.wfile.write(f"<h2 style='font-family:sans-serif'>{msg}</h2>".encode("utf-8"))

        def log_message(self, *a):  # 요청 기록을 화면에 찍지 않기
            pass

    server = HTTPServer((parsed.hostname, parsed.port or 80), Handler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    url = AUTHORIZE_URL + "?" + urlencode({
        "client_id": rest_key,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "talk_message",
    })
    print("① 브라우저에서 카카오 로그인·동의 화면을 열어요. 직접 로그인하고 '동의'를 눌러 주세요.")
    print(f"   (창이 안 열리면 이 주소를 브라우저에 붙여넣기: {url})")
    webbrowser.open(url)
    thread.join(timeout=args.timeout)
    server.server_close()

    if not result.get("code"):
        sys.exit(f"✗ 인증 코드를 받지 못했어요. {result.get('error') or '시간 초과'}")

    print("② 인증 코드를 토큰으로 바꾸는 중…")
    data = {
        "grant_type": "authorization_code",
        "client_id": rest_key,
        "redirect_uri": redirect_uri,
        "code": result["code"],
    }
    if os.environ.get("KAKAO_CLIENT_SECRET"):
        data["client_secret"] = os.environ["KAKAO_CLIENT_SECRET"]
    with make_client() as client:
        resp = client.post(TOKEN_URL, data=data)
    if resp.status_code >= 400:
        sys.exit(f"✗ 토큰 발급 실패 ({resp.status_code}): {resp.text[:300]}")
    body = resp.json()
    if "talk_message" not in (body.get("scope") or ""):
        print("⚠ '카카오톡 메시지 전송' 동의가 빠졌어요. 동의 항목 설정을 확인하고 다시 실행해 주세요.")

    TokenStore().save(
        access_token=body["access_token"],
        refresh_token=body.get("refresh_token"),
        refresh_expires_in=body.get("refresh_token_expires_in"),
    )
    days = int(body.get("refresh_token_expires_in", 0)) // 86400
    print(f"③ 저장 완료 → {TOKEN_FILE}")
    print(f"   리프레시 토큰 유효기간: 약 {days}일 (사용할 때마다 만료가 가까우면 자동으로 새로 받아요)")
    if args.show:
        print("\n[GitHub Secret 'KAKAO_REFRESH_TOKEN' 에 넣을 값 — 다른 사람에게 보여주지 마세요]")
        print(body.get("refresh_token", "(없음)"))
    else:
        print("   GitHub Actions에서 쓰려면 --show 옵션으로 다시 실행하거나, 위 파일의 refresh_token 값을")
        print("   GitHub 저장소 Settings > Secrets > KAKAO_REFRESH_TOKEN 에 넣어 주세요.")


if __name__ == "__main__":
    main()
