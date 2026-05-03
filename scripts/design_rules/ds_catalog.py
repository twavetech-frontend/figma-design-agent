"""DS component key catalog.

Single source of truth for every componentKey we use, plus name-pattern
matchers used by R23 to detect raw-frame violations.

Sourced from feedback_design_invariants_2026_05_04.md. Keep this in sync
with the live Figma library; if a key changes, update here and rebuild.
"""
from __future__ import annotations

import re

# componentKey by canonical role name
COMPONENT_KEYS = {
    # Brand / chrome
    "Logo":                 "81efeddd245e95f31a2724aa370ee54d3caf93d0",
    "Logo (alt)":           "957912b03baf924a48ef83424ed66f22a4a386a8",  # CLAUDE.md NavBar logo
    # Pills
    "Pill sm Brand":        "d0163041d0c710551c31ffd4acaca5ce42f993ac",
    "Pill sm Success":      "e8f010fe720f6742a38c8c8c1c591531fcb5149b",
    "Pill sm Warning":      "8cf0d360a58aa027e447ee6c47944e41d89f9699",
    "Pill sm Pink":         "cd973d99c3f1baab0c1a37aa1f1982c73f1b1ca9",
    "Pill sm Gray blue":    "718da0d3d3a6881c12167505d6d1c5b22f372f61",
    # Badges
    "Badge sm Brand":       "03b25488b460f514f23ddf39b5b42f7d31e7935e",
    "Badge sm Purple":      "39170ab4e765ca3e09fc46b27f7e50061696065e",
    "Badge sm Success":     "6c0c2ebab689aedebd84c160e1e3ce6af3dcd8f2",
    "Badge sm Warning":     "5e675a5727f7868ff72f067dad64ea50fe04a43e",
    # Action / icons
    "Action Button":        "ed0032bcf28f03da97e4b3006f54d30a0fbe5914",
    "Icon x-close":         "4ba052703931aeecf495c7698e5002b6c89d1ad4",
    "Icon search-md":       "7c9a1100b148110910806002a8a85b6eb9920582",
}


# (regex, category-name) — used by R23 + L3 status-bar inject
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
