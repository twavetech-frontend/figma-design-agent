# Design Rules

> **디자인 생성 전 반드시 읽기: 기본 빌드 규칙 (MUST READ FIRST)**

## 기본 빌드 규칙 (디자인 생성 시 첫 번째로 적용)

아래 규칙은 **모든 디자인 생성/수정 시** 기본으로 적용한다. 위반하면 QA에서 반드시 실패한다.

### ⚠️ 룰 0: 와이어프레임 1:1 복제 금지 + 색상 절제 (사용자 명시 2026-05-18, 색상 2026-05-22 갱신)
> 가장 자주 지적받는 품질 문제. 와이어프레임을 입력으로 받아도 결과가 와이어프레임처럼 보이면 실패다.

- **와이어프레임/PRD는 콘텐츠·정보 구조의 source일 뿐, 시각 레이아웃 청사진이 아니다.** 평면 배치(인라인 텍스트 나열, 단색 박스, 균일 카드)를 그대로 옮기지 말 것.
- **시각 위계 재구성 필수**:
  - 핵심 수치 → 히어로 크기 (인라인 문장 → 큰 숫자 블록, 28px+ Bold)
  - 정보 → 카드·통계 미니블록으로 그룹화 (나열 금지)
  - 반복 요소 → 차등화 (1순위/강조 카드는 보더·그림자·랭크 뱃지로 구분)
- **색상 — 절제된 단일 액센트 + 폴리시** (2026-05-23 갱신): 브랜드 컬러를 앱의 단일 일관 액센트로 의도된 여러 지점(주 액션·active 탭/네비·핵심 수치·중요 링크/아이콘)에 사용. 피드백(상태) 컬러는 미납·완료 등 진짜 상태 정보에만 소량·차분하게. 입체감(카드 그림자)·도형-배경 대비·타이포 위계로 폴리시 — 평면 그레이 박스만 나열하면 와이어프레임처럼 보임(금지). 자세히는 아래 '컬러' 규칙 참조.
- 와이어프레임 = "무엇을", 에이전트 = "어떻게 보여줄지". "와이어프레임이랑 똑같다" 피드백 = 실패.

### ⚠️ 룰 0-B: 매 디자인은 새로 분석 — 이전 블루프린트/생성기 재사용 금지 (사용자 명시 2026-05-18)
- 디자인 생성 요청 시 이전 폴리시드 블루프린트(`blueprint_*.json`)나 생성기 스크립트(`gen_*.py`)를 그대로 재실행하지 말 것.
- 같은 와이어프레임이라도 **매번 처음부터 재분석** — 콘텐츠 추출 → reference 검색 → 시각 위계 재구성 → 새 블루프린트 직접 저작.
- 이전 결과물은 참고만 가능, 복사·재실행 금지.

### 디자인 생성 전 필수 실행 스텝 (MANDATORY PRE-BUILD)
> 이 스텝을 건너뛰면 잘못된 색상, 깨진 레이아웃이 생성된다. **스킵 절대 금지.**

1. **DS 토큰 동기화**: `bash scripts/sync-tokens-from-github.sh` 실행 (디자인 생성 요청마다 매번)

### Blueprint 컬러 규칙 — $token() 참조 필수 (RGBA 하드코딩 절대 금지)
> **블루프린트 JSON에 RGBA 값을 직접 넣지 마라.** 토큰 이름으로 참조하면 빌드 시 TOKEN_MAP.json에서 최신값으로 자동 resolve된다.

- **사용법**: `fill`, `fontColor`, `iconColor`, `stroke` 등 컬러 필드에 `"$token(토큰이름)"` 사용
- ⚠️ **컬러 필드별 토큰 컬렉션 (필수 — 위반하면 바인딩이 잘못된 변수로 연결됨)**:
  - **`fontColor` (텍스트 색상)** → 반드시 `Colors/Text/`의 **`text-*`** 토큰 (`text-primary`, `text-secondary`, `text-tertiary`, `text-brand-primary`, `text-success-primary` 등). **`fg-*` 절대 금지**
  - **`iconColor` (아이콘 색상)** → `Colors/Foreground/`의 **`fg-*`** 토큰
  - **`fill` (배경)** → `Colors/Background/`의 **`bg-*`** 토큰
  - **`stroke` (보더)** → `Colors/Border/`의 **`border-*`** 토큰
- **예시**:
  ```json
  {"fill": "$token(bg-brand-solid)"}
  {"fontColor": "$token(text-brand-primary)"}
  {"iconColor": "$token(fg-primary)"}
  {"stroke": "$token(border-secondary)"}
  {"fill": {"r": 1, "g": 1, "b": 1, "a": 1}}   ← 흰색/검정 등 기본색만 직접 RGBA 허용
  ```
