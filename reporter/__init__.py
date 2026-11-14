"""주제 교체형 리포트 엔진.

이 폴더(reporter/)의 코드는 '주제'와 무관하게 동작해요.
주제는 topics/*.yaml, 디자인은 themes/*.yaml 에서 정해요.
"""

from pathlib import Path

# 프로젝트 최상위 폴더 (mailing_service/)
ROOT = Path(__file__).resolve().parent.parent
