"""발송 채널 모음 — 설정(delivery)에서 enabled: true 인 채널만 실행해요.

채널은 모두 같은 모양의 함수예요:
    send(report: Report, channel_cfg: dict, ctx: DeliveryContext) -> str(결과 메시지)

새 채널(예: Slack)을 추가하려면:
  1) 이 폴더에 slack.py 를 만들고 send 함수 작성
  2) 아래 CHANNELS 와 CHANNEL_ORDER 에 등록
  3) 설정 파일 delivery 아래에 slack: { enabled: true, ... } 추가
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from ..errors import KakaoAuthError
from ..models import Report
from ..renderer import Renderer
from . import email, kakao, web

# web을 먼저 실행해야 이메일·카카오톡에 웹 리포트 주소를 넣을 수 있어요.
CHANNEL_ORDER = ["web", "email", "kakao"]
CHANNELS = {"web": web.send, "email": email.send, "kakao": kakao.send}


@dataclass
class DeliveryContext:
    cfg: dict
    renderer: Renderer
    dry_run: bool
    out_dir: Path            # 미리보기(dry-run) 결과가 저장되는 곳
    site_dir: Path           # 실제 웹 리포트가 저장되는 곳 (GitHub Pages)
    log: logging.Logger = field(default_factory=lambda: logging.getLogger("reporter.delivery"))


def enabled_channels(cfg: dict) -> list[str]:
    delivery = cfg.get("delivery", {})
    return [name for name in CHANNEL_ORDER if delivery.get(name, {}).get("enabled")]


def deliver_all(report: Report, ctx: DeliveryContext) -> dict[str, str]:
    """켜진 채널로 차례대로 보내요. 한 채널이 실패해도 나머지는 계속 보내요."""
    results: dict[str, str] = {}
    delivery = ctx.cfg.get("delivery", {})
    for name in enabled_channels(ctx.cfg):
        try:
            results[name] = "성공: " + CHANNELS[name](report, delivery[name], ctx)
        except KakaoAuthError as exc:
            results[name] = f"실패(재인증 필요): {exc}"
            ctx.log.error("카카오톡 발송 실패 — %s", exc)
            _alert_kakao_reauth(exc, ctx)
        except Exception as exc:
            results[name] = f"실패: {exc}"
            ctx.log.exception("%s 발송 실패", name)
    return results


def _alert_kakao_reauth(exc: Exception, ctx: DeliveryContext) -> None:
    """카카오 토큰이 만료되면 이메일로 알려줘요."""
    email_cfg = ctx.cfg.get("delivery", {}).get("email", {})
    if ctx.dry_run or not email_cfg.get("enabled"):
        return
    try:
        email.send_alert(
            subject=f"[{ctx.cfg['title']}] 카카오톡 재인증이 필요해요",
            body=(
                "카카오톡 '나에게 보내기' 토큰이 만료됐거나 올바르지 않아요.\n\n"
                f"오류: {exc}\n\n"
                "해결 방법 (README 6장):\n"
                "1) 내 컴퓨터에서  python -m reporter.tools.kakao_auth  실행\n"
                "2) GitHub에서 돌리는 경우, 새 리프레시 토큰을 GitHub Secret(KAKAO_REFRESH_TOKEN)에 넣기\n"
            ),
            channel_cfg=email_cfg,
        )
        ctx.log.info("카카오 재인증 안내 메일을 보냈어요.")
    except Exception as mail_exc:  # 알림 메일까지 실패해도 프로그램은 계속
        ctx.log.warning("재인증 안내 메일 발송 실패: %s", mail_exc)