- **resolve 흐름**: `figma_mcp_client.py build` 실행 → `$token()` 발견 → `TOKEN_MAP.json`에서 hex 조회 → RGBA 변환 → 빌드
- **토큰 이름**: `DESIGN_TOKENS.md`의 토큰 이름 사용 (예: `bg-brand-solid`, `fg-primary`, `border-secondary`)
- **직접 RGBA 허용 케이스**: 순수 흰색 `{r:1,g:1,b:1,a:1}`, 순수 검정 `{r:0,g:0,b:0,a:1}`, 투명 `{r:0,g:0,b:0,a:0}` 등 DS 토큰이 아닌 기본색만
- **이 규칙을 위반하면**: 토큰 변경 시 디자인에 이전 컬러가 남아 불일치 발생

### 빌드 규칙
1. **부모 프레임에 배경색이 있으면 자식 레이아웃 프레임은 투명** — Card Top, Card Tags, Title Group 등 순수 레이아웃 프레임에 fill 넣지 않기. 태그/버튼/아바타 등 의도적 시각 구분 요소만 fill 허용
2. **리스트 아이템의 아이콘-텍스트 간격 최소 12px** — HORIZONTAL auto-layout의 `itemSpacing`을 12~16px로 설정. 아이콘과 텍스트가 붙어 보이면 안 됨
3. **FAB는 Tab Bar 위 최소 16px 간격** — `FAB.y = TabBar.y - FAB.height - 16`
    > **섹션 간 간격 24px 균일 (필수)** — 루트 프레임 직접 자식인 콘텐츠 섹션(Hero Section, Recommended Stages, Fun Section, Daily Tasks 등) 사이 간격은 **일관되게 24px**. 예외: NavBar↔Ribbon↔Hero는 0px 밀착, FAB↔TabBar는 16px. 빌드 후 반드시 각 섹션의 y, height를 조회하여 `gap = next.y - (prev.y + prev.h)` 계산으로 검증. 겹침(음수 gap) 절대 금지
4. **Tab Bar 외곽선 없음** — Tab Bar 프레임에 검은/진한 stroke 금지. 필요하면 상단 1px 연한 회색(`#F0F0F1`) stroke만 허용
5. **Tab Bar 아이템 균등 배분** — 모든 탭 아이템 `layoutSizingHorizontal: "FILL"`, `layoutMode: "VERTICAL"`, `counterAxisAlignItems: "CENTER"`, `primaryAxisAlignItems: "CENTER"`, `itemSpacing: 4`
6. **아이콘은 SVG로 렌더링 확인** — `batch_build_screen` 후 `_fallback: true`인 아이콘 프레임은 반드시 수정. SVG가 없으면 직접 `type: "svg_icon"` + `svgData`로 삽입
7. **Tab Bar / FAB는 root 직접 자식 + ABSOLUTE** — Content 프레임 안에 넣지 않는다. root 하단에 ABSOLUTE 포지셔닝
8. **SPACE_BETWEEN + FILL 자식 금지 / HORIZONTAL FILL이 itemSpacing을 삼키는 문제** — HORIZONTAL auto-layout에서 `primaryAxisAlignItems: "SPACE_BETWEEN"`과 자식 `layoutSizingHorizontal: "FILL"`을 동시에 사용하면 간격이 0이 됨. FILL 자식이 있으면 `primaryAxisAlignItems: "MIN"`으로 설정하고 `itemSpacing`으로 고정 간격 지정. **추가**: HORIZONTAL 부모에서 자식 중 하나라도 `layoutSizingHorizontal: "FILL"`이면 그 자식이 남은 공간을 전부 차지하여 `itemSpacing`이 시각적으로 사라짐 (0px 간격). 배너/리스트 등 아이콘+텍스트+chevron 행에서 텍스트 프레임을 FILL로 설정하면 아이콘·chevron과 붙어버림 → **텍스트 프레임은 HUG로 설정**하고 `itemSpacing`으로 간격 확보할 것
9. **blueprint에 FILL이 필요한 프레임은 반드시 명시적 width도 함께 설정** — `layoutSizingHorizontal: "FILL"`만으로는 code.js 빌드 후 루트 auto-layout 제거 시 width가 HUG로 축소됨. 안전장치로 `width: 353` (부모 inner width) 등 명시적 크기 병행 설정
10. **빌드 후 프로그래밍적 QA 필수** — 스크린샷만으로 QA하지 말 것. `get_node_info`로 주요 섹션의 실제 width, height를 확인하고 rootWidth(393)와 비교. width < 393*0.9인 full-width 섹션은 즉시 수정
11. **텍스트 중요도에 따라 fontWeight 차등 적용 (필수)** — 모든 텍스트가 동일 weight면 시각적 위계가 없어 가독성이 떨어짐. 아래 기준 준수:
    - **섹션 타이틀** (추천! 스테이지, 놓칠 수 없는 즐거움 등): **Bold**
    - **카드 핵심 정보** (금액, 이름, CTA 라벨): **Bold** 또는 **SemiBold**
    - **카드 보조 정보** (이율, 기간, 탭 라벨): **Medium**
    - **설명/부제목** (서브타이틀, 캡션): **Regular**
    - **절대 금지**: 화면 전체를 Regular 또는 Medium 하나로 통일하는 것
