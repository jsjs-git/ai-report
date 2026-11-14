import shutil

import yaml

from reporter.renderer import Renderer
from reporter.theme import THEMES_DIR, load_theme


def test_web_report_has_all_detail_parts(sample_report):
    html = Renderer(load_theme("dark")).render_report(sample_report, channel="web", detail="full")
    for text in ("한눈에 보기", "배경", "무엇이 바뀌었나", "왜 중요한가", "용어 풀이", "하네스",
                 "핵심 아이디어", "오늘의 핵심", "신규 주목", "2026년 11월 10일 화요일"):
        assert text in html, text
    assert "#0B0B0D" in html  # 블랙 배경


def test_email_short_mode_links_to_web(sample_report):
    sample_report.web_url = "https://me.github.io/r/x.html"
    html = Renderer(load_theme("dark")).render_report(sample_report, channel="email", detail="short")
    assert "자세한 설명 읽기" in html and "#item-" in html
    assert "무엇이 바뀌었나" not in html
    assert "pretendard.min.css" not in html  # 이메일에는 웹 글꼴 파일을 불러오지 않아요 (이름만 대체 목록에)


def test_short_date_shows_year_only_for_other_years():
    from datetime import date, datetime
    r = Renderer(load_theme("dark"))
    this_year = datetime.now(r.tz).year
    assert r.kdate_short(date(this_year, 3, 5)) == "3월 5일"
    assert r.kdate_short(date(this_year - 1, 11, 26)) == f"{this_year - 1}년 11월 26일"


def test_changing_theme_file_changes_design(tmp_path, sample_report):
    """디자인 값은 테마 파일에만 있어요: 강조색 하나만 바꿔도 결과가 바뀌어야 해요."""
    shutil.copy(THEMES_DIR / "dark.yaml", tmp_path / "custom.yaml")
    data = yaml.safe_load((tmp_path / "custom.yaml").read_text(encoding="utf-8"))
    data["colors"]["accent"] = "#FF00AA"
    (tmp_path / "custom.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")

    html = Renderer(load_theme("custom", tmp_path)).render_report(sample_report, channel="email", detail="full")
    assert "#FF00AA" in html
    assert "#5CC8FF" not in html


def test_templates_have_no_hardcoded_colors():
    """템플릿에 색상 값(#xxxxxx)을 직접 쓰지 않았는지 확인 (디자인은 테마에서만)."""
    import re
    from reporter.renderer import TEMPLATES_DIR
    for path in TEMPLATES_DIR.rglob("*.j2"):
        assert not re.search(r"#[0-9A-Fa-f]{6}\b", path.read_text(encoding="utf-8")), path.name
