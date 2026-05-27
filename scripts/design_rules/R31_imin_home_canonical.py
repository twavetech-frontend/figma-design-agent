"""R31 — imin_home Recommend & Schedule canonical structure.

Canonical Recommend Section (V20, 2026-05-05):
  • FULL brand-purple card (bg-brand-solid, radius ~24)
  • Header: small eyebrow ("XX님을 위한 추천") + multi-line action headline
  • Big amount block: eyebrow + huge number + sub line (월/기간/이율)
  • White Detail Card (bg-primary, radius ~16) containing 3 rows:
      받는 순번 (read-only label+value)
      월 납입 금액 (label + stepper)
      기간 (label + stepper)
  • CTA Row: 2 CTAs side-by-side
      Primary: white solid pill, brand-color text + arrow
      Secondary: outline pill, white text
  • Bottom: "어떻게 계산되나요?" with info icon

Earlier intermediate v12 attempts produced cramped brand-purple layouts with
broken Round overflow and missing CTAs. v17 bg-secondary card was an experiment
that was later superseded — the user's canonical is the V20 full-purple pattern.

Canonical Schedule Section (v17, 17037:3674):
  • NO wrapper card; cells float at section level
  • Title row: "이번 달 스케줄" muted + "미납 N" pill badge + month right-aligned
  • Horizontal scroll cells; each cell tinted by status:
      미납 = bg-error-secondary, fg-error-primary text
      오늘 = bg-brand-primary (light), fg-brand-primary text, brand-solid status chip
      지급/예정 = bg-secondary, fg-primary text

This rule LINT-blocks deviations from these canonical structures.
"""
from __future__ import annotations

from typing import Iterable, Optional

from .base import Phase, Rule, Severity, Violation, register, walk_blueprint


# ── Detection helpers ──────────────────────────────────────────────

def _is_imin_home(bp: dict) -> bool:
    name = (bp.get("rootName") or bp.get("name") or "").lower()
    if "imin_home" in name or "imin home" in name:
        return True
    for node, _ in walk_blueprint(bp):
        nm = (node.get("name") or "")
        if nm == "Recommend Section" or "주현님" in nm or "민지님" in nm:
            return True
        if node.get("type") == "text":
            t = node.get("characters") or node.get("text") or ""
            if "을 위한 추천" in t:
                return True
    return False


def _find_recommend_root(bp: dict) -> Optional[tuple]:
    for node, path in walk_blueprint(bp):
        nm = (node.get("name") or "").lower()
        if "recommend section" in nm:
            return node, path
        if "추천" in (node.get("name") or "") and node.get("type") == "frame":
            return node, path
    return None


def _has_action_headline(rec_root: dict) -> bool:
    """V20 requires a multi-line action headline (e.g., 'NNN원 모으기 도전,
    지금 시작하면 N번째에 받아요'). Heuristic: any TEXT containing both
    '모으기' / '도전' / '받아요' style action verbs.
    """
    for node, _ in walk_blueprint(rec_root):
        if node.get("type") == "text":
            t = node.get("characters") or node.get("text") or ""
            if any(k in t for k in ("모으기 도전", "받아요", "받으세요")):
                return True
    return False


def _has_detail_card(rec_root: dict) -> bool:
    """V20 has a white sub-card containing the 3 detail rows (받는 순번 etc.).
    Heuristic: any frame with bg-primary fill + radius ≥12 + ≥3 row children
    where children contain TEXT with '받는 순번' / '월 납입' / '기간'.
    """
    found_labels = set()
    for node, _ in walk_blueprint(rec_root):
        if node.get("type") == "text":
            t = node.get("characters") or node.get("text") or ""
            for lab in ("받는 순번", "월 납입", "기간"):
                if lab in t:
                    found_labels.add(lab)
    return len(found_labels) >= 2  # at least 2 of the 3 detail rows


def _count_ctas(rec_root: dict) -> int:
    """V20 has 2 CTAs in a row. Count distinct CTA-like nodes — works whether
    they're raw frames or DS Action Button instances (R23 inject swaps them,
    keeping the name + an _instanceText)."""
    count = 0
    for node, _ in walk_blueprint(rec_root):
        if node.get("type") in ("frame", "instance"):
            nm = (node.get("name") or "").lower()
            if "cta" in nm and ("primary" in nm or "secondary" in nm):
                count += 1
            elif str(node.get("_dsResolvedRole") or "").startswith("Action Button"):
                count += 1
    if count > 0:
        return count
    # Fallback: count CTA-text nodes (incl. inside _originalChildren stripped
    # by R23 inject) and _instanceText labels.
    cta_texts = 0
    seen = set()
    _CTAS = ("스테이지 참여하기", "맞는 스테이지 찾기")
    def _scan(n):
        nonlocal cta_texts
        if not isinstance(n, dict):
            return
        if n.get("type") == "text":
            t = (n.get("characters") or n.get("text") or "").strip().lstrip("⁠").strip()
            if t in _CTAS and t not in seen:
                seen.add(t); cta_texts += 1
        it = str(n.get("_instanceText") or "").strip().lstrip("⁠").strip()
        if it in _CTAS and it not in seen:
            seen.add(it); cta_texts += 1
        for c in (n.get("children") or []):
            _scan(c)
        for c in (n.get("_originalChildren") or []):
            _scan(c)
    _scan(rec_root)
    return cta_texts


