# Design Rules

> **디자인 생성 전 반드시 읽기: 기본 빌드 규칙 (MUST READ FIRST)**

## 기본 빌드 규칙 (디자인 생성 시 첫 번째로 적용)

아래 규칙은 **모든 디자인 생성/수정 시** 기본으로 적용한다. 위반하면 QA에서 반드시 실패한다.

### ⚠️ 룰 0: 와이어프레임 1:1 복제 금지 + 컬러 단조로움 금지 (사용자 명시 2026-05-18)
> 가장 자주 지적받는 품질 문제. 와이어프레임을 입력으로 받아도 결과가 와이어프레임처럼 보이면 실패다.

- **와이어프레임/PRD는 콘텐츠·정보 구조의 source일 뿐, 시각 레이아웃 청사진이 아니다.** 평면 배치(인라인 텍스트 나열, 단색 박스, 균일 카드)를 그대로 옮기지 말 것.
- **시각 위계 재구성 필수**:
  - 핵심 수치 → 히어로 크기 (인라인 문장 → 큰 숫자 블록, 28px+ Bold)
  - 정보 → 카드·통계 미니블록으로 그룹화 (나열 금지)
  - 반복 요소 → 차등화 (1순위/강조 카드는 보더·그림자·랭크 뱃지로 구분)
- **컬러 단조로움 금지**: 브랜드 단색 반복 금지. 시맨틱 액센트 2~3색(success 그린·warning 오렌지)을 의미에 맞게 — 태그/뱃지/상태/통계 강조/긍정·부정 지표에 운용.
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
- **예시**:
  ```json
  {"fill": "$token(bg-brand-solid)"}
  {"fontColor": "$token(fg-brand-primary)"}
  {"fill": "$token(bg-brand-section)"}
  {"iconColor": "$token(fg-primary)"}
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

---

## 컴포넌트 복제 규칙 (clone_node vs create_component_instance)
- **마스터 컴포넌트를 `clone_node`하면 마스터가 복제된다** — 인스턴스가 아닌 또 다른 마스터 컴포넌트가 생성됨
- **인스턴스를 만들려면 반드시 `create_component_instance(componentKey)`를 사용** → `insert_child`로 원하는 부모에 배치
- `clone_node`는 **인스턴스 노드를 복제**할 때만 사용 가능 (인스턴스를 clone하면 인스턴스가 복제됨)
- 마스터 컴포넌트의 key는 `get_local_components`로 조회 가능
- Status Bar 등 이미 인스턴스인 노드(`1:3448`)는 `clone_node`로 복제해도 인스턴스가 유지됨

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

## People Photos (Unsplash)
- **사람 얼굴/인물 사진이 필요한 경우 Gemini로 생성하지 않는다** — 반드시 **Unsplash**에서 검색하여 실제 사진을 가져올 것
- 프로필 아바타, 사용자 썸네일, 팀원 소개 등 사람이 등장하는 모든 이미지에 적용
- **사용법**: `https://images.unsplash.com/photo-{ID}?w={size}&h={size}&fit=crop&crop=face` — API 키 불필요
- **검색 URL**: `https://unsplash.com/s/photos/{keyword}` 에서 적절한 이미지 ID 확보
- 다운로드 후 PIL로 리사이즈 (Figma 노드 크기 × 3) → base64로 `set_image_fill` 적용
- 아바타 프레임은 `cornerRadius`를 width/2로 설정하여 원형으로 만들 것
- Gemini는 3D 오브젝트, 일러스트, 배너 그래픽 등 **비사진 그래픽**에만 사용

## Graphics & Illustrations (Gemini 이미지 생성)
- **히어로 이미지 타겟 노드 규칙 (필수):**
  1. Hero Section 안에 **Banner Card 프레임이 있으면** → Banner Card에 `set_image_fill` 적용 (Hero Section 자체에는 이미지 채우지 않음)
  2. Banner Card 프레임이 **없으면** → Hero Section 프레임에 직접 `set_image_fill` 적용
  - 두 프레임 모두에 이미지가 채워지는 일이 절대 없어야 함
