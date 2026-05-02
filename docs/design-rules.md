# Design Rules

> **디자인 생성 전 반드시 읽기: 기본 빌드 규칙 (MUST READ FIRST)**

## 기본 빌드 규칙 (디자인 생성 시 첫 번째로 적용)

아래 규칙은 **모든 디자인 생성/수정 시** 기본으로 적용한다. 위반하면 QA에서 반드시 실패한다.

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
- 절차: `create_component_instance(componentKey="81efeddd245e95f31a2724aa370ee54d3caf93d0")` → `insert_child(parentId=navBarId, childId=인스턴스ID, index=0)` — NavBar의 첫 번째 자식으로 배치

## 버튼/CTA 컴포넌트 인스턴스 필수
- 버튼은 반드시 DS `Buttons/Button` 컴포넌트 인스턴스를 사용 — 프레임+텍스트로 수동 구성 금지
- **CTA 버튼**: `Size=xl, Hierarchy=Primary, State=Default, Icon only=False` (componentKey: `83a1917f02ba561dbbaa08dbf3845b91a47b0907`)
- **일반 버튼 (Large)**: `Size=lg, Hierarchy=Primary, State=Default, Icon only=False` (componentKey: `0caf4692294b0ec93e44516b94b3728a85b0963c`)
- **일반 버튼 (Medium)**: `Size=md, Hierarchy=Primary, State=Default, Icon only=False` (componentKey: `ed0032bcf28f03da97e4b3006f54d30a0fbe5914`)
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

## 시각 스타일 레퍼런스 — 아임인 홈 스타일

> 아임인 홈 화면 레퍼런스(`docs/references/imin-home/`)에서 추출한 **비주얼 DNA**. 토큰·컴포넌트 구조와 독립적으로 시각 패턴만 규정한다.
> 컬러는 모두 `$token()` 참조(최신 DS 자동 반영), 수치 스펙(padding·radius·size)은 숫자 고정. DS 토큰이 없는 항목(border-warning/success 등)은 `fg-*-primary`나 `border-primary`로 폴백.

### VS1. 큰 숫자 강조 패턴
- **금액/카운트 등 대표 숫자**는 반드시 아래 조합으로 강조 (평탄한 타이포그래피 방지):
  - `fontName: { family: "Pretendard", style: "Bold" }` 또는 `ExtraBold`
  - `letterSpacing: { value: -2, unit: "PERCENT" }` (−0.02em, 36px 이상 숫자는 −3 권장)
  - **사이즈 단계**: 보조 숫자 18~20sp / 강조 24sp / Premium 카드 대표 숫자 36sp
- **숫자 + 단위 페어링**: 큰 숫자 Bold + 바로 옆 작은 단위 Medium (예: `360` 24sp Bold + `만원` 14sp Medium) — 같은 HORIZONTAL auto-layout에 `counterAxisAlignItems: "BASELINE"` 설정해 베이스라인 정렬
- **단위 텍스트 컬러**는 보조톤 (`fg-tertiary` 또는 `fg-quaternary`) — 숫자와 동일 톤으로 하지 말 것

### VS2. 상태 컬러 3원색 세트 (error / warning / success)
- 모든 **상태성 알림·카드·배지**는 아래 공식으로 컬러 세트 구성:
  | 레이어 | 토큰 |
  |-------|------|
  | 배경 (연한톤) | `$token(bg-{status}-primary)` |
  | 테두리 | `$token(border-{status})` — warning/success는 DS에 없으면 `$token(fg-{status}-primary)` 폴백 |
  | 아이콘 배지 배경 (진한톤) | `$token(bg-{status}-secondary)` |
  | 타이틀/강조 텍스트 | `$token(fg-{status}-primary)` |
  | 배지 내 흰 아이콘 | `{r:1, g:1, b:1, a:1}` |
- `{status}` = `error` / `warning` / `success` — 동일 구조로 variant만 교체
- **절대 금지**: 상태 카드에 `bg-brand-*` 사용 금지, 컬러 배경 위 검정 아이콘 금지 (대비 부족)

### VS3. Pill 배지 표준 스펙
- 카운트/라벨/카테고리 배지는 아래 스펙 고정:
  - `layoutSizingHorizontal: "HUG"` (rule 13 필수)
  - `autoLayout: HORIZONTAL + CENTER + paddingTop:3 + paddingBottom:3 + paddingLeft:8~9 + paddingRight:8~9`
  - `cornerRadius: 999`
  - 텍스트: **11~12sp / Bold 700**
  - 컬러 조합은 VS2 공식 적용 (bg-{variant}-primary + fg-{variant}-primary) 또는 brand(bg-brand-primary + fg-brand-primary)
- **우측 상단 수치 배지**(알림 dot 등)는 bg-{error|warning}-secondary + 흰 텍스트 + 2px 흰 border

### VS4. 아이콘 배지 원형/라운드
- 상태 알림·리스트 아이콘·카운트 뱃지에 쓰이는 **아이콘 컨테이너** 스펙:
  - **크기**: 32×32 (Alert/리스트) / 40×40 (온보딩/CTA) / 36×36 (ListTimeline 항목)
  - **radius**: 999 (원형, 상태 알림) 또는 10 (라운드, 온보딩)
  - **배경**: `$token(bg-{status}-secondary)` 진한톤
  - **아이콘**: 흰색 `{r:1,g:1,b:1,a:1}`, 사이즈 18, **strokeWidth 2~2.5** (기본 1.67보다 굵게)
  - autoLayout HORIZONTAL + primaryAxis CENTER + counterAxis CENTER
- **절대 금지**: 컬러 배경 위 검정/다크 아이콘, strokeWidth 1.67 이하 — 작은 배지에선 선이 얇아 보이지 않음

### VS5. 가로 스크롤 섹션 표준 패턴
- 카드 3+개를 옆으로 흘려 보여주는 섹션(스테이지 목록, 상품 라운지 등)은 모두 동일 구조:
  - **Carousel Wrapper**: `HORIZONTAL` + `clipsContent: true` + `itemSpacing: 10` + `paddingLeft: 16` + `paddingRight: 16` + `layoutSizingHorizontal: "FILL"`, height는 HUG
  - **각 카드**: **FIXED width** (150~220px 범위) — FILL 금지 (캐로셀 안에서 너비 수축)
  - 우측 peek을 만들고 싶으면 카드 폭을 화면 폭 − 48px 근사치로 설정 (예: 393 화면 → 220 카드는 73px peek)
