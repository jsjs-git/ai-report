"""예시 데이터 수집기 — 인터넷 없이 리포트 모양을 확인할 때 써요. (topics/demo.yaml)

설정 예:
  - name: 예시 소스
    type: sample
    file: samples/demo_items.json
    section_key: updates      # JSON 안에서 이 값과 같은 항목만 가져와요
"""

from __future__ import annotations

import json
from datetime import timedelta

from .. import ROOT
from ..models import Item, Summary


def collect(source: dict, section: dict, ctx) -> list[Item]:
    data = json.loads((ROOT / source["file"]).read_text(encoding="utf-8"))
    key = source.get("section_key", section["id"])
    items = []
    for row in data.get("items", []):
        if row.get("section_key") != key:
            continue
        items.append(
            Item(
                section_id=section["id"],
                source_name=source["name"],
                group=row.get("group", ""),
                title=row["title"],
                url=row["url"],
                published=ctx.now - timedelta(hours=row.get("hours_ago", 1)),
                text=row.get("text", ""),
                authors=row.get("authors", []),
                citations=row.get("citations"),
                venue=row.get("venue", ""),
                upvotes=row.get("upvotes"),
                paper_ids=row.get("paper_ids", {}),
                summary=Summary.model_validate(row["summary"]) if row.get("summary") else None,
            )
        )
    return items