- **Banner Card 높이 = 200px 고정** — 히어로 섹션 내 배너 카드는 항상 height=200으로 설정. MIN_HERO_SIZE(200) 우회 불필요
- **히어로 배너 텍스트 width = 배너 폭의 50%** — Banner Card 안의 타이틀/서브타이틀/설명 텍스트는 width를 배너 폭의 50% 이하로 제한 (예: 배너 353px → 텍스트 ~176px). 이미지 그래픽과 텍스트가 겹치지 않도록 좌측 절반에만 텍스트 배치
- **히어로 배너 이미지 레이아웃 규칙 (필수):** Gemini로 히어로 배너 이미지 생성 시, 프롬프트에 **반드시** 다음 조건을 포함:
  - 이미지의 **좌측 절반은 완전히 비워둘 것** — 단색 배경만 허용, 오브젝트/텍스트/장식 일체 금지
  - 모든 3D 오브젝트/그래픽은 **우측 절반에만** 배치
  - 좌측은 텍스트 오버레이 영역이므로, 텍스트 가독성을 해치는 요소가 절대 없어야 함
- **배경 제거 규칙 (필수):**
  - **히어로/배너 이미지**: 배경 유지 (isHero=true, rembg 미적용)
  - **그 외 모든 이미지 (아이콘, 카드 그래픽 등)**: 반드시 **rembg로 배경 제거** → 투명 PNG로 적용. Gemini API 직접 호출 시에도 rembg 파이프라인을 반드시 거칠 것
- **생성 이미지는 반드시 단일 오브젝트** — Gemini로 생성하는 모든 그래픽(3D, 2D 무관)에는 **오브젝트를 딱 하나만** 배치. 여러 오브젝트가 있으면 프레임에 잘리거나 시각적으로 산만해짐. Gemini 프롬프트에 반드시 `"ONLY ONE single object, nothing else"` 포함. 예: 선물 아이콘 → 선물상자 1개만, 계산기 아이콘 → 계산기 1개만
- **기본 3D 아이콘 스타일 = 카카오/쏘카 스타일 (소프트 매트 3D)** — 3D 아이콘/일러스트 생성 시 기본 스타일. `assets/reference-images/icon/` 레퍼런스를 반드시 Gemini API에 함께 전달
  - **Gemini 프롬프트 키워드**: `"3D rendered icon in the style of Korean apps like KakaoTalk and SOCAR. Soft matte finish, NOT glossy, rounded clay-like proportions, warm and friendly. Subtle soft lighting, minimal highlights, smooth surfaces. Chunky compact form. ONLY ONE single object, nothing else. Pure white background. No text. No shadow."`
  - **스타일 특징**: 과한 광택 없음(not too glossy), 부드러운 매트/클레이 질감, 따뜻한 색감, 둥근 비율, 미니멀 하이라이트
  - **레퍼런스**: `assets/reference-images/icon/` 에서 랜덤 2장을 `inlineData`로 전달 필수
  - **후처리**: rembg 배경 제거 → 투명 PNG → `set_image_fill(scaleMode: FIT)` 적용
  - **프레임 설정**: 배경 fill 투명(`a:0`), cornerRadius 0 — 3D 이미지만 보이도록
- **히어로/배너 배경 스타일 = 3D 소프트 매트 (기존 유지)** — 히어로/배너 배경 이미지는 기존 소프트 매트 스타일(Cinema4D, Octane render, matte finish) 유지. 아이콘/일러스트와 배경 이미지의 스타일을 구분
- **2D 스타일 = 토스페이스(Tossface) 이모지 스타일** — 사용자가 2D/flat을 요청한 경우 적용
  - **Gemini 프롬프트 키워드**: `"2D flat emoji icon in the style of Tossface (Toss Korean fintech app emoji). Simple geometric shapes, bold flat colors, minimal details, no gradients, no shadows, no outlines. Cute and friendly expression. Single centered object. Pure white background. No text."`
  - **레퍼런스 이미지 필수**: `assets/reference-images/2d/` 폴더의 토스페이스 PNG + 스크린샷을 Gemini API 호출 시 `inlineData`로 반드시 함께 전달 — 스타일 일관성의 핵심
  - **후처리**: rembg 배경 제거 → 투명 PNG → `set_image_fill(scaleMode: FIT)` 적용
  - **특징**: 완전 플랫 단색, 그라데이션/투명/그림자 금지, 굵은 단순 형태, 귀여운 느낌
