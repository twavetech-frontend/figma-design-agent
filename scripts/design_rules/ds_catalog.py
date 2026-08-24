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
    "Logo (alt)":           "13b53a11b20a467ad465deb4cf2611cb3aa0c804",

    # ── Toast (스낵바/토스트, 2026-08-20 search_design_system 확보 — 사용자 제공 DS 파일) ──
    # 하단 어텐션 안내는 raw dark pill 금지 → DS 'Toast' 인스턴스(SET). Left icon#19189:0
    # BOOLEAN(기본 초록 체크 — 실패/안내류는 off), 텍스트는 내부 TEXT override, 353x48 배치 관례.
    "Toast":                              "SET:27655caa76f725b709d2807c893c3467beb6c0b7",

    # ── Pagination dot group (캐로셀 인디케이터, 2026-06-05 추출) ──────
    # 캐로셀/배너 인디케이터는 raw bullet/dot frame 금지 → 이 DS 컴포넌트 인스턴스 사용.
    # 기본 = lg, Style=Dot, Framed=False (사용자 선택). variant 키 전체 등록.
    "Pagination dot group":               "2ac006ab01ff82ad9b74c16d4cf6c17609a02d79",  # lg Dot Framed=False (default)
    "Pagination dot group lg Dot":        "2ac006ab01ff82ad9b74c16d4cf6c17609a02d79",
    "Pagination dot group md Dot":        "347badbada16ce6814540e82246101d2dc65a295",
    "Pagination dot group lg Dot Framed": "242fd303853f217a9a4abe26a9994654071ccdde",
    "Pagination dot group md Dot Framed": "62c7b2992edd5f2b5ae5273cb89b2588894bdc3d",

    # ── Mobile system chrome ───────────────────────────────────
    # 2026-07-10 키 갱신: 구 키(e11cb49d…)는 import 실패(미게시/구버전) — R24 inject 가
    # 이 키로 instance 를 박아 ⚠ 에러 프레임이 되고 code.js 이름 기반 폴백까지 억제되던
    # 회귀. 신 키는 DS 파일(Imin Design System) 연결 상태에서 get_local_components 실측 추출.
    "Status Bar":           "13557b1ed59ce3f8c2dfbf9df46ec8fa7f772486",  # iPhone 9:41

    # ── Bottom Tab Bar (DS 'Tab bar' set, 2026-06-02 추출) ──────
    # variant prop "Selected": 1.홈 / 2 커뮤니티 / 3 스테이지 / 4 라운지 / 5 나.
    # active 탭에 해당하는 variant key 로 인스턴스 생성 → 그 탭이 selected 로 렌더.
    # "Tab Bar" 기본값 = 홈 selected. raw frame 으로 그리지 말고 이 인스턴스 사용.
    "Tab Bar":              "0faaa55563de4da617964ea93ba07f09bc1279f6",  # = Selected 1.홈 (default)
    "Tab Bar 홈":           "0faaa55563de4da617964ea93ba07f09bc1279f6",
    "Tab Bar 커뮤니티":      "b7d390e90bae2d41059671f4474102a2bd92b7c1",
    "Tab Bar 스테이지":      "a56726e0de4bc0e71875159662b320e9b2ac695c",
    "Tab Bar 라운지":        "7dcb6d5d2b97d36e0b5d601441f22f87e2d26f5c",
    "Tab Bar 나":           "740120b5e954cae262d21fefffa946afc26f2d63",

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

    # ── Avatars (standalone circular, verified via create_component_instance 2026-05-28) ──
    # Placeholder=False = image avatar (default photo); Placeholder=True = grey silhouette.
    # Onboarding/list 익명 회원 → placeholder (silhouette). 그 외 size 별 image avatar.
    "Avatar xs":             "41a67c754c1dc5cf9215b5b01d1fdfcefde0b1f1",  # 24
    "Avatar sm":             "2ea40a42128815074ad25674746cae569e2ecc56",  # 32 ✓
    "Avatar md":             "36bbd0bcaa2fffffc9fb836c08c35bd2cdd295d1",  # 40 ✓ (image)
    "Avatar lg":             "7df978a75360c4eeddc2887645cf09bee1ed51d5",  # 48
    "Avatar xl":             "1c46df6e93dfba27ce07a7ca5646ce7d71c17dba",  # 56
    "Avatar 2xl":            "6c92320d202ea44b388ef92255b0c47aa386412c",  # 64
    "Avatar placeholder md": "77ba27f9a412574b97843b5fedcbe032ef6679c0",  # 40 silhouette ✓ (익명 기본)

    # ── Tags / Chips ───────────────────────────────────────────
    "Tag md":                "fa59791b4002ab31b67ca4bb77f171c62ccd6ea3",
    "Tag sm":                "7993e38b2b06048331d58dd6f588e419123ffece",

    # ── Divider ────────────────────────────────────────────────
    "Divider":               "643b56de33f422bdf0c7611555210a08b25e21a8",

    # ── Link (text link, 2026-05-28 사용자 제공 node 16572:310388) ──
    "Link md":               "4ea3f73a0528550d1bdcdbffeeb5bb2f1f91852b",  # Size=md Color=Link color Default
    "Link md gray":          "b46cabe302d52e4926a63d9ee6f857e4ec114c5d",  # Size=md Color=Link gray Default
    "Link lg":               "6b5ee63ad1c6859224db24f9f500dbc5b8243b85",  # Size=lg Color=Link color Default
    "Link sm":               "4ea3f73a0528550d1bdcdbffeeb5bb2f1f91852b",  # fallback md

    # ── Modal (2026-05-28 사용자 제공 node 172:4293, Breakpoint=Mobile) ──
    "Modal":                 "2fbf6f2a1b5e98d72073baefc64c5790c36626dd",  # Stacked left aligned Mobile
    "Modal Warning":         "a50f41e12825a0e7294a9a9387d60c0f98c4bc05",
    "Modal Destructive":     "0d444a64241a7cbd19c580754d709bf8b45021cb",
    "Modal Horizontal":      "774a3de5d96ed5df283c6bec0c1ace374fb3cac4",

    # ── IMIN composite components (camelCase 내부 컴포넌트, 이름 매칭) ──
    # 2026-05-28 사용자: "컴포넌트 목록 없어?" — DS 전체에서 추출한 IMIN 고유 컴포넌트.
    # composite 라 shape 검출 안 되고 이름 매칭으로만 swap (blueprint 이름이 role 과 일치 시).
    "Month Cell":            "786ecc644d2a5b35e7e3aa3253fb7f451c836e1c",  # monthCell
    "Card default":          "fd8bfe2911f0fd86868aaad298d285455e954352",  # Type=Card default Mobile
    "Button group":          "6eeac5347bb698e42d184eb6de21103e0c7357fd",  # Type=Button group Single line
    "Avatar group md":       "cbf96575fc618ab0c481b96a8bd8cadad4709dae",  # Type=Avatar group md

    # ── Tabs ───────────────────────────────────────────────────
    "Underline Tab Item":   "143ee3e3fdd529c89c4360e3d70a583be4a83f53",
    # Horizontal tabs (전체 탭 그룹) — setKey f11bda3cf5430bdb7052591a5beead9d5abdf093
    # 2026-06-01 사용자 룰: 2-tab 이상 텍스트만 있는 탭 nav 는 raw frame 금지, DS instance 사용 강제.
    "Horizontal Tabs Underline sm Mobile":         "143ee3e3fdd529c89c4360e3d70a583be4a83f53",
    "Horizontal Tabs Underline md Mobile":         "143ee3e3fdd529c89c4360e3d70a583be4a83f53",
    "Horizontal Tabs Underline sm Full Mobile":    "143ee3e3fdd529c89c4360e3d70a583be4a83f53",
    "Horizontal Tabs Underline md Full Mobile":    "143ee3e3fdd529c89c4360e3d70a583be4a83f53",
    "Horizontal Tabs Button Brand sm Mobile":      "143ee3e3fdd529c89c4360e3d70a583be4a83f53",
    "Horizontal Tabs Button Gray sm Mobile":       "143ee3e3fdd529c89c4360e3d70a583be4a83f53",
    # Alias for blueprint naming convention — Mode Tabs / Section Tabs / Top Tabs
    # 이 셋 모두 underline sm Mobile 로 매핑 (project canonical)
    "Mode Tabs":           "143ee3e3fdd529c89c4360e3d70a583be4a83f53",
    "Mode Tabs Wrap":      "143ee3e3fdd529c89c4360e3d70a583be4a83f53",
    "Section Tabs":        "143ee3e3fdd529c89c4360e3d70a583be4a83f53",
    "Top Tabs":            "143ee3e3fdd529c89c4360e3d70a583be4a83f53",

    # ── NavBar variants ────────────────────────────────────────
    "Modal Header":         "689757096008812f6a99c76efb51e914feb4fd2c",
    "Type Header":          "ed6ef9d403a570d5176d69bc314a54390409bbac",
    # 🔴 2026-06-12 사용자 룰 (절대 규칙 0-W): 상단 툴바(NavBar)는 raw frame 으로 그리지
    # 말고 Imin DS 'Tool Bar' 컴포넌트 인스턴스 사용. variant 개별 키가 비공개라
    # "SET:<setKey>:<Variant>" 형식 (code.js importComponentFlexible 가
    # importComponentSetByKeyAsync 로 import 후 variant 매칭). set key = c9299ef0… .
    #   Type=Home        — 메인(탭바 홈): 로고 + 우측 아이콘 2개
    #   Type=Detail view — 서브 화면: back + 중앙 타이틀 + 우측 아이콘
    "Tool Bar Home":        "SET:c9299ef0c3c7cc271850a048025a3c8d0e82b230:Type=Home",
    "Tool Bar Detail":      "SET:c9299ef0c3c7cc271850a048025a3c8d0e82b230:Type=Detail view",
    "NavBar Home":          "SET:c9299ef0c3c7cc271850a048025a3c8d0e82b230:Type=Home",
    "NavBar Detail":        "SET:c9299ef0c3c7cc271850a048025a3c8d0e82b230:Type=Detail view",

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
    "Segmented tab item":        "143ee3e3fdd529c89c4360e3d70a583be4a83f53",  # segmentedTabItem (used by R29)
}