- R3 (히어로 캐로셀) 패턴과 동일 원리 — Banner는 353px 고정, Stage/상품 카드는 150~220px 고정

### VS6. 섹션 헤더 3요소 구조
- 모든 콘텐츠 섹션 상단은 **(좌) 타이틀 + (옵션) 상태 배지 · (우) '전체보기 >' 링크** 3요소 구조 고정:
  - **컨테이너**: HORIZONTAL + SPACE_BETWEEN + CENTER, paddingLeft/Right 20, paddingBottom 12, FILL
  - **좌측 그룹**: HORIZONTAL + CENTER + itemSpacing 8
    - 타이틀: **16sp / Bold 700** (rule 11과 일치), `$token(fg-primary)`
    - 배지(옵션): VS3 Pill 스펙, 상태별 variant (미납 → error, 신규 → warning 등)
  - **우측 링크 그룹**: HORIZONTAL + CENTER + itemSpacing 2
    - 텍스트: **13sp / Medium 500**, `$token(fg-tertiary)`
    - chevron-right 14, `$token(fg-tertiary)`
- 단독 타이틀(배지 없음)은 좌측 그룹 내부에서 배지 노드만 제거, 타이틀은 그대로 유지

### VS7. Premium CTA 카드
- 사용자의 **핵심 Conversion 지점**(추천 스테이지, 도전 시뮬레이터 등)에만 사용하는 최상위 CTA 카드:
  - **배경**: `$token(bg-brand-solid)` 단색 또는 `linear-gradient(180deg, bg-brand-solid, bg-brand-secondary)` — Figma는 `fillGradient` 사용
  - **padding**: 20 전방향
  - **cornerRadius**: 20
  - **shadow**: 브랜드 컬러 글로우 `0 8px 24px -4px rgba(브랜드rgb, 0.35)` (DS에 effectStyle 있으면 우선 사용)
  - **대표 숫자**: **36sp / ExtraBold 800 / letterSpacing −3%** (VS1 확장)
  - **내부 보조 라벨**: 흰색 불투명 85% — `{r:1,g:1,b:1,a:0.85}` 또는 DS에 `fg-white-secondary` 있으면 사용
  - **CTA 버튼**: 흰 배경 + 브랜드 텍스트 — `fill:{r:1,g:1,b:1,a:1}` + `fontColor: $token(fg-brand-primary)` + radius 12, padding 14/16, 15sp/Bold
- **절대 금지**: Premium 카드에 gray 톤 배경, 36sp 미만의 대표 숫자, 아웃라인 버튼 — 시각적 위계가 떨어짐
- **사용 빈도**: 화면당 **최대 1개** — 여러 개면 Premium의 의미가 없어짐

### VS8. 진행률 바 스펙
- 한도·적립·목표 달성률 등 모든 **Linear Progress Bar**는 스펙 고정:
  - **Track (트랙)**: `layoutSizingHorizontal: "FILL"` + height 8 + `cornerRadius: 999` + `fill: $token(bg-quaternary)` (가장 연한 회색)
  - **Fill (채움)**: inner frame + width = `Math.round(trackWidth * pct/100)` + height 8 + `cornerRadius: 999` + `fill: $token(bg-brand-solid)` (또는 그라데이션 `bg-brand-secondary → bg-brand-solid`)
  - Track는 `autoLayout HORIZONTAL` + counterAxis가 기본이면 Fill 프레임이 left-align됨
- **수치 라벨**은 반드시 Progress Bar 위쪽 헤더 라인에 배치 — 바 내부에 텍스트 올리지 말 것 (대비 문제)
- **절대 금지**: height 8px 미만(시각적 검색 어려움), radius 999 미만(각진 바는 핀테크 톤 아님), Fill에 테두리(stroke) 적용

### VS9. Modal Header (X-close only)
- 풀스크린·바텀시트 모달의 **가장 간소한 헤더** 패턴 (타이틀 텍스트 없음):
  - `HORIZONTAL` + `primaryAxisAlignItems: "MAX"` (우측 끝) + `counterAxisAlignItems: "CENTER"`
  - padding 12/20, height 48~56, 배경 투명 또는 `bg-primary`
  - 우측 아이콘: `x-close` 24sp, `$token(fg-primary)`
  - **좌측은 빈 공간** — 모달 본문의 첫 카드가 타이틀 역할 수행 (예: "진행중인 4건의 스테이지 내역" 카드가 헤더 대신)
- **절대 금지**: 중앙 타이틀 텍스트 + X 버튼 조합 — 이 조합은 페이지 네비게이션용 (AppBar)이지 모달 헤더 아님. 모달은 본문이 타이틀 역할을 맡음
- **X 버튼은 반드시 우측** — 좌측 X는 iOS 네비게이션 back 관례와 충돌

### VS10. 금액 값 링크 스타일 (탭 가능 표시)
- 요약 카드의 **탭 가능한 금액/수치 값**은 링크임을 시각적으로 명시:
  - `fontName: Bold`, `fontColor: $token(fg-brand-primary)`, `textDecoration: "UNDERLINE"`
  - 부호(+ −)는 값 텍스트 앞에 공백 붙여 포함: `"+ 14,420,320원"` / `"− 5,240,010원"`
  - 14sp 기본 (VS1 대표 숫자와 다름 — 링크 row는 한 줄에 나란히 읽히는 용도)
- **Row 구조**: `HORIZONTAL` + `SPACE_BETWEEN` + `BASELINE`
  - 좌측 라벨: 13sp Regular, `$token(fg-tertiary)` — 탭 불가능
  - 우측 값: 위 링크 스타일
- **언제 사용**: 요약 카드 내 "모은 금액 / 빌린 금액" 같이 **값 자체가 상세 화면 진입점**인 경우
- **반대로 금지**: 탭 불가능한 단순 정보 표시에 underline 넣지 말 것 — 링크 affordance 오인