def _has_brand_purple_root_card(rec_root: dict) -> bool:
    """V20 requires the recommend container itself (or its single direct child
    'Recommend Brand Card') to be brand-purple.
    """
    BRAND_TOKENS = {"$token(bg-brand-solid)", "$token(bg-brand-primary)", "$token(bg-brand-section_subtle)"}
    def _is_purple(n):
        f = n.get("fill")
        if isinstance(f, str) and f in BRAND_TOKENS:
            return True
        if isinstance(f, dict):
            r, g, b = f.get("r", 0), f.get("g", 0), f.get("b", 0)
            if abs(r - 0.42) < 0.1 and g < 0.2 and abs(b - 0.88) < 0.15:
                return True
        return False
    if _is_purple(rec_root):
        return True
    for c in rec_root.get("children") or []:
        if c.get("type") == "frame" and _is_purple(c):
            return True
    return False


# ── Schedule helpers (unchanged) ──────────────────────────────────

def _find_schedule_root(bp: dict):
    for node, path in walk_blueprint(bp):
        nm = (node.get("name") or "")
        if (("Schedule" in nm or "스케줄" in nm) and node.get("type") == "frame"):
            return node, path
    return None


def _v12_solid_purple_today_cell(schedule_root: dict):
    for node, _ in walk_blueprint(schedule_root):
        if node.get("type") != "frame":
            continue
        nm = (node.get("name") or "")
        if "chip" in nm.lower() or "title" in nm.lower():
            continue
        f = node.get("fill")
        is_brand_solid = False
        if isinstance(f, str) and f in ("$token(bg-brand-solid)", "$token(bg-brand-primary)"):
            is_brand_solid = True
        if isinstance(f, dict):
            r, g, b = f.get("r", 0), f.get("g", 0), f.get("b", 0)
            if abs(r - 0.42) < 0.08 and g < 0.1 and abs(b - 0.88) < 0.1:
                is_brand_solid = True
        if not is_brand_solid:
            continue
        cr = node.get("cornerRadius") or 0
        if cr < 8:
            continue
        text_count = sum(1 for inner, _ in walk_blueprint(node) if inner.get("type") == "text")
        if text_count >= 2:
            return nm or "(unnamed cell)"
    return None


def _has_schedule_card_wrapper(schedule_root: dict) -> bool:
    nm = (schedule_root.get("name") or "")
    if "Schedule Section" in nm:
        return False
    if "Schedule Card" in nm or "schedule card" in nm.lower():
        return True
    for c in schedule_root.get("children") or []:
        if (("Schedule Card" in (c.get("name") or "") or
             "Cells" in (c.get("name") or ""))
            and c.get("type") == "frame"
            and (c.get("fill") or c.get("cornerRadius"))):
            return True
    return False


# ── Rule check ─────────────────────────────────────────────────────

REC_REMEDIATION = (
    "Use blueprint_templates.json → sections.RecommendSectionV20 "
    "(canonical 2026-05-05). Brand-purple full card with action headline + "
    "white detail sub-card (받는 순번 / 월 납입 금액 / 기간) + 2 CTAs "
    "(스테이지 참여하기 + 맞는 스테이지 찾기) + '어떻게 계산되나요?' link."
)

SCHED_REMEDIATION = (
    "Use blueprint_templates.json → sections.ScheduleSectionV17 "
    "(extracted from imin_home_v17 frame node 17037:3674). "
    "v17 has no wrapper card; cells float at section level with "
    "state-tinted bg (미납=bg-error-secondary, 오늘=bg-brand-primary "
    "with brand-purple TEXT not solid bg, 지급/예정=bg-secondary)."
)


def _check_recommend(rec: dict, rec_path: str) -> Iterable[Violation]:
    # 1) Must have brand-purple container card (V20 canonical)
    if not _has_brand_purple_root_card(rec):
        yield Violation(
            "R31-imin-home-canonical",
            Severity.ERROR,
            rec_path,
            (f"Recommend Section missing brand-purple container card. "
             f"V20 canonical requires the recommend to be wrapped in a "
             f"bg-brand-solid card with cornerRadius≈24. {REC_REMEDIATION}"),
            Phase.LINT,
        )

    # 2) Must have action headline
    if not _has_action_headline(rec):
        yield Violation(
            "R31-imin-home-canonical",
            Severity.ERROR,
            rec_path,
            (f"Recommend Section missing action headline (e.g., "
             f"'NNN원 모으기 도전, 지금 시작하면 N번째에 받아요'). "
             f"V20 requires a multi-line action headline above the amount. "
             f"{REC_REMEDIATION}"),
            Phase.LINT,
        )

    # 3) Must have detail card with 받는 순번 / 월 납입 / 기간 rows
    if not _has_detail_card(rec):
        yield Violation(
            "R31-imin-home-canonical",
            Severity.ERROR,
            rec_path,
            (f"Recommend Section missing detail rows (받는 순번 / 월 납입 / 기간) "
             f"in a white sub-card. {REC_REMEDIATION}"),
            Phase.LINT,
        )

    # 4) Must have 2 CTAs
    cta_n = _count_ctas(rec)
    if cta_n < 2:
        yield Violation(
            "R31-imin-home-canonical",
            Severity.ERROR,
            rec_path,
            (f"Recommend Section has {cta_n} CTA(s) — V20 requires 2 "
             f"(스테이지 참여하기 + 맞는 스테이지 찾기). {REC_REMEDIATION}"),
            Phase.LINT,
        )


