"""카카오 토큰 보관함.

토큰 = 카카오가 "이 프로그램이 내 카톡으로 메시지를 보내도 된다"고 허락해 준 출입증.
  - 액세스 토큰 : 짧게(몇 시간) 쓰는 출입증 → 보낼 때마다 새로 받아요
  - 리프레시 토큰: 오래(약 두 달) 쓰는 출입증 → 새 액세스 토큰을 받는 데 써요.
                  만료가 가까워지면 카카오가 새것을 주고, 그때 자동으로 바꿔 저장해요.

저장 위치
  - 내 컴퓨터     : .secrets/kakao_token.json (git에 올라가지 않음)
  - GitHub Actions: 환경변수 KAKAO_REFRESH_TOKEN (GitHub Secret)
                    → 새 리프레시 토큰을 받으면 GitHub Secret도 자동으로 바꿔요.
                      (SECRETS_PAT 라는 이름의 GitHub 토큰이 필요, README 7장)
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import ROOT
from .errors import KakaoAuthError

log = logging.getLogger(__name__)

TOKEN_FILE = ROOT / ".secrets" / "kakao_token.json"
SECRET_NAME = "KAKAO_REFRESH_TOKEN"


class TokenStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path or TOKEN_FILE)

    def _read(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                log.warning("토큰 파일이 손상됐어요: %s", self.path)
        return {}

    def load_refresh(self) -> str:
        token = self._read().get("refresh_token") or os.environ.get(SECRET_NAME, "").strip()
        if not token:
            raise KakaoAuthError(
                "카카오 리프레시 토큰이 없어요. 먼저  python -m reporter.tools.kakao_auth  를 실행하세요."
            )
        return token

    def save(self, access_token: str | None = None, refresh_token: str | None = None,
             refresh_expires_in: int | None = None) -> None:
        """받은 토큰을 저장해요. refresh_token이 None이면 기존 값을 그대로 둬요."""
        data = self._read()
        now = datetime.now(timezone.utc).isoformat()
        if access_token:
            data["access_token"] = access_token
            data["access_saved_at"] = now
        if refresh_token:
            data["refresh_token"] = refresh_token
            data["refresh_saved_at"] = now
            if refresh_expires_in:
                data["refresh_expires_in"] = refresh_expires_in
        if not data:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        if refresh_token:
            os.environ[SECRET_NAME] = refresh_token
            if os.environ.get("GITHUB_ACTIONS") == "true":
                update_github_secret(SECRET_NAME, refresh_token)


def update_github_secret(name: str, value: str) -> bool:
    """GitHub Actions 안에서 실행 중이면, 새 값으로 GitHub Secret을 바꿔요.
    값은 화면(로그)에 찍지 않고 표준입력으로만 넘겨요."""
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not os.environ.get("GH_TOKEN") or not repo:
        log.warning(
            "새 카카오 리프레시 토큰을 받았지만 GitHub Secret을 바꿀 권한(SECRETS_PAT)이 없어요. "
            "약 두 달 안에 README 6장대로 재인증해 주세요."
        )
        return False
    try:
        subprocess.run(
            ["gh", "secret", "set", name, "--repo", repo],
            input=value, text=True, check=True, capture_output=True, timeout=60,
        )
        log.info("GitHub Secret %s 를 새 토큰으로 바꿨어요.", name)
        return True
    except (subprocess.SubprocessError, FileNotFoundError) as exc:
        log.warning("GitHub Secret 업데이트 실패: %s", getattr(exc, "stderr", exc))
        return False