# Roles whose key is verified to instantiate as the right atomic control →
# R23 may auto-swap a *shape-matched* raw frame to them. Button hierarchies
# are handled separately (detect_button_shape). Everything else is WARN-only.
_VERIFIED_AUTOSWAP_ROLES = {"Toggle", "Progress bar", "Checkbox", "Radio", "Input field", "Slider", "Tooltip", "Dropdown", "Avatar"}


# ── NavBar(Tool Bar) 우측 버튼 아이콘 swap 키 (절대 규칙 0-W, 2026-06-12) ──
# DS Tool Bar 인스턴스 우측 버튼의 중첩 아이콘 인스턴스를 swap_instance_component 로
# 교체할 때 쓰는 iconName → 컴포넌트 키 맵 (Imin DS 24px line 아이콘).
# blueprint 의 `_navIcons: ["bell-01", "search-lg"]` 마커가 이 맵으로 해석된다.
# 맵에 없는 아이콘은 swap skip + WARN (마스터 기본 아이콘 유지) — 새 아이콘이 필요하면
# Imin DS 에서 키를 찾아 여기 추가할 것 (search_design_system 또는 sync-components).
NAV_ICON_KEYS = {
    "bell-01":             "f80e23373a1afc1b460be44da32915f390b5af2a",
    "bell":                "f80e23373a1afc1b460be44da32915f390b5af2a",
    "message-circle-01":   "3071d1cea18e103f7187986d83ecc64972cccb21",
    "message-chat-circle": "3071d1cea18e103f7187986d83ecc64972cccb21",
    "chat":                "3071d1cea18e103f7187986d83ecc64972cccb21",
    "search-lg":           "7c9a1100b148110910806002a8a85b6eb9920582",  # search-md
    "search-md":           "7c9a1100b148110910806002a8a85b6eb9920582",
    "search":              "7c9a1100b148110910806002a8a85b6eb9920582",
    "x-close":             "4ba052703931aeecf495c7698e5002b6c89d1ad4",
    "home-01":             "3b9e167503a7a91c597375d8c11c4f1a39fe5705",
    "shopping-bag-01":     "152430df50a07e03ae0c23e66095ca1e01cad66a",
    "users-01":            "79e81ec517b9231b88e83c3b2320152ae38fd683",
    "menu-01":             "773e8ac3572b64c2031233074661490b45c43584",
    "stars-01":            "781d56540e849275dbc6f0cbf93b0bdb1a1392f4",
    "wallet-01":           "aa266194d742496709395561be5836b1445ee6ab",
    "wallet-02":           "aa266194d742496709395561be5836b1445ee6ab",
    "calendar":            "f698e668f4259ac533a78c5f3be2cef705f3e9c7",
    "calendar-check-01":   "9fd39ab78add0eb0bb1c14dec21f94436602d89c",
    "check-verified-01":   "3573927df03a08371e487d78803095fe0fd47423",
    "help-circle":         "8cf3b907326b40b752388a53b50320e3d7700a5e",
    # 2026-06-12 search_design_system 으로 확보 (정확 이름 일치 항목만)
    "share-07":            "f3279037645fb703bf67be50991e319c62d00625",
    "share":               "f3279037645fb703bf67be50991e319c62d00625",
    "share-01":            "f3279037645fb703bf67be50991e319c62d00625",
    # 2026-07-14 사용자 지적("왜 NavBar 를 직접 만드냐") 후 search_design_system 으로 확보 —
    # 키가 없으면 _customNavBar 우회가 아니라 이렇게 **키를 확보해 여기 등록**하는 것이 정답.
    "edit-01":             "cf4b7befec381191ddc14244fc59e85be85b1662",
    "edit":                "cf4b7befec381191ddc14244fc59e85be85b1662",
    "pencil-01":           "cf4b7befec381191ddc14244fc59e85be85b1662",
    "pencil":              "cf4b7befec381191ddc14244fc59e85be85b1662",
    "settings-01":         "110d888816e9bb5ce620761786951ce6ad2cf459",
    "settings":            "110d888816e9bb5ce620761786951ce6ad2cf459",
    "dots-vertical":       "4701c3d1add2af0b2cacd0362c19a23c08a04773",
    # trash/delete (2026-08-18 배송지 수정 상단 삭제 버튼 — search_design_system 확보)
    "trash":               "768df4f8e834000ce1c6ca369cc76b3e1358c3fd",
    "trash-01":            "768df4f8e834000ce1c6ca369cc76b3e1358c3fd",
    "ic_trash_04":         "768df4f8e834000ce1c6ca369cc76b3e1358c3fd",
    # 채팅 만들기 (2026-08-24 채팅 목록 변환 — 원본 앱 에셋 btn_top_make_chat,
    # search_design_system 으로 ic_message_plus_circle(line) 확보)
    "message-plus-circle": "8ed30fa4e9ea171c740a1d3a3954aab0a8f66bdc",
    "make-chat":           "8ed30fa4e9ea171c740a1d3a3954aab0a8f66bdc",
    "btn_top_make_chat":   "8ed30fa4e9ea171c740a1d3a3954aab0a8f66bdc",
}


