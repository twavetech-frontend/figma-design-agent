"""R61 — 텍스트 노드에 이모지 금지, 아이콘 자리엔 DS 아이콘 (2026-06-02 사용자 룰).

사용자 명시: "지금 초기에 있었던 문제들이 다시 발생했다. 아이콘이 들어갈 위치에
텍스트 이모티콘이 사용되었어." + "이건 큰 문제야. 원인을 찾아봐."

근본 원인 (분석 결과):
  1. `enhanceBlueprint`(figma-mcp-embedded.ts)의 이모지→아이콘 자동 변환기 `isEmojiOnlyText`
     가 텍스트 내용을 `n.text` 로만 읽었다. 그러나 blueprint 텍스트 노드는 `characters`
     필드를 쓴다 (plugin batch builder 는 `spec.text || spec.characters` 둘 다 받지만
     변환기는 `text` 만 봄). → `characters` 로 작성한 이모지(🔍 등)는 변환기에 안 잡혀
     리터럴 이모지로 빌드됨. (TS 측은 2026-06-02 `n.text ?? n.characters` 로 수정.)
  2. 변환기는 **emoji-only** 텍스트만 대상이라 "🚀 빠른 시작" 같은 이모지+텍스트 혼합
     라벨은 애초에 변환 대상이 아니었다 → 이모지가 그대로 남음.
  3. 이모지를 막는 design rule 이 없었다 (FAB 한정 R57 만 존재) → 새 세션마다 작성자가
     이모지를 넣으면 통과. "이모지→아이콘 자동변환" 기능을 신뢰한 게 재발의 직접 원인.

수정 (이 룰 — 시스템 강제, 모든 빌드 자동):
  L2 lint   — 텍스트 노드의 characters/text 에 이모지가 있으면 WARN (작성자에게 가시화).
  L3 inject — 이모지를 자동 제거. 혼합 라벨("🚀 빠른 시작")은 이모지만 떼고 텍스트 보존
              ("빠른 시작"). emoji-only("🔍")는 `type:"icon"` 으로 변환 (TS 변환기가
              놓쳐도 여기서 1차 차단) — 매핑 없으면 텍스트만 비워 빈 노드가 되지 않도록
              안전 처리. → 리터럴 이모지가 빌드 트리에 절대 도달하지 않음.
  L5 verify — 빌드 트리 TEXT characters 에 이모지가 남아 있으면 ERROR (회귀 차단).

스코프: 모든 TEXT 노드. (숫자/문자가 섞인 일반 텍스트는 이모지 코드포인트만 제거되고
        나머지는 그대로 — 한글/영문/숫자는 손대지 않음.)
"""
from __future__ import annotations

import re
from typing import Iterable

from .base import Phase, Rule, Severity, Violation, register

# emoji-only 텍스트 → DS svg 아이콘 이름 매핑 (TS EMOJI_TO_ICON_MAP 과 동기화 권장)
_EMOJI_ICON = {
    "🔍": "search-lg", "🔎": "search-lg",
    "🚀": "rocket-02", "⚡": "zap", "💰": "coins-stacked-01", "💎": "diamond-01",
    "⭐": "star-01", "🌟": "star-01", "🔔": "bell-01", "❤️": "heart",
    "📲": "phone-01", "🎁": "gift-01", "✅": "check-circle", "📅": "calendar",
}

# 이모지 / 변형 셀렉터 / ZWJ / keycap 등 — 제거 대상 코드포인트
_EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF"   # 대부분의 이모지 블록
    "\U00002600-\U000027BF"    # Misc symbols + Dingbats
    "\U0001F1E6-\U0001F1FF"    # regional indicators
    "\U00002190-\U000021FF"    # arrows (▾ 는 별도 처리 — 아래 _GLYPH_ARROWS)
    "️‍⃣]",
    flags=re.UNICODE,
)
# 화살표 글리프(▾ ▸ ⌄ 등)도 아이콘 자리에 텍스트로 쓰면 안 됨 — chevron 으로 안내
_GLYPH_ARROWS = {"▾": "chevron-down", "▿": "chevron-down", "⌄": "chevron-down",
                 "▴": "chevron-up", "▸": "chevron-right", "▹": "chevron-right",
                 "◂": "chevron-left", "→": "arrow-right", "←": "arrow-left"}


def _text_of(n: dict):
    return n.get("characters") if n.get("characters") is not None else n.get("text")


