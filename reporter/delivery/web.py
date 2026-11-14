"""웹 채널 — 리포트를 HTML 파일로 저장하고 '지난 리포트' 목록을 갱신해요.

저장 위치 (GitHub Pages가 docs/ 폴더를 그대로 웹사이트로 보여줘요)
  docs/index.html                         ← 전체 주제 목록
  docs/<주제>/index.html                  ← 이 주제의 지난 리포트 목록
  docs/<주제>/reports/2026-11-10-daily.html
미리보기(dry-run)일 때는 out/site/ 에 저장해요.

설정 예:
  web:
    enabled: true
    base_url: "https://<아이디>.github.io/<저장소>/"
"""

from __future__ import annotations

import json
from pathlib import Path

from ..models import Report


def send(report: Report, ch: dict, ctx) -> str:
    base_dir: Path = (ctx.out_dir / "site") if ctx.dry_run else ctx.site_dir
    topic_dir = base_dir / report.topic
    rel_path = f"{report.topic}/reports/{report.slug}.html"
    base_url = (ch.get("base_url") or "").strip()
    if base_url and not base_url.endswith("/"):
        base_url += "/"

    # 이메일·카카오톡이 이 주소를 링크로 써요
    report.web_url = base_url + rel_path if base_url else (base_dir / rel_path).resolve().as_uri()
    report.archive_url = base_url + f"{report.topic}/" if base_url else (topic_dir / "index.html").resolve().as_uri()

    page = base_dir / rel_path
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(ctx.renderer.render_report(report, channel="web", detail="full"), encoding="utf-8")

    _update_archive(report, topic_dir, ctx)
    _update_home(base_dir, ctx)
    (base_dir / ".nojekyll").touch()  # GitHub Pages가 파일을 그대로 보여주도록
    return f"{report.web_url}" + ("  (미리보기 파일)" if ctx.dry_run else "")


def _update_archive(report: Report, topic_dir: Path, ctx) -> None:
    meta_path = topic_dir / "reports.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    entries = [e for e in meta.get("entries", []) if e.get("slug") != report.slug]
    entries.append({
        "slug": report.slug,
        "date": report.date.isoformat(),
        "mode": report.mode,
        "count": report.item_count,
        "one_liner": report.one_liner,
    })
    entries.sort(key=lambda e: (e["date"], e["mode"]), reverse=True)
    meta = {"title": ctx.cfg["title"], "description": ctx.cfg.get("description", ""), "entries": entries}
    topic_dir.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    from datetime import date
    view = [
        {**e, "href": f"reports/{e['slug']}.html",
         "date_label": ctx.renderer.kdate(date.fromisoformat(e["date"]))}
        for e in entries
    ]
    html = ctx.renderer.render_archive(meta["title"], meta["description"], view, home_url="../index.html")
    (topic_dir / "index.html").write_text(html, encoding="utf-8")


def _update_home(base_dir: Path, ctx) -> None:
    topics = []
    for meta_path in sorted(base_dir.glob("*/reports.json")):
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        latest = meta["entries"][0] if meta.get("entries") else None
        topics.append({
            "title": meta.get("title", meta_path.parent.name),
            "description": meta.get("description", ""),
            "href": f"{meta_path.parent.name}/index.html",
            "latest": latest["date"] if latest else "",
        })
    (base_dir / "index.html").write_text(ctx.renderer.render_home(topics), encoding="utf-8")