def resolve_nav_icon_key(icon_name: str):
    """iconName → Tool Bar 우측 버튼 swap 용 컴포넌트 키 (없으면 None)."""
    if not icon_name:
        return None
    nm = str(icon_name).strip().lower()
    if nm in NAV_ICON_KEYS:
        return NAV_ICON_KEYS[nm]
    # 사이즈/번호 suffix 무시한 prefix 매칭 (e.g. 'bell-02' → 'bell')
    base = nm.split("-")[0]
    return NAV_ICON_KEYS.get(base)


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
    (re.compile(r"\bLink\b",         re.I),  "Link"),
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

    # Text link — name ends with " Link" (e.g. "더보기 Link", "Detail Link")
    (re.compile(r"\blink$",                                   re.I), "Link md"),

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
    # 결제 상태(2026-06-04) — '입금 전' 등이 status badge 로 일관 swap 되도록(원형화 방지)
    "입금 전", "입금전", "지급 전", "지급전", "출금 전", "납입 전", "납입전", "입금 완료",
    # 2026-05-28 — onboarding 성공/실패 후기 status. 이전엔 누락되어 status pill 이
    # button 으로 오인 → WARN-only raw frame. 이제 badge 로 confident swap.
    "성공", "실패", "달성", "도전", "참여", "마감", "대기", "성공!", "success", "fail", "failed",
)


