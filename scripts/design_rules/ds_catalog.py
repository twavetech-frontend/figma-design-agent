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

    # ── Buttons ────────────────────────────────────────────────
    "Action Button md":     "c51e2ea849dccd8545523288c29a5edf25b5a88b",
    "Action Button md (legacy)": "ed0032bcf28f03da97e4b3006f54d30a0fbe5914",
    "Action Button sm":     "a8a4d7eb7874c469ab89105cc342fad85a3d28ce",

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
}


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

    # CTA Action Button (must end with Btn/Button)
    (re.compile(r"\ball[\s-]*view\s+btn$",                    re.I), "Action Button md"),
    (re.compile(r"^(?:cta|primary|action)\s+button$",         re.I), "Action Button md"),

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
