"""주제 설정 파일(topics/*.yaml)을 읽고 검사해요.

- 빠진 값은 기본값으로 채워요.
- "${환경변수}" 라고 쓴 곳은 .env(또는 GitHub Secrets) 값으로 바꿔요.
  예) to: ["${REPORT_EMAIL_TO}"]  → 공개 저장소에 이메일 주소가 노출되지 않아요.
"""

from __future__ import annotations

import copy
import os
import re
from pathlib import Path

import yaml

from . import ROOT
from .errors import ConfigError

TOPICS_DIR = ROOT / "topics"

# 설정 파일에 안 적으면 이 값이 쓰여요.
DEFAULTS: dict = {
    "language": "ko",
    "timezone": "Asia/Seoul",
    "theme": "dark",
    "skip_if_empty": True,          # 새 소식이 없으면 발송 안 함
    "summary": {
        "enabled": True,
        "model": "claude-opus-5-5",
        "effort": "medium",         # low | medium | high
        "detail_level": "detailed", # brief(요약만) | detailed(요약+자세한 설명)
        "max_input_chars": 15000,   # 원문을 AI에게 넘길 때 최대 글자 수
        "fallbacks": True,          # AI가 응답을 거절하면 다른 모델로 자동 재시도
    },
    "weekly": {
        "max_items_per_section": 8,
        "min_importance": "중",      # 주간판에는 이 중요도 이상만
    },
    "delivery": {
        "web": {"enabled": False, "base_url": ""},
        "email": {"enabled": False, "to": [], "full_detail": False},
        "kakao": {"enabled": False, "summary_lines": 3, "button_title": "웹 리포트 보기"},
    },
}

SECTION_KINDS = {"news", "papers"}

_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")


def load_env() -> None:
    """프로젝트 폴더의 .env 파일을 읽어 환경변수로 등록해요. (없으면 그냥 넘어감)"""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover
        return
    load_dotenv(ROOT / ".env", override=False)


def _expand_env(value):
    """문자열 안의 ${NAME} 또는 ${NAME:-기본값} 을 환경변수 값으로 바꿔요."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(lambda m: os.environ.get(m.group(1)) or (m.group(2) or ""), value)
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    return value


def _deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def list_topics() -> list[str]:
    """topics/ 폴더의 주제 이름 목록 (밑줄로 시작하는 양식 파일은 제외)."""
    return sorted(p.stem for p in TOPICS_DIR.glob("*.yaml") if not p.stem.startswith("_"))


def load_topic(name_or_path: str) -> tuple[dict, list[str]]:
    """주제 설정을 읽어서 (설정, 경고 목록)을 돌려줘요."""
    path = Path(name_or_path)
    if not path.suffix:
        path = TOPICS_DIR / f"{name_or_path}.yaml"
    if not path.exists():
        raise ConfigError(
            f"주제 설정 파일을 찾을 수 없어요: {path}\n"
            f"사용할 수 있는 주제: {', '.join(list_topics()) or '(없음)'}"
        )
    with path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    cfg = _deep_merge(DEFAULTS, raw)
    cfg = _expand_env(cfg)
    warnings = validate(cfg, source=str(path))
    return cfg, warnings


def validate(cfg: dict, source: str = "설정") -> list[str]:
    """설정을 검사해요. 고쳐야 하는 문제는 ConfigError, 참고할 점은 경고로 돌려줘요."""
    from .collectors import COLLECTORS  # 순환 import 방지를 위해 여기서 불러요

    errors: list[str] = []
    warnings: list[str] = []

    for key in ("topic", "title", "sections"):
        if not cfg.get(key):
            errors.append(f"'{key}' 항목이 비어 있어요.")

    seen_ids: set[str] = set()
    for i, sec in enumerate(cfg.get("sections") or [], start=1):
        where = f"sections {i}번째"
        if not isinstance(sec, dict):
            errors.append(f"{where}: 형식이 잘못됐어요.")
            continue
        sid = sec.get("id")
        if not sid:
            errors.append(f"{where}: 'id'가 필요해요.")
        elif sid in seen_ids:
            errors.append(f"{where}: id '{sid}'가 중복이에요.")
        seen_ids.add(sid or "")
        if not sec.get("title"):
            errors.append(f"{where}: 'title'이 필요해요.")
        if sec.get("kind", "news") not in SECTION_KINDS:
            errors.append(f"{where}: kind는 {sorted(SECTION_KINDS)} 중 하나여야 해요.")
        sources = sec.get("sources") or []
        if not sources:
            errors.append(f"{where}: 'sources'(수집 소스)가 하나 이상 필요해요.")
        for j, src in enumerate(sources, start=1):
            stype = (src or {}).get("type")
            if stype not in COLLECTORS:
                errors.append(
                    f"{where} 소스 {j}번째: type '{stype}'은(는) 지원하지 않아요. "
                    f"가능한 값: {', '.join(sorted(COLLECTORS))}"
                )

    delivery = cfg.get("delivery", {})
    if delivery.get("kakao", {}).get("enabled") and not delivery.get("web", {}).get("enabled"):
        warnings.append("카카오톡 버튼은 웹 리포트 주소로 연결돼요. delivery.web도 켜는 것을 추천해요.")
    if delivery.get("web", {}).get("enabled") and not delivery["web"].get("base_url"):
        warnings.append("delivery.web.base_url(웹 주소)이 비어 있어요. 링크가 파일 경로로만 표시돼요.")
    if not any(ch.get("enabled") for ch in delivery.values() if isinstance(ch, dict)):
        warnings.append("켜진 발송 채널이 없어요. (delivery의 enabled 값을 확인하세요)")

    if errors:
        raise ConfigError(f"{source} 설정에 문제가 있어요:\n  - " + "\n  - ".join(errors))
    return warnings


def section_by_id(cfg: dict, section_id: str) -> dict | None:
    return next((s for s in cfg["sections"] if s.get("id") == section_id), None)
