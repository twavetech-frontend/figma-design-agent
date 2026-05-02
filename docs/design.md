# 디자인 생성 룰 (PRD/와이어프레임 → Figma)

> **이 문서가 디자인 룰의 단일 진실 공급원(SSOT)이다.** CLAUDE.md에는 짧은 인덱스만 두고 본문은 모두 여기에 둔다.
> 새 룰 추가 시 항상 이 파일에 추가하고, CLAUDE.md 인덱스에 한 줄 링크만 추가한다.

관련 문서:
- [`design-rules.md`](design-rules.md) — VS 시각 규칙 (VS1~VS8) + 컴포넌트/타이포 스케일
- [`references/INDEX.md`](references/INDEX.md) — 비주얼 레퍼런스 컬렉션
- [`ds-architecture.md`](ds-architecture.md) — DS 토큰 조회/변수 업데이트/MCP 도구
- [`mobile-patterns.md`](mobile-patterns.md) — 모바일 화면 패턴
- [`qa-checklist.md`](qa-checklist.md) — 빌드 후 QA 체크리스트
- [`pencil-to-figma.md`](pencil-to-figma.md) — Pencil → Figma 변환

---

## 🚨 디자인 생성 SOP (필수 5단계 — 절대 순서 변경 금지)

> **PRD/와이어프레임 → Figma 디자인 빌드의 모든 작업은 이 5단계를 정확히 순서대로 따른다.**
> 한 단계라도 건너뛰면 사용자 분노 + 디자인 퀄리티 하락이 보장됨 (2026-05-01 검증).