### VS11. 월 캘린더 가로 스크롤 + Active Ring
- 거래 스케줄·납입 일정 등 **월 단위 타임라인 엔트리**는 아래 구조 고정:
  - 컨테이너: `HORIZONTAL` + `SPACE_BETWEEN` + `CENTER`, 좌/우 chevron-left/right 20sp (`$token(fg-tertiary)`) nav
  - 월 셀 7개 균등 배치, 각 셀: `VERTICAL` + `CENTER` + `itemSpacing: 4`
    - 월 이름(영문 3자): 11sp Regular, `$token(fg-tertiary)`
    - 날짜 숫자: 18sp Bold, `$token(fg-primary)`
    - 이벤트 dot: 4×4 radius 999, `$token(fg-quaternary)` (이벤트 있을 때만) / brand 컬러(강조 이벤트)
  - **Active 월**: 날짜 숫자를 **원형 컨테이너**(36sq, radius 999, `$token(bg-brand-solid)`)로 감쌈, 내부 숫자 흰색. 원 아래 보조 라벨("이번달" 등) 11sp Medium `$token(fg-brand-primary)`
- **필터 드롭다운**(옵션): 캘린더 카드 하단 `paddingTop: 12` + `HORIZONTAL END`, 텍스트 13sp Medium + `chevron-down` 14
- **절대 금지**: Active 월에 사각형 배경 강조(원형이 원칙), 월 이름 한글("10월") 대신 영문 약자 사용

### VS12. D-day 날짜 배지 (타임라인 좌측)
- 납입 스케줄·미션·이벤트 등 **타임라인 리스트 아이템 좌측 날짜 박스**:
  - 사이즈 **48×56** 고정 (정사각형 아님 — 세로로 약간 긴 rect)
  - `cornerRadius: 10`
  - `VERTICAL` + `CENTER` + `itemSpacing: 2`
  - 상단: 날짜 텍스트(예: "29일") 14sp Bold
  - 하단: D-day 라벨(예: "D+3", "D-1", "오늘") 10sp Regular, opacity 85%
- **상태별 컬러 매핑**:
  - **오늘/미납(active)**: `fill: $token(bg-primary)` (다크) + 흰색 텍스트 `{r:1,g:1,b:1,a:1}`
  - **과거/미래(inactive)**: `fill: $token(bg-secondary)` + `fontColor: $token(fg-primary)`
- **절대 금지**: D-day 라벨 생략, 날짜 박스 radius 999(원형) — 원형은 타임라인의 "점" 메타포와 혼동

### VS13. 타임라인 리스트 with Progress Bar (회차 진행률)
- 스테이지/분납/적립 회차처럼 **아이템마다 진행률 정보가 있는 리스트**는 progress bar를 리스트 아이템에 직접 포함:
  - 아이템 전체: `HORIZONTAL` + `CENTER` + `itemSpacing: 12` + `FILL`, padding 12/20
  - 구조: `Date Badge(VS12) | Middle Content(FILL) | Action(HUG)`
  - Middle Content: `VERTICAL` + `itemSpacing: 4`
    - 타이틀 14sp SemiBold, 금액 13sp Regular, **얇은 Progress Bar (height 3)**
  - Progress Bar: VS8 스펙에서 **height만 3으로 축소** (리스트 내 밀집 표현용) + 상태별 Fill 컬러:
    - `overdue`(미납): `$token(bg-error-secondary)`
    - `today`(진행 중): `$token(bg-brand-solid)`
    - `completed`(완료 5/5): `$token(bg-success-secondary)` — Fill 100%
    - `scheduled`(예정): `$token(bg-quaternary)` — Fill 0% (트랙만 표시)
- **우측 Action**:
  - `actionType: "pill"` — outline pill (stroke `$token(border-primary)`, 투명 bg, padding 8/14, radius 999, 13sp Medium `$token(fg-primary)`). 사용자 액션 유도("납입 하기", "선납 하기")
  - `actionType: "text"` — 테두리 없음, 13sp Medium `$token(fg-tertiary)`. 완료/대기 등 **불가 상태 표시**("납입 처리 완료", "납입 완료")
- **아이템 사이**: 1px bottom border `$token(border-tertiary)` 또는 `itemSpacing: 0` + 내부 divider
- **절대 금지**: 리스트 아이템에 두꺼운 progress bar(height 8, VS8은 카드 전용), 액션 pill + 텍스트 혼용

### VS14. Flat Stats Strip (카드 없는 3-col 통계 띠)
- 카드/테두리 없이 **3개 관련 수치를 얇은 구간으로 병렬 표시**:
  - `HORIZONTAL` + `SPACE_BETWEEN` + `CENTER` + `FILL`, padding 16/20
  - 배경: `$token(bg-secondary)` (얕은 구분) 또는 투명
  - 3개 셀 각각: `VERTICAL` + `CENTER` + `itemSpacing: 4` + **FILL 균등 분배**
    - 라벨: 12sp Regular, `$token(fg-tertiary)`
    - 값: 16sp Bold, `$token(fg-primary)`
- **언제 사용**: Summary Card와 리스트 사이 **중간 요약 구간**, 월 납입액/완료액/남은액처럼 **같은 카테고리 3개 수치**를 짧게 보여줄 때
- **절대 금지**: 셀 사이 divider 추가(flat이 원칙), 카드 shell(border/shadow) 추가 — 카드 구성이 필요하면 `SummaryCard2Col` 사용
- **카드와의 구분**: Card는 독립적 정보 단위, Stats Strip은 **카드들 사이 brief**

### VS15. Outline Chip 필터 스크롤
- 추천/직접/신규/인기/마감임박 등 **4+ 카테고리 필터**는 outline pill 가로 스크롤:
  - 각 칩: `HUG` + `HORIZONTAL` + `CENTER`, padding `8px 16px`, `cornerRadius: 999`
  - **Active**: stroke `$token(border-brand)` 1px + fill `$token(bg-brand-primary)` + 텍스트 `$token(fg-brand-primary)` Bold 700 / 13sp
  - **Inactive**: stroke `$token(border-primary)` 1px + fill `$token(bg-primary)` + 텍스트 `$token(fg-tertiary)` Medium 500 / 13sp
  - 컨테이너: `HORIZONTAL` + `clipsContent: true` + `itemSpacing: 6` + 좌우 padding 20
- **rule 14(Underline DS Tabs) 면제 조건**: Underline은 **뷰/섹션 전환**, Outline chip은 **필터링**. 용도 다름
- **절대 금지**: 칩 개수 3개 이하에 사용(세그먼티드 탭이 더 적합 — VS16), active inactive 모두 같은 border 색(차별화 실패)

