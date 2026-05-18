"""DS component key catalog.

Single source of truth for every componentKey we use, plus name-pattern
matchers used by R23 to detect raw-frame violations + auto-inject componentKeys.

Sourced from local DS dump (get_local_components) + memory invariants.
Keep in sync with the live Figma library; if a key changes, update here.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple


# ── componentKey by canonical role name ─────────────────────────

COMPONENT_KEYS = {
    # ── Brand / chrome ─────────────────────────────────────────
    "Logo":                 "81efeddd245e95f31a2724aa370ee54d3caf93d0",
    "Logo (alt)":           "957912b03baf924a48ef83424ed66f22a4a386a8",

    # ── Mobile system chrome ───────────────────────────────────
    "Status Bar":           "51ddb19de206b67eae2d554b1d20c018feb754f4",  # iPhone 9:41

    # ── Pills (sm) ─────────────────────────────────────────────
    "Pill sm Brand":        "d0163041d0c710551c31ffd4acaca5ce42f993ac",
    "Pill sm Success":      "e8f010fe720f6742a38c8c8c1c591531fcb5149b",
    "Pill sm Warning":      "8cf0d360a58aa027e447ee6c47944e41d89f9699",
    "Pill sm Pink":         "cd973d99c3f1baab0c1a37aa1f1982c73f1b1ca9",
    "Pill sm Gray blue":    "718da0d3d3a6881c12167505d6d1c5b22f372f61",

    # ── Pills (md, no icon) ───────────────────────────────────
    "Pill md Brand":        "bcaa38d6c59bb21c31522489f5cb9af4c85d7333",
    "Pill md Warning":      "db55c05edb3d5f9ba13805fcdb715c9048d4f396",
    "Pill md Success":      "47bf09ac3906a76fdcd0e63925aeb9813ae72b62",
    "Pill md Gray blue":    "fe43f9b5a880ef8e3f7cbe6c5434f32c56a7361b",
    "Pill md Blue light":   "d33f595efd17911c2f437fe839b03f515f795c91",

    # ── Badges (sm) ────────────────────────────────────────────
    "Badge sm Brand":       "03b25488b460f514f23ddf39b5b42f7d31e7935e",
    "Badge sm Purple":      "39170ab4e765ca3e09fc46b27f7e50061696065e",
    "Badge sm Success":     "6c0c2ebab689aedebd84c160e1e3ce6af3dcd8f2",
    "Badge sm Warning":     "5e675a5727f7868ff72f067dad64ea50fe04a43e",

    # ── Buttons (DS "Buttons/Button" — Size/Hierarchy/State/Icon only) ──
    # 2026-05-12: c51e2ea8… ("Action buttons" Type) is a composite w/ a
    # "Supporting text" slot that renders a stray "Edit" label — WRONG for a
    # CTA. The real single CTA is the Hierarchy=* variant set below.
    "Action Button md":            "ed0032bcf28f03da97e4b3006f54d30a0fbe5914",  # =Primary
    "Action Button md Primary":    "ed0032bcf28f03da97e4b3006f54d30a0fbe5914",
    "Action Button md Secondary":  "19c3ba6ad85401ae2427b178c20129d4260c62d0",
    "Action Button md Tertiary":   "56f68ea2e54e10240c904c0cef9cbbea13adcf0f",
    "Action Button md Outline":    "f00aebde66a2e045ad67d833202e6403305a3872",
    "Action Button md Ghost":      "d8e947e4d7eed3449e7ca89d4f974fe728b6d1eb",
    "Action Button md (composite, do-not-use)": "c51e2ea849dccd8545523288c29a5edf25b5a88b",
    "Action Button sm":            "a8a4d7eb7874c469ab89105cc342fad85a3d28ce",

    # ── Tabs ───────────────────────────────────────────────────
    "Underline Tab Item":   "2fd0d4316087ce3d04816dc5f2eb8c421e43588f",

    # ── NavBar variants ────────────────────────────────────────
    "Section Header":       "24c310156df2b11a3204cc317fb4bf9149953f9a",
    "Back Header":          "7378e8e6833234a06636571a0507a2e9cb114363",
    "Modal Header":         "ee5c0e5184d4597e1ccf804de204198e0f13b0a4",
    "Type Header":          "ed6ef9d403a570d5176d69bc314a54390409bbac",

    # ── Header / utility icons (24px, line) ────────────────────
    "Icon bell":            "f80e23373a1afc1b460be44da32915f390b5af2a",  # bell-01
    "Icon chat":            "3071d1cea18e103f7187986d83ecc64972cccb21",  # message-circle-01
    "Icon home":            "3b9e167503a7a91c597375d8c11c4f1a39fe5705",  # home-01
    "Icon home solid":      "aa98f2a00ec685f444b8db18b8f569c87a8333e1",  # solid_home-line
    "Icon shopping bag":    "152430df50a07e03ae0c23e66095ca1e01cad66a",  # shopping-bag-01
    "Icon users":           "79e81ec517b9231b88e83c3b2320152ae38fd683",  # users-01
    "Icon menu":            "773e8ac3572b64c2031233074661490b45c43584",  # menu-01
    "Icon stars":           "781d56540e849275dbc6f0cbf93b0bdb1a1392f4",  # stars-01
    "Icon wallet":          "aa266194d742496709395561be5836b1445ee6ab",  # wallet-01
    "Icon calendar":        "f698e668f4259ac533a78c5f3be2cef705f3e9c7",
    "Icon calendar check":  "9fd39ab78add0eb0bb1c14dec21f94436602d89c",
    "Icon verified":        "3573927df03a08371e487d78803095fe0fd47423",  # check-verified-01
    "Icon help":            "8cf3b907326b40b752388a53b50320e3d7700a5e",
    "Icon chevron right":   "e651fa113a7da73d33c1c755c8e4ed252bd6a9f5",
    "Icon x close":         "4ba052703931aeecf495c7698e5002b6c89d1ad4",
    "Icon search":          "7c9a1100b148110910806002a8a85b6eb9920582",  # search-md
    "Icon stage":           "79e81ec517b9231b88e83c3b2320152ae38fd683",  # users-01 fallback (스테이지)

    # ── Form controls / atoms ──────────────────────────────────
    # 2026-05-12: created a test instance of each candidate key to verify.
    # VERIFIED (auto-swap eligible — see _VERIFIED_AUTOSWAP_ROLES):
    "Toggle":               "6c66b20c0054ba23e40420d9972267ada9b6191b",  # 36×20 switch ✓
    "Progress bar":         "7c6682945eb3fd533b05e7bdc03b896162de6cdb",  # 320×8 progress bar ✓
    "Progress bar labeled": "32834eea5e574fb40c33a6e038c4884655b5eecd",  # Progress=0%, Label=Right
    # UNVERIFIED — the first key I picked turned out to be an *icon* or a
    # *modal* or a *tag*, not the control. Detection still emits a WARN so
    # the gap is visible, but these are NOT auto-swapped until a real key is
    # confirmed. (Real ones likely under Type=Checkbox / Type=Radio button /
    # Type=Input field component SETS — needs a careful pass.)
    "Checkbox md":           "bbd5c20958464e51295e73c3c90ef7d54c0b0b69",  # 20×20 Checked=False ✓
    "Checkbox md checked":   "73691ec35c62c70735d61722347dfd995b32c5ec",  # 20×20 Checked=True ✓
    "Radio md":              "f743202ee1c1ac21c07e5347063230cd1f3aed76",  # 20×20 Selected=False ✓
    "Radio md selected":     "b0c3ae6338fa48cfd619e3c347a1d008b1d414c6",  # 20×20 Selected=True ✓
    "Input field":           "074f2839b4ce11d761931642b0305f277f811563",  # CS 'Input field' default member, 320×96 ✓
    "Slider":                "dda7a750676f41444425e6616d01f06fbcb3ff6c",  # CS 'Slider' Label=Top floating 0% 320×24 ✓
    "Tooltip":               "e979943c0c6acb589d90da7afff7e62e294a7031",  # CS 'Tooltip' Supporting text=False, Arrow=None 106×34 ✓
    "Dropdown":              "7a694080c6546c9c4d27acbe35e8dc36ceb18559",  # CS 'Dropdown' Type=Button Open=False 111×36 ✓
    "Select":                "f7a3ef93afb47ca7d13e96a735a332732839cb87",  # CS 'Select' md Placeholder 320×88 ✓
    "Segmented tab item":        "28269da222042366fed0e1032514bb8ff7d4b094",  # segmentedTabItem (used by R29)
}

# Roles whose key is verified to instantiate as the right atomic control →
# R23 may auto-swap a *shape-matched* raw frame to them. Button hierarchies
# are handled separately (detect_button_shape). Everything else is WARN-only.
_VERIFIED_AUTOSWAP_ROLES = {"Toggle", "Progress bar", "Checkbox", "Radio", "Input field", "Slider", "Tooltip", "Dropdown"}


# ── Pattern → category (for R23 lint detection) ─────────────────

DS_PATTERNS = [
    (re.compile(r"\bStatus\s*Bar\b", re.I),  "Status Bar"),
    (re.compile(r"\bNav\s*Bar\b",    re.I),  "NavBar"),
    (re.compile(r"\bTab\s*Bar\b",    re.I),  "Tab Bar"),
    (re.compile(r"\bLogo\b",         re.I),  "Logo"),
    (re.compile(r"\bPill\b",         re.I),  "Pill"),
    (re.compile(r"\bBadge\b",        re.I),  "Badge"),
    (re.compile(r"\b(?:Action\s*)?Button\b", re.I), "Button"),
    (re.compile(r"\bAvatar\b",       re.I),  "Avatar"),
    (re.compile(r"\bChip\b",         re.I),  "Chip/Tag"),
]


# ── name → componentKey resolver (used by R23 inject) ───────────
#
# This is the magic that turns raw frames into instances automatically.
# The matcher walks rules in order; first match wins. Each rule maps a
# regex on the node's `name` to a canonical role (one of COMPONENT_KEYS).

# Strict resolvers: require explicit DS-component keyword as a TOKEN, not
# just a substring. Wrappers like "Home Tabs", "Stage Progress Wrap",
# "Recommend Stage Card", "Lounge Section" must not match.
#
# Convention:
#   icons → must end with " Icon" or " Btn"
#   pills → must end with " Pill"
#   badges → must end with " Badge"
#   buttons → must end with " Button" or " Btn" (when meant as a CTA button,
#             not the generic icon-button suffix above)
#
# A node like "Home Tabs" → last token "tabs" is in _CONTAINER_SUFFIXES so
# is_container() catches it before resolver runs anyway.

_NAME_RESOLVERS: list[Tuple[re.Pattern, str]] = [
    # Mobile system chrome (full-name match)
    (re.compile(r"^status\s*bar$",                            re.I), "Status Bar"),

    # Brand (full-name or "Logo Placeholder")
    (re.compile(r"^(?:imin\s*)?logo(?:\s*placeholder)?$",     re.I), "Logo"),

    # CTA Action Button — only for explicitly-named primary action buttons.
    # NOTE: "All View Btn" intentionally NOT mapped — DS Action Button master
    # is a 2-link button group (Delete/Edit), not a single-text CTA. Keep
    # such single-text CTAs as raw styled frames or use DS only when names
    # clearly indicate dual-action.
    (re.compile(r"^(?:primary|action)\s+button$",             re.I), "Action Button md"),

    # Pills — must end with " Pill" + color prefix
    (re.compile(r"^(?:active|brand)\s+pill(?:\s+\S+)?$",      re.I), "Pill md Brand"),
    (re.compile(r"^success\s+pill(?:\s+\S+)?$",               re.I), "Pill md Success"),
    (re.compile(r"^warning\s+pill(?:\s+\S+)?$",               re.I), "Pill md Warning"),
    (re.compile(r"^gray\s+pill(?:\s+\S+)?$",                  re.I), "Pill md Gray blue"),
    # Pill with content suffix e.g. "Gray Pill 10만원" — match the prefix form
    (re.compile(r"^pill(?:\s+\S+)?$",                         re.I), "Pill md Gray blue"),

    # Badges — must end with " Badge"
    (re.compile(r"^verified\s+badge$",                        re.I), "Icon verified"),
    (re.compile(r"^light\s+badge$",                           re.I), "Icon stars"),
    (re.compile(r"^success\s+badge$",                         re.I), "Badge sm Success"),
    (re.compile(r"^warning\s+badge$",                         re.I), "Badge sm Warning"),
    (re.compile(r"^purple\s+badge$",                          re.I), "Badge sm Purple"),
    (re.compile(r"^(?:brand)?\s*badge$",                      re.I), "Badge sm Brand"),

    # Icons / button-style wrappers — must end with " Icon" or " Btn"
    (re.compile(r"^bell\s+btn$",                              re.I), "Icon bell"),
    (re.compile(r"^(?:chat|message|conversation)\s+btn$",     re.I), "Icon chat"),
    (re.compile(r"^home\s+icon$",                             re.I), "Icon home"),
    (re.compile(r"^lounge\s+icon$",                           re.I), "Icon shopping bag"),
    (re.compile(r"^stage\s+icon$",                            re.I), "Icon users"),
    (re.compile(r"^community\s+icon$",                        re.I), "Icon users"),
    (re.compile(r"^menu\s+icon$",                             re.I), "Icon menu"),
    (re.compile(r"^wallet\s+icon$",                           re.I), "Icon wallet"),
    (re.compile(r"^calendar\s+icon$",                         re.I), "Icon calendar"),
    (re.compile(r"^help\s+icon$",                             re.I), "Icon help"),
    (re.compile(r"^chevron(?:\s+right)?\s+icon$",             re.I), "Icon chevron right"),
    (re.compile(r"^(?:close|x[\s-]*close)\s+icon$",           re.I), "Icon x close"),
    (re.compile(r"^search\s+icon$",                           re.I), "Icon search"),
    (re.compile(r"^stars?\s+icon$",                           re.I), "Icon stars"),
    (re.compile(r"^verified\s+icon$",                         re.I), "Icon verified"),
]


# Names that are *containers* of DS components, NOT swappable themselves.
_CONTAINER_NAMES = {
    "navbar", "nav bar",
    "tab bar",
    "header actions",
    "badge row", "pill row",
    "header", "header row",
    "tab row", "round bar",
}


# Suffix keywords that mark a node as a layout wrapper (never swap).
# If a node's name ends with — or contains as a token — any of these,
# treat as container regardless of other matches.
_CONTAINER_SUFFIXES = (
    "section", "wrap", "wrapper",
    "row", "column", "col",
    "card", "group", "container",
    "scroll", "list",
    "tabs",  # "Home Tabs" is the tab strip, not a tab item
    "header",
)


def is_container(name: str) -> bool:
    """Return True for layout wrappers (Section/Wrap/Row/Card/Group/Header/Tabs).

    Strict: matches the trailing keyword token, OR the explicit container
    name list. This prevents R23 from swapping wrappers like "Home Tabs",
    "Stage Progress Wrap", "Lounge Section", "Recommend Stage Card".
    """
    if not name:
        return False
    nl = name.strip().lower()
    if nl in _CONTAINER_NAMES:
        return True
    # Tokenize on whitespace; check last token first (suffix), then any
    tokens = nl.replace("(", " ").replace(")", " ").split()
    if not tokens:
        return False
    last = tokens[-1]
    if last in _CONTAINER_SUFFIXES:
        return True
    # also catch e.g. "Day Cells Row" where last="row" but inner has plural too
    for t in tokens:
        if t in _CONTAINER_SUFFIXES:
            return True
    return False


def resolve_component_key(name: str) -> Optional[Tuple[str, str]]:
    """Return (role, componentKey) if the name resolves to a known DS component.

    Returns None if no match — caller decides whether to keep as raw frame
    (containers) or fail the lint (unsatisfiable DS-implied name).
    """
    if not name:
        return None
    for pat, role in _NAME_RESOLVERS:
        if pat.search(name):
            key = COMPONENT_KEYS.get(role)
            if key:
                return role, key
    return None


# ── Structural (shape-based) DS detection ──────────────────────
#
# Name-pattern matching only catches frames named exactly "Action Button"
# / "Success Badge" etc. — almost no real blueprint names a CTA that way
# (they use "Pay Now Btn", "CTA Primary", "스케줄 확인", ...). So DS-first
# was effectively unenforced. These detect a button / badge by *shape*
# regardless of name, so they get caught + auto-swapped + hard-gated.
# User policy 2026-05-12: "DS 컴포넌트 우선" must be enforced structurally,
# not via fragile name strings.

def _children(node: dict) -> list:
    return node.get("children") or node.get("_originalChildren") or []


def _text_of(node: dict) -> Optional[str]:
    return node.get("characters") or node.get("text")


def _corner_radius(node: dict) -> float:
    cr = node.get("cornerRadius")
    if isinstance(cr, (int, float)):
        return float(cr)
    # individual radii
    for k in ("topLeftRadius", "topRightRadius", "bottomLeftRadius", "bottomRightRadius"):
        v = node.get(k)
        if isinstance(v, (int, float)) and v:
            return float(v)
    return 0.0


def _h_padding(node: dict) -> float:
    al = node.get("autoLayout") or {}
    pl = al.get("paddingLeft", node.get("paddingLeft", 0)) or 0
    pr = al.get("paddingRight", node.get("paddingRight", 0)) or 0
    return float(pl) + float(pr)


def _v_padding(node: dict) -> float:
    al = node.get("autoLayout") or {}
    pt = al.get("paddingTop", node.get("paddingTop", 0)) or 0
    pb = al.get("paddingBottom", node.get("paddingBottom", 0)) or 0
    return float(pt) + float(pb)


# Korean / English short status words → these tiny pills are BADGES, not CTAs.
_STATUS_WORDS = (
    "미납", "연체", "완료", "진행중", "진행", "지급예정", "지급", "예정", "오늘 납입",
    "납입 완료", "납입완료", "신규", "new", "hot", "done", "active", "pending",
)


def _layout_mode(node: dict) -> str:
    al = node.get("autoLayout") or {}
    return (al.get("layoutMode") or node.get("layoutMode") or "").upper()


_ARROW_CHARS = {"→", "›", ">", "↗", "⟶", "»"}


def _is_label_only_children(node: dict) -> Optional[str]:
    """If a node's children are ONLY text (1 label, optionally + an arrow glyph),
    return the label text. Else None. Vector/icon/frame children → None."""
    ch = _children(node)
    if not ch:
        return None
    label = None
    for c in ch:
        ct = (c.get("type") or "frame").lower()
        if ct != "text":
            return None
        txt = (_text_of(c) or "").strip().lstrip("⁠").strip()
        if not txt:
            continue
        if txt in _ARROW_CHARS or (len(txt) <= 2 and not txt[0].isalnum()):
            continue  # arrow / chevron glyph — ignore
        if label is None:
            label = txt
        else:
            # two real labels — not a simple button (maybe segmented row)
            return None
    return label


def detect_button_shape(node: dict) -> Optional[Tuple[str, str, str]]:
    """Detect a CTA-button-shaped frame. Returns (role, componentKey, labelText)
    or None.

    Heuristic: a frame (not a container by name) whose children are text-only
    (label, optionally + arrow), has a cornerRadius, horizontal padding, and a
    HORIZONTAL auto-layout. Width/height not required (FILL buttons have no
    explicit size in the blueprint).
    """
    if not isinstance(node, dict):
        return None
    ntype = (node.get("type") or "frame").lower()
    if ntype not in ("frame",):
        return None
    if node.get("componentKey"):
        return None
    name = node.get("name") or ""
    if is_container(name):
        # …but "X Btn" / "X Button" / "CTA X" should NOT be treated as a
        # container even though some end with a container-ish token.
        nl = name.lower()
        if not (nl.endswith("btn") or nl.endswith("button") or nl.startswith("cta ")
                or " btn " in f" {nl} " or " button " in f" {nl} "):
            return None
    label = _is_label_only_children(node)
    if not label:
        return None
    if _corner_radius(node) < 6:
        return None
    if _h_padding(node) < 8:
        return None
    if _layout_mode(node) and _layout_mode(node) != "HORIZONTAL":
        return None
    # explicit height sanity — buttons aren't tall blocks
    h = node.get("height")
    if isinstance(h, (int, float)) and h > 80:
        return None
    # ── exclude BADGE/PILL-tier frames ──────────────────────────
    # A CTA button has generous vertical padding (≥ ~8, usually 12–16) so its
    # HUG height lands ~36–52. A status pill / badge has tiny padding (≤ ~6)
    # and short text. So: tiny vertical padding ⇒ NOT a button → let
    # detect_badge_shape claim it. (User policy 2026-05-12: "미납 1" must be a
    # badge, not a button — systemic, not a one-off.)
    vp = _v_padding(node)
    if vp and vp < 8:
        return None
    if (isinstance(h, (int, float)) and h <= 28):
        return None
    # very short label + narrow/no explicit width + small padding = badge
    if (label and len(label) <= 6 and vp <= 6
            and (not isinstance(node.get("width"), (int, float)) or node.get("width") < 96)):
        return None
    # pick the Hierarchy variant by the raw frame's fill / stroke
    role = _button_hierarchy_role(node)
    key = COMPONENT_KEYS[role]
    return (role, key, label)


# fill-token → Action Button Hierarchy variant role
_BRAND_FILL_HINTS = ("brand-solid", "brand-primary-solid", "brand-section",
                     "error", "warning", "success")  # colored solid CTA → Primary master


def _button_hierarchy_role(node: dict) -> str:
    """Map the raw frame's fill/stroke to one of the DS Button Hierarchy
    variant component roles. Best-effort — a wrong guess is visually fixable;
    the point is to use the DS component at all."""
    fill = node.get("fill") or node.get("fills")
    fill_s = fill.lower() if isinstance(fill, str) else ""
    has_stroke = bool(node.get("stroke") or node.get("strokes") or node.get("strokeColor"))
    if any(h in fill_s for h in _BRAND_FILL_HINTS):
        return "Action Button md Primary"
    if has_stroke:
        return "Action Button md Outline"
    if not fill_s or "bg-primary" in fill_s or "bg-secondary" in fill_s:
        # white/neutral background pill → Secondary (light brand) button
        return "Action Button md Secondary"
    return "Action Button md Primary"


# kept for backward-compat; not used for key selection anymore
def button_variant_props(node: dict) -> dict:  # noqa: D401
    return {}


# Status-badge / tag colors → DS Badge sm component
_BADGE_COLOR_ROLE = [
    (("success", "진행", "완료", "납입 완료", "지급"), "Badge sm Success"),
    (("warning", "예정", "곧", "오늘"), "Badge sm Warning"),
    (("error", "미납", "연체", "긴급"), "Badge sm Warning"),  # no error badge → warning
    (("purple",), "Badge sm Purple"),
]


def detect_badge_shape(node: dict) -> Optional[Tuple[str, str, str]]:
    """Detect a small status-badge / tag-shaped frame: a frame with exactly one
    short text child, a cornerRadius, and small dimensions. Returns
    (role, componentKey, labelText) or None."""
    if not isinstance(node, dict):
        return None
    ntype = (node.get("type") or "frame").lower()
    if ntype not in ("frame",) or node.get("componentKey"):
        return None
    name = (node.get("name") or "")
    if is_container(name):
        return None
    label = _is_label_only_children(node)
    if not label or len(label) > 12:
        return None
    if _corner_radius(node) < 4:
        return None
    h = node.get("height")
    w = node.get("width")
    if isinstance(h, (int, float)) and h > 30:
        return None
    if isinstance(w, (int, float)) and w > 140:
        return None
    # must have *some* fill (a transparent text-only row isn't a badge)
    if not (node.get("fill") or node.get("fills")):
        return None
    fill_s = str(node.get("fill") or "").lower()
    combined = (fill_s + " " + label).lower()
    role = "Badge sm Brand"
    for keys, r in _BADGE_COLOR_ROLE:
        if any(k.lower() in combined for k in keys):
            role = r
            break
    key = COMPONENT_KEYS.get(role) or COMPONENT_KEYS["Badge sm Brand"]
    return (role, key, label)



# ── Additional structural detectors (form controls / atoms) ─────
#
# Each returns (role, componentKey, instanceText|None) or None — same shape
# as detect_button_shape / detect_badge_shape. Auto-swap eligibility is
# decided centrally in detect_ds_role_structural() using
# _VERIFIED_AUTOSWAP_ROLES + a per-role "distinctive shape present" check;
# anything else surfaces as a WARN only (no swap).

def _has_child_of_type(node: dict, *types: str) -> bool:
    ts = {t.lower() for t in types}
    return any((c.get("type") or "").lower() in ts for c in _children(node))


def _name_hints(node: dict, *needles: str) -> bool:
    nl = (node.get("name") or "").lower()
    return any(n in nl for n in needles)


def _name_ends_with(node: dict, *words: str) -> bool:
    """True if the node name's LAST whitespace token is one of `words`.
    Stricter than substring — 'Calc Toggle Row' (last token 'row') won't
    match 'toggle', but 'Notify Toggle' will."""
    toks = (node.get("name") or "").strip().lower().replace("(", " ").replace(")", " ").split()
    return bool(toks) and toks[-1] in {w.lower() for w in words}


_PLACEHOLDER_RE = re.compile(r"(입력해?|선택해?\s*주세요|예\s*:|placeholder|검색)", re.I)


def detect_input_shape(node: dict):
    """Text input: bordered frame, cornerRadius ≥ 4, h ≈ 32–64, single
    placeholder-ish TEXT child. (Key UNVERIFIED → WARN only.)"""
    if (node.get("type") or "frame").lower() != "frame" or node.get("componentKey"):
        return None
    name_ok = _name_ends_with(node, "input", "field", "입력칸", "입력필드")
    if is_container(node.get("name") or "") and not name_ok:
        return None
    has_border = bool(node.get("stroke") or node.get("strokes") or node.get("strokeColor"))
    label = _is_label_only_children(node)
    h = node.get("height")
    shape_ok = (has_border and _corner_radius(node) >= 4
                and (not isinstance(h, (int, float)) or 32 <= h <= 64)
                and label is not None and bool(_PLACEHOLDER_RE.search(label or "")))
    if not (shape_ok or name_ok):
        return None
    return ("Input field", COMPONENT_KEYS["Input field"], label)


def detect_dropdown_shape(node: dict):
    """Dropdown / select trigger: bordered frame + a TEXT child + a chevron/
    caret/icon child, h ≈ 32–60. (Key UNVERIFIED → WARN only.)"""
    if (node.get("type") or "frame").lower() != "frame" or node.get("componentKey"):
        return None
    name_ok = _name_ends_with(node, "dropdown", "select", "드롭다운")
    if is_container(node.get("name") or "") and not name_ok:
        return None
    has_border = bool(node.get("stroke") or node.get("strokes"))
    has_text = _has_child_of_type(node, "text")
    has_icon = any(("chevron" in (c.get("name") or "").lower() or "caret" in (c.get("name") or "").lower()
                    or (c.get("type") or "").lower() in ("vector", "icon"))
                   for c in _children(node))
    h = node.get("height")
    shape_ok = (has_border and has_text and has_icon and _corner_radius(node) >= 4
                and (not isinstance(h, (int, float)) or 32 <= h <= 60))
    if not (shape_ok or name_ok):
        return None
    return ("Dropdown", COMPONENT_KEYS["Dropdown"], None)


def detect_toggle_shape(node: dict):
    """Switch/toggle: small elongated pill (radius ≥ ~half-height) with one
    ellipse child (the knob), w ≈ 28–56, h ≈ 14–32, w > h. Key VERIFIED."""
    if (node.get("type") or "frame").lower() != "frame" or node.get("componentKey"):
        return None
    w, h = node.get("width"), node.get("height")
    shape_ok = (isinstance(w, (int, float)) and isinstance(h, (int, float))
                and 26 <= w <= 60 and 14 <= h <= 34 and w > h
                and _corner_radius(node) >= h / 2 - 2
                and _has_child_of_type(node, "ellipse"))
    name_ok = _name_ends_with(node, "toggle", "switch", "스위치", "토글")
    if not (shape_ok or name_ok):
        return None
    return ("Toggle", COMPONENT_KEYS["Toggle"], None)


def detect_checkbox_shape(node: dict):
    """Checkbox: tiny ≈14–26px square frame, small cornerRadius (≤8), with a
    'check' child, or named '… checkbox'. (Key UNVERIFIED → WARN only.)"""
    if (node.get("type") or "frame").lower() != "frame" or node.get("componentKey"):
        return None
    name_ok = _name_ends_with(node, "checkbox", "체크박스")
    w, h = node.get("width"), node.get("height")
    shape_ok = (isinstance(w, (int, float)) and isinstance(h, (int, float))
                and 14 <= w <= 26 and 14 <= h <= 26 and abs(w - h) <= 4
                and 0 <= _corner_radius(node) <= 8 and _name_hints(node, "check"))
    if not (shape_ok or name_ok):
        return None
    checked = _name_hints(node, "checked", "selected", "true", "on")
    role = "Checkbox" + (" md checked" if checked else " md")
    key = COMPONENT_KEYS["Checkbox md checked" if checked else "Checkbox md"]
    return ("Checkbox", key, None)


def detect_radio_shape(node: dict):
    """Radio: tiny ≈14–26px circular frame, or named '… radio'.
    (Key UNVERIFIED → WARN only.)"""
    if (node.get("type") or "frame").lower() != "frame" or node.get("componentKey"):
        return None
    name_ok = _name_ends_with(node, "radio", "라디오")
    w, h = node.get("width"), node.get("height")
    shape_ok = (isinstance(w, (int, float)) and isinstance(h, (int, float))
                and 14 <= w <= 26 and 14 <= h <= 26 and abs(w - h) <= 3
                and _corner_radius(node) >= min(w, h) / 2 - 1
                and _name_hints(node, "radio", "option"))
    if not (shape_ok or name_ok):
        return None
    sel = _name_hints(node, "selected", "checked", "true", "on", "active")
    key = COMPONENT_KEYS["Radio md selected" if sel else "Radio md"]
    return ("Radio", key, None)


def detect_slider_shape(node: dict):
    """Slider: thin track (h ≤ 28) with an ellipse 'thumb' child, or named
    '… slider'. (Key UNVERIFIED → WARN only.)"""
    if (node.get("type") or "frame").lower() != "frame" or node.get("componentKey"):
        return None
    name_ok = _name_ends_with(node, "slider", "슬라이더")
    h = node.get("height")
    shape_ok = (isinstance(h, (int, float)) and h <= 28
                and _has_child_of_type(node, "ellipse") and _corner_radius(node) >= 2)
    if not (shape_ok or name_ok):
        return None
    return ("Slider", COMPONENT_KEYS["Slider"], None)


def _progress_shape_ok(node: dict) -> bool:
    h, w = node.get("height"), node.get("width")
    thin = isinstance(h, (int, float)) and 2 <= h <= 14
    wide = (not isinstance(w, (int, float))) or w >= 40
    aspect_ok = (not isinstance(w, (int, float)) or not isinstance(h, (int, float))) or (w >= 4 * h)
    return bool(thin and wide and aspect_ok and _corner_radius(node) >= 2)


def detect_progress_shape(node: dict):
    """Progress bar: thin (h 2–14) wide track frame, full-ish radius, or a
    frame named '… progress track / progress bar'. Key VERIFIED."""
    if (node.get("type") or "frame").lower() != "frame" or node.get("componentKey"):
        return None
    nl = (node.get("name") or "").lower()
    name_ok = ("progress" in nl and ("track" in nl or "bar" in nl)) or _name_ends_with(node, "progress")
    has_bar_child = any(
        isinstance(c.get("height"), (int, float)) and c["height"] <= 14
        for c in _children(node) if (c.get("type") or "").lower() == "frame"
    )
    if not (_progress_shape_ok(node) or (name_ok and (_progress_shape_ok(node) or has_bar_child))):
        return None
    return ("Progress bar", COMPONENT_KEYS["Progress bar"], None)


# Roles eligible for auto-swap require BOTH a verified key (above) AND that
# the node carries the role's distinctive *shape* (not just a name hint).
def _has_distinctive_shape(node: dict, role: str) -> bool:
    if role == "Toggle":
        w, h = node.get("width"), node.get("height")
        return (isinstance(w, (int, float)) and isinstance(h, (int, float))
                and 26 <= w <= 60 and 14 <= h <= 34 and w > h
                and _has_child_of_type(node, "ellipse"))
    if role == "Progress bar":
        return _progress_shape_ok(node)
    if role == "Checkbox":
        return _name_ends_with(node, "checkbox", "체크박스")
    if role == "Radio":
        return _name_ends_with(node, "radio", "라디오")
    if role == "Input field":
        h = node.get("height")
        has_border = bool(node.get("stroke") or node.get("strokes") or node.get("strokeColor"))
        return _name_ends_with(node, "input", "field", "입력칸", "입력필드") or (
            has_border and isinstance(h, (int, float)) and 32 <= h <= 96 and _corner_radius(node) >= 4)
    if role == "Slider":
        h = node.get("height")
        return _name_ends_with(node, "slider", "슬라이더") or (
            isinstance(h, (int, float)) and h <= 28 and _has_child_of_type(node, "ellipse"))
    if role == "Tooltip":
        return _name_ends_with(node, "tooltip", "툴팁")
    if role == "Dropdown":
        h = node.get("height")
        has_border = bool(node.get("stroke") or node.get("strokes"))
        has_chevron = any(("chevron" in (c.get("name") or "").lower() or "caret" in (c.get("name") or "").lower())
                          for c in _children(node))
        return _name_ends_with(node, "dropdown", "select", "드롭다운", "셀렉트") or (
            has_border and has_chevron and _has_child_of_type(node, "text")
            and isinstance(h, (int, float)) and 32 <= h <= 88 and _corner_radius(node) >= 4)
    return False


def detect_ds_role_structural(node: dict):
    """Unified structural DS detector. Returns (role, componentKey,
    instanceText, confident) or None.

      confident=True  ⇒ R23 auto-swaps the raw frame to the DS instance.
      confident=False ⇒ R23 emits a WARN (component-shaped raw frame) but
                        leaves it as-is.

    Priority: button → badge/tag → input → dropdown → toggle → checkbox →
    radio → slider → progress. Buttons are always confident (verified key,
    strict shape). For everything else: confident only if the role's key is
    verified (_VERIFIED_AUTOSWAP_ROLES) AND the node has the role's
    distinctive shape — name hints alone are never enough to auto-swap.
    """
    if not isinstance(node, dict):
        return None
    # 1) button — DETECTED but NOT auto-swapped (2026-05-12). The DS
    #    "Buttons/Button" instance doesn't drop in cleanly: collapses to ~1px
    #    in a shared HORIZONTAL row, overflows its container, keeps leading/
    #    trailing icon slots the instanceProperties override doesn't reliably
    #    turn off. Until a dedicated post-fix DS-button sizing/icon pass
    #    exists, buttons stay raw styled frames (render fine) + WARN.
    b = detect_button_shape(node)
    if b:
        return (b[0], b[1], b[2], False)
    # 2) badge / tag — confident (auto-swap) if the name says so OR the label
    #    is a known short status word ("미납 1" / "완료" / "진행중" …): those
    #    tiny pills ARE badges by definition. (User: "미납1 은 badge로 표현.")
    bd = detect_badge_shape(node)
    if bd:
        ll = (bd[2] or "").strip().lower()
        is_status = any(w.lower() in ll for w in _STATUS_WORDS)
        confident = is_status or _name_hints(node, "badge", "뱃지", "배지", "태그", "chip", " tag")
        return (bd[0], bd[1], bd[2], confident)
    # 3) form controls
    for det in (detect_input_shape, detect_dropdown_shape, detect_toggle_shape,
                detect_checkbox_shape, detect_radio_shape, detect_slider_shape,
                detect_progress_shape):
        r = det(node)
        if r:
            role = r[0]
            confident = (role in _VERIFIED_AUTOSWAP_ROLES) and _has_distinctive_shape(node, role)
            return (r[0], r[1], r[2], confident)
    return None