# ── FUNCTION-ROLE lexicons — distinguish action-BUTTON vs status-BADGE by what
#    the element DOES, not just its rectangular shape (2026-06-01 사용자 요청:
#    "리스트 상단 badge 가 직사각형이라 button 으로 잡힘 — 기능으로 구분/검증 강화").
#
# Button = an action/CTA. Its label is an imperative/verb (참여하기·신청·확인·더보기·
#   결제하기 / Submit·Continue·Apply…). Badge = a status/category/count label
#   (진행중·미납·추천·이벤트·D-7·6개·1회차 / NEW·HOT…). Same pill shape, different role.
_ACTION_LABEL_RE = re.compile(
    r"(하기$|하기\s|하러|해보기|받기$|담기$|보기$|보러|가기$)"
    r"|(확인|신청|결제|충전|시작|로그인|로그아웃|가입|등록|작성|수정|삭제|저장|전송|"
    r"보내|다음|이전|완료하|선택하|업로드|다운로드|더\s*보기|전체\s*보기|자세히|"
    r"구매|주문|예약|신고|문의|취소|동의|계속|열기|닫기|확인하|참여하|신청하|"
    r"교환|환불|적립|받으러|보러\s*가기|시작하)"
    r"|\b(submit|continue|next|back|done|confirm|apply|start|log\s*in|log\s*out|"
    r"sign\s*up|sign\s*in|buy|order|get\s|view|see\s*(more|all|details?)|download|"
    r"upload|send|save|cancel|agree|open|close|join|pay|checkout|add\s*to|"
    r"learn\s*more|read\s*more|show\s*more)\b",
    re.I,
)
# count / D-day / explicit badge-tier word → strong BADGE signal.
_BADGE_LABEL_RE = re.compile(
    r"^[+\-]?\d{1,4}\s*(개|건|원|명|회|회차|일|분|시간|점|위|％|%|kg|km)?$"   # 6 / +6 / 13회 / 1회차
    r"|^[dD][-–]\s*\d+$"                                                    # D-7
    r"|(공지|이벤트|추천|인기|신규|광고|무료|할인|필수|선택|점검|종료|예정|마감|"
    r"진행\s*중|진행|완료|미납|연체|성공|실패|달성|도전|참여|대기|지급|혜택|이벤트|"
    r"\d+\s*회차|\d+\s*등급|등급|new|hot|best|ad|sale|free|tip|n빵)",
    re.I,
)


def _label_is_action(label: Optional[str]) -> bool:
    """라벨이 동작/CTA 의미인가 (버튼 신호)."""
    return bool(label) and bool(_ACTION_LABEL_RE.search(label.strip()))


def _label_is_badge_word(label: Optional[str]) -> bool:
    """라벨이 상태/카테고리/카운트인가 (배지 신호)."""
    if not label:
        return False
    ll = label.strip().lower()
    if any(w.lower() in ll for w in _STATUS_WORDS):
        return True
    return bool(_BADGE_LABEL_RE.search(label.strip()))


def _is_list_item_context(parent: Optional[dict]) -> bool:
    """부모가 리스트 행/아이템/카드 헤더처럼 보이는가 — leading 소형 요소를
    badge 로 판정하기 위한 위치 신호. parent 없으면 False (보수적)."""
    if not isinstance(parent, dict):
        return False
    pn = (parent.get("name") or "").lower()
    if any(k in pn for k in ("list", "item", "row", "card", "cell", "header",
                             "리스트", "아이템", "행", "카드", "헤더", "셀")):
        return True
    # HORIZONTAL parent with a text sibling (title) next to the small pill → list-row-like
    al = parent.get("autoLayout") or {}
    mode = (al.get("layoutMode") or parent.get("layoutMode") or "").upper()
    kids = parent.get("children") or parent.get("_originalChildren") or []
    if mode == "HORIZONTAL" and len(kids) >= 2:
        has_text_sibling = any((c.get("type") or "").lower() == "text" for c in kids)
        return has_text_sibling
    return False