- **스타일 레퍼런스 이미지 참조 (필수):** `assets/reference-images/` 폴더의 레퍼런스 이미지를 Gemini API 호출 시 `inlineData`로 함께 전달하여 스타일 일관성 유지. `generate_image` MCP 도구 사용 시 자동 처리되지만, Gemini API 직접 호출 시에도 반드시 레퍼런스를 포함할 것
  - **3D 아이콘/일러스트**: `assets/reference-images/icon/` 에서 랜덤 2장 참조 (기본)
  - **2D/flat 스타일**: `assets/reference-images/2d/` 에서 랜덤 2장 참조 (style="2d" 시)
  - **히어로/배너**: `assets/reference-images/hero/` 에서 랜덤 2장 참조 (isHero=true 시)
  - 키워드 매칭: hero(banner/배너/히어로/carousel/cover), icon(icon/아이콘/logo/symbol/badge/coin/gift/object), 매칭 없으면 icon/ 기본
- **그래픽·일러스트가 필요한 영역은 반드시 Gemini(nano-banana-pro)로 생성해서 삽입** — 배너 배경 이미지, 히어로 일러스트, 3D 오브젝트, 캐릭터, 프로모션 비주얼 등
- **전체 UI 화면을 Gemini로 생성하는 것은 금지** — 스타일 일관성이 깨지고 수정 불가능. 그래픽 에셋 생성에만 사용
- **생성 워크플로우:**
  1. 이미지를 채울 프레임/rectangle 노드를 먼저 Figma에 생성
  2. Python으로 Gemini API 호출 → `assets/generated/` 에 PNG 저장
  3. HTTP 서버(`python3 -m http.server 18765`, 프로젝트 루트 기준)로 서빙
  4. `set_image_fill(url="http://localhost:18765/assets/generated/파일명.png", scaleMode="FILL")`로 적용
- **API 정보:**
  - Endpoint: `https://generativelanguage.googleapis.com/v1beta/models/gemini-3-pro-image-preview:generateContent`
  - Header: `X-goog-api-key: {API_KEY}`
  - Body: `{"contents":[{"parts":[{"text":"..."}]}],"generationConfig":{"responseModalities":["IMAGE","TEXT"]}}`
  - API Key: Settings UI에서 설정 (src/main/settings-store.ts에 저장됨)
  - 응답: `candidates[0].content.parts[].inlineData.data` (base64 PNG)