### VS16. Segmented Tab Control (2~3-way 뷰 전환)
- "추천/직접" 같이 **적은 수의 상호 배타 뷰 전환**은 iOS-style Segmented Control:
  - Track (외곽): `HORIZONTAL` + `FILL` + padding 4 전방향 + fill `$token(bg-secondary)` + `cornerRadius: 999`
  - 각 세그먼트: **FILL 균등 분배** + `HORIZONTAL` + `CENTER`, padding `10px 16px`, `cornerRadius: 999`
  - **Active**: fill `$token(bg-primary)` (흰) + `effects: [{type:"DROP_SHADOW", color:rgba(10,13,18,.05), offset:{x:0,y:1}, radius:2}]` (subtle lift) + 텍스트 13sp Bold `$token(fg-primary)`
  - **Inactive**: fill 투명 `{r:0,g:0,b:0,a:0}` + 테두리 없음 + 텍스트 13sp Medium `$token(fg-tertiary)`
- **track padding 4의 역할**: active 세그먼트가 track 내부로 inset 되면서 외곽 track을 시각적으로 유지 — **padding 없이 active가 track에 꽉 차면 track이 안 보여 패턴 붕괴**
- **권장 세그먼트 개수**: 2~3개. 4개 이상은 `CategoryChipScroller` (VS15) 사용
- **절대 금지**: Active에 brand 배경 사용(과한 강조), inactive에 border 추가(시각적 노이즈), 가로 스크롤(세그먼트는 FILL 균등)
- **VS15와의 선택 기준**: 탐색 필터(여러 카테고리 탐색) → VS15 / 뷰 전환(추천 vs 직접 등 명확한 이분법) → VS16
- **4탭 variant (상세 화면 서브 탭)**: 스테이지 상세 등 **한정 공간에서 4개 뷰 전환**이 필요할 때만 예외. 스펙: track padding 3 (축소) + radius 10 (track) / 7 (segment), 각 segment padding 8/4, 텍스트 **12sp**로 축소. 5개 이상은 여전히 VS15 Outline Chip 사용

### VS17. Stepper 입력 행 (필터 카드)
- ± 버튼으로 값 조정하는 필터 행 표준 스펙:
  - Row: `HORIZONTAL` + `SPACE_BETWEEN` + `CENTER`, padding 상하 10
  - 좌측 라벨: 14sp Medium, `$token(fg-secondary)`
  - 우측 Stepper Group: `HORIZONTAL` + `CENTER` + `itemSpacing: 14`
    - **Minus/Plus 버튼**: 26×26, `cornerRadius: 999`, stroke `$token(border-primary)` 1px, fill `$token(bg-primary)`, 중앙 아이콘 16 `$token(fg-secondary)` strokeWidth 2.2
    - **값 디스플레이**: **width 90 고정** + `textAlignHorizontal: "CENTER"` — 값이 바뀌어도 간격 안정. 숫자 14sp Bold `$token(fg-primary)` + 단위 12sp Medium `$token(fg-tertiary)` 옆에 `marginLeft: 2`
- **카드 shell (여러 Stepper Row 묶기)**: fill `$token(bg-secondary)` + `cornerRadius: 14` + padding `6px 16px` (수직 6 수평 16)
- Row 사이 구분: 1px `$token(border-tertiary)` bottom stroke (마지막 Row 제외)
- **절대 금지**: 값 디스플레이 width가 가변(HUG) — 숫자 자릿수 바뀌면 ± 버튼이 움직여 탭 정확도 저하

### VS18. Slider — Track + Fill + **Thumb(필수)** 3요소
- **Thumb은 옵션이 아니라 필수**. Track + Fill만 있으면 슬라이더로 인지되지 않음 (2026-04-22 사용자 피드백)
- 드래그로 범위 빠르게 스캔하는 필터 / 값 선택 UI:
  - Row: `VERTICAL` + `itemSpacing: 6~8`, padding 상하 10
  - **Header Row**: `HORIZONTAL` + `SPACE_BETWEEN` + `BASELINE`. 좌 라벨 12~13sp Medium / 우 값 12~13sp Bold + 단위 11sp Medium
  - **Slider Track**: `FILL` 가로 + height `4~6` + `cornerRadius: 999` + 옅은 배경 (`$token(bg-quaternary)` 또는 `white 30% alpha` for colored cards) + **`clipsContent: false`**
  - **Slider Fill**: FIXED width = `(value-min)/(max-min) * trackWidth` + height `4~6` + cornerRadius 999 + 강조 fill (`$token(bg-brand-solid)` 또는 white for dark cards) + **`clipsContent: false`**
  - **Slider Thumb**: **16×16**, cornerRadius 999, fill white, Drop Shadow `(offset y=2, radius 6, color black 20%)`

**Fill width 계산 공식** (이걸 안 하면 Thumb 위치가 progress와 어긋남):
```
fill_width = track_available_width × (current / max)
```
- `track_available_width` = 부모 체인 padding 전부 뺀 실제 가용 폭
- 예: iPhone 16 → Recommendation(20×2) → Card(20×2) → Panel(14×2) = **285px**
- 3/13회차 → 285 × 3/13 ≈ **66px**

**권장 구현 — autoLayout MAX 정렬 (ABSOLUTE 불필요)**:
```
Slider Track  (FILL, h=6, cornerRadius 999, clipsContent: false,
               autoLayout HORIZONTAL, counterAxisAlignItems CENTER)
  └── Slider Fill  (**FIXED** w=계산값, h=6, cornerRadius 999, clipsContent: false,
                    autoLayout HORIZONTAL,
                    primaryAxisAlignItems MAX, counterAxisAlignItems CENTER)
        └── Slider Thumb  (16×16, **FIXED**, cornerRadius 999, fill white, DROP_SHADOW)
```
**Fill/Thumb에 반드시 `layoutSizingHorizontal: "FIXED"` 명시** — post-fix가 이름에 `slider` 포함한 노드를 skip하므로 FIXED 보존됨 (`figma_mcp_client.py` SKIP_KEYWORDS에 `"slider"` 등록)
- Fill의 `primaryAxisAlignItems: MAX` → Thumb이 Fill 우측 끝(progress value 지점)에 위치
- `counterAxisAlignItems: CENTER` → Thumb이 Fill 세로 중앙 = Track 세로 중앙
- Track/Fill 모두 `clipsContent: false` — Thumb(16px)이 Track(6px)보다 커서 상하 5px씩 튀어나옴
- Slider Track 감싸는 **상위 Row(Turn Row 등)에도 `clipsContent: false`** — 안 그러면 튀어나온 Thumb 잘림
- Thumb이 autoLayout 자식이므로 `layoutPositioning: ABSOLUTE` / 수동 후속 API 호출 **불필요**