def _check_schedule(sched: dict, sched_path: str) -> Iterable[Violation]:
    bad_cell = _v12_solid_purple_today_cell(sched)
    if bad_cell:
        yield Violation(
            "R31-imin-home-canonical",
            Severity.ERROR,
            f"{sched_path}/{bad_cell}",
            (f"Schedule cell '{bad_cell}' uses solid brand-purple bg — "
             f"v12 anti-pattern. v17 uses light bg-brand-primary with "
             f"brand-purple TEXT. {SCHED_REMEDIATION}"),
            Phase.LINT,
        )

    if _has_schedule_card_wrapper(sched):
        yield Violation(
            "R31-imin-home-canonical",
            Severity.ERROR,
            sched_path,
            (f"Schedule cells are wrapped in a card container — v12 "
             f"anti-pattern. v17 has NO wrapper. {SCHED_REMEDIATION}"),
            Phase.LINT,
        )


def _has_footer_section(bp: dict) -> bool:
    """imin_home requires a Footer Section with legal text (이용약관 등).
    Heuristic: any frame named 'Footer' OR contains text '이용약관' /
    'Copyright' / '사업자등록번호'."""
    LEGAL_KEYS = ("이용약관", "Copyright", "사업자등록", "통신판매업")
    for node, _ in walk_blueprint(bp):
        nm = (node.get("name") or "")
        if "footer" in nm.lower():
            return True
        if node.get("type") == "text":
            t = node.get("characters") or node.get("text") or ""
            if any(k in t for k in LEGAL_KEYS):
                return True
    return False


def _has_fab(bp: dict) -> bool:
    """imin_home requires a floating action button (FAB) above the Tab Bar.
    Heuristic: any frame whose name == 'FAB' or contains 'fab' token-bounded."""
    import re
    FAB_NAME_RE = re.compile(r"\bfab\b|^fab$", re.I)
    for node, _ in walk_blueprint(bp):
        if (node.get("type") or "").lower() != "frame":
            continue
        nm = (node.get("name") or "")
        if FAB_NAME_RE.search(nm):
            return True
    return False


FAB_REMEDIATION = (
    "Use blueprint_templates.json → sections.FAB (120×44 pill, cornerRadius 22, "
    "fill $token(bg-brand-solid), HORIZONTAL auto-layout with icon+label). "
    "post-fix automatically applies ABSOLUTE positioning at x=253, y=Tab Bar_y - 60. "
    "Default label '마이 월렛' (icon wallet-02) — override per PRD if needed. "
    "imin_home baseline always includes FAB; omitting it leaves the home screen "
    "without its primary floating CTA."
)


FOOTER_REMEDIATION = (
    "Use blueprint_templates.json → sections.FooterSection (canonical legal "
    "footer with 이용약관 / 개인정보처리방침 / 사업자등록번호 / Copyright). "
    "imin_home v22 baseline always includes it; omitting it produces a "
    "truncated-looking page where the bottom Tab Bar floats below the last "
    "content section."
)


def _check(bp: dict, ctx: dict) -> Iterable[Violation]:
    if not _is_imin_home(bp):
        return
    found = _find_recommend_root(bp)
    if found:
        rec, rec_path = found
        yield from _check_recommend(rec, rec_path)
    sched_found = _find_schedule_root(bp)
    if sched_found:
        sched, sched_path = sched_found
        yield from _check_schedule(sched, sched_path)
    if not _has_footer_section(bp):
        yield Violation(
            "R31-imin-home-canonical",
            Severity.ERROR,
            "root",
            (f"imin_home missing Footer Section (legal text: 이용약관 / "
             f"개인정보처리방침 / 사업자등록번호 / Copyright). {FOOTER_REMEDIATION}"),
            Phase.LINT,
        )
    if not _has_fab(bp):
        yield Violation(
            "R31-imin-home-canonical",
            Severity.ERROR,
            "root",
            (f"imin_home missing FAB (floating action button above Tab Bar). "
             f"{FAB_REMEDIATION}"),
            Phase.LINT,
        )


register(Rule(
    rule_id="R31-imin-home-canonical",
    title="imin_home Recommend (V20) + Schedule (v17) canonical structure",
    description=(
        "Enforces V20 brand-purple Recommend Section pattern (action headline + "
        "white detail sub-card + 2 CTAs) and v17 wrapperless Schedule Section "
        "with state-tinted cells."
    ),
    check_blueprint_fn=_check,
))
