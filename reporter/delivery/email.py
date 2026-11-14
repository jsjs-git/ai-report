"""이메일 채널 — Gmail로 HTML 리포트를 보내요.

필요한 비밀값(.env 또는 GitHub Secrets)
  GMAIL_ADDRESS       : 보내는 Gmail 주소
  GMAIL_APP_PASSWORD  : Gmail '앱 비밀번호' (일반 비밀번호 아님, README 5장)

설정 예:
  email:
    enabled: true
    to: ["${REPORT_EMAIL_TO}"]   # 비어 있으면 보내는 주소로 받아요
    full_detail: false           # true면 자세한 설명 전체를 메일에도 넣어요
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage

from ..errors import DeliveryError
from ..models import Report

GMAIL_CLIP_BYTES = 102_000  # Gmail은 이보다 큰 메일을 중간에서 잘라 보여줘요


def recipients(ch: dict) -> list[str]:
    out = [addr.strip() for value in (ch.get("to") or []) for addr in str(value).split(",") if addr.strip()]
    if out:
        return out
    sender = os.environ.get("GMAIL_ADDRESS", "").strip()
    return [sender] if sender else []


def subject_for(report: Report, renderer) -> str:
    if report.mode == "weekly":
        return f"[{report.title}] 주간 정리 · {renderer.kdate_short(report.date)}"
    return f"[{report.title}] {renderer.kdate(report.date)}"


def send(report: Report, ch: dict, ctx) -> str:
    # 웹 리포트가 있으면 메일은 짧게(+자세히 읽기 링크), 없으면 전체를 메일에 넣어요
    detail = "full" if ch.get("full_detail") or not report.web_url else "short"
    if report.mode == "weekly":
        detail = "brief"
    html = ctx.renderer.render_report(report, channel="email", detail=detail)
    size = len(html.encode("utf-8"))
    if size > GMAIL_CLIP_BYTES:
        ctx.log.warning("메일 크기가 %dKB예요. Gmail에서는 일부만 보이고 '전체 메일 보기'를 눌러야 해요.", size // 1000)

    if ctx.dry_run:
        path = ctx.out_dir / f"{report.topic}-{report.slug}-email.html"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(html, encoding="utf-8")
        return f"미리보기 저장 → {path}  (받는 사람: {', '.join(recipients(ch)) or '아직 설정 안 됨'})"

    _smtp_send(subject_for(report, ctx.renderer), plain_text(report), html, ch)
    return f"{', '.join(recipients(ch))} 에게 보냄"


def send_alert(subject: str, body: str, channel_cfg: dict) -> None:
    """간단한 안내 메일 (예: 카카오 재인증 필요)."""
    _smtp_send(subject, body, None, channel_cfg)


def _smtp_send(subject: str, text: str, html: str | None, ch: dict) -> None:
    sender = os.environ.get("GMAIL_ADDRESS")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not sender or not password:
        raise DeliveryError("GMAIL_ADDRESS 와 GMAIL_APP_PASSWORD 가 필요해요. (.env 확인)")
    to = recipients(ch)
    if not to:
        raise DeliveryError("받는 사람 주소가 없어요. REPORT_EMAIL_TO 또는 GMAIL_ADDRESS 를 확인하세요.")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    host = ch.get("smtp_host", "smtp.gmail.com")
    port = int(ch.get("smtp_port", 465))
    try:
        with smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=30) as smtp:
            smtp.login(sender, password.replace(" ", ""))
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError as exc:
        raise DeliveryError("Gmail 로그인 실패. '앱 비밀번호'가 맞는지 확인하세요. (README 5장)") from exc


def plain_text(report: Report) -> str:
    """HTML을 못 보는 메일 앱용 글자 버전."""
    lines = [f"{report.title} · {report.mode_label} · {report.date.isoformat()}", ""]
    if report.one_liner:
        lines += [report.one_liner, ""]
    for i, h in enumerate(report.highlights, 1):
        lines.append(f"{i}. {h}")
    for section in report.sections:
        if not section.items:
            continue
        lines += ["", f"■ {section.title}"]
        for it in section.items:
            title = it.summary.title_ko if it.summary and it.summary.title_ko else it.title
            lines.append(f"- {title}\n  {it.url}")
    if report.web_url:
        lines += ["", f"웹에서 보기: {report.web_url}"]
    return "\n".join(lines)