**대안 — ABSOLUTE 오버레이 방식** (Thumb이 Fill 우측 끝을 **정확히 중심**으로 나와야 하는 경우):
- Thumb을 Track의 자식으로 두고 `layoutPositioning: ABSOLUTE`, `x = Fill.width - 8` (thumb 반지름만큼 안쪽), `y = (track.h - thumb.h) / 2`
- 빌드 후 `set_layout_positioning` 수동 호출 필요 — 구조 간단한 autoLayout 방식 우선 검토
- **VS17과의 차이**: Stepper는 **정확한 값**(1단위 조정), Slider는 **범위 감각**(빠른 스캔). 금액/기간 둘 다 가능하지만 사용자가 정확한 숫자 원하면 Stepper 권장

### VS19. 필터 칩 트리거 (바텀시트 호출)
- 상단 작은 라벨 + 하단 큰 값 + chevron-down 형태의 outline 칩 — 탭하면 바텀시트(VS20)로 상세 입력:
  - 각 칩: `HUG` + `HORIZONTAL` + `CENTER` + `itemSpacing: 6`, padding `10px 14px`, stroke `$token(border-primary)` 1px, fill `$token(bg-primary)`, `cornerRadius: 10`
  - Text Group: `VERTICAL` + `itemSpacing: 1`
    - 라벨 10sp Medium `$token(fg-quaternary)`
    - 값 13sp Bold `$token(fg-primary)` — 현재 설정된 값 명시
  - chevron-down 16sp `$token(fg-tertiary)`
- 컨테이너: `HORIZONTAL` + `clipsContent: true` + `itemSpacing: 8`, 좌우 padding 20
- **언제 사용**: 여러 필터가 있지만 화면 공간 한정될 때 — 칩은 현재 값만 보여주고 편집은 시트에서
- **VS17/VS18과의 선택**: 같은 화면에서 즉시 편집(VS17/18), 모달 편집(VS19). 화면 밀도 ↓ 원하면 VS19

### VS20. Bottom Sheet 공통 구조
- 단일 값·옵션을 full-attention 모달로 받는 하단 시트:
  - **Overlay**: ABSOLUTE inset 0, fill `{r:0, g:0, b:0, a:0.4}` (반투명 검정) — 하단으로 시트 정렬
  - **Sheet**: `FILL` 가로 + `HUG` 세로 + `borderTopLeftRadius: 20` + `borderTopRightRadius: 20` + padding `12/20/28/20` (상/좌우/하/좌우), fill `$token(bg-primary)`
  - **Drag Handle**: 40×4, `cornerRadius: 2`, fill `$token(bg-quaternary)`, CENTER 정렬. 시트 최상단, paddingBottom 12
  - **Title**: 16sp Bold `$token(fg-primary)`, `letterSpacing: -2%`
  - **Value Display** (시트의 핵심): `HORIZONTAL` + `CENTER` + `BASELINE` + `itemSpacing: 4`, padding 상하 18
    - 대형 숫자: **36sp ExtraBold `$token(fg-brand-secondary)` letterSpacing -3%** — VS7 Premium 숫자 확장
    - 단위: 16sp Medium `$token(fg-tertiary)` 옆에 부착
  - **Slider/컨트롤**: VS18 Slider Track/Fill 스펙
  - **Min/Max Labels**: `HORIZONTAL` + `SPACE_BETWEEN`, 각 11sp Regular `$token(fg-quaternary)` — slider 아래
  - **CTA**: `FILL` + padding 14 + `cornerRadius: 10` + fill `$token(bg-brand-solid)` + 텍스트 흰 15sp Bold. DS Buttons/Button (xl, Primary) 인스턴스 권장
- **X 닫기 버튼**: 선택적 — 단순 값 조정 시트는 drag handle만으로 충분. **복합 정보 시트**(VS30 DecisionBottomSheet 등 회차 선택+금액 상세+CTA 혼합)는 우측 상단 **36sq X 버튼** 허용 — drag handle보다 명시적 닫기 동선 제공
- **절대 금지**: 시트 높이 꽉 채움(full-screen은 별도 모달), radius 둥글지 않은 사각 모서리, drag handle 생략

### VS21. 아바타 스크롤 Row (메이커·참여자)
- 스테이지 메이커·모임 참여자·친구 등 **소셜 단위 가로 스크롤**:
  - 컨테이너: `HORIZONTAL` + `clipsContent: true` + `itemSpacing: 16`, padding `4/20/18/20`, fill `$token(bg-primary)`
  - **추가(+) 버튼** (맨 앞): VERTICAL CENTER itemSpacing 6
    - 원 52×52, radius 999, **dashed stroke `$token(border-primary)` 1.5** (dashPattern [4,4]), fill `$token(bg-primary)`, plus 아이콘 22 `$token(fg-quaternary)`
    - 라벨 "추가" 11sp Medium `$token(fg-quaternary)`
  - **각 아바타**: VERTICAL CENTER itemSpacing 6
    - Avatar Circle 52×52, radius 999, **fillGradient 135deg (고유 컬러 0% → 알파 80% 100%)**, 중앙 이모지/이니셜 20sp 흰색 Bold
    - **Crown/Rank Badge** (옵션): ABSOLUTE `bottom: -2, right: -2`, 18×18, radius 999, fill `$token(bg-brand-solid)` + 2px 흰 border, 중앙 👑 9sp
    - Text Group: CENTER 정렬, maxWidth 60
      - 이름 10sp Bold `$token(fg-secondary)` letterSpacing -2% + truncate 1-line
      - 레벨 "(lv.123)" 9sp Medium `$token(fg-quaternary)`
- **절대 금지**: 사각 아바타, 크기 52 미만(얼굴 인식 어려움), 이름 2줄(디자인 깨짐), rank badge 좌측 상단(시선 혼선 — 반드시 우하단)

### VS22. 스테이지 카드 multi-layout (timeline/ring/number)
- 스테이지 추천 카드는 **3가지 상단 레이아웃 중 1개** 선택 (같은 페이지에서는 일관된 레이아웃 유지):
  - 공통 카드 shell: fill `$token(bg-primary)` + border `$token(border-secondary)` 1px + `cornerRadius: 14` + padding `16/16/14/16` + `shadow-xs`
  - 공통 하단: **금액 요약 2-row** (목돈 + 총이자, `border-top` 1px `$token(border-tertiary)`) + **혜택 배지 band** (bg-secondary + radius 8 + 포인트/수수료 Pill 2개)
