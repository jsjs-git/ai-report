"""기억 저장소 — 이미 보낸 항목을 기록해서 같은 소식을 두 번 보내지 않아요.

data/<주제>.sqlite 파일 하나에 저장돼요. (주간 정리도 이 기록을 사용)
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from . import ROOT
from .models import Item

DATA_DIR = ROOT / "data"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sent (
    uid         TEXT PRIMARY KEY,
    section_id  TEXT NOT NULL,
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    sent_at     TEXT NOT NULL,   -- 기록한 시각 (UTC)
    report_date TEXT NOT NULL,   -- 리포트 날짜 (현지 날짜)
    item_json   TEXT NOT NULL    -- 요약까지 포함한 항목 전체 (주간 정리용)
);
CREATE INDEX IF NOT EXISTS idx_sent_report_date ON sent(report_date);
-- 보내지 않고 넘긴 항목 (너무 오래된 글 등) → 다음번에 다시 확인하지 않아요
CREATE TABLE IF NOT EXISTS skipped (
    uid        TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    skipped_at TEXT NOT NULL
);
"""


class State:
    def __init__(self, topic: str, data_dir: Path | None = None):
        folder = Path(data_dir or DATA_DIR)
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / f"{topic}.sqlite"
        self.db = sqlite3.connect(self.path)
        self.db.executescript(_SCHEMA)

    # with State(...) as state: 형태로 쓰면 끝날 때 자동으로 닫혀요
    def __enter__(self) -> "State":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self.db.commit()
        self.db.close()

    def is_sent(self, uid: str) -> bool:
        row = self.db.execute("SELECT 1 FROM sent WHERE uid = ?", (uid,)).fetchone()
        return row is not None

    def is_known(self, uid: str) -> bool:
        """이미 보냈거나, 넘기기로 한 항목이면 True."""
        row = self.db.execute(
            "SELECT 1 FROM sent WHERE uid = ? UNION SELECT 1 FROM skipped WHERE uid = ?", (uid, uid)
        ).fetchone()
        return row is not None

    def filter_new(self, items: list[Item]) -> list[Item]:
        """아직 보내지도, 넘기지도 않은 항목만 남겨요."""
        return [it for it in items if not self.is_known(it.uid)]

    def mark_skipped(self, items: list[Item]) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.db.executemany(
            "INSERT OR IGNORE INTO skipped VALUES (?, ?, ?)",
            [(it.uid, it.title, now) for it in items],
        )
        self.db.commit()

    def mark_sent(self, items: list[Item], report_date: date) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.db.executemany(
            "INSERT OR REPLACE INTO sent VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (it.uid, it.section_id, it.title, it.url, now, report_date.isoformat(),
                 json.dumps(it.to_dict(), ensure_ascii=False))
                for it in items
            ],
        )
        self.db.commit()

    def items_between(self, start: date, end: date) -> list[Item]:
        """start ~ end(포함) 날짜 리포트에 실렸던 항목들 (주간 정리용)."""
        rows = self.db.execute(
            "SELECT item_json FROM sent WHERE report_date BETWEEN ? AND ? ORDER BY report_date",
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        return [Item.from_dict(json.loads(r[0])) for r in rows]

    def count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM sent").fetchone()[0]
