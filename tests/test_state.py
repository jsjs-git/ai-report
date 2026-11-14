from datetime import date

from reporter.models import Item, Summary
from reporter.state import State


def test_sent_and_skipped_are_remembered(tmp_path):
    a = Item(section_id="s", source_name="x", title="A", url="https://e.com/a",
             summary=Summary(title_ko="가", headline=["한 줄"], importance="상"))
    b = Item(section_id="s", source_name="x", title="B", url="https://e.com/b")
    c = Item(section_id="s", source_name="x", title="C", url="https://e.com/c")
    with State("t", tmp_path) as st:
        st.mark_sent([a], date(2026, 11, 9))
        st.mark_skipped([b])
        assert [it.title for it in st.filter_new([a, b, c])] == ["C"]

    # 파일을 다시 열어도 기억하고, 요약까지 되살아나야 해요 (주간 정리용)
    with State("t", tmp_path) as st:
        back = st.items_between(date(2026, 11, 3), date(2026, 11, 9))
        assert len(back) == 1 and back[0].summary.title_ko == "가"
        assert st.items_between(date(2026, 11, 10), date(2026, 11, 16)) == []