### Step 1 — 룰 + 레퍼런스 로드
- [ ] `Read docs/design.md` (이 문서, 모든 룰 #1~#36)
- [ ] `Read docs/references/INDEX.md` (비주얼 레퍼런스 컬렉션)
- [ ] 필요 시 `Read docs/design-rules.md` (VS1~VS8 시각 규칙)

### Step 2 — DS 컴포넌트 카탈로그 사전 조회 (룰 #34 필수 선행)
- [ ] `Read ds/DS_COMPONENT_DOCS.json` (프로젝트 컴포넌트 카탈로그 전체)
- [ ] `mcp__figma-tools__get_remote_components` (라이브러리 컴포넌트)
- [ ] `mcp__figma-tools__get_local_components` (현재 파일 컴포넌트)
- [ ] DS 문서 페이지 WebFetch (룰 최우선): `https://twavetech-frontend.github.io/design-system-docs/components/{name}` — PRD에 등장하는 모든 UI 요소
- [ ] **출력**: 사용 가능한 컴포넌트 목록 + 각 variant/prop/size

### Step 3 — 와이어프레임 분석 + DS 컴포넌트 매핑 표 (자동 진행)
- [ ] 와이어프레임 / PRD에서 UI 요소 모두 추출 (룰 #33: 정보 구조만, 룰 #36: 임의 누락 금지)
- [ ] **DS 컴포넌트 매핑 표 자동 작성** — Step 2에서 조회한 DS 카탈로그 기반으로 즉시 결정. 사용자 확인 받지 말 것.

  | 와이어프레임 UI | DS 컴포넌트 | variant / props |
  |---|---|---|
  | 버튼 | `Buttons / Action button` | primary, size=lg, label="..." |
  | Pill (status) | `Badges` | color=brand, size=sm, type=pill |
  | 아바타 | `Avatars` | size=md, status=online |
  | 탭 | `Tabs` | type=underline, fullWidth=true |
  | … | … | … |

- [ ] DS에 정확히 일치하는 컴포넌트가 없는 unique 요소만 frame raw 작성 (Step 5 보고에 사유 포함)
- [ ] **매핑 결정에 모호함이 있을 때만** AskUserQuestion 사용. 그 외는 즉시 Step 4로 진행.

### Step 4 — Blueprint 작성 (DS 인스턴스 + 위계 + 와이어프레임 UI 모두 유지)
- [ ] 모든 매칭된 UI를 `type:"instance"` + `componentKey` 형태로 명시:
  ```json
  {
    "name":"...", "type":"instance",
    "componentKey":"<DS_KEY>",
    "instanceProperties":{ "variant":"primary", "size":"lg", "label":"..." }
  }
  ```
- [ ] 카드 위계 한 단계씩 (룰 #35): root `bg-primary` → 카드 `bg-secondary` → sub-card `bg-tertiary` → 강조 셀 `bg-quaternary`. **점프 금지**.
- [ ] Brand-bg 카드 위 sub-component는 alpha-white-N + 단단한 grey (룰 #28)
- [ ] 와이어프레임 모든 UI 요소 포함 (룰 #36)
- [ ] 동일 반복 카드는 위계/강조 차이 부여 (룰 #33)

### Step 5 — 빌드 + 검증 + 보고
- [ ] `python3 scripts/figma_mcp_client.py build <blueprint>.json` (자동 sanitize + post-fix + token-bind)
- [ ] post-fix `_apply_bg_hierarchy` 결과 검사 — 위계 점프 위반 0건이어야 (룰 #35)
- [ ] Token 바인딩 카운트 0이 아닌지 확인 (룰 #26)
- [ ] **사용자 보고 시 필수 명시**:
  - root nodeId + 화면 크기
  - **사용한 DS 컴포넌트 목록** (예: "Action Button×3, Badges×2, Avatar×5, Tabs underline×1")
  - DS에 없어 frame으로 작성한 부분 + 사유
  - Token 바인딩: `colors=N numbers=M text=K effects=E`
  - unmapped colors 카운트

### 위반 패턴 — 사용자 분노 트리거 (절대 금지)
- ❌ Step 2 건너뛰고 곧장 Blueprint 작성 → "DS 만든 의미 없음"
- ❌ Button/Pill/Avatar 등을 raw frame + text로 시뮬레이션
- ❌ 와이어프레임 UI 요소를 "정리" 명목으로 임의 누락
- ❌ 동일 카드 3개를 동일 디자인으로 (위계 부재)
- ❌ root white 위에 직접 bg-tertiary/quaternary (위계 점프)
- ❌ DS 카탈로그 매핑 표 없이 빌드 시작

---

## 룰 인덱스

| # | 룰 | 키워드 |
|---|---|---|
| 1 | NavBar 로고는 컴포넌트 인스턴스 | `create_component_instance` |
| 2 | 색상 다양성 — 브랜드 컬러만 사용 금지 | accent palette |
| 3 | Tab Bar 아이템 FILL 균등 분배 | `layoutSizingHorizontal: FILL` |
| 4 | 3D 아이콘 정사각형 비율 | center-crop |
| 5 | 히어로 그래픽 최대 3개 | imageGen 룰 |
| 6 | Underline Tab + Individual stroke | `strokeBottomWeight` |
| 7 | Tab Bar — vertical FILL + CENTER | post-fix 자동 교정 |
| 8 | 모든 FRAME FILL 가로 사이징 (HUG 금지) | layoutSizingHorizontal |
| 9 | Tab Bar/FAB — 루트 하단 ABSOLUTE | layoutPositioning |
| 10 | 히어로 = 가로 캐로셀 | clipsContent + itemSpacing |
| 11 | 카드 텍스트 가시성 | fg-primary |
| 12 | 섹션 gap = 0 (동색 + no divider) | spacing |
| 14 | Stage Card 아이콘/이미지 금지 | 단순 구성 |
| 15 | 혜택 리스트 썸네일 24px 2D | imageGen 2D |
| 16 | 이미지 자동 생성 (`imageGen` 필드) | Gemini |
| 17 | Fun 카드 32px 썸네일 + VERTICAL | 위치 룰 |
| 18 | 루트 높이 = 콘텐츠 높이 (852px 금지) | post-fix root height |
| 19 | 스크린샷 QA 필수 | PRD 1:1 대조 |
| 20 | CTA Button autoLayout padding 필수 | HUG 안전성 |
| 21 | Stroke INSIDE 강제 | clipsContent crop 방지 |
| 22 | 가로 스크롤 — 카드 ≤ 165px (peek) | "Scroll" 네이밍 |
| 23 | 신규 화면 — 레퍼런스 deepcopy 우선 | scratch 금지 |
| 24 | Slider Track + Fill + Thumb 3요소 | width = track × progress |
| 25 | Status Bar + NavBar 배치 + bg 매칭 | children[0]/[1] |
| 26 | **마지막 단계 = Semantic Token Binding 검증** | post-fix step 9 |
| 27 | **컬러 = `1. Color modes` 시멘틱만** (스케일 금지) | _Primitives 금지 |
| 28 | **Brand-bg 위 sub-component** = alpha-white-N + grey stepper | Premium CTA Card 패턴 |
| 29 | **카드 위계** = primary > secondary > tertiary > quaternary | depth-별 raw (v2: bg-secondary=#f3f4f6, bg-tertiary=#e6e8ea) |
| 30 | **Day Card 4상태** = overdue/today/scheduled/empty | error/brand/secondary/tertiary bg |
| 31 | **SummaryCard 헤더 순서** = `[Title 좌측] [Pill 우측]` | justify-between |
| 32 | **Progress Bar** = bg-tertiary track + brand-solid fill | `#70f` |
| 33 | **와이어프레임 = 정보 구조 추출 용** | 레이아웃 그대로 베끼지 말 것 |
| 34 | **DS 컴포넌트 인스턴스 우선 사용** | raw frame으로 시뮬레이션 절대 금지 |
| 35 | **위계는 한 단계씩만** | primary→quaternary 점프 금지 |
| 36 | **와이어프레임 UI 요소는 모두 유지** | 임의 누락 금지, 위계만 디자인으로 |
| 37 | **🚨 clone_node 금지 — scratch에서 polished 디자인이 기본** | sections-*.jsx 모든 micro-detail 정밀 재현 (gradient avatar / ABSOLUTE crown / card shadow / outline pill / FAB 52sq / brand 카드 alpha-white sub-component) |

---

## 🚨 최우선 규칙 — DS 문서 사이트를 먼저 검색하고 요소를 그대로 써라

**모든 디자인 생성 시작 전에 반드시 https://twavetech-frontend.github.io/design-system-docs/ 의 모든 페이지를 WebFetch로 검색해서, 거기에 정의된 컴포넌트·variant·토큰·패턴을 그대로 사용해야 한다.**

- 이 사이트는 디자인 시스템의 **단일 진실 공급원(SSOT)** — 새로운 컴포넌트를 임의로 발명하지 말 것
- 사용 흐름:
  1. PRD/요청에서 필요한 UI 요소 식별 (예: pagination, slider, date picker, progress, loading, tabs, badges, alerts 등)
  2. WebFetch로 `/components/{name}` 페이지 조회 (예: `/components/pagination`, `/components/sliders`)
  3. 해당 페이지의 컴포넌트 이름·variant·prop·토큰을 **그대로** Blueprint/Plugin 호출에 인용
- 컴포넌트 페이지 진입점 예시:
  - `/components/buttons`, `/components/inputs`, `/components/tabs`, `/components/badges`, `/components/tags`, `/components/avatars`, `/components/dropdowns`, `/components/selects`, `/components/checkboxes`, `/components/radio-group`, `/components/segmented-control`, `/components/toggles`, `/components/tooltip`, `/components/table`, `/components/modal`, `/components/alerts`, `/components/charts`
  - `/components/pagination`, `/components/date-pickers`, `/components/loading-indicators`, `/components/progress-indicators`, `/components/sliders`
- DS 페이지에 없는 요소가 꼭 필요할 때만 신규 작성하되, DS 페이지의 토큰·간격·radius·타이포 스케일을 따른다
- **금지**: DS에 정의된 컴포넌트를 무시하고 scratch에서 비슷한 것 새로 그리기, prop 이름 임의 변경, 페이지에 없는 variant 추측해서 사용

## 🎨 비주얼 스타일 레퍼런스 컬렉션
- 이 프로젝트에서 생성되는 **모든 GUI의 비주얼 기준**은 `docs/references/` 하위 레퍼런스 시안들 — 단일 화면이 아닌 누적 컬렉션
- **전체 목록·기여 매핑**: [`references/INDEX.md`](references/INDEX.md) — 레퍼런스별 Blueprint 템플릿과 VS 규칙 추적
- 신규 화면 디자인 시 반드시 `design-rules.md`의 **VS 시각 규칙** (현재 VS1~VS8) 준수
- Blueprint 작성 시 `scripts/blueprint_templates.json`의 재사용 템플릿(`SummaryCard2Col`, `AlertCard`, `SectionHeader`, `HorizontalCardScroll`, `ProgressCard`, `AttendanceStrip` 등)을 우선 활용
- 디테일한 인터랙션·마이크로 레이아웃이 모호할 때 해당 레퍼런스의 `sections-*.jsx` 원본 코드를 Read로 참조
- 컬러는 항상 `$token()` 참조 사용 — DS 토큰은 `bash scripts/sync-tokens-from-github.sh`로 GitHub `twavetech-frontend/design-system-docs`에서 최신값 갱신

---

## 디자인 룰

### 1. NavBar 로고는 반드시 컴포넌트 인스턴스로 생성
- 텍스트 노드로 로고를 만들지 말 것
- `create_component_instance(componentKey="81efeddd245e95f31a2724aa370ee54d3caf93d0")` → `insert_child`로 NavBar에 삽입
- `clone_node`로 마스터 컴포넌트를 복제하면 마스터가 복제됨 — 반드시 `create_component_instance` 사용

### 2. 색상 다양성 — 브랜드 컬러만 사용 금지
- CTA/강조에 브랜드 컬러(`bg-brand-solid`)만 반복 사용하면 단조로워짐
- **최소 2–3개 액센트 컬러**를 섞어 사용:
  - `$token(bg-warning-primary)` — 오렌지/경고 (포인트, 이벤트)
  - `$token(bg-success-primary)` — 그린/성공 (달성률, 완료)
  - `$token(bg-error-primary)` — 레드/긴급 (알림, 한정)
- 카드형 CTA 배경도 동일 브랜드 컬러 반복 금지 — 각 카드마다 다른 톤 적용
- 숫자/통계 강조에 `fg-success-primary`, `fg-warning-primary` 등 시맨틱 색상 활용

### 3. Tab Bar 아이템은 반드시 FILL 균등 분배
- Tab Bar 내 모든 아이템: `layoutSizingHorizontal: "FILL"`, `layoutSizingVertical: "FILL"`
- HUG/FIXED 혼용 금지 — 아이템 간격이 불균등해짐
- 빌드 후 반드시 Tab Bar 아이템 사이징 검증할 것

### 4. 3D 아이콘 생성 — 정사각형 비율 필수
- Gemini로 3D 아이콘 생성 시 프롬프트에 **`"chunky, compact, equal width and height, square proportions"`** 포함
- 생성 후 PIL로 **center-crop to square** 처리: `min(w,h)` 기준 정사각형 크롭 → 리사이즈
- 세로로 길쭉한 아이콘 방지: crop 없이 resize만 하면 비율 왜곡됨
- rembg 배경 제거 후 적용

### 5. 히어로/배너 이미지 — 그래픽 요소 최대 3개
- 히어로 배너 그래픽 생성 시 **오브젝트 최대 3개** 제한 (예: 동전 + 선물 + 반짝이)
- 요소가 많으면 복잡하고 산만해짐 — 심플하고 임팩트 있는 구성
- 텍스트가 올라갈 영역(좌측)은 비워둘 것 — 그래픽은 우측에 배치

### 6. Underline Tab Active/Inactive 높이 일치 + Individual Stroke
- Underline 스타일 탭에서 Active에는 Underline Bar(2px)가 있어 Inactive보다 높아짐
- **Tab Inactive는 `layoutSizingVertical: "FILL"`** 설정 — Tab Row(HORIZONTAL) 내에서 Active 높이에 맞춰 자동 확장
- 텍스트 세로 정렬이 틀어지면 안 됨 — 빌드 후 높이 일치 검증 필수
- **Tab Row 스트로크는 individual stroke: bottom only** — 4면 전체가 아닌 하단만 1px 보더
  - `set_stroke_color(nodeId, r, g, b, a, strokeWeight=1, strokeTopWeight=0, strokeBottomWeight=1, strokeLeftWeight=0, strokeRightWeight=0)`
  - `strokeAlign: "INSIDE"` 권장

### 7. Tab Bar 아이템 — vertical FILL + 텍스트 CENTER 정렬 (자동 교정)
- Tab Bar 내 모든 아이템: `layoutSizingVertical: "FILL"` (아이콘+텍스트 세로 정렬 일치)
- 모든 Tab Label 텍스트: `textAlignHorizontal: "CENTER"`, `layoutSizingHorizontal: "FILL"`
- HUG 텍스트 + FILL 아이템 혼용 시 아이콘과 텍스트 정렬이 어긋남
- **이 규칙은 몇 달간 반복적으로 발생한 버그**: FILL 텍스트의 `textAlignHorizontal: LEFT` 기본값으로 인해 Tab Label이 왼쪽으로 쏠려 아이콘과 어긋남
- **자동 교정 (post-fix)**: `_fix_tab_bar_items`가 이름에 `"tab bar"/"tabbar"/"bottom nav"/"bottomnav"` 포함된 섹션의 자식 FRAME을 FILL 가로 정렬 + 내부 TEXT의 `textAlignHorizontal`을 CENTER로 강제
- **Blueprint 작성 시**: Bottom Nav / Tab Bar 내 label 텍스트에 `textAlignHorizontal: "CENTER"` 명시 필수 (post-fix가 빠뜨려도 교정하지만 원천 차단이 안전)

### 8. ⚠️ 모든 섹션/카드/리스트는 반드시 FILL 가로 사이징 (절대 HUG 금지)
- **이 규칙은 가장 자주 위반된다. 반드시 지켜야 한다.**
- Blueprint에서 모든 `FRAME` 타입 자식 노드에 `"layoutSizingHorizontal": "FILL"` 명시
- 특히 **섹션 프레임, 카드 프레임, 리스트 아이템 프레임** — HUG로 두면 가로 너비가 텍스트 길이에 따라 들쭉날쭉
- 텍스트 노드(`type: "text"`)만 HUG 가능 — FRAME은 HUG 금지
- **빌드 후 검증**: `get_node_info`로 모든 섹션/카드의 `layoutSizingHorizontal` 확인, HUG인 것 발견 시 즉시 FILL로 수정
- **Blueprint JSON 규칙**: root 직계 자식과 그 자식들은 모두 `layoutSizingHorizontal: "FILL"` 필수 (아이콘 등 고정 크기 요소 제외)

### 9. ⚠️ Tab Bar와 FAB — 루트 프레임 하단에 배치 (콘텐츠 아래)
- **이 규칙도 매번 누락된다. 빌드 후 반드시 적용해야 한다.**
- **batch_build_screen은 `layoutPositioning: "ABSOLUTE"`를 적용하지 않는다** → 빌드 후 반드시 별도 `set_layout_positioning` 호출
- **배치 원칙**: 모든 콘텐츠가 루트 프레임 안에 보여야 하고, Tab Bar는 루트 프레임 맨 하단, FAB는 Tab Bar 바로 위
- **위치 계산**:
  1. 마지막 콘텐츠 요소의 bottom (y + height) 확인
  2. FAB: `y = content_bottom + 24` (스페이서), `x = 253` (우측 정렬)
  3. Tab Bar: `y = FAB_y + 44 + 16` (FAB 높이 + 간격)
  4. Root height: `Tab Bar_y + 73` (Tab Bar 높이)
- Tab Bar: `set_layout_positioning(positioning: "ABSOLUTE")` → `move_node(x: 0, y: 계산값)`
- FAB: `set_layout_positioning(positioning: "ABSOLUTE")` → `move_node(x: 253, y: 계산값)`
- **FAB 크기**: pill 형태 `120×44`, `cornerRadius: 22` — 56×56 원형은 텍스트가 잘림
- **FAB 컬러**: PRD에 특정 색상이 지정되어 있으면 해당 색상 사용 (config에서 fill 오버라이드). 미지정 시 브랜드 컬러 `$token(bg-brand-solid)` 사용 — FAB는 화면에서 가장 중요한 버튼이므로 브랜드 컬러가 기본
- **빌드 후 검증**: `get_node_info`로 Tab Bar/FAB가 루트 프레임 하단에 있는지, 콘텐츠와 겹치지 않는지 확인

### 10. ⚠️ 히어로 배너는 반드시 가로 캐로셀 구조
- **이 규칙도 매번 VERTICAL 스택으로 잘못 생성된다.**
- 히어로 섹션(VERTICAL, paddingLeft/Right=0) 안에 **"Banner Carousel" 래퍼 프레임(HORIZONTAL)** 필수:
  ```
  Hero Section (VERTICAL, FILL, paddingTop=20, paddingLeft=0, paddingRight=0, clipsContent=true)
    └─ Banner Carousel (HORIZONTAL, clipsContent: true, FILL x FIXED 162, paddingLeft=20, itemSpacing=12)
    │   ├─ Banner Card 1 (FIXED 353×162)
    │   ├─ Banner Card 2 (FIXED 353×162)
    │   └─ Banner Card 3 (FIXED 353×162)
    └─ Indicator (HORIZONTAL, HUG)
        ├─ Dot 1 (active)
        ├─ Dot 2
        └─ Dot 3
  ```
- **Hero Section `paddingTop: 20`, `paddingLeft/Right: 0`** — 상단 패딩 20px 필수, 좌우 패딩은 Carousel의 `paddingLeft: 20`으로 대신 적용
- Banner Carousel에 **`clipsContent: true`** 필수 — `set_auto_layout`의 `clipsContent` 파라미터로 설정
- **`itemSpacing: 12`** — Banner 2가 우측에 약 8px peek 보여 스와이프 가능 힌트 제공
- **Blueprint 작성 시**: 캐로셀 래퍼 노드를 명시적으로 포함하고, `clipsContent: true` 설정
- 배너 카드는 FIXED 사이징 (FILL로 하면 캐로셀 내에서 줄어듦)

### 11. ⚠️ 카드 내 레이블/버튼 텍스트는 반드시 가시적으로
- 카드 내 텍스트가 배경색과 비슷하면 안 보임
- 텍스트 컬러: `$token(fg-primary)` 또는 `$token(fg-secondary)` 사용 (어두운 색)
- 카드 배경이 밝은 색이면 텍스트는 Bold + 어두운 색 필수
- **빌드 후 검증**: 스크린샷에서 모든 레이블/버튼 텍스트가 눈에 보이는지 확인

### 12. 섹션 간 간격 — 배경색 동일 + divider 없으면 gap 0
- 인접한 섹션의 배경색이 동일(둘 다 투명/white)이고 사이에 divider가 없으면 **gap 0px** — 섹션 내부 padding이 여백 역할
- 배경색이 다르거나(컬러 → white 등) 사이에 divider가 있으면 gap 유지

### 14. ⚠️ 스테이지 카드 — 아이콘/이미지 삽입 금지
- Stage Card 안에 아이콘, 이미지, imageGen 노드를 **절대 넣지 말 것**
- Stage Card 구성: 태그(포인트/기프티콘) + 금액 텍스트 + 이율/기간 정보 + 북마크 — **이것만**
- 아이콘/이미지를 넣으면 카드가 복잡해지고 PRD 의도에서 벗어남

### 15. ⚠️ 혜택 리스트 썸네일 — 2D 스타일, 24px, radius 0
- "매일매일 혜택받기" 등 리스트형 섹션의 썸네일 아이콘:
  - **크기: 24×24px** (32px, 40px 아님)
  - **cornerRadius: 0** (둥근 모서리 금지)
  - **스타일: 2D flat** (3D 금지) — Tossface 이모지 스타일 또는 단순 2D 일러스트
  - imageGen 프롬프트: `"2D flat illustration of [subject], simple clean lines, minimal detail, solid colors, Tossface emoji style. Single centered object. Pure white background. No text. No shadow."`
- 3D 아이콘은 히어로 배너, Fun 섹션 등 **큰 카드 전용** — 리스트 썸네일에는 2D만 사용

### 16. 이미지 자동 생성 — Blueprint `imageGen` 필드
- Blueprint 노드에 `imageGen` 필드를 추가하면 **디자인 빌드 후 자동으로 Gemini 이미지 생성 + 적용**
- 디자인 빌드 한 번으로 **빌드 → post-fix → 이미지 생성/적용**까지 전부 자동 실행
- **Blueprint 예시**:
  ```json
  {
    "name": "Banner Card 1",
    "type": "frame",
    "imageGen": {
      "prompt": "3D gold coins floating with green sparkles, right side composition",
      "isHero": true
    },
    ...
  }
  ```
- **imageGen 필드**:
  - `prompt` (필수): Gemini 이미지 생성 프롬프트 (영어)
  - `isHero` (선택): `true`면 히어로/배너 이미지 (배경 유지, 노드 크기 자동 감지), `false`(기본값)면 아이콘 (배경 제거)
  - `width`/`height` (선택): 아이콘 크기 (isHero=false일 때, 기본 120)
  - `style` (선택): 스타일 오버라이드
- **주의**: `imageGen.prompt`에 3D 스타일 키워드는 자동 적용되지 않음 — 프롬프트에 직접 포함할 것
- **⚠️ MCP generate_image(isHero=true) 수동 호출 시 주의**: Banner Card nodeId를 전달해야 하며, Hero Section이나 Carousel nodeId를 전달하면 안 됨. `isHero=true`는 전달된 nodeId의 크기를 자동 감지하여 이미지를 적용하므로, 부모 프레임을 전달하면 부모에 이미지가 적용됨. Blueprint의 `imageGen` 필드를 사용하면 nodeMap으로 정확한 nodeId가 매핑되어 이 문제가 발생하지 않음.
- **⚠️ `set_image_fill`은 `imageData` (base64) 전용 — `url` 파라미터 절대 사용 금지**
  - Figma 플러그인에 URL 다운로드 기능 없음 — `url`을 전달하면 `"Missing imageData"` 에러
  - 반드시 파일을 읽어서 `base64.b64encode()` 후 `imageData`로 전달
  - `figma_mcp_client.py`의 `call_tool`에 `url` 사용 시 자동 차단 로직 있음 (ValueError)
  - `figma-mcp-embedded.ts` 스키마에서 `url` 파라미터 제거됨, `imageData` required

### 17. ⚠️ Fun 카드 (랜덤박스/기프트샵) — 32px 썸네일, 텍스트 위에 배치
- "놓칠 수 없는 즐거움" 등 Fun 섹션의 카드 아이콘:
  - **크기: 32×32px** (50px 아님)
  - **위치: 텍스트 위에 배치** — 아이콘이 카드 상단, 텍스트(제목+설명)가 아래
  - **스타일: 3D 비비드 글로시** (여기어때/야놀자 스타일)
  - **카드 레이아웃**: VERTICAL auto-layout, `[32px 아이콘] → [제목 텍스트] → [설명 텍스트]`
  - cornerRadius: 0 (아이콘 프레임)
- **절대 금지**: 아이콘을 텍스트 옆(HORIZONTAL)에 배치하거나 50px 이상으로 키우는 것

### 18. ⚠️ 루트 프레임 높이 = 전체 콘텐츠 높이 (852px로 줄이지 말 것)
- **post-fix가 설정한 루트 높이를 임의로 줄이지 말 것**
- 852px(iPhone 16 뷰포트)는 **프로토타입 전용** — 디자인 프레임 크기가 아님
- 루트 프레임은 **모든 콘텐츠(+ CTA Bar/Tab Bar)가 다 보이는 높이**여야 함
- CTA Bar/Tab Bar를 ABSOLUTE로 배치할 때도 루트 높이는 콘텐츠 전체를 포함해야 함
- 루트를 852px로 줄이면 하단 섹션이 잘려서 안 보임 → **절대 금지**

### 19. ⚠️ 스크린샷 QA — PRD 모든 섹션 보이는지 확인 필수
- 스크린샷 촬영 후 **PRD에 명시된 모든 섹션이 화면에 보이는지** 1:1 대조
- "스크롤 영역이라 정상"으로 넘기지 말 것 — 디자인 프레임에 전체 콘텐츠가 보여야 완료
- 하나라도 안 보이면 **완료 선언 금지** — 원인 파악 후 수정
- 체크 순서: PRD 섹션 목록 나열 → 스크린샷에서 각 섹션 존재 확인 → 누락 시 수정

### 20. ⚠️ CTA/Button 프레임 — autoLayout에 paddingTop/Bottom 필수
- CTA Button, Submit Button 등 **텍스트를 포함한 버튼 프레임**에 `autoLayout` padding 필수
- `height: 52`만 지정하고 padding을 빼면, HUG 사이징에서 높이가 텍스트(~20px)로 축소됨
- **올바른 패턴**: `autoLayout: { ..., paddingTop: 16, paddingBottom: 16 }` → HUG여도 16+20+16 = 52px
- `height`에 의존하지 말고 **padding으로 높이를 확보**하는 것이 안전
- `validate_blueprint`의 R5 규칙이 자동 검증

### 21. ⚠️ Stroke Alignment — 항상 INSIDE (OUTSIDE/CENTER 금지)
- **이 규칙은 스크롤/캐로셀 내부 카드에서 매번 잘려 보이는 문제를 만든다. 반드시 지켜야 한다.**
- stroke가 있는 모든 FRAME: `strokeAlign: "INSIDE"` 강제. **OUTSIDE / CENTER 절대 금지**.
- **이유**: OUTSIDE/CENTER stroke는 부모가 `clipsContent: true`(가로 캐로셀, 스크롤 Row 등)이면 바깥쪽으로 튀어나간 stroke가 **잘려보임**. 특히 "today" 강조 카드의 ±2px 보더에서 상단이 잘리는 사례 반복.
- **실전 사례 (2026-04-22)**: Schedule Today Card(월 20 오늘)가 Day Card Row `clipsContent:true`에 의해 상단 stroke 잘림. INSIDE로 교체 후 4방향 모두 선명하게 렌더.
- **자동 강제**: post-fix의 `_fix_stroke_alignment()`가 모든 OUTSIDE stroke를 빌드 후 INSIDE로 자동 변환. Blueprint에서 OUTSIDE로 작성해도 자동 교정됨.
- **빌드 후 검증**: `get_node_info`로 stroke 있는 카드의 `strokeAlign` 확인 — OUTSIDE이면 즉시 `set_stroke_color(strokeAlign="INSIDE")`로 수정.

### 22. ⚠️ 가로 스크롤 섹션 — 마지막 카드 peek 필수 (뷰포트 40% 이하)
- **이 규칙은 스와이프 가능 힌트를 보장하기 위함이다. 반드시 지켜야 한다.**
- 가로 스크롤 섹션은 **3가지 조건 모두 충족**:
  1. HORIZONTAL autoLayout + `clipsContent: true`
  2. **이름에 "Scroll" 키워드 포함** (예: `"Stage Card Scroll"`, `"Product Scroll"`) — 네이밍 컨벤션으로 일반 HORIZONTAL 섹션과 구분
  3. 자식 카드는 `layoutSizingHorizontal: "FIXED"` + width 명시
- 카드 너비 **최대 165px** (iPhone 16 뷰포트 393 기준 약 **40%**).
- **목적**: 2.1~2.5개 카드가 한 화면에 들어와 **3번째 카드가 우측에서 20~40% peek** — 사용자에게 "스와이프 가능" 시각 힌트 제공.
- **나쁜 예**: Stage Card 220px (56%) → 2개만 완전히 보이고 3번째 완전 hidden → 스와이프 불가로 보임.
- **좋은 예**: Product Card 150px (38%) → 2개 full + 3번째 30% peek → 자연스러운 스와이프 유도.
- **권장 수치 (뷰포트 393, paddingLeft 16, itemSpacing 10 기준)**:
  - 카드 width 150~160px → 3번째 카드 약 22~30% peek
  - paddingRight 0 (또는 ≤ 8) — peek 공간 확보
- **카드 내부 콘텐츠 설계**: 카드 너비 160 → 내부 padding 16 양쪽 → 가용 128px. 금액 300만원(24sp Bold) / 이율 3.2% / 10~13자 라벨(12sp) 모두 들어감.
- **빌드 후 검증**: post-fix의 `_check_horizontal_scroll_peek()`이 자동 경고 (이름에 "Scroll" + clipsContent + 자식 FIXED). 0건이 정상.
- **예외**: 히어로 배너 캐로셀(1개씩 스와이프) — 카드 353px (뷰포트 90%, 좌우 20px peek). 이 경우 peek는 양쪽에.

### 23. ⚠️ 신규 화면 설계 — 기존 레퍼런스 섹션 `copy.deepcopy()` 우선 (scratch 작성 금지)
- **이 규칙은 완성도 저하 재발 방지용**. 2026-04-22 사용자 피드백: "레퍼런스에 없는 화면 만들어 달라하면 완성도가 최하단 수준으로 나옴."
- **원칙**: 새 화면의 각 섹션에 대해 **기존 레퍼런스에 유사 구조가 있으면 반드시 deepcopy 후 텍스트만 교체**. scratch로 새로 작성하지 말 것.
- **이유**: 완성도 = padding 밀도 + 타이포 계층 + 아이콘 사이즈 + micro-spacing 등 수백 개 micro-decision의 누적. LLM/Python은 "적절한 기본값"은 알지만 이 프로젝트의 "검증된 디테일"은 레퍼런스에만 있음.
- **패턴 매칭 예시**:
  | 새 섹션 의도 | 재사용 소스 |
  |-------------|-----------|
  | 요약 카드 (N건 + 2-col 금액) | `imin-home/blueprint.json children[3]` SummaryCard Wrap |
  | 한도/사용률 게이지 | `children[5]` Limit Section |
  | 추천 CTA 큰 카드 | `children[6]` Recommendation Section |
  | 가로 스크롤 카드 리스트 | `children[8]` Stage Card Scroll / `children[13]` Product Scroll |
  | 연속 출석 + 7일 dot | `children[10]` Attendance Wrap |
  | 이벤트 배너 | `children[11]` Event Banner Wrap |
  | 섹션 헤더 + "전체보기" | `children[7]` Header 참여 중인 스테이지 |
- **Python 복제 패턴**:
  ```python
  import copy, json
  imin_home = json.load(open('docs/references/imin-home/blueprint.json'))
  summary = copy.deepcopy(imin_home['children'][3])  # SummaryCard
  # 텍스트만 교체
  summary['children'][0]['children'][0]['children'][0]['text'] = "완료 0건"  # pill
  summary['children'][0]['children'][1]['text'] = "스테이지 내역"  # title
  ```
- **완전 신규 패턴이 불가피할 때** (예: 랭킹 보드, 지도 뷰, 채팅 버블): 장식 요소(아바타/메달/progress bar/overlay badge)를 풍부하게 넣되 레퍼런스 수준에는 **못 미친다는 것을 전제**로 작업. 완성도 부족하면 레퍼런스 폴더에 추가 등록 후 재사용.
- **금지**: "빠르게 단순한 구조로 프로토타입" 작성 — 이전 v1/v2에서 한 실수. 시간 아끼는 게 아니라 재작업을 부름.

### 24. ⚠️ Slider 컴포넌트 — Track + Fill + **Thumb 3요소 필수 + Fill width = track × progress 비율**
- **2026-04-22 사용자 피드백 2건**:
  1. Track + Fill만 만들고 Thumb(드래그 컨트롤러)을 빠뜨려 "슬라이더가 슬라이더로 안 보인다"
  2. 3/13회차인데 Thumb이 Track **끝**에 있음 — Fill width가 progress 비율에 맞지 않음
- **규칙 3원칙**:
  1. **Track·Fill·Thumb 3요소 모두 있어야 한다** (Thumb 생략 금지)
  2. **Fill width는 progress 비율로 정확히 계산한다** — 대충 70 넣으면 안 됨
  3. **Slider Fill/Thumb은 반드시 `layoutSizingHorizontal: "FIXED"` 명시** — post-fix가 FILL 강제 변환 대상에서 제외시키기 위한 원천 차단

**Fill width 계산 공식**:
```
fill_width = track_available_width × (current_value / max_value)
```
- `track_available_width` = Slider Track의 부모 체인 padding을 모두 뺀 실제 가용 폭
- 예: iPhone 16 (393px) → Recommendation Section(padding 20×2) → Premium CTA Card(padding 20×2) → Controls Panel(padding 14×2) 이면 **track_width = 393 − 40 − 40 − 28 = 285px**
- 3/13회차 → fill_width = 285 × 3/13 ≈ **66px**
- 7/12회차 → 285 × 7/12 ≈ **166px**
- Blueprint 작성 시 **반드시 이 계산을 한 번 하고 반올림값 적용**

**구조 (Blueprint 표준 패턴)**:
```json
{
  "name": "Slider Track",
  "type": "frame",
  "layoutSizingHorizontal": "FILL",
  "height": 6,
  "cornerRadius": 999,
  "fill": { "track bg — 옅은 색, 예: white 30% alpha" },
  "clipsContent": false,
  "autoLayout": {
    "layoutMode": "HORIZONTAL",
    "counterAxisAlignItems": "CENTER"
  },
  "children": [{
    "name": "Slider Fill",
    "type": "frame",
    "layoutSizingHorizontal": "FIXED",    // ★ 필수 — post-fix FILL 강제 방지
    "width": 66,                           // ★ track × (current/max)
    "height": 6,
    "cornerRadius": 999,
    "fill": { "white 또는 brand color" },
    "clipsContent": false,
    "autoLayout": {
      "layoutMode": "HORIZONTAL",
      "primaryAxisAlignItems": "MAX",     // Thumb을 Fill 우측 끝에
      "counterAxisAlignItems": "CENTER"   // Thumb을 세로 중앙에
    },
    "children": [{
      "name": "Slider Thumb",
      "type": "frame",
      "layoutSizingHorizontal": "FIXED",   // ★ FIXED 명시
      "layoutSizingVertical": "FIXED",
      "width": 16,
      "height": 16,
      "cornerRadius": 999,
      "fill": { "r":1, "g":1, "b":1, "a":1 },
      "effects": [{
        "type": "DROP_SHADOW",
        "color": { "r":0, "g":0, "b":0, "a":0.2 },
        "offset": { "x":0, "y":2 },
        "radius": 6, "spread": 0,
        "visible": true, "blendMode": "NORMAL"
      }]
    }]
  }]
}
```

**중요 핀포인트**:
- Track/Fill 모두 **`clipsContent: false`** — Thumb(16px)이 Track(6px)보다 커서 상하로 5px씩 튀어나와야 함
- Slider Track을 감싸는 **상위 Row(예: "Turn Row")도 `clipsContent: false`** — 안 그러면 Thumb 잘림
- Thumb은 autoLayout 자식이므로 `layoutPositioning: ABSOLUTE` / 수동 후속 호출 **불필요**
- **progress 비율이 바뀌는 slot**(예: 3회차 → 5회차)을 다룰 때는 **Fill width 값을 slot이나 binder 로직으로 계산**해야 한다 — 하드코딩된 70 금지

**post-fix 예외 — 이미 자동 처리됨** (`figma_mcp_client.py` SKIP_KEYWORDS에 `"slider"` 추가됨, 2026-04-22):
- 이름에 `slider` 포함된 모든 frame은 FILL 강제 변환 대상에서 제외
- 즉 Blueprint의 `layoutSizingHorizontal: "FIXED"` + `width: N` 설정이 보존됨

**금지**:
- Track + Fill만 있고 Thumb 없는 구조
- Fill width를 progress 비율 무시하고 대충 70 등으로 설정
- Slider Fill/Thumb에 `layoutSizingHorizontal` 명시 생략 (post-fix에 의해 FILL로 리셋될 위험)

### 25. ⚠️ Status Bar + Tool Bar (NavBar) 배치 — 루트 `children[0]`은 Status Bar, `children[1]`은 NavBar
- **2026-04-23 사용자 피드백**: "Status bar - iPhone 인스턴스를 복제해서 화면 최상단, 그 아래에 tool bar."
- **Blueprint 구조 규칙**:
  ```
  Root frame
    ├── children[0]  Status Bar  (clone 또는 자동 주입)  ← 반드시 최상단
    ├── children[1]  NavBar / App Header / Tool Bar
    ├── children[2]  ... (콘텐츠 섹션들)
    └── children[last]  Bottom Nav / Tab Bar (ABSOLUTE)
  ```
- **두 가지 주입 방식 (둘 중 하나 선택)**:

  **방식 A — 자동 탐색 (포터블, 권장)**:
  - 루트에 `"statusBar": true` 한 줄만 추가
  - Plugin이 문서 전체 페이지에서 이름에 `"status bar"` 포함한 COMPONENT/INSTANCE/FRAME을 찾아 자동 복제 + 루트 첫 자식으로 삽입
  - 매칭은 substring 기반 — "Status bar - iPhone", "Status Bar Light" 등 suffix 있어도 매칭 (2026-04-23 plugin code.js 패치)
  - 이름이 `status bar`를 포함하는 노드가 **반드시 Figma 파일 어딘가에 존재**해야 함

  **방식 B — 명시적 sourceNodeId clone (특정 인스턴스 고정)**:
  - 루트 `children[0]`에 직접 추가:
    ```json
    { "type": "clone", "name": "Status Bar",
      "sourceNodeId": "81:8606", "layoutSizingHorizontal": "FILL" }
    ```
  - `sourceNodeId`는 현재 Figma 문서의 Status Bar 인스턴스 노드 ID
  - 장점: 정확한 인스턴스 선택. 단점: 다른 문서로 이식 시 무효 (해당 문서에도 같은 인스턴스 있어야)
  - Clone 실패 시 plugin이 붉은색 "[CLONE FAILED]" placeholder 생성 → 디버깅 용이

- **아임인 레퍼런스(`docs/references/imin-home/blueprint.json`)는 방식 B + 방식 A 병용**: 방식 A로 먼저 시도 → 이미 자식으로 Status Bar 있으면 plugin이 skip → 방식 B의 clone이 그대로 유지
- **Plugin 수정 필요 시 재로드**: `src/figma-plugin/code.js` 수정 후 Figma 앱에서 플러그인 Close/Run 한 번 해줘야 반영 (현재 substring 매칭 패치는 플러그인 재로드 대상)

**Status Bar 배경색 = NavBar(tool bar) 배경색 (2026-04-23 추가)**:
- Status Bar의 bg color는 **반드시 바로 아래 NavBar의 bg color와 일치**시켜야 한다. 시스템 영역과 앱 헤더 사이 색 경계가 보이면 디자인 완성도가 크게 떨어진다.
- NavBar가 brand color(예: 보라)이면 Status Bar도 같은 보라. NavBar가 white이면 Status Bar도 white.
- **자동 적용**: `scripts/figma_mcp_client.py`의 post-fix 마지막 단계 `_match_status_bar_bg_to_nav`가 `children[0]`(Status Bar)의 fill을 `children[1]`(NavBar)의 첫 SOLID fill로 덮어쓴다. NavBar fill이 SOLID가 아니거나 없으면 skip.
- **한계**: post-fix가 스킵되는 경우 수동으로 `set_fill_color(Status Bar nodeId, NavBar fill 값)` 호출 필요. cmd_build의 rootId 파싱 실패 시 이 단계도 스킵됨을 주의.
- **예외**: NavBar가 투명 + 그 뒤에 colored hero 배경이 비쳐 보이는 디자인이라면 Status Bar도 동일하게 투명으로. 이 경우에도 "NavBar fill과 동일" 원칙은 유지 (투명=투명).

- **금지**:
  - Status Bar를 `children[1]` 이후에 배치 (NavBar보다 아래)
  - Status Bar 없이 NavBar만 최상단에 두는 구조 (iPhone 표준 시스템 UI 누락)
  - Status Bar bg를 NavBar와 다른 색으로 남겨두기 (상단 색 경계선 발생)

### 26. ⚠️ 디자인 생성 마지막 단계 — Semantic Token Binding 필수 검증 (PRD/와이어프레임 → 디자인 모든 케이스)
- **사용자가 PRD나 와이어프레임으로 디자인을 생성해 달라고 요청하면 빌드 흐름의 마지막 단계는 "변수 바인딩 결과 확인"이다 — 절대 생략 금지.**
- post-fix step 9 (`_bind_semantic_tokens`)이 자동 sweep을 수행하지만, 다음 사유로 skip될 수 있음:
  - plugin 직렬화 실패 (`Cannot unwrap symbol` — figma.mixed Symbol이 strokes/effects 등에 포함)
  - root `get_node_info` 응답이 빈 응답 (큰 트리)
  - TOKEN_MAP empty / load 실패
- **빌드 종료 후 반드시 다음 4가지를 검증한다:**
  1. post-fix 출력의 마지막 라인 `Token 바인딩: colors=N numbers=M text=K effects=E`에서 **각 카운트가 0이 아닌지** 확인
  2. **0이거나 `skip`이면** plugin reload(Figma 앱에서 플러그인 Close → Run) 후 `python3 scripts/figma_mcp_client.py post-fix <rootId>` 명시적 재실행
  3. fallback 로그(`root fetch failed → falling back to per-child fetch`, `child <id> fetch failed`)가 출력되면 그 노드의 binding이 누락된 것 → plugin 패치(figma.mixed 가드) 적용 또는 해당 subtree 수동 binding
  4. unmapped report(`/tmp/unmapped-tokens-{rootId}.json`) 검토 — token map에 없는 raw 값이 있는지 확인. 필요 시 `bash scripts/sync-tokens-from-github.sh`로 토큰 최신화 후 재시도
- **사용자에게 보고 시 binding 카운트를 명시적으로 포함**: "Token 바인딩: colors=258 numbers=431 text=77 effects=0" 형식으로 노출. 0건이거나 skip된 경우 그 사유와 조치도 함께.
- **빌드 후 자동 시퀀스에 포함됨** (`figma_mcp_client.py build`):
  ```
  build → post-fix(1차, token-bind skip) → post-fix(2차, token-bind 실행)
        → 이미지 생성 → 로고 인스턴스 교체 → [최종 binding 카운트 출력]
  ```
  최종 출력에서 binding 카운트 0이면 마지막 단계 검증이 실패한 것 — 보강 후 다시 실행.
- **plugin 직렬화 가드 (참고)**: `src/figma-plugin/code.js`의 `collectNodeInfo`는 `fills`/`strokes`/`effects` 모두 `figma.mixed` Symbol 가드 + plain 객체로 sanitize 처리됨 (2026-05-01 패치). 향후 plugin에 mixed 가능 필드를 추가할 때 동일 가드 패턴 적용 필요.
- **client-side fallback (참고)**: `_bind_semantic_tokens`는 root fetch 실패 시 자동으로 children-by-children fetch + 재귀 fallback으로 복구 (2026-05-01 추가). plugin이 빌드 안 된 상태에서도 binding이 가능한 한 진행됨.

### 27. ⚠️ 컬러 시스템 — `1. Color modes` 시멘틱 토큰만 사용 (스케일/Primitives 금지)
- **사용자 규칙 (2026-05-01)**:
  1. **컬러는 반드시 `1. Color modes` 컬렉션의 시멘틱 토큰만 사용** — `bg-primary`, `fg-primary`, `border-primary`, `icon-fg-brand`, `button-primary-icon` 등.
  2. **`_Primitives` 컬렉션의 스케일 컬러 절대 사용 금지** — `Colors/Brand/300`, `Colors/Gray-light/500`, `Colors/Error/600`, `Colors/Base/white` 등 raw scale은 모두 금지.
  3. **`bg-disabled`, `bg-disabled_subtle` 등 disabled 토큰은 사용 금지** — 명확한 사용자 요청이 있을 때만 사용. raw 값이 `bg-primary`와 동일해 token-bind 자동 매칭이 잘못 될 수 있음.
  4. **화면 전체 bg는 `bg-primary` 단일** — 섹션마다 다른 bg 컬러 사용 금지. wrapper 섹션은 root bg와 동일하게.
- **시멘틱 토큰 식별 (figmaPath prefix)**:
  - `Colors/Background/`, `Colors/Foreground/`, `Colors/Border/`, `Colors/Text/`, `Colors/Effects/`
  - `Component colors/` (button-primary-icon, footer-button-fg, avatar-styles-bg-neutral 등)
- **자동 강제 (post-fix step 8.5 — `_normalize_screen_background`)**:
  - root 노드 fill을 `bg-primary` (`#ffffff`)로 강제
  - 직계 자식 wrapper frame fill을 모두 `bg-primary`로 통일 (NavBar/BottomNav/Status Bar 포함)
- **자동 강제 (token-bind allow-list)**: `_load_token_index`가 `_COLOR_MODES_PATH_PREFIXES` 검사로 시멘틱 토큰만 color_index에 등록. _Primitives와 disabled/hover 토큰은 매칭 후보에서 자동 제외.
- **Blueprint 작성 시**: fill에 raw RGB 대신 가능하면 시멘틱 토큰 reference 사용 — token-bind가 자동 적용. 단, 빌드 단계는 raw RGB도 허용 (post-fix가 매핑).
- **금지**:
  - `Colors/Brand/600` 등 스케일 토큰을 raw로 의도해서 사용
  - bg-disabled, bg-disabled_subtle을 일반 background로 사용
  - 섹션 wrapper마다 다른 회색 배경(`#e6e6e6`, `#f9fafb` 등) 사용 — 통일 필수

### 28. ⚠️ Brand-bg(보라/colored) 카드 위 sub-component 위계 — alpha-white-N + 단단한 grey 스테퍼
- **사용자 수정 레퍼런스 (2026-05-01, Figma node `16941:51405`)**에서 추출한 결정형 패턴.
- **Card 본체**: `bg-brand-section` (`#5200b0`, 어두운 보라). hover/_alt 절대 금지.
- **Card 위 텍스트**:
  - 주 amount/title: `text-white` (`#ffffff`)
  - 보조 텍스트: `alpha-white-70` (`rgba(255,255,255,0.7)`)
  - 활성 라벨/현재값: `text-white` 또는 `rgba(255,255,255,0.85)`
  - **`text-primary_on-brand` 등 modifier 토큰 사용 금지** — 사용자 수정 디자인은 `text-white` 사용
- **Sub-component 위계 (Card 위에 떠 있는 요소들)**:
  - 정보 Pill (label-only 캡슐): bg = `alpha-white-10` (`rgba(255,255,255,0.1)`)
  - Sub-section Panel (여러 컨트롤을 묶는 컨테이너): bg = `alpha-white-10`
  - Slider Track: bg = `alpha-white-20` (`rgba(255,255,255,0.2)`)
  - **Slider Fill / Slider Thumb**: bg = `#e6e8ea` (단단한 grey, **NOT white, NOT alpha**) + Thumb은 drop shadow `0px 2px 6px rgba(0,0,0,0.2)`
  - **Stepper container** (숫자 +/- 묶음): bg = `bg-secondary` (`#f9fafb`) — 단단한 light gray pill
  - **Stepper minus/plus button**: bg = `#e6e8ea` (단단한 grey)
  - Stepper 숫자 text: `text-primary` (`#2c3744`) — Stepper bg 위 어두운 텍스트
  - **Primary CTA Button** (예: "맞는 스테이지 찾기"): bg = `fg-light` (white) + text = `#5200b0` (brand-section, 카드 본체와 동일 보라)
- **Slider 구조 (Thumb 위치 = Fill width)**: Track(`alpha-white-20`) → Fill(`#e6e8ea`, width=track×progress) → Thumb(`#e6e8ea` 16px, drop shadow). Fill 안 Thumb은 `primaryAxisAlignItems: MAX` + `counterAxisAlignItems: CENTER`.
- **금지**:
  - 보라 카드 위 sub-component를 solid white로 (큰 흰 박스가 됨, 사용자 분노 트리거)
  - hover/disabled/_alt modifier 토큰 사용 (mobile에는 hover 없음)
  - Slider Fill/Thumb을 white로 (사용자 디자인은 `#e6e8ea` grey)
  - Stepper btn을 alpha-white로 (단단한 grey여야)

### 29. ⚠️ 카드 위계 (depth 1~3) — bg-primary > bg-secondary > bg-tertiary > bg-quaternary
- **사용자 수정 레퍼런스 v2 (2026-05-01 갱신)** Figma 노드 `16941:51284` 검증 raw 값:
  - **depth 0 (root frame)**: `bg-primary` = `#ffffff` (white). 화면 전체 배경.
  - **depth 1 (Section wrapper)**: 보통 fill 없음(투명). 또는 `bg-primary` (`#fcfcfd` 또는 `#ffffff`). Wrapper는 padding만 책임지고 색은 root가 보임.
  - **depth 2 (Card — SummaryCard, Stage Card, Limit Card 등)**: `bg-secondary` = **`#f3f4f6`** (이전 `#f9fafb`에서 갱신) + border `border-secondary` = `#e6e8ea`. cornerRadius 14~16px.
  - **depth 3 (Sub-card — SummaryCard 안의 Grid Left/Right 같은 inner section)**: `bg-tertiary` = **`#e6e8ea`** (이전 `#f3f4f6`에서 갱신). cornerRadius 12px.
  - **depth 4+ (강조 셀)**: `bg-quaternary` = `#d2d6db` (또는 `border-primary`).
- **자동 적용**: post-fix step 8.6 `_apply_bg_hierarchy`가 cornerRadius 있는 + near-white(rgb≥0.93) frame을 depth별 raw로 retint. 부모가 non-neutral(보라/alert)면 자식 retint 차단.
- **카드 위 텍스트 룰**:
  - 주 amount/title: `text-primary` (`#2c3744`)
  - 보조 unit/sub: `fg-secondary` (`#596069`)
  - Brand 강조: `text-brand-secondary` (`#5200b0`) — pill 안 brand 텍스트, 강조 amount
  - 더 어두운 brand: `bg-brand-section` (`#340078`) — primary amount 강조
- **Pill 패턴 (카드 안 status badge)** — v2 갱신 (2026-05-01):
  - **Brand count pill (진행 중)**: bg = `bg-brand-primary` (`#f4ecff`) + border `#e6d4ff` + text = `#5200b0`
  - **Default pill (미납 텍스트만)**: bg 없음 + text = `text-error-primary` (`#d92d20`)
  - **Warning pill (지급 예정)**: bg = `bg-warning-primary` (`#fffaeb`) + text = `#b54708` (utility-warning-700)
  - **Solid alert pill (미납 P0 알림 카드 등)**: bg = `utility-error-600` (`#d92d20`) + text = `text-primary_on-brand` (white)
- **금지**:
  - depth 2 카드를 white solid로 (#ffffff) — bg-secondary 사용
  - depth 3 sub-card를 bg-secondary로 동일 — bg-tertiary로 차별화
  - bg-secondary_hover, bg-primary_hover 등 _hover 변형 사용 (mobile = no hover)

### 30. ⚠️ Day Card 4상태 패턴 (Schedule Section의 날짜 카드)
- **사용자 수정 레퍼런스 v2 (2026-05-01)** Figma `16941:51350` (Day Card Scroll). Day Card는 4가지 상태로 명확히 구분.
- **공통 구조**: 68px × 96px FIXED, padding 8, cornerRadius 14, justify-between (Day Top + Amount + Status Pill)

| 상태 | Card bg | Card border | text 컬러 | Status Pill |
|---|---|---|---|---|
| **overdue (미납)** | `utility-error-50` `#fef3f2` | `border-error_subtle` `#fda29b` | `#b42318` | bg=`bg-error-secondary` `#fee4e2` + border=`border-error_subtle` `#fda29b` + text=`#b42318` |
| **today** | `bg-brand-primary` `#f4ecff` | none | `text-brand-primary` `#6a00e0` | bg=`bg-brand-secondary` `#e6d4ff` + text=`text-brand-primary` `#6a00e0` |
| **scheduled** | `bg-secondary` `#f3f4f6` | `border-primary` `#d2d6db` | `text-primary` `#2c3744` | none (Day Top + 빈 영역) |
| **empty/past** | `bg-tertiary` `#e6e8ea` | `border-tertiary` `#f3f4f6` | `text-secondary` `#687079` | none + opacity 0.55 |

- **Status Pill 내부**: dot 4×4 + text 10px Semibold. dot 색상 = pill text 색상.
- **Day Top 내부**: dow-text (12px Medium) + day-number (18px Bold). 같은 색상 family 유지.
- **금지**:
  - 모든 Day Card를 같은 색으로 (사용자가 요일 + 상태 인지를 못함)
  - empty/past 카드에 opacity 100% (차별화 사라짐)
  - today 카드에 brand-secondary bg를 직접 사용 — bg는 brand-primary가 옅고, pill만 brand-secondary가 진한 톤

### 31. ⚠️ SummaryCard 헤더 순서 — `[Title 좌측] · · · [Pill 우측]`
- **사용자 수정 레퍼런스 v2 (2026-05-01)** Figma `16941:51319`. 이전 v1은 `[Pill 좌측] [Title 우측]`이었으나 v2에서 변경.
- **올바른 패턴**: `justify-between` autoLayout
  - 좌측: 타이틀 (예: "내 스테이지") — `text-md/Bold` `text-primary`
  - 우측: Count Pill (예: "3건 진행 중") — `bg-brand-primary` + `border #e6d4ff` + text `#5200b0`
- **이유**: 모바일 스캔 동선이 좌→우. 가장 중요한 라벨(타이틀)이 좌측, 보조 정보(개수/상태)가 우측에 배치.
- **금지**:
  - Pill을 좌측에 두고 타이틀을 우측에 (스캔 우선순위 역전)
  - Pill bg를 `bg-quaternary`로 (Brand 강조 사라짐)

### 37. 🚨 clone_node 절대 금지 — scratch에서 polished 디자인이 기본 기준선
- **사용자 정책 (2026-05-01)**: "야 누가 복사하래! 다른 사용자들은 이런게 없다고. 다시 너가 처음부터 만들어야지!"
- **금지**:
  - 와이어프레임/PRD → 디자인 작업에서 `clone_node`로 기존 빌드된 Figma 노드를 복사하는 행위 절대 금지
  - 룰 #23 "deepcopy"는 sections-*.jsx 등 **코드/구조의 deepcopy**이지 빌드 결과물의 clone이 아님
  - 콘텐츠 교체조차 안 하고 그대로 복사 → 사용자 강력 분노
- **기준선**: production의 다른 사용자에겐 cloned 레퍼런스가 없음. AI는 매번 scratch에서 polished 디자인을 만들 수 있어야 정상.
- **scratch 빌드 시 정밀 재현 체크리스트**:
  1. **컬러 정밀도**: sections-*.jsx의 brand-50/100/600/700 등 primitive를 시멘틱 토큰으로 정확 매핑
     - brand-50 → `bg-brand-primary` / brand-100 → 더 옅은 brand bg / brand-600 → `bg-brand-solid` / brand-700 → `fg-brand-secondary`
  2. **추천 outline Pill**: bg-brand-primary 옅은 보라 + fg-brand-secondary 텍스트 + brand-600 1px border. 단순 회색 배경 절대 금지
  3. **Avatar circle**: solid color 금지 — `fillGradient` 135deg with 2 stops [`{position:0, color}`, `{position:1, color rgba 0.8}`]. 각 아바타 다른 컬러 (#8b5cf6 / #ec4899 / #f59e0b / #10b981)
  4. **Crown badge**: ABSOLUTE positioning bottom-right, 18sq circle, brand-solid bg, 2px 흰 border, 9sp 👑 이모지 — lv가 active한 1명에게만
  5. **Card shadow**: effects 배열에 DROP_SHADOW `{type:'DROP_SHADOW', offset:{x:0,y:1}, radius:2, color:{r:0.04,g:0.05,b:0.07,a:0.06}}` 명시
  6. **Card border**: 1px `border-secondary` INSIDE
  7. **CreateStageFAB**: 52sq + brand-solid + 3px 흰 border + brand shadow `{r:0.41,g:0.22,b:0.94,a:0.35}` + plus 24 흰 아이콘. **pill 120×44 형태 절대 금지**
  8. **Brand card 안 sub-component fill**: post-fix `_apply_bg_hierarchy`가 depth 4+를 quaternary로 덮어쓰므로 — Brand 카드 안의 Benefit Band 등은 명시적 RGBA로 하되 nodeName에서 "Benefit Band" 같은 일반어 유지(post-fix가 우선 무시), fill은 alpha-white-12 RGBA로
  9. **텍스트 가시성** (룰 #11): 흰 배경에서 fg-quaternary 너무 흐림 → fg-tertiary 이상 사용
  10. **Section 구조**: 단순 frame이 아닌 padding+itemSpacing+secondary action 포함된 컴포넌트 구조
- **위반 결과**: clone 사용 시 사용자가 알아채면 즉시 분노. 형편없는 scratch 결과 보여줘도 분노. **빌드 결과 형편없으면 즉시 삭제 후 재빌드**, 사용자에게 형편없는 결과 절대 보여주지 말 것.

### 36. ⚠️ 와이어프레임 UI 요소는 모두 유지 — 임의 누락 금지
- **사용자 정책 (2026-05-01)**: "와이어프레임에 UI 요소를 빼지 마. 금액/월/기간 조정하는 거 왜 빼냐."
- **올바른 절차**:
  - 와이어프레임의 모든 UI 요소(stepper, slider, filter, pill, button, badge 등)를 **완전 보존**해서 디자인에 포함
  - 위계 부여, 시각 강조, DS 컴포넌트 사용 등은 **추가 작업**이지 UI 제거가 아님
  - 와이어프레임 단순화는 **사용자가 명시 요청한 경우만**
- **금지**:
  - "위계 부여를 위해 단순화" 명목으로 UI 제거
  - "디자인 정리"를 위해 stepper/slider 통합/제거
  - "추천 카드라서 사용자 입력 불필요"라며 stepper 빼기 — 와이어프레임에 있으면 유지

### 35. ⚠️ 위계는 한 단계씩만 — primary → secondary → tertiary → quaternary 점프 금지
- **사용자 정책 (2026-05-01)**: "기본적으로 bg-primary 위에 바로 bg-quaternary가 올라올 수 없다."
- **올바른 위계 흐름**:
  - root `bg-primary` (#ffffff) → 직계 자식 카드 = `bg-secondary` (#f3f4f6)
  - `bg-secondary` 카드 → 그 안 sub-card = `bg-tertiary` (#e6e8ea)
  - `bg-tertiary` sub-card → 그 안 강조 셀 = `bg-quaternary` (#d2d6db)
  - **각 단계는 정확히 한 칸씩**. 두 칸 이상 점프 절대 금지.
- **금지 예시**:
  - root white → 카드 `bg-quaternary` (#d2d6db) ❌ — 두 칸 점프
  - `bg-secondary` 카드 → 그 안 셀 `bg-quaternary` ❌ — 한 칸 (tertiary) 건너뜀
  - `bg-tertiary` 셀 → 그 안 inner sub `bg-secondary` ❌ — 위계 거꾸로
- **자동 검증 필요**: `_apply_bg_hierarchy`가 depth 잘못 계산하면 위계 점프 발생 가능. 빌드 후 노드 walk + 부모 fill과 자식 fill 차이가 두 단계 이상이면 즉시 정정.
- **카드 위 add-button/avatar의 fill**: 부모 카드 위에 떠있는 sub-element는 부모보다 **어두운 색** (한 단계 아래). 흰색 동그라미를 secondary 카드 위에 올리는 것은 위계 거꾸로.

### 34. ⚠️ DS 컴포넌트 인스턴스 우선 — raw frame으로 시뮬레이션 절대 금지
- **사용자 정책 (2026-05-01)**: "디자인 시스템 다 만들었고 컴포넌트도 만들었는데 하나도 사용을 안 하네??"
- **올바른 접근**:
  1. PRD/와이어프레임 분석 시 **각 UI 요소를 DS 컴포넌트와 매칭**:
     - 버튼 → `Buttons / Action button` (variant: primary/secondary/tertiary/outline/ghost)
     - 배지 → `Badges` (color, size, type, icon)
     - 태그/Pill → `Tags`
     - 입력 → `Inputs`
     - 슬라이더 → `Sliders`
     - 스테퍼 → `Inputs/Stepper` 또는 별도 컴포넌트
     - 아바타 → `Avatars` / `AvatarGroup`
     - 탭 → `Tabs` (button-brand / underline / button-gray etc.)
     - Progress bar → `Progress indicators / Progress Bar`
     - Modal → `Modal`
     - Alert → `Alerts`
     - Date picker → `Date pickers`
  2. Blueprint에 **`type: "instance"` + `componentKey: "..."`** 명시:
     ```json
     {
       "name": "Primary Button",
       "type": "instance",
       "componentKey": "<DS component key>",
       "instanceProperties": { "variant": "primary", "size": "md", "label": "참여하기" }
     }
     ```
  3. 컴포넌트 키 조회: `mcp__figma-tools__get_remote_components` 또는 `get_local_components` 또는 `lookup_component_docs`로 검색
  4. DS에 없는 unique한 요소만 frame raw로 작성
- **DS 카탈로그 위치**:
  - `ds/DS_COMPONENT_DOCS.json` — 프로젝트의 컴포넌트 카탈로그
  - `https://twavetech-frontend.github.io/design-system-docs/components/*` — 변형/prop 문서
  - Figma 라이브러리: imin Design System file (현재 `SsgiLsXVMkf0wv8OhRGwks`)
- **금지**:
  - DS 컴포넌트가 있는데 frame + text로 시뮬레이션 (예: Button, Pill, Stepper, Avatar)
  - "스타일만 카피"로 raw 작성 — DS 컴포넌트의 variant/state/prop 모두 무시됨
  - DS 컴포넌트 카탈로그 미확인 빌드 — 매 빌드 시작 전 카탈로그 확인 필수

### 33. ⚠️ 와이어프레임 = 정보 구조 추출 용 — 레이아웃 그대로 베끼지 말 것
- **사용자 정책 (2026-05-01)**: "와이어프레임은 정보 구조 파악 용도지 레이아웃을 그대로 똑같이 할 필요 없어. 이럴거면 디자인을 할 이유가 없잖아."
- **올바른 절차 (와이어프레임 → 디자인)**:
  1. 와이어프레임에서 **정보 구조만 추출**: 어떤 데이터, 어떤 흐름, 어떤 사용자 의사결정이 필요한가?
  2. **위계/우선순위 재해석**: 가장 중요한 1개는 brand-bg 카드(Premium CTA), 나머지는 secondary card. 동일 반복 카드 3개 → 위계 차이 부여.
  3. **imin DS 검증된 섹션 deepcopy** (룰 #23): imin-home/blueprint.json의 SummaryCard, Premium CTA Card, Stage Card 등을 베이스로
  4. 와이어프레임 텍스트 → 정보 구조에 맞게 매핑
  5. 와이어프레임에 없던 시각 디테일(텍스트 위계, 컬러 강조, alpha-white sub-component 등)은 룰 #28~#32 적용
- **금지**:
  - 와이어프레임의 회색 placeholder를 그대로 회색 박스로 빌드 (DS 토큰 무시)
  - 와이어프레임의 좌표/크기/위치를 1:1로 따라가기 (디자인 의미 사라짐)
  - 동일 반복 카드 3개를 동일 디자인으로 — 위계/강조 차이 부여 필수
  - "와이어프레임 그대로 빌드" 사고: 디자인 = 정보 구조 + 시각 위계 + DS 패턴 적용. 셋 다 있어야.
- **사용자 분노 트리거 패턴**:
  - "와이어프레임 분석" 요청 → 그대로 회색 박스 빌드 (룰 #33 위반)
  - 동일 반복 섹션 → 동일 디자인 (위계 부재)
  - imin-home 같은 레퍼런스를 무시하고 scratch 작성

### 32. ⚠️ Progress Bar — Track + Fill 컬러 패턴
- **사용자 수정 레퍼런스 v2 (2026-05-01)** Figma `16941:51390` (Limit Card 안 Progress).
- **Progress Track**: `bg-tertiary` (`#e6e8ea`) — 카드 위에 떠 있는 트랙
- **Progress Fill**: brand solid `#7700ff` (`#70f`) — 강조 색
- **높이**: 8px, cornerRadius 999 (pill)
- **Fill width 계산**: `track_width × (current/total)` — 정확한 비율
- **금지**:
  - Track을 white solid로 (대비 사라짐)
  - Fill을 alpha-purple로 (단단한 brand-solid가 정답)

---

## 빌드 후 자동 후처리 파이프라인

`figma_mcp_client.py build` 호출 시 자동 실행 순서:

1. **Step 0 — Sanitize** (`blueprint_sanitizer.sanitize_blueprint`): letterSpacing/hex/textAutoResize/iconNames + transparent placeholder fill 제거 + _Primitives raw → 시멘틱 raw remap
2. **batch_build_screen** (plugin)
3. **post-fix 1차** (`cmd_post_fix(run_token_bind=False)`)
4. **post-fix 2차** (`cmd_post_fix(run_token_bind=True)`):
   - step 1: 노드 트리 수집
   - step 2: FILL 사이징 검증/수정 (FRAME 자식 → FILL)
   - step 3: Tab Bar/FAB 배치 + 섹션 갭 조정
   - step 4: Tab Bar item FILL + individual stroke
   - step 5: zero-width 텍스트 수정
   - step 6: Stroke INSIDE 정렬 강제
   - step 7: 가로 스크롤 Peek 검증
   - step 8: Status Bar bg를 NavBar fill과 매칭
   - **step 8.5: Screen background normalization** — root + 직계 wrapper → bg-primary
   - **step 8.6: bg-* depth hierarchy** — depth 2/3/4 → secondary/tertiary/quaternary (부모 white일 때만)
   - **step 8.7: Icon wrapper fill clear** — VECTOR-only 자식의 작은 frame fill 제거
   - **step 9: Semantic Token Binding Sweep** (allow-list = Color modes only, deny = disabled/hover, sort = plain > modifier, primary > secondary > ...)
5. 이미지 생성 (`imageGen` 필드 있을 시)
6. NavBar 로고 인스턴스 교체

---

## 빌드 보고 형식 (사용자 응답)

빌드 후 사용자에게 보고할 때 반드시 포함:

```
✅ 빌드 완료 — root: <nodeId> (<width>x<height>)
- Token 바인딩: colors=N numbers=M text=K effects=E
- unmapped: <count>개 (detail: /tmp/unmapped-tokens-<rootId>.json)
- 위계 적용: <count>건 (depth 2/3/4)
- icon wrapper clear: <count>건
- Status Bar bg 매칭: OK / skip
```

binding 카운트가 0이거나 skip된 경우 사유와 조치 함께 보고.