12. **정보성 리본/띠 배너는 저대비 스타일 필수** — 누적 거래 건수, 공지사항 한 줄 등 보조 정보를 표시하는 얇은 리본(띠 배너)에 `bg-brand-section`(짙은 보라) 같은 고대비 배경을 사용하면 NavBar/히어로와 시각적으로 충돌하여 화면이 산만해짐. 반드시 **연한 배경 + 중간 톤 텍스트** 조합 사용:
    - **배경**: `$token(bg-brand-primary)` (연한 보라 #f4f3ff) 또는 `$token(bg-secondary)` (연한 회색 #fafafa)
    - **텍스트**: `$token(fg-tertiary)` (회색 #535862) 또는 `$token(fg-secondary)` (진한 회색 #414651)
    - **아이콘**: `$token(fg-brand-primary)` (브랜드 보라 #6938ef) — 텍스트보다 살짝 강조
    - **절대 금지**: 리본에 `bg-brand-section`, `bg-brand-solid` 등 짙은 배경 + 흰색 텍스트 조합. 이 스타일은 히어로 배너 전용
13. **Tag/Chip/Badge는 반드시 width: HUG** — 태그, 칩, 배지, 인디케이터 등 라벨 컨테이너는 **예외 없이** `layoutSizingHorizontal: "HUG"` 사용. FILL이 되면 부모 너비 전체로 늘어나 디자인이 깨짐. 히어로 배너 내부 태그(EVENT 등), 이율 태그, 보너스 태그, 탭 필터, 카루셀 인디케이터 모두 해당. Blueprint에서 태그/칩 프레임에 `layoutSizingHorizontal`을 명시하지 않거나 `"FILL"`로 설정하는 것은 금지
14. **섹션 내 탭 메뉴는 DS Tabs 컴포넌트(Underline) 스타일 사용** — 추천 스테이지 등 섹션 내 필터/탭 전환 UI는 pill/버튼 스타일이 아닌 **Underline 스타일** 적용. DS 참조: `https://twavetech-frontend.github.io/design-system-docs/components/tabs`
    - **Tab Row (컨테이너)**: HORIZONTAL auto-layout, `itemSpacing: 8`, 배경 fill 없음(투명), **하단 stroke 1px `$token(border-secondary)` (inside)** — 전체 너비에 걸친 회색 베이스라인 역할. `layoutSizingHorizontal: "FILL"` (부모 너비 채움)
    - **Active 탭**: VERTICAL auto-layout, HUG×HUG, padding `T4/B0/L4/R4`, `itemSpacing: 8`, 배경 투명, cornerRadius 0. 자식: ① 텍스트 `$token(fg-brand-primary)` + fontWeight 600(SemiBold) ② Underline bar (height 2px, `layoutSizingHorizontal: "FILL"`, brand 컬러 fill `$token(bg-brand-solid)`)
    - **Inactive 탭**: VERTICAL auto-layout, HUG×FILL (세로 FILL — Active 탭 높이에 맞춰 베이스라인 정렬), padding `T4/B0/L4/R4`, 배경 투명, cornerRadius 0. 자식: 텍스트 `$token(fg-tertiary)` + fontWeight 500(Medium), 언더라인 없음
    - **베이스라인 원리**: Tab Row의 하단 stroke가 전체 너비 회색 선을 그리고, Active 탭의 2px 언더라인 bar가 그 위에 겹쳐서 brand 컬러로 활성 탭을 표시. Inactive 탭은 `layoutSizingVertical: "FILL"`로 Active 탭과 동일 높이를 유지하여 베이스라인 정렬
    - **절대 금지**: pill 형태(cornerRadius 20 + 배경 fill) 탭을 섹션 내 필터로 사용하는 것. Pill 탭은 상단 네비게이션 전용
15. **배너형 CTA 카드(아이콘+텍스트+chevron 행)는 padding 16, spacing 16** — 계산기 배너, 프로모션 배너 등 아이콘+텍스트그룹+chevron을 한 줄로 배치하는 카드형 CTA는: `HORIZONTAL`, `SPACE_BETWEEN`, `CENTER`, **padding 16(전방향)**, **itemSpacing 16**, `cornerRadius: 16`. 텍스트 그룹은 반드시 `HUG` (FILL 금지 — rule 8 참조)
16. **그림자(DROP_SHADOW) 카드는 부모 안에 그림자 여백 확보 (R42 자동 강제)** — 그림자 달린 카드/프레임은 부모 autoLayout 의 padding·itemSpacing 이 그림자 extent(`radius + spread + |offset|`, 보통 ~12px) 이상이어야 한다. 안 그러면 그림자가 인접 섹션의 불투명 배경에 덮여 잘려 보인다. **섹션 래퍼 `paddingBottom: 0` 금지** — 그림자 카드를 담으면 ≥ 그림자 extent. `R42` inject 가 빌드 전 자동 보정 + 조상 `clipsContent` 해제(가로 캐로셀 제외).
17. **부모와 같은 색으로 채운 레이아웃 래퍼 프레임은 fill 제거 (R43 자동 강제)** — root 가 `bg-primary` 인데 그 위 섹션 래퍼도 `bg-primary` 로 채우면 중복이다. cornerRadius/stroke/effects 없는 순수 레이아웃 프레임은 부모와 같은 색이면 fill 을 넣지 말 것(투명 → 부모 배경이 비침). 카드(cornerRadius·stroke·그림자 중 하나라도 있음)는 독립 표면이므로 같은 색이라도 유지. `R43` inject 가 중복 fill 자동 제거.
18. **카드 표면 = bg-primary + 보더 (2026-05-23 룰, `_enforce_card_surface` 자동 강제)** — 루트 위 최상위 카드는 `$token(bg-primary)` fill + `$token(border-secondary)` 1px 보더로 표면을 정의한다. `bg-secondary`(회색)로 채우지 말 것 — 흰 카드를 보더 + (자동 주입되는) subtle shadow 로 구분한다. 카드 안의 인셋·서브카드(`bg-secondary`/`bg-tertiary`)와 브랜드 컬러 카드는 대상 아님. **예외 — 맨 아래 Footer는 `bg-secondary` fill + 보더·그림자 없음**(페이지를 닫는 회색 띠, 카드 아님). `cmd_build` 의 `_enforce_card_surface` 가 최상위 그레이 카드 + Footer 를 자동 교정한다.
19. **타이포 위계 = 크기·굵기 차이로 시각 리듬 (2026-05-23 룰, `_enforce_text_hierarchy` 자동 승격)** — 컬러가 절제될수록 위계는 폰트 크기·굵기로 만든다. 표준 type scale: HERO(카드 핵심 금액·수치) `28~36px Bold` / TITLE `22~26px Bold` / SECTION 헤더 `17~19px Bold` / BODY `14~16px Medium·SemiBold` / CAPTION `11~13px Medium·Regular fg-tertiary`. 같은 카드 안에 최소 3단계 이상 차이를 두고, HERO는 BODY의 2배 안팎. `cmd_build`의 `_enforce_text_hierarchy` 가 카드 안의 통화 hero(부호 `+/−` 또는 천단위 콤마 금액)를 30px Bold 로 자동 승격한다.
20. **Modal 화면 패턴 (2026-05-24 룰, `_enforce_modal_pattern` 자동 강제)** — Full modal(홈 위로 슬라이드업되는 단일 화면)은 **상단 X 닫기 버튼만** 두고, 로고·알림·채팅 등 nav 아이콘 없음, **Footer 없음 · Tab Bar 없음 · 상단 Tab 메뉴 없음**. Blueprint root 에 `"_screenType": "modal"` 명시 시 `cmd_build` 의 `_enforce_modal_pattern` 이 Footer/Tab Bar/상단 탭(`Tab Row`/`Top Tab`/`Section Tab`)/non-X nav 아이콘 노드를 자동 제거하고 NavBar 를 우측 정렬한다.
21. **정보 그룹 divider (2026-05-24 룰, `_enforce_section_dividers` 자동 삽입)** — 컬러가 절제되면 섹션 경계가 흐려진다. 타이틀 섹션과 서브 섹션, 서브 섹션끼리 사이에 **1px `border-secondary` divider** 를 두되 **위·아래 padding 20px** 으로 콘텐츠와 띄워서 표시한다(라인이 콘텐츠에 딱 붙으면 답답). `cmd_build` 의 `_enforce_section_dividers` 가 blueprint 루트의 직계 콘텐츠 섹션 사이에 `Section Divider` 컨테이너(VERTICAL, `paddingTop/Bottom: 20`, 투명 fill) + 내부 `Divider Line` 자식(FILL 가로, height 1, `fill: $token(border-secondary)`) 을 자동 삽입. Status Bar / NavBar / Bottom Action Bar / Tab Bar / Footer 같은 utility 프레임 사이에는 넣지 않는다. 재실행 안전.
22. **루트 minHeight=852 + 하단 바 bottom-pin (2026-05-24 룰, `_enforce_root_min_height` 자동 강제)** — 루트 프레임 **min height = 852** (iPhone 16 뷰포트). 콘텐츠가 늘면 따라서 늘어남. 콘텐츠 합이 852 보다 짧을 때 화면에 고정된 하단 바(Bottom Action Bar / Tab Bar / CTA Bar / FAB) 는 **루트 하단(y = 852 - bar.height)** 에 bottom-align — 콘텐츠 끝에 떠서 붙지 않게 한다. `cmd_post_fix` 의 `_enforce_root_min_height` 가 루트 높이 < 852 일 때 852 로 늘리고, 이름에 `tab bar`/`tabbar`/`bottom action bar`/`action bar`/`cta bar`/`fab` 포함된 자식을 ABSOLUTE + bottom constraint MAX 로 재배치한다. 콘텐츠가 852 이상이면 손대지 않음.
23. **하단 CTA = DS Action Button 인스턴스 우선 (2026-05-24 룰, R23 + `detect_button_shape` 자동 swap)** — Bottom Action Bar 의 Primary CTA / Submit Button 류는 **항상 DS `Action Button` 컴포넌트 인스턴스**로 만든다. raw frame 금지. DS 로 표현이 안 되는 특수 케이스에만 직접 그림. 사용 키: `Action Button md/sm Primary/Secondary/Tertiary/Outline/Ghost` (catalog `ds_catalog.py`). 대형 CTA = `Size: lg`, 비활성 = `State: Disabled` (variant 로 적용). 라벨은 `componentProperties` text override, 아이콘 토글(`⬅️ Icon leading` / `➡️ Icon trailing`) 기본 false. R23 inject 의 `detect_button_shape` 가 raw button frame 자동 swap; 2026-05-24 — name 에 `cta`/`button`/`submit` 포함 시 layoutMode 무관 인정 (VERTICAL CTA 도 잡힘). catalog 미스 시 build ERROR.

---

## 컴포넌트 복제 규칙 (clone_node vs create_component_instance)
- **마스터 컴포넌트를 `clone_node`하면 마스터가 복제된다** — 인스턴스가 아닌 또 다른 마스터 컴포넌트가 생성됨
- **인스턴스를 만들려면 반드시 `create_component_instance(componentKey)`를 사용** → `insert_child`로 원하는 부모에 배치
- `clone_node`는 **인스턴스 노드를 복제**할 때만 사용 가능 (인스턴스를 clone하면 인스턴스가 복제됨)
- 마스터 컴포넌트의 key는 `get_local_components`로 조회 가능
- Status Bar 등 이미 인스턴스인 노드는 `clone_node`로 복제해도 인스턴스가 유지됨

## ⚠️ Status Bar는 blueprint에 넣지 말 것 — 빌드가 자동 삽입
- **Status Bar를 텍스트/프레임으로 직접 그리거나 blueprint에 노드로 넣지 말 것.**
- `batch_build_screen`은 blueprint에 status bar 노드가 없으면 **DS "Status Bar" 인스턴스를 루트 첫 자식으로 자동 삽입**한다. blueprint에 status bar를 넣으면 빌드가 그걸 사용 → 직접 그린 게 박힘(= 버그).
- 로고: NavBar에 `"Logo Placeholder"` 프레임을 넣으면 `cmd_build`가 DS 로고 인스턴스로 자동 교체(Step G).
- "Styles" 페이지(`276:1882`)에 마스터 인스턴스 존재 — Status Bar `279:4758`, 로고 `279:4757` (자동 삽입이 안 되는 특수 상황에서만 `clone_node`로 수동 삽입)
- 자세한 내용은 CLAUDE.md "디자인 생성 필수 규칙 1" 참조

## Root Frame
- 루트 프레임(스크린)은 **Auto Layout을 사용하지 않는다** — 자식 요소는 절대 좌표로 배치
- `batch_build_screen` 사용 시에도 루트에 `autoLayout` 설정 금지
- **내용이 길어질 경우 루트 프레임 height를 미리 충분히 늘려서** UI 생성 및 배치 — 콘텐츠가 프레임 밖으로 잘리지 않도록 사전에 여유 확보 후, 완성 후 적절히 조정
- **새 화면 생성 시 기존 프레임 삭제 금지** — 캔버스에 이미 존재하는 프레임을 절대 삭제하지 않는다. 새 화면은 기존 프레임의 **오른쪽**에 생성할 것

## NavBar 로고 (필수)
- **NavBar 로고는 반드시 icons 페이지의 logo 컴포넌트(`64:1449`)를 인스턴스로 생성**해서 사용할 것
- 텍스트 노드로 "imin" 로고를 직접 만들지 않는다
- **`clone_node` 사용 금지** — 마스터 컴포넌트를 `clone_node`하면 마스터가 복제되어 의도치 않은 마스터 컴포넌트가 생김
- 절차: `create_component_instance(componentKey="957912b03baf924a48ef83424ed66f22a4a386a8")` → `insert_child(parentId=navBarId, childId=인스턴스ID, index=0)` — NavBar의 첫 번째 자식으로 배치

## 버튼/CTA 컴포넌트 인스턴스 필수
- 버튼은 반드시 DS `Buttons/Button` 컴포넌트 인스턴스를 사용 — 프레임+텍스트로 수동 구성 금지
- **CTA 버튼**: `Size=xl, Hierarchy=Primary, State=Default, Icon only=False` (componentKey: `90cc91183f75975cc066f2fc156babfdad1c6937`)
- **일반 버튼 (Large)**: `Size=lg, Hierarchy=Primary, State=Default, Icon only=False` (componentKey: `e31817b31fc5241395325fe519bba29c306c9d5e`)
- **일반 버튼 (Medium)**: `Size=md, Hierarchy=Primary, State=Default, Icon only=False` (componentKey: `db2280e1aaa99563769a7d0fce59dfcde7a39b09`)
- **Secondary 버튼**: `Size=md, Hierarchy=Secondary, State=Default, Icon only=False` (componentKey: `10d012c26a93c7623d06`)
- 텍스트 변경: `textOverrides` 또는 `set_text_content`로 인스턴스 내부 텍스트 노드(name="Text") 수정
- `batch_build_screen`에서 `type: "instance"` + `componentKey` 사용
- **아이콘 표시 규칙** (Button 인스턴스 속성):
  - `⬅️ Icon leading#3287:1577` (BOOLEAN): leading 아이콘 표시 여부
  - `➡️ Icon trailing#3287:2338` (BOOLEAN): trailing 아이콘 표시 여부
  - `🔀 Icon leading swap#3466:91` (INSTANCE_SWAP): leading 아이콘 컴포넌트 교체
  - `🔀 Icon trailing swap#3466:852` (INSTANCE_SWAP): trailing 아이콘 컴포넌트 교체
  - **CTA 버튼**: leading/trailing 모두 `false` — 텍스트 전용이 가장 깔끔 (핀테크 표준)
  - **네비게이션 버튼**: trailing만 `true` + chevron-right 아이콘
  - **아이콘 첨부 버튼**: leading만 `true` + 해당 아이콘
  - **주의**: INSTANCE_SWAP에 리모트 라이브러리 아이콘 ID(`17:xxxx`)는 직접 사용 불가 — 로컬 컴포넌트 ID만 가능

## Auto Layout (루트 하위 모든 컴포넌트에 필수)
- 루트 프레임의 직접 자식 섹션 (NavBar, 카드, 섹션 등)과 그 하위 모든 컴포넌트에 **Auto Layout 필수 적용**
- 방향별 기준:
  - **NavBar**: HORIZONTAL, primaryAxis=SPACE_BETWEEN, counterAxis=CENTER, paddingLeft/Right=16, height 고정
  - **섹션 카드 (수직 나열)**: VERTICAL, paddingTop/Bottom=20, paddingLeft/Right=20, gap 적절히
  - **행(Row) / 버튼 / 태그**: HORIZONTAL, counterAxis=CENTER, gap 적절히
  - **테이블 행**: HORIZONTAL, primaryAxis=SPACE_BETWEEN, counterAxis=CENTER, paddingLeft/Right=8
- `batch_build_screen`에서 `autoLayout` 속성으로 설정하거나, 생성 후 `set_auto_layout`으로 적용

## Typography
- 모든 텍스트는 기본 폰트 **Pretendard** 사용 — 디자이너의 특별한 요청이 없는 한 예외 없음
- `create_text`, `batch_build_screen` 등으로 텍스트 생성 시 반드시 Pretendard 폰트 적용
- **섹션 타이틀은 반드시 Bold** — "추천! 스테이지", "놓칠 수 없는 즐거움" 등 섹션 헤더 텍스트는 `fontName: {family: "Pretendard", style: "Bold"}` 필수. Regular/Medium 금지

## Icons
- 기호(+, ×, ✓, 화살표 등)는 **절대 텍스트로 처리하지 않는다** — 반드시 `ds-1-icons.json`에서 해당 아이콘을 찾아 인스턴스로 삽입
- 아이콘 삽입 방법: icons 페이지에서 해당 아이콘 노드를 `clone_node` → 부모에 `insert_child` → `set_selection_colors`로 색상 적용 → `resize_node`로 크기 조정

## Text
- 텍스트가 프레임 하단에 위치할 때는 **textAlignVertical을 BOTTOM**으로 설정 — 텍스트가 잘려 보이는 것을 방지
- 텍스트 박스 높이는 **언제나 auto height** 사용 — `set_layout_sizing`의 `vertical: "HUG"` 또는 `textAutoResize: "HEIGHT"` 적용
- 텍스트 줄 수 제한 요청 시 → `textAutoResize: "TRUNCATE"` + `maxLines` 설정 (예: "2줄로 제한" → `maxLines: 2`)
- **줄바꿈은 반드시 `<br>` 마커 사용** — `\n`(Enter/paragraph break)은 Figma에서 단락 간격을 추가하므로 금지. `<br>`은 MCP 서버가 자동으로 U+2028(Shift+Enter/line break)로 변환하여 동일 단락 내 줄바꿈을 생성

## Colors
- **커스텀 컬러 절대 금지** — 모든 색상은 반드시 `DESIGN_TOKENS.md`에 정의된 DS 토큰만 사용
- fill, stroke, text color 모두 DS 변수로 바인딩할 것 — `set_bound_variables`의 `fills/0`, `strokes/0` 필드 사용
- DS에 정확한 색상이 없으면 가장 가까운 토큰으로 대체 (커스텀 hex 값 사용 금지)
- Primitive 색상(Colors/Blue/500 등)은 라이브러리에 퍼블리시되지 않을 수 있음 → Semantic 토큰(Colors/Background/, Colors/Text/ 등) 또는 Component colors(Component colors/Utility/) 사용
- **Color token은 반드시 DS 전용** — `DESIGN_TOKENS.md`의 Semantic/Component 토큰만 사용. 다른 앱 색상 팔레트나 hex 값을 참고해 직접 적용하는 행위 금지
- **Brand color도 DS 전용** — DS v1의 brand 토큰(`Colors/Background/bg-brand-*`, `Colors/Foreground/fg-brand-*`, `Component colors/Utility/Brand/*` 등)을 그대로 사용. 임의 변형이나 외부 브랜드 색상 대입 금지

### 브랜드 컬러 — $token() 참조 사용 (RGBA 하드코딩 금지)
- **블루프린트에서 브랜드 컬러는 반드시 `$token()` 참조** — `"$token(bg-brand-solid)"`, `"$token(fg-brand-primary)"` 등. RGBA 직접 입력 금지
- **CTA/액션 버튼은 반드시 `$token(bg-brand-solid)` 사용** — 임의 색상 사용 금지
- **Grep으로 hex 조회 후 RGBA 변환은 더 이상 불필요** — `figma_mcp_client.py build`가 자동 resolve

### Brand Color 사용 범위 규칙
- **Brand color는 CTA와 Primary Action 전용** — 버튼, FAB, 강조 링크, active 탭 등 사용자의 핵심 행동을 유도하는 요소에만 사용
- **필터 칩/토글/배지 등 보조 UI에는 brand color 사용 금지** — 뉴트럴 다크(Gray-700 #344054 등) 또는 outline 스타일 사용. 필터 옵션은 CTA가 아님
- **아이콘 명도 대비 4:1 필수** — 색상 배경 위 아이콘은 반드시 흰색(#FFF) 사용. 검정/다크 아이콘을 컬러 배경에 올리면 대비 부족으로 안 보임
- 대비 확인 기준: 짙은 배경(brand, dark gray 등) → 아이콘/텍스트 **흰색**, 연한 배경(gray-50, white 등) → 아이콘/텍스트 **다크**

### 컬러 — 절제된 단일 액센트 + 폴리시 (2026-05-23 갱신)
- **베이스는 뉴트럴 그레이** — 배경 `bg-primary`/`bg-secondary`/`bg-tertiary`, 텍스트 `fg-primary`/`fg-secondary`/`fg-tertiary`, 보더 `border-secondary`. 단, 완전 무채색 평면은 금지.
- **브랜드 컬러 = 앱의 단일 일관 액센트** — 주 액션(CTA)·active 탭/네비·핵심 수치·중요 링크/아이콘 등 의도된 여러 지점에 일관 사용. 거부된 건 "여러 색 난무"이지 브랜드 컬러 자체가 아니다. 모든 카드·태그·통계에 무분별하게 까는 것만 금지.
- **피드백(상태) 컬러는 소량·차분하게** — 미납·완료·주의 등 진짜 상태 정보에만 success/warning/error 계열을 절제된 톤으로 소량. 장식·태그·통계 전반에 색을 까는 건 금지.
- **폴리시 필수 (와이어프레임 탈피)** — 평평한 그레이 박스만 나열하면 와이어프레임처럼 보인다. 카드 그림자/elevation, 흰 카드 ↔ 연한 그레이 면의 도형-배경 대비, 강한 타이포 위계(히어로 수치 크게·Bold)로 "디자인된" 느낌을 만든다. `cmd_build`의 `_enforce_card_elevation`이 그림자 없는 카드에 자동으로 subtle shadow를 주입한다.

---

## ⚠️ 반복 위반 방지 규칙 (CRITICAL — 매번 빌드 후 반드시 검증)

> 아래 5개 규칙은 **매 디자인 생성 시 반복적으로 위반되는** 항목이다. 빌드 후 프로그래밍적으로 검증하고 위반 시 즉시 수정해야 한다.

### R1. 모든 섹션/카드/리스트 프레임은 FILL 가로 사이징 (HUG 절대 금지)
- Blueprint의 모든 FRAME 자식에 `"layoutSizingHorizontal": "FILL"` 명시
- HUG로 두면 텍스트 길이에 따라 너비가 불규칙해짐
- 텍스트 노드(`type: "text"`)와 아이콘 프레임(고정 크기)만 HUG/FIXED 허용
- **검증**: `get_node_info`로 root의 모든 자식/손자 FRAME의 `layoutSizingHorizontal` 확인

### R2. Tab Bar + FAB → ABSOLUTE + 루트 프레임 하단 (콘텐츠 아래)
- `batch_build_screen`은 `layoutPositioning: "ABSOLUTE"`를 적용하지 않음 → **빌드 후 반드시** `set_layout_positioning` 호출
- **모든 콘텐츠가 루트 프레임 안에 보여야 함** — Tab Bar/FAB도 루트 프레임 안에 위치
- 위치 계산:
  1. 마지막 콘텐츠의 bottom (y + height) 구하기
  2. FAB: `y = content_bottom + 24`, `x = 253` (우측)
  3. Tab Bar: `y = FAB_y + 44 + 16`, `x = 0`, `width = 393`
  4. Root height = `Tab Bar_y + 73`
- FAB: pill형 `120×44`, `cornerRadius: 22`
- **검증**: 루트 프레임 높이 안에 모든 요소 포함 확인

### R3. 히어로 배너 → 가로 캐로셀 (HORIZONTAL + clipsContent)
- 히어로 섹션(VERTICAL) → Banner Carousel 래퍼(HORIZONTAL, `clipsContent: true`) → Banner Cards(FIXED 353×162)
- `clipsContent: true`가 없으면 모든 배너가 다 보임
- Blueprint에 캐로셀 래퍼 노드 포함 필수, `batch_build_screen`으로 빌드하면 `clipsContent` 자동 적용
- 배너 카드는 FIXED 사이징 (FILL이면 캐로셀 내에서 줄어듦)

### R4. FAB는 pill 형태 (120×44) — 원형(56×56)은 텍스트 잘림
- FAB에 텍스트가 있으면 pill 형태로 충분한 너비 확보
- 아이콘만 있는 FAB만 원형 허용
- **FAB 컬러**: PRD에 특정 색상 지정 시 해당 색상 사용, 미지정 시 `$token(bg-brand-solid)` — FAB는 가장 중요한 버튼이므로 브랜드 컬러가 기본

### R5. 카드 내 레이블 텍스트 가시성
- 카드 배경이 밝은 색이면 텍스트는 어두운 색(`fg-primary`) + Bold
- 배경색과 텍스트 색이 비슷하면 안 보임 → 스크린샷으로 반드시 확인

---

## Variable Binding (필수)
- 디자인 생성 완료 후 **반드시 마지막 단계에서 DS 변수 바인딩 수행** — 절대 빠뜨리지 말 것
- 바인딩 순서: ① Text Style (`set_text_style_id`) → ② Typography 변수 (fontSize, lineHeight) → ③ Radius 변수 → ④ Color 변수 (fills/0, strokes/0)
- `set_bound_variables`로 바인딩: fontSize, lineHeight, cornerRadius(topLeftRadius 등), padding, itemSpacing, fills/0, strokes/0
- `set_text_style_id`로 Text Style 바인딩 (Style ID 형식: `S:{key},{nodeId}`)
- ⚙️ **자동화 (2026-05-24 복원)** — `cmd_build` 의 Step E.5.5 `_apply_ds_text_styles` 가 매 빌드 시 자동 실행: `get_styles().texts` 의 `(fontSize, weight bucket)` → styleKey 인덱스로 모든 TEXT 노드(인스턴스 내부 `I…;…` 제외)에 `set_text_style_id` 자동 적용. off-scale 사이즈는 ±3px 안 DS 스케일(12/14/16/18/20/24/30/36/48/60/72)로 snap. `batch_set_text_style_id` 는 무응답 사례가 확인돼 단일 호출 루프로 안정 적용한다. 이전(2026-05-22 머지)으로 사라진 기능을 복원한 것.

### ⚠️ TEXT 컬러는 `Colors/Text/text-*` 에 바인딩 (사용자 정책 2026-05-18)
- **TEXT 노드의 fill 컬러는 `fg-*`가 아닌 `Colors/Text/text-*` 토큰에 바인딩한다**
- `text-*`에 해당 컬러가 없으면 `Component colors/Utility/utility-*` 토큰을 fallback으로 사용
- 아이콘(VECTOR)/프레임 배경/보더는 기존대로 `fg-*` / `bg-*` / `border-*` 사용 — 이 규칙은 **텍스트 컬러 전용**
- 코드 강제: `figma_mcp_client.py` 의 `_collect_bindings`가 TEXT fill 매칭 결과를 `_remap_text_token`으로 `fg-→text-` 리맵, 미해당 시 `prefer_class="utility"`로 재매칭. `_auto_classify_black_texts`/`_fix_tab_bar_icon_colors`도 text- 반환
- 기존 빌드 화면 갱신: `python3 scripts/rebind_text_to_text_tokens.py <rootNodeId>` (post-fix sweep은 이미 바인딩된 fill을 스킵하므로 강제 재바인딩 필요)