def _is_leading_small(node: dict, parent: Optional[dict]) -> bool:
    """node 가 부모의 leading(첫) 자식이면서 작은가 — 리스트 상단 badge 전형."""
    if not isinstance(parent, dict):
        return False
    kids = parent.get("children") or parent.get("_originalChildren") or []
    if not kids or kids[0] is not node:
        return False
    h = node.get("height")
    if isinstance(h, (int, float)) and h > 32:
        return False
    return True


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


def detect_button_shape(node: dict, parent: Optional[dict] = None) -> Optional[Tuple[str, str, str]]:
    """Detect a CTA-button-shaped frame. Returns (role, componentKey, labelText)
    or None.

    Heuristic: a frame (not a container by name) whose children are text-only
    (label, optionally + arrow), has a cornerRadius, horizontal padding, and a
    HORIZONTAL auto-layout. Width/height not required (FILL buttons have no
    explicit size in the blueprint).

    Function-role gate (2026-06-01): a rectangular pill is only a BUTTON if it
    *acts* like one — a verb/CTA label or a button-named frame. A non-action,
    short, small, or list-leading pill is a BADGE and is deferred to
    detect_badge_shape. `parent` (optional) enables the list-position signal.
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
    # status word label (성공/실패/완료/미납 …) → 버튼 아님, badge 로 양보 (2026-05-28).
    # 단, 액션 라벨(참여하기·완료하기 — '참여'/'완료' 가 status word 와 부분일치)은
    # 버튼이므로 양보하지 않는다 (2026-06-01).
    ll = label.strip().lower()
    if (not _label_is_action(label)) and any(w.lower() in ll for w in _STATUS_WORDS):
        return None
    if _corner_radius(node) < 6:
        return None
    if _h_padding(node) < 8:
        return None
    # CTA/Button 이름이 명시되면 layoutMode 무관 (VERTICAL 로 잘못 작성된 CTA 도 잡음 — 2026-05-24)
    nl = name.lower()
    is_named_cta = (nl.endswith("btn") or nl.endswith("button") or nl.startswith("cta ")
                    or " cta" in f" {nl}" or "primary cta" in nl or "submit" in nl)
    if not is_named_cta and _layout_mode(node) and _layout_mode(node) != "HORIZONTAL":
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
    # ── FUNCTION-ROLE gate — distinguish action-button from status-badge by
    #    ROLE, not rectangular shape alone (2026-06-01). A button must *act*:
    #    named CTA/Btn/Submit OR a verb/action label. Otherwise, a short pill
    #    that is small / lightly-padded / a known badge word / a leading item
    #    in a list row is a BADGE → defer to detect_badge_shape.
    nm_l = (node.get("name") or "").lower()
    is_button_named = (nm_l.endswith("btn") or nm_l.endswith("button")
                       or nm_l.startswith("cta ") or " cta" in f" {nm_l}"
                       or "submit" in nm_l or "primary cta" in nm_l)
    if not is_button_named and not _label_is_action(label):
        h_val = node.get("height")
        short = bool(label) and len(label) <= 10
        small_h = isinstance(h_val, (int, float)) and h_val <= 32
        light_pad = vp <= 10
        if (_label_is_badge_word(label)
                or _is_leading_small(node, parent)
                or (short and (small_h or light_pad))):
            return None  # role = badge, not button → let detect_badge_shape claim it
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
    # 결제 '입금 전/지급 전' 등 예정/대기 상태(2026-06-04) — 먼저 매칭(완료보다 우선).
    # '입금 완료' 는 '완료'(Success) 가 잡으므로 여기 '입금 전' 류만 Brand 로.
    (("입금 전", "입금전", "지급 전", "지급전", "출금 전", "납입 전", "납입전"), "Badge sm Brand"),
    (("success", "진행", "완료", "납입 완료", "지급", "성공", "달성"), "Badge sm Success"),
    (("warning", "예정", "곧", "오늘", "대기", "마감"), "Badge sm Warning"),
    (("error", "미납", "연체", "긴급", "실패"), "Badge sm Warning"),  # no error badge → warning
    (("도전", "참여", "신규", "new"), "Badge sm Brand"),
    (("purple",), "Badge sm Purple"),
]


# Avatar: 원형 frame + person/user icon (또는 이니셜) 든 작은 프로필.
# 2026-05-28 사용자 분노: avatar 를 raw circle 로 그리고, R23 검출을 이름을
# 'circle' 로 바꿔 회피했음. 이제 shape 로 검출 → 이름 무관 강제. DS Avatar instance.
_AVATAR_ICON_HINTS = ("user", "person", "avatar", "profile", "member", "프로필", "아바타", "회원")


def _avatar_role_for_size(w) -> str:
    """원형 폭 → DS Avatar size role. 익명(placeholder)이 기본 — onboarding/list."""
    if not isinstance(w, (int, float)) or w <= 0:
        return "Avatar placeholder md"
    if w <= 28:
        return "Avatar xs"
    if w <= 36:
        return "Avatar sm"
    if w <= 46:
        return "Avatar placeholder md"  # 40 안팎 = 익명 list avatar 기본 silhouette
    if w <= 60:
        return "Avatar lg"
    return "Avatar xl"


def detect_avatar_shape(node: dict) -> Optional[Tuple[str, str, Optional[str]]]:
    """Detect a profile-avatar-shaped frame: near-circular (cornerRadius ≥ ~w/2),
    24–80px, ~square, whose child is a user/person/avatar icon OR 1–2-char
    initials text. Returns (role, componentKey, None) or None.

    Name hints (avatar/profile/프로필/아바타) also qualify even without a circle.
    Calendar/date/icon-only circles WITHOUT a person hint are NOT avatars."""
    if not isinstance(node, dict):
        return None
    if (node.get("type") or "frame").lower() != "frame" or node.get("componentKey"):
        return None
    name = node.get("name") or ""
    w, h = node.get("width"), node.get("height")
    name_ok = _name_ends_with(node, "avatar", "프로필", "아바타") or _name_hints(node, "avatar", "profile")

    # person/user icon 또는 이니셜 자식 검사
    has_person_child = False
    for c in _children(node):
        cn = (c.get("name") or "").lower()
        ic = (c.get("iconName") or "").lower()
        if any(hh in cn or hh in ic for hh in _AVATAR_ICON_HINTS):
            has_person_child = True
            break
        # 이니셜: 1~2자 텍스트
        if (c.get("type") or "").lower() == "text":
            txt = (c.get("characters") or c.get("text") or "").strip()
            if 1 <= len(txt) <= 2 and txt.isalpha():
                has_person_child = True
                break

    circular = _corner_radius(node) >= (min(w, h) / 2 - 3) if (
        isinstance(w, (int, float)) and isinstance(h, (int, float))) else False
    sized = (isinstance(w, (int, float)) and isinstance(h, (int, float))
             and 20 <= w <= 80 and 20 <= h <= 80 and abs(w - h) <= 6)

    if not ((circular and sized and has_person_child) or name_ok):
        return None
    role = _avatar_role_for_size(w)
    key = COMPONENT_KEYS.get(role) or COMPONENT_KEYS["Avatar placeholder md"]
    return (role, key, None)


# 🎨 DS Badge `Color` prop 의 13개 유효 옵션 (2026-06-01 사용자 명시). Badge 색을 바꿀 땐
# fill/stroke 가 아니라 이 prop 에서 고른다 — set_instance_properties(id, {"Color": "<옵션>"}).
BADGE_COLOR_PROP = "Color"
BADGE_COLOR_PROP_OPTIONS = (
    "Gray", "Brand", "Error", "Warning", "Success", "Blue light", "Blue",
    "Indigo", "Purple", "Pink", "Orange", "Blue gray", "Gray blue",
)
# detect_badge_shape 가 고르는 role("Badge sm Warning" 등) → Color prop 값 매핑.
_BADGE_ROLE_TO_COLOR_PROP = {
    "Badge sm Brand": "Brand", "Badge sm Warning": "Warning",
    "Badge sm Success": "Success", "Badge sm Purple": "Purple",
    "Badge sm Gray": "Gray", "Badge sm Error": "Error",
}


def badge_color_prop_from_role(role: Optional[str]) -> Optional[str]:
    """Badge role/이름 → 유효한 Color prop 값 (없으면 None). 마지막 토큰도 시도."""
    if not role:
        return None
    if role in _BADGE_ROLE_TO_COLOR_PROP:
        return _BADGE_ROLE_TO_COLOR_PROP[role]
    # "Badge sm <Color>" 형태에서 색 부분 추출 후 유효 옵션과 대조 (대소문자 무시)
    tail = role.replace("Badge", "").replace("sm", "").replace("md", "").strip()
    for opt in BADGE_COLOR_PROP_OPTIONS:
        if tail.lower() == opt.lower():
            return opt
    return None


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
    cr = _corner_radius(node)
    # circular bare-number / single-initial marker = AVATAR or step indicator,
    # NOT a status badge (2026-06-01). A fully-round chip holding only a number
    # (도토리 번호 / 회차 step / 내 수령 표식) is an identity marker — leave it
    # raw. Real count badges ("13회"·"+6") have a unit or sign and survive.
    w = node.get("width")
    # bare number / single char = step·회차·index·avatar-initial 마커지 status badge 아님.
    # circular 든 rectangular 든 동일 (2026-06-02: 회차 1~13 셀이 Badge 로 오스왑되던 회귀).
    # 진짜 count badge('13회'·'+6')는 단위/부호가 있어 \d{1,3} 단독 매칭 안 됨 → 살아남음.
    if re.fullmatch(r"\d{1,3}|[A-Za-z가-힣]", label.strip()):
        return None
    # cornerRadius: pills are rounded, but rectangular TAGS are squared-off
    # (2026-06-01). Accept low/zero radius when the label/name *says* badge.
    badge_worded = _label_is_badge_word(label) or _name_hints(node, "badge", "뱃지", "배지", "태그", "chip", " tag")
    if cr < 4 and not badge_worded:
        return None
    h = node.get("height")
    w = node.get("width")
    if isinstance(h, (int, float)) and h > 32:   # was 30 — allow rectangular list-top tags
        return None
    if isinstance(w, (int, float)) and w > 160:  # was 140 — allow a slightly wider category tag
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


def detect_tooltip_shape(node: dict):
    """Tooltip / speech bubble: a rounded frame holding a TEXT child, usually
    with a dismiss (x-close) icon — a floating hint / coach mark. Confident only
    with a name hint (tooltip/툴팁/bubble/말풍선) per the anti-over-swap policy;
    pure shape → WARN-only. Key VERIFIED (`Tooltip`).

    2026-06-04 — added to close the gap where a raw '궁금한 건 물어보세요. ✕'
    bubble (stage_detail) was authored as a raw frame and NO detector existed to
    surface/swap it ('Tooltip' was in _VERIFIED_AUTOSWAP_ROLES but unreachable).
    """
    if (node.get("type") or "frame").lower() != "frame" or node.get("componentKey"):
        return None
    # 툴팁은 반드시 직계 TEXT 를 품는다 — 이 가드가 "Bubble Wrap" 같은 래퍼 오스왑 차단.
    if not _has_child_of_type(node, "text"):
        return None
    name_ok = _name_hints(node, "tooltip", "툴팁", "bubble", "말풍선", "speech", "coach")
    if is_container(node.get("name") or "") and not name_ok:
        return None
    kids = _children(node)
    has_close = any(
        ("x-close" in (c.get("name") or "").lower()
         or "close" in (c.get("name") or "").lower()
         or "dismiss" in (c.get("name") or "").lower()
         or (c.get("iconName") or "").lower() in ("x-close", "x", "x-circle"))
        for c in kids)
    shape_ok = _corner_radius(node) >= 6 and has_close
    if not (shape_ok or name_ok):
        return None
    label = None
    for c in kids:
        if (c.get("type") or "").lower() == "text":
            label = c.get("characters") or c.get("text") or c.get("content")
            break
    return ("Tooltip", COMPONENT_KEYS["Tooltip"], label)


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
    # 2026-07-14: underline tabs 의 3px 밑줄 bar(0-J 문법)가 progress 로 오인돼
    # DS Progress bar 인스턴스로 auto-swap 되던 회귀(참여중/진행중 탭) — 명시 제외.
    if "underline" in nl:
        return None
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
    if role and role.startswith("Avatar"):
        # detect_avatar_shape 이미 원형+person/이니셜 검증함 → distinctive 인정
        return True
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
        if _name_hints(node, "tooltip", "툴팁", "bubble", "말풍선", "speech"):
            return True
        has_close = any(("x-close" in (c.get("name") or "").lower()
                         or "close" in (c.get("name") or "").lower()
                         or (c.get("iconName") or "").lower() in ("x-close", "x", "x-circle"))
                        for c in _children(node))
        return has_close and _has_child_of_type(node, "text") and _corner_radius(node) >= 6
    if role == "Dropdown":
        h = node.get("height")
        has_border = bool(node.get("stroke") or node.get("strokes"))
        has_chevron = any(("chevron" in (c.get("name") or "").lower() or "caret" in (c.get("name") or "").lower())
                          for c in _children(node))
        return _name_ends_with(node, "dropdown", "select", "드롭다운", "셀렉트") or (
            has_border and has_chevron and _has_child_of_type(node, "text")
            and isinstance(h, (int, float)) and 32 <= h <= 88 and _corner_radius(node) >= 4)
    return False


# 2026-06-02 — structural auto-swap 은 '이름 힌트' 가 있을 때만 confident.
# 순수 모양 일치(이름 힌트 없음)는 WARN-only 로 남겨, hand-authored 콘텐츠/장식
# (금액 pill·회차 셀·필터 헤더·칩 등)이 DS 컴포넌트로 오스왑돼 콘텐츠가 파괴되는 회귀 차단.
# 사용자 명시(2026-06-02): "새 세션에서 또 이상하게 생성되면 안 된다 — R23 근본 수정."
_ROLE_NAME_HINTS = {
    "button":   ("button", "btn", "cta", "submit", "버튼"),
    "badge":    ("badge", "뱃지", "배지", "태그", "tag", "chip", "칩"),
    "avatar":   ("avatar", "profile", "프로필", "아바타"),
    "dropdown": ("dropdown", "select", "드롭다운", "셀렉트"),
    "input":    ("input", "field", "입력"),
    "toggle":   ("toggle", "switch", "스위치", "토글"),
    "checkbox": ("checkbox", "체크박스"),
    "radio":    ("radio", "라디오"),
    "slider":   ("slider", "슬라이더"),
    "progress": ("progress", "프로그레스", "진행"),
    "tooltip":  ("tooltip", "툴팁", "bubble", "말풍선", "speech"),
}


def _role_category(role: Optional[str]) -> Optional[str]:
    r = (role or "").lower()
    for cat in ("button", "badge", "tag", "avatar", "dropdown", "input",
                "toggle", "checkbox", "radio", "slider", "progress", "tooltip"):
        if cat in r:
            return "badge" if cat == "tag" else cat
    return None


def _has_role_name_hint(node: dict, role: str) -> bool:
    """node 이름에 role 에 해당하는 DS 컴포넌트 단어가 있나 (confident swap 게이트).

    이름 힌트가 없으면 순수 모양 일치만으로는 confident swap 하지 않는다(WARN-only).
    """
    cat = _role_category(role)
    if not cat:
        return False
    low = (node.get("name") or "").lower()
    return any(w in low for w in _ROLE_NAME_HINTS.get(cat, ()))


def detect_ds_role_structural(node: dict, parent: Optional[dict] = None):
    """Unified structural DS detector. Returns (role, componentKey,
    instanceText, confident) or None.

      confident=True  ⇒ R23 auto-swaps the raw frame to the DS instance.
      confident=False ⇒ R23 emits a WARN (component-shaped raw frame) but
                        leaves it as-is.

    Priority: badge/tag (role-confirmed) → button → avatar → input → dropdown →
    toggle → checkbox → radio → slider → progress.

    2026-06-01 — badge/button disambiguation is ROLE-based, not shape-only:
    a rectangular pill whose label is a status/category/count (or that sits as
    a small leading item in a list row) is a BADGE even if it is rectangular.
    `parent` (optional) supplies the list-position signal. detect_button_shape
    defers such pills, so checking badge first is belt-and-suspenders.
    Buttons stay always-confident (verified key); other roles need a verified
    key + distinctive shape.
    """
    if not isinstance(node, dict):
        return None
    # 0) badge / tag — checked FIRST when the ROLE is unambiguous (label is a
    #    status/category/count word, the name says badge/tag, or it is a small
    #    leading pill in a list row). This stops rectangular status badges from
    #    being mis-detected as buttons (2026-06-01 사용자 분노: 리스트 상단 badge
    #    가 button 으로 잡힘).
    bd = detect_badge_shape(node)
    if bd:
        ll = (bd[2] or "").strip().lower()
        is_status = any(w.lower() in ll for w in _STATUS_WORDS)
        # 2026-06-02 — leading-small 위치만으로는 confident 안 함 (회차 1~13 셀 같은
        # 작은 리스트 선두 요소가 badge 로 오스왑되던 회귀). status 라벨·badge 이름 같은
        # 의미/이름 신호가 있을 때만 confident, 나머지는 아래 line 의 WARN-only 로.
        role_badge = (is_status or _label_is_badge_word(bd[2])
                      or _name_hints(node, "badge", "뱃지", "배지", "태그", "chip", " tag"))
        # A clear action label means it is actually a button, not a badge —
        # do not claim it here; fall through to the button detector.
        if role_badge and not _label_is_action(bd[2]):
            return (bd[0], bd[1], bd[2], True)
    # 1) button — DETECTED and auto-swapped. detect_button_shape now defers
    #    non-action / badge-tier pills (function-role gate), so what reaches
    #    here is a genuine action/CTA.
    b = detect_button_shape(node, parent)
    if b:
        # 2026-05-28 — 버튼 auto-swap (사용자: "제일 중요한 컴포넌트는 버튼").
        # 2026-06-02 — confident swap 은 이름이 button/cta/submit 을 가리킬 때만.
        # 순수 버튼 모양 + action 라벨(필터 칩 '빠른 시작'·금액 pill 등)은 WARN-only —
        # 콘텐츠/필터가 버튼으로 오스왑되던 회귀 차단. 진짜 CTA 는 이름(cta/button)을
        # 주거나 blueprint 에서 type:instance 로 직접 작성(2-G). post-fix 가 sizing 교정.
        confident = _has_role_name_hint(node, b[0])
        return (b[0], b[1], b[2], confident)
    # 1.5) avatar — confident auto-swap (2026-05-28). person/user icon 든 원형 프로필.
    av = detect_avatar_shape(node)
    if av:
        # 2026-06-02 — 이름 힌트(avatar/profile) 있을 때만 confident, 아니면 WARN-only.
        return (av[0], av[1], av[2], _has_role_name_hint(node, av[0]))
    # 1.6) tooltip / 말풍선 — 이름 힌트(tooltip/툴팁/bubble/말풍선) 또는 x-close+텍스트
    #      라운드 = 명확한 툴팁. 아래 badge WARN-only fallback 보다 먼저 claim 해야
    #      말풍선이 generic pill(badge) 로 새지 않는다 (2026-06-04 회귀 fix).
    tt = detect_tooltip_shape(node)
    if tt:
        confident = (_has_distinctive_shape(node, "Tooltip")
                     and _has_role_name_hint(node, "Tooltip"))
        return (tt[0], tt[1], tt[2], confident)
    # 2) badge / tag — shape-detected but role NOT confirmed above → WARN only
    #    (surfaces the gap without forcing a possibly-wrong badge instance).
    if bd and not _label_is_action(bd[2]):
        return (bd[0], bd[1], bd[2], False)
    # 3) form controls
    for det in (detect_input_shape, detect_dropdown_shape,
                detect_toggle_shape, detect_checkbox_shape, detect_radio_shape,
                detect_slider_shape, detect_progress_shape):
        r = det(node)
        if r:
            role = r[0]
            # 2026-06-02 — form control 도 이름 힌트 필수 (dropdown/input/toggle 등).
            # 순수 모양만으론 WARN-only — 콘텐츠 frame 오스왑 방지.
            confident = ((role in _VERIFIED_AUTOSWAP_ROLES)
                         and _has_distinctive_shape(node, role)
                         and _has_role_name_hint(node, role))
            return (r[0], r[1], r[2], confident)
    return None
