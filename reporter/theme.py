"""디자인 테마 읽기 — themes/<이름>.yaml 의 값을 템플릿에 넘겨줘요.

템플릿에는 색상 값을 직접 쓰지 않고 t.colors.bg 처럼 '이름'으로만 써요.
그래서 테마 파일만 바꾸면 웹·이메일 디자인이 함께 바뀌어요.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from . import ROOT
from .errors import ConfigError

THEMES_DIR = ROOT / "themes"

REQUIRED = {
    "colors": ["bg", "surface", "surface_alt", "border", "text", "text_muted", "text_faint",
               "accent", "accent_text", "link", "tag_default",
               "importance_high", "importance_mid", "importance_low", "tier_new", "tier_proven"],
    "fonts": ["body"],
    "sizes": ["base", "small", "tiny", "title", "section", "item", "line_height"],
    "layout": ["max_width", "page_padding", "card_padding", "gap", "radius", "radius_small"],
}


class Theme:
    def __init__(self, name: str, data: dict):
        self.name = name
        self.data = data

    def group_color(self, group: str) -> str:
        return (self.data.get("group_colors") or {}).get(group) or self.data["colors"]["tag_default"]

    def importance_color(self, level: str) -> str:
        c = self.data["colors"]
        return {"상": c["importance_high"], "중": c["importance_mid"]}.get(level, c["importance_low"])

    def tier_color(self, tier: str) -> str:
        c = self.data["colors"]
        return c["tier_new"] if tier == "new" else c["tier_proven"]

    def css(self, channel: str) -> str:
        """<style> 안에 들어갈 CSS. 대부분의 스타일은 태그에 직접(inline) 들어가고,
        여기에는 휴대폰 화면 대응과 웹 전용 효과만 있어요."""
        c, s, l = self.data["colors"], self.data["sizes"], self.data["layout"]
        bp = l.get("mobile_breakpoint", "600px")
        mp = l.get("mobile_padding", "16px")
        css = [
            f":root{{color-scheme:dark;}}",
            f"body{{margin:0;padding:0;background:{c['bg']};}}",
            f"a{{color:{c['link']};}}",
            f"@media (max-width:{bp}){{"
            f".rp-page{{padding:{mp} !important;}}"
            f".rp-card{{padding:{mp} !important;}}"
            f".rp-title{{font-size:calc({s['title']} - 4px) !important;}}"
            f".rp-item-title{{font-size:calc({s['item']} - 1px) !important;}}"
            f"}}",
        ]
        if channel == "web":
            # CSS 변수: 브라우저 개발자 도구에서 색을 바로 바꿔 보며 실험할 때 편해요
            css.insert(0, ":root{" + "".join(f"--{k.replace('_', '-')}:{v};" for k, v in c.items()) + "}")
            css += [
                "a:hover{text-decoration:underline !important;}",
                ".rp-btn:hover{filter:brightness(1.1);}",
                "html{scroll-behavior:smooth;}",
                ".rp-card:target{outline:2px solid " + c["accent"] + ";outline-offset:2px;}",
            ]
        return "".join(css)


def load_theme(name: str, themes_dir: Path | None = None) -> Theme:
    path = Path(themes_dir or THEMES_DIR) / f"{name}.yaml"
    if not path.exists():
        available = ", ".join(p.stem for p in Path(themes_dir or THEMES_DIR).glob("*.yaml"))
        raise ConfigError(f"디자인 테마 '{name}'을(를) 찾을 수 없어요. 사용 가능: {available}")
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    missing = [f"{group}.{key}" for group, keys in REQUIRED.items() for key in keys
               if key not in (data.get(group) or {})]
    if missing:
        raise ConfigError(f"테마 '{name}'에 빠진 값이 있어요: {', '.join(missing)}")
    return Theme(name, data)