- **레이아웃 A — Timeline Bar**: 회차 수만큼 `gridTemplateColumns: repeat(N, 1fr)` + `itemSpacing: 2`. 각 cell height 22 + radius 4. 수령 회차는 `bg-brand-solid` + 흰 숫자 / 나머지 `bg-brand-primary` + `fg-brand-secondary` 숫자. 상단 설명/하단 안내 텍스트 13sp SemiBold CENTER.
- **레이아웃 B — Ring Gauge**: SVG 90×90, 배경 원(brand-primary stroke 8), progress arc(brand-solid stroke 8 + strokeDasharray + strokeDashoffset + rotate -90), 중앙 큰 숫자 + "/N회차" 작은 텍스트. 우측 보조 텍스트 그룹.
- **레이아웃 C — Number Hero**: 상단 라벨 11sp Bold `$token(fg-brand-secondary)` letterSpacing +4% UPPERCASE + 22sp ExtraBold 대표 금액 letterSpacing -3% + 13sp Medium 부제 + 얇은 progress bar height 4.
- **언제 어느 레이아웃**: Timeline = 납입 스케줄 시각화 강조 / Ring = 진행률 %감각 / Number = 금액 중심 판매
- **절대 금지**: 한 화면 내 레이아웃 혼용(일관성 파괴), 혜택 배지 4개 이상(카드 밀도 과다), 카드 내 CTA 버튼(탭 전체가 CTA이므로 이중 버튼 불필요)

### VS23. Legal Footer (3-col 약관 + 사업자 정보)
- 스크롤 최하단 법적 고지·사업자 정보 블록:
  - 컨테이너: `VERTICAL` + `FILL` + `itemSpacing: 6`, padding `18/20/16/20`, **상단 1px border-top `$token(border-tertiary)`**
  - **약관 Links Grid**: `VERTICAL` + `itemSpacing: 4` + paddingBottom 10. 각 Row `HORIZONTAL` + `itemSpacing: 12` + 3개 link FILL. 링크 11sp Medium `$token(fg-tertiary)`
  - **Company Block**: `VERTICAL` + `itemSpacing: 6`. 각 라인 10sp Regular `$token(fg-quaternary)`, lineHeight 170%
    - 대표자·사업자번호·통신판매업번호 등 다중 라인
  - **Copyright**: 10sp Regular `$token(fg-quaternary)` — 최하단
- **절대 금지**: footer에 색 배경/그라데이션(시선 유인 금지), 11sp 초과 폰트(footer 위계 파괴), 브랜드 로고 반복(상단에 이미 있음)

### VS24. Back-only Header (상세 화면 네비게이션)
- 상세 화면 상단 헤더는 **뒤로가기 버튼만** — 타이틀/우측 액션 없음:
  - `HORIZONTAL` + `MIN` (좌측) + `CENTER`, padding `4/8/8/8`, fill `$token(bg-primary)`
  - 버튼: 40×40 + `cornerRadius: 8` + 중앙 아이콘 `chevron-left` 24 `$token(fg-primary)` strokeWidth 2
- **본문 첫 카드가 타이틀 역할**: 스테이지 상세는 첫 카드가 스테이지 제목+요약(VS25), 모달 화면은 첫 카드가 제목 — AppBar 중앙 타이틀 패턴과 의도적으로 다름
- **VS9(X-close) vs VS24(back-only) 구분**: 모달/시트 → VS9 우측 X / 페이지 네비게이션 → VS24 좌측 chevron
- **절대 금지**: 중앙 타이틀 텍스트(AppBar 관례와 혼동), 우측 액션 버튼 추가(단일 진입 페이지는 액션 최소화)

### VS25. Asymmetric 3-col Summary (1fr : 1.4fr : 1fr)
- 상세 화면 요약 카드의 3-col 그리드는 **비대칭 비율**로 중요도 표현:
  - Grid Row: `HORIZONTAL` + `FILL` + `itemSpacing: 12`. 각 Item `layoutGrow` **1 / 1.4 / 1** — 중앙 셀(보통 금액·가격)이 가장 넓게
  - 각 Item: `VERTICAL` + `itemSpacing: 4`. 라벨 11sp SemiBold `$token(fg-tertiary)` + 값 14sp Bold `$token(fg-primary)` `letterSpacing: -2%`
- **카드 Header Row (타이틀+라벨 페어)**: `HORIZONTAL` + `BASELINE` + `itemSpacing: 10` — 타이틀과 보조 라벨이 베이스라인 공유
  - 타이틀: 16sp **ExtraBold** `letterSpacing: -2%`
  - 시작/서브 라벨: 11sp Medium `$token(fg-tertiary)` `letterSpacing: -1%`
- **왜 비대칭?**: 등분(1:1:1)은 숫자 자릿수 다를 때 셀이 어색하게 남고, 의사결정에 핵심인 값(약정금·목돈)을 시각적으로 부각하지 못함. **가운데가 가장 중요한 숫자**라는 구조를 명시
- **절대 금지**: 1:1:1 균등 그리드(중요도 불명확), 5-col 이상(`StatsStrip3Col`로 압축), 숫자 자릿수에 따라 비율 임의 변경

### VS26. Timeline 참여자 Row (rail + node + card)
- 좌측 세로선 **rail** + 원형 **node** + 우측 **card** 3-부 구성:
  - Row: `HORIZONTAL` + `itemSpacing: 14` + `CENTER` + `FILL`, 상하 padding **10** (normal) / **6** (tight density)
  - **Left Rail** (width 36): `VERTICAL` + `CENTER`. 자식 2개
    - **세로 연결선** (옵션): ABSOLUTE 2px × FILL, fill `$token(bg-quaternary)`, zIndex 1, top 0 bottom `-padY*2` (다음 Row까지 연결). **마지막 Row는 세로선 생략**
    - **Timeline Node** 36×36 radius 999 + zIndex 2 + 중앙 정렬 (VS27 비주얼 variant)
  - **Right Card** (FILL): `HORIZONTAL` + `CENTER` + `itemSpacing: 10`, padding 14/16 (normal) / 10/14 (tight), radius 12
    - 기본: fill `$token(bg-primary)` + border `$token(border-secondary)` + shadow-xs
    - **emphasize=true**: fill `$token(bg-brand-solid)` + stroke 없음 + brand shadow (`0 4px 12px rgba(brand-rgb, 0.25)`) + 텍스트 흰색 + 설명 `rgba(255,255,255,0.85)`
  - 카드 내부: Text Group (FILL, VERTICAL, itemSpacing 2) + 우측 Action Pill (HUG)