- **3x 해상도 필수:** 모든 그래픽 이미지는 **Figma 노드 사이즈의 3배**로 생성 후, 원래 크기의 노드에 `FILL`로 적용. Figma가 자동으로 축소하여 고해상도 렌더링. 예: 36×36 노드 → 108×108 이미지 생성, 361×180 배너 → 1083×540 이미지 생성
- **크기 맞추기:** Gemini 출력 비율이 타겟과 다를 수 있음 → PIL로 center-crop 후 `img.resize((W*3, H*3), Image.LANCZOS)` 적용 (3x 해상도)
- **스타일 레퍼런스:** 이전에 생성한 이미지를 `inlineData`로 같이 전달하면 스타일 일관성 유지 가능
- **히어로/배너 배경 그래픽 스타일:** `Cinema4D, Octane render, soft diffused studio lighting, matte finish, front view, orthographic view` — 히어로/배너 배경 이미지 전용. 아이콘/일러스트는 위의 "여기어때/야놀자 비비드 글로시" 스타일 사용
- **이미지 사이즈 규칙 (용도별 4단계):**
  - **대형 배너 (히어로, 프로모션 등):** 이미지 사이즈 = 배너 프레임 사이즈 × 3. 텍스트가 좌측에 배치될 경우, Gemini 프롬프트에 "place the 3D object on the **right side** of the image, leave the **left half empty** for text overlay"를 포함하여 그래픽을 우측에 생성
  - **중형 카드 그래픽 (랜덤박스, 기프트샵 등):** Figma 노드 **32×32px 고정** → 이미지 **96×96px** (3x)로 생성. Gemini 출력 후 PIL로 투명 영역 trim → `96×96`로 리사이즈. 투명 배경 필수 (rembg 적용). **카드 내 텍스트 위에 배치** (아이콘 상단 → 텍스트 하단 VERTICAL 구조)
  - **소형 아이콘 그래픽 (3D):** Figma 노드 32×32px → 이미지 **96×96px**로 생성. 동일하게 trim 후 리사이즈. DS 아이콘으로 대체 불가능한 커스텀 일러스트에만 사용
  - **2D 플랫 그래픽 (리스트 아이콘 등):** Figma 노드 **24×24px 고정**, `cornerRadius: 0` 필수 → 이미지 **72×72px** (3x)로 생성. `assets/reference-images/2d/` 토스페이스 레퍼런스를 `inlineData`로 반드시 함께 전달. 투명 배경 필수 (rembg 적용). 토스페이스 스타일: 완전 플랫 단색, 그라데이션/투명/그림자 금지

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

### 컬러 조화 규칙 (화면 단조로움 방지)
- **중요 텍스트·기능·버튼은 Brand color** — CTA, 핵심 수치, 강조 라벨, active 탭 아이콘 등
- **기본 톤은 Gray Modern** — 배경: `bg-primary`(white) / `bg-secondary`(gray-50), 텍스트: `fg-primary`(gray-900) / `fg-secondary`(gray-600) / `fg-tertiary`(gray-400), 보더: `border-secondary`(gray-200)
- **2~3개 액센트 컬러 혼용 필수** — Brand 단색만 쓰면 단조로움. DS 토큰의 Error(빨강), Warning(주황), Success(초록) 등 Semantic color를 상황에 맞게 배치하여 시각적 리듬감 부여
  - 예: 마감임박 배지 → Error red, 수익률/긍정 지표 → Success green, 신규/HOT 태그 → Warning orange
  - 히어로 배너 배경 → `bg-brand-section` (짙은 brand), 카드 배경 → `bg-brand-primary` (연한 brand)
- **동일 색상의 농도 변화로 깊이감** — bg-brand-primary(연) → bg-brand-secondary(중) → bg-brand-solid(진) 순으로 계층 표현

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

### ⚠️ TEXT 컬러는 `Colors/Text/text-*` 에 바인딩 (사용자 정책 2026-05-18)
- **TEXT 노드의 fill 컬러는 `fg-*`가 아닌 `Colors/Text/text-*` 토큰에 바인딩한다**
- `text-*`에 해당 컬러가 없으면 `Component colors/Utility/utility-*` 토큰을 fallback으로 사용
- 아이콘(VECTOR)/프레임 배경/보더는 기존대로 `fg-*` / `bg-*` / `border-*` 사용 — 이 규칙은 **텍스트 컬러 전용**
- 코드 강제: `figma_mcp_client.py` 의 `_collect_bindings`가 TEXT fill 매칭 결과를 `_remap_text_token`으로 `fg-→text-` 리맵, 미해당 시 `prefer_class="utility"`로 재매칭. `_auto_classify_black_texts`/`_fix_tab_bar_icon_colors`도 text- 반환
- 기존 빌드 화면 갱신: `python3 scripts/rebind_text_to_text_tokens.py <rootNodeId>` (post-fix sweep은 이미 바인딩된 fill을 스킵하므로 강제 재바인딩 필요)
