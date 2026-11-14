"""실행 입구.

사용 예
  python -m reporter --topic ai_trends --dry-run          # 보내지 않고 out/ 에 미리보기
  python -m reporter --topic ai_trends                    # 실제 발송 (매일 리포트)
  python -m reporter --topic ai_trends --mode weekly      # 주간 정리
  python -m reporter --topic ai_trends --mark-seen        # 첫 실행: 지금 글들을 '본 것'으로만 기록
  python -m reporter --topic ai_trends --stage collect    # 수집만 → out/ai_trends-pending.json
  python -m reporter --topic ai_trends --stage send       # (Claude가 요약을 채운 뒤) 발송
  python -m reporter --list-topics                        # 주제 목록
"""

from __future__ import annotations

import argparse
import logging
import sys

from .config import list_topics
from .errors import ConfigError
from .pipeline import RunOptions, run


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # 윈도우에서도 한글·기호가 깨지지 않게
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except AttributeError:
            pass

    p = argparse.ArgumentParser(prog="python -m reporter", description="주제별 리포트 만들기·보내기")
    p.add_argument("--topic", help="topics/ 폴더의 주제 이름 (예: ai_trends)")
    p.add_argument("--mode", choices=["daily", "weekly"], default="daily", help="daily(매일) 또는 weekly(주간)")
    p.add_argument("--dry-run", action="store_true", help="실제로 보내지 않고 out/ 폴더에 미리보기만 저장")
    p.add_argument("--no-summary", action="store_true", help="AI 요약 없이 진행 (비용 0원 테스트)")
    p.add_argument("--mark-seen", action="store_true", help="지금 있는 글을 '이미 본 것'으로 기록만 (첫 실행 폭탄 방지)")
    p.add_argument("--stage", choices=["all", "collect", "send"], default="all",
                   help="collect: 수집해서 out/<주제>-pending.json 저장 / send: 그 파일(요약 채운 것)로 발송")
    p.add_argument("--list-topics", action="store_true", help="사용할 수 있는 주제 목록 보기")
    p.add_argument("-v", "--verbose", action="store_true", help="자세한 기록 보기")
    args = p.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(message)s",
    )
    for noisy in ("httpx", "httpcore", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if args.list_topics or not args.topic:
        print("사용할 수 있는 주제:", ", ".join(list_topics()) or "(없음)")
        if not args.topic:
            print("실행 예: python -m reporter --topic ai_trends --dry-run")
        return 0

    try:
        result = run(RunOptions(
            topic=args.topic, mode=args.mode, dry_run=args.dry_run,
            no_summary=args.no_summary, mark_seen=args.mark_seen, stage=args.stage,
        ))
    except ConfigError as exc:
        print(f"\n✗ 설정 오류\n{exc}", file=sys.stderr)
        return 2

    print()
    if result.message:
        print(f"ℹ {result.message}")
    if result.report and result.results:
        print(f"■ {result.report.title} · {result.report.mode_label} · 항목 {result.report.item_count}건"
              + ("  [미리보기]" if args.dry_run else ""))
        for channel, outcome in result.results.items():
            mark = "✓" if outcome.startswith("성공") else "✗"
            print(f"  {mark} {channel}: {outcome}")
    return 1 if result.failed else 0


if __name__ == "__main__":
    sys.exit(main())