- **VS13과의 차이**: VS13은 D-day 날짜 배지 중심(회차 납입 리스트), VS26은 **세로선 rail + 원형 node 중심** (참여자 + 회차 목표 혼합 타임라인)
- **absolute 세로선 주의**: Figma에서 autoLayout 내부에 ABSOLUTE로 연결선을 만들려면 Left Rail을 HUG + 중앙 node 위아래에 ABSOLUTE 선 삽입. 대안: 각 Row 사이에 독립된 vertical-line 요소를 외부 컨테이너에서 그릴 것

### VS27. TimelineNode 비주얼 variant (number / avatar / stage)
- VS26 Timeline Row의 36×36 원형 노드는 **3가지 모드** 중 하나:
  - **`number` (기본)**: 숫자 1~N. 기본은 fill `$token(bg-primary)` + border `$token(border-primary)` 1.5px + 텍스트 13sp Bold `$token(fg-secondary)` `letterSpacing: -2%`. **emphasize=true**: fill `$token(bg-brand-solid)` + border `$token(border-brand)` + 텍스트 흰색
  - **`avatar`**: 사용자 프로필
    - `rowType='invite'` (실제 사용자): fill **linear-gradient 135deg** (팔레트 5색 중 id 기반 선택: 보라/핑크/오렌지/그린/블루) + border 없음 + 중앙 이니셜 13sp Bold 흰색
    - `rowType='plan'` (계획/목표): fill `$token(bg-brand-primary)` + 중앙 아이콘 `credit-card` 18 `$token(fg-brand-secondary)`. emphasize 시 fill brand-solid + 흰 아이콘
  - **`stage` (단계 dot)**: fill `$token(bg-primary)` + border `$token(border-primary)` 1.5px. 중앙에 10×10 radius 999 dot `$token(bg-brand-solid)`. emphasize 시 node fill brand-solid + 중앙 dot 흰색
- **그라데이션 팔레트** (avatar/invite): `['#8b5cf6', '#ec4899', '#f59e0b', '#10b981', '#3b82f6']` — DS에 없는 보조 컬러. 135deg 각도, 0% fullColor → 100% 알파 80%
- **어느 variant 언제**: 숫자 시퀀스 강조 → `number` / 소셜 관계 강조 → `avatar` / 달성 여부 강조 → `stage`. 같은 타임라인 내에서 **혼용 허용** (plan은 credit-card 아이콘, invite은 이니셜, milestone은 dot)

### VS28. Empty State Placeholder (빈 상태)
- 빈 탭·검색 결과 없음·데이터 미존재 등 'empty state':
  - 컨테이너: `VERTICAL` + `CENTER` + `FILL` + `itemSpacing: 18`, padding **80/24** (상하 80, 좌우 24) — 상하 여백으로 수직 중앙 느낌
  - **Icon Circle**: 64×64 + `cornerRadius: 999` + fill `$token(bg-secondary)` + 중앙 아이콘 28 `$token(fg-quaternary)` **strokeWidth 1.6** (얇은 선으로 낮은 강조)
  - 타이틀: 15sp Bold `$token(fg-secondary)` `letterSpacing: -2%` CENTER
  - 서브: 12sp Regular `$token(fg-quaternary)` CENTER — 안내/가이드 톤
- **절대 금지**: 빈 상태에 CTA 버튼 추가(진짜 empty는 탐색 유도만, 액션은 별도 블록에서 / 3회 이상 같은 empty 반복되면 온보딩 필요 시그널), 아이콘 strokeWidth 2+ (과한 강조), 타이틀 Bold-ExtraBold (empty는 시선을 적게 끌어야 함)
- **isolation**: 부모 컨테이너가 `FILL` 높이여야 세로 중앙 정렬이 유효. 고정 높이면 padding 80/80 유지 (상하 40+ 보장)

### VS29. N-cell 선택 그리드 (+ 삼각 pointer)
- 회차·월·숫자 등 **순차형 선택 UI**:
  - Grid Row: `HORIZONTAL` + `FILL` + `itemSpacing: 3`. 각 Cell `FILL` + `layoutGrow: 1` (균등 분배) — gridTemplateColumns repeat(N,1fr) 동등
  - 각 Cell: height **26** + `cornerRadius: 4` + `HORIZONTAL CENTER`. 내부 숫자 11sp Bold
    - **Active**: fill `$token(bg-brand-solid)` + 숫자 흰색
    - **Inactive**: fill `$token(bg-brand-primary)` + 숫자 `$token(fg-brand-secondary)`
  - **Pointer Container** (바로 아래): FILL + height 14. 내부 ABSOLUTE 삼각형 (10×6, fill `$token(bg-brand-solid)`, 뾰족 아래쪽)
    - **삼각 위치**: `left = ((activeIndex - 0.5) / totalCells) * 100% - 5px`, `top: 0`
  - Info Text (선택적, 하단): 13sp SemiBold CENTER + 선택 숫자 부분만 `$token(fg-brand-secondary)` Bold (set_styled_text_segments)
- **VS22 Stage Card Timeline Bar와 차이**: VS22는 정적 시각화 (회차 스트라이프 + 수령 포인트 고정), VS29는 **사용자 상호작용 선택** (활성 셀이 탭으로 바뀜 + pointer 이동)
- **절대 금지**: 셀 높이 20 미만(탭 영역 부족), 13+ 셀 개수에서 gap 5+ (스트라이프 깨짐), pointer 없이 active만으로 식별(시각적 연결 부족)

### VS30. Decision BottomSheet (복합 결정 시트)
- 선택 → 확인 → 실행 결정 플로우의 복합 바텀시트 (단일 값 조정 VS20과 구분):
  - **3-Section 구조**:
    1. **Header Band**: Grabber(VS20) + (옵션) 우측 상단 X(VS20 업데이트) + 헤더 설명 텍스트(13sp SemiBold CENTER) + 셀렉터(VS29) + 안내 텍스트
    2. **Amount Detail Section**: top border `$token(border-tertiary)` 1px, padding 16/20. 라벨/값 row 반복 (라벨 13sp Medium `$token(fg-tertiary)` / 값 14sp Bold — 상태별 컬러: 이자>0=success, 이자<0=error, 기본=fg-primary) + 하단 배지 row (선물/수수료 Pill, VS3)
    3. **CTA Section**: top border `$token(border-tertiary)` 1px, padding 10/20/24/20. Full-width CTA 버튼 (padding 15, radius 10, fill `$token(bg-brand-solid)`, 흰 15sp Bold, brand shadow)
  - Sheet 본체: FILL 가로 + HUG 세로 + topLeftRadius/topRightRadius 20 + `clipsContent: true` + `$token(bg-primary)`