def _has_emoji(s: str) -> bool:
    if not isinstance(s, str):
        return False
    if _EMOJI_RE.search(s):
        return True
    return any(g in s for g in _GLYPH_ARROWS)


def _strip_emoji(s: str) -> str:
    s = _EMOJI_RE.sub("", s)
    for g in _GLYPH_ARROWS:
        s = s.replace(g, "")
    return s.strip()


def _first_icon(s: str):
    for ch, ic in _EMOJI_ICON.items():
        if ch in s:
            return ic
    for g, ic in _GLYPH_ARROWS.items():
        if g in s:
            return ic
    return None


# ── L2 lint ───────────────────────────────────────────────────────
def _check_blueprint(bp: dict, ctx: dict) -> Iterable[Violation]:
    def walk(n, path="root"):
        if not isinstance(n, dict):
            return
        if (n.get("type") or "").lower() == "text":
            t = _text_of(n)
            if isinstance(t, str) and _has_emoji(t):
                yield Violation(
                    "R61-no-emoji-in-text", Severity.WARN, f"{path}/{n.get('name','text')}",
                    f"텍스트에 이모지/글리프 '{t}' — 아이콘 자리엔 DS 아이콘 인스턴스를 쓸 것. "
                    f"inject 가 이모지를 제거(혼합은 텍스트 보존)한다.",
                    Phase.LINT)
        for c in n.get("children") or []:
            yield from walk(c, f"{path}/{n.get('name','?')}")
    yield from walk(bp)


# ── L3 inject ─────────────────────────────────────────────────────
def _inject(bp: dict) -> dict:
    n_fixed = [0]

    def walk(n):
        if not isinstance(n, dict):
            return
        if (n.get("type") or "").lower() == "text":
            t = _text_of(n)
            if isinstance(t, str) and _has_emoji(t):
                stripped = _strip_emoji(t)
                if stripped:
                    # 혼합 라벨 → 이모지만 제거, 텍스트 보존
                    if n.get("characters") is not None:
                        n["characters"] = stripped
                    else:
                        n["text"] = stripped
                else:
                    # emoji-only → 아이콘 변환 (매핑 있으면), 없으면 노드 무력화
                    ic = _first_icon(t)
                    if ic:
                        n["type"] = "icon"
                        n["name"] = ic
                        n["size"] = n.get("fontSize") or 24
                        for k in ("text", "characters", "fontSize", "fontWeight",
                                  "fontFamily", "fontColor", "textAlignHorizontal",
                                  "layoutSizingHorizontal"):
                            n.pop(k, None)
                    else:
                        if n.get("characters") is not None:
                            n["characters"] = ""
                        else:
                            n["text"] = ""
                n_fixed[0] += 1
        for c in n.get("children") or []:
            walk(c)

    walk(bp)
    if n_fixed[0]:
        print(f"  [inject R61] 이모지/글리프 텍스트 {n_fixed[0]}건 제거·아이콘화")
    return bp


# ── L5 verify ─────────────────────────────────────────────────────
def _verify(tree: dict, ctx: dict) -> Iterable[Violation]:
    def walk(n, path="root"):
        if not isinstance(n, dict):
            return
        if (n.get("type") or "").upper() == "TEXT":
            t = n.get("characters")
            if isinstance(t, str) and _has_emoji(t):
                yield Violation(
                    "R61-no-emoji-in-text", Severity.ERROR, f"{path}/{n.get('name','text')}",
                    f"빌드 트리 TEXT 에 이모지 '{t}' 가 남음 — 아이콘으로 교체 필요.",
                    Phase.VERIFY)
        for c in n.get("_children_full") or n.get("children") or []:
            yield from walk(c, f"{path}/{n.get('name','?')}")
    yield from walk(tree)


register(Rule(
    rule_id="R61-no-emoji-in-text",
    title="No emoji/glyph in TEXT — use DS icon instances",
    description=(
        "TEXT 노드의 characters/text 에 이모지·화살표 글리프 금지. 혼합 라벨은 이모지만 "
        "제거하고 텍스트 보존, emoji-only 는 DS 아이콘으로 변환. 근본 원인: enhanceBlueprint "
        "이모지 변환기가 characters 필드를 못 읽어 리터럴 이모지가 빌드되던 재발 버그."
    ),
    check_blueprint_fn=_check_blueprint,
    inject_blueprint_fn=_inject,
    check_built_fn=_verify,
))