- **VS20과의 선택 기준**: 단일 값 조정 (월 납입 슬라이더) → VS20 / 복합 정보 확인 후 실행 (회차 선택 + 금액 확인 + 참여하기) → VS30
- **Section 사이 visual divider**: 2개 border-tertiary top border로 3섹션을 명확히 분리 — 단일 Card처럼 합치면 CTA가 덜 중요해 보임
- **절대 금지**: CTA 없는 DecisionBottomSheet(결정을 요구하는데 실행 동선 없음 = 설계 실패), 3-section 외 섹션 추가(밀도 과다, 별도 풀스크린 모달로), sticky CTA 없이 CTA를 중간에 배치(화면 하단에 고정되어야 엄지 도달 가능)

### VS32. 가로 스크롤 섹션 — Peek 패턴 (뷰포트 40% 카드 + 3번째 카드 부분 노출)
- **규칙**: 가로 스크롤 리스트(HORIZONTAL autoLayout + `clipsContent: true`) 내부 카드 너비는 **뷰포트 40% 이하** (iPhone 16 393px 기준 **150~165px**).
- **목적**: 한 화면에 2.1~2.5개 카드가 들어와 **마지막 카드가 20~40% peek** — "스와이프 가능" 시각 힌트 제공. 2개 카드가 딱 맞게 들어와 3번째가 완전히 숨으면 사용자는 리스트를 스크롤 가능한지 알 수 없음.
- **실전 비교 (2026-04-22 imin-home)**:
  - ❌ **Stage Card 220px (뷰포트 56%)**: 2개 full + 3번째 완전 hidden → 스와이프 힌트 없음
  - ✅ **Product Card 150px (뷰포트 38%)**: 2개 full + 3번째 28% peek → 자연스러운 스와이프 유도
  - 조치: Stage Card를 220 → 160px로 축소 (뷰포트 40.7%)
- **권장 수치 (뷰포트 393, paddingLeft 16, itemSpacing 10)**:
  - 카드 width **150~160px** → 3번째 카드 22~30% peek
  - `paddingRight: 0` (또는 ≤ 8) — peek 영역 확보
- **카드 내부 밀도**: 160px 내부 padding 16 양쪽 = 가용 128px. 금액(24sp Bold)·이율·라벨 10~13자(12sp) 모두 수용.
- **예외 — 히어로 배너 캐로셀**: 1개씩 전체 스와이프하는 배너는 카드 **353px (뷰포트 90%)**, 좌우 20px peek로 다음 배너 힌트. VS5 참조.
- **자동 검증 (post-fix)**: `_check_horizontal_scroll_peek()`가 아래 조건을 모두 충족한 섹션에서 카드 width > 165px 감지 시 경고:
  - HORIZONTAL autoLayout + `clipsContent: true`
  - **섹션 이름에 "Scroll" 포함** (네이밍 컨벤션 강제 — 일반 grid/row와 구분)
  - 자식 모두 `layoutSizingHorizontal: FIXED`
  - 자식 총 너비 > 부모 width (실제 스크롤 필요)
- **절대 금지**:
  - 가로 스크롤 카드 width > 180px (뷰포트 50% 초과) — 3번째 카드 peek 사라짐
  - `clipsContent: false` + 가로 스크롤 — 카드가 화면 밖으로 나가 레이아웃 깨짐
  - paddingRight를 itemSpacing 이상으로 설정 — peek 영역이 padding에 의해 사라짐

### VS31. Stroke Alignment — 항상 INSIDE (OUTSIDE 금지)
- **규칙**: stroke가 있는 모든 프레임/카드는 `strokeAlign: "INSIDE"` 강제. OUTSIDE/CENTER 절대 금지.
- **배경**: OUTSIDE/CENTER stroke는 부모가 `clipsContent: true`(가로 캐로셀, 스크롤 영역 등)이면 바깥쪽 stroke가 **잘려보임**. 특히 "today" 강조 카드처럼 ±2px OUTSIDE 보더를 쓰는 케이스에서 상단/좌우가 잘리는 버그가 반복적으로 발생.
- **실전 사례 (2026-04-22)**: Schedule 섹션의 Today Card(월/20/50만/오늘 pill)가 Day Card Row의 `clipsContent: true`에 의해 상단 보더가 잘림. INSIDE로 교체 후 4방향 모두 정상 렌더.
- **Why INSIDE가 안전한가**:
  - 프레임의 실제 bbox(외곽 치수) = 지정 width/height — 부모 레이아웃 계산에 영향 없음
  - 부모 clip 여부와 무관하게 항상 렌더됨
  - 내부 콘텐츠 영역이 stroke 굵기만큼 줄어들지만, 카드 padding이 보통 8px+ 여유라 간섭 없음
- **자동 강제**: `scripts/figma_mcp_client.py` post-fix의 `_fix_stroke_alignment()`가 모든 OUTSIDE stroke를 빌드 후 INSIDE로 자동 변환. Blueprint에서 OUTSIDE로 작성했어도 post-fix가 교정.
- **절대 금지**: OUTSIDE stroke를 "의도적인 디자인"으로 남겨두기 (모든 케이스에서 INSIDE로 시각 결과 동등하거나 우월), CENTER 정렬(OUTSIDE와 동일한 clip 리스크).

---

## Variable Binding (필수)
- 디자인 생성 완료 후 **반드시 마지막 단계에서 DS 변수 바인딩 수행** — 절대 빠뜨리지 말 것
- 바인딩 순서: ① Text Style (`set_text_style_id`) → ② Typography 변수 (fontSize, lineHeight) → ③ Radius 변수 → ④ Color 변수 (fills/0, strokes/0)
- `set_bound_variables`로 바인딩: fontSize, lineHeight, cornerRadius(topLeftRadius 등), padding, itemSpacing, fills/0, strokes/0
- `set_text_style_id`로 Text Style 바인딩 (Style ID 형식: `S:{key},{nodeId}`)
