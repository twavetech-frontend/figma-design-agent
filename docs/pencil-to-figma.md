# Pencil → Figma 보내기 ("figma로 보내줘")

사용자가 "figma로 보내줘", "figma로 보내", "피그마로 보내" 등을 말하면:

**전제 조건**: Figma Design Agent 앱이 실행 중이고 Figma 플러그인과 연결된 상태

**방식**: LLM 중재 — Pencil 스크린샷(시각) + JSX(구조)를 보고 LLM이 `batch_build_screen` blueprint를 직접 생성

**워크플로우** (5단계, 자동 실행):
1. **Pencil 현재 상태 읽기**: `mcp__pencil-mcp__get_editor_state()` → 현재 선택된 노드/아트보드 ID
2. **시각 + 구조 수집** (동시 호출):
   - `mcp__pencil-mcp__get_screenshot({ nodeId, scale: 2 })` → 시각적 레이아웃/색상/아이콘
   - `mcp__pencil-mcp__get_jsx({ nodeId, format: "inline-styles" })` → 텍스트/색상값/padding
3. **Blueprint 생성**: LLM이 스크린샷 + JSX 분석 → `batch_build_screen` blueprint 직접 생성
4. **Figma 빌드**: `mcp__figma-tools__batch_build_screen({ blueprint })` → 한 번에 전체 화면 생성
5. **결과 비교 QA**: 빌드 결과 스크린샷과 원본 Pencil 스크린샷 비교 검증

**참고**:
- `convert_pen_to_figma` 사용 금지 (deprecated) — 런타임에서 차단됨
- DS v1 컴포넌트 활용 + 아이콘 시맨틱 매핑 (Pencil 아이콘 → DS v1 아이콘)
- `figma-tools` MCP 서버는 Electron 앱의 HTTP MCP (port 8769) — 앱 실행 필요

---

## Pencil → Figma Blueprint 생성 규칙

> `batch_build_screen` blueprint를 LLM이 생성할 때 반드시 적용하는 규칙. 이 규칙을 무시하면 레이아웃이 깨짐.

### 폰트 규칙
- Figma에서 한글 텍스트는 **반드시 Pretendard** 사용 — DM Sans, Bricolage Grotesque 등 Latin 전용 폰트는 한글 글리프가 없어 텍스트가 렌더링되지 않음
- Pencil 원본이 DM Sans/Bricolage Grotesque를 사용해도 Figma blueprint에서는 **전부 Pretendard로 대체**
- fontWeight 매핑: 400→Regular, 500→Medium, 600→SemiBold, 700→Bold, 800→ExtraBold

### Auto Layout 사이징 규칙 (code.js 자동 적용)
- Auto-layout 프레임에 **명시적 width/height가 없으면 → HUG** (콘텐츠에 맞춤)
- Auto-layout 프레임에 **명시적 width/height가 있으면 → FIXED** (지정 크기 유지)
- Blueprint에서 카드/섹션 등 콘텐츠 래퍼는 height를 생략하여 HUG 자동 적용

### 텍스트 FILL 사이징 규칙 (code.js 자동 적용)
- 텍스트 노드의 자동 FILL은 **VERTICAL 부모에서만** 적용
- HORIZONTAL 부모에서 텍스트에 FILL을 적용하면 텍스트들이 폭을 경쟁하여 **글자가 세로로 1자씩 줄바꿈**되는 버그 발생
- HORIZONTAL 부모 내 텍스트가 공간을 채워야 할 경우, **텍스트를 감싸는 부모 프레임**에 layoutSizingHorizontal: "FILL"을 설정

### 텍스트 정렬 규칙
- **FILL 너비 텍스트는 textAlignHorizontal 명시 필수**
- 탭 라벨, 버튼 라벨 등 중앙에 위치해야 하는 텍스트: **textAlignHorizontal: "CENTER"**
- counterAxisAlignItems: "CENTER" 부모 내의 FILL 너비 텍스트: **textAlignHorizontal: "CENTER"**

### 아이콘 래퍼 프레임 규칙
- 아이콘을 감싸는 프레임(배경색 있는 아이콘 박스)은 **정사각형 또는 의도된 비율**이어야 함
- 아이콘 래퍼 프레임: **명시적 width/height를 동일하게 설정** (예: 48×48, 56×56)
- 래퍼 프레임에 width/height를 생략하면 HUG가 적용되어 아이콘 크기(24)에만 맞춰져 패딩 없는 찌그러진 프레임이 됨

### 탭바/네비게이션 스타일 규칙
- 탭 바 필(pill) 배경: **흰색(#FFFFFF) + 회색 보더(#F3F4F6, 1px, inside)** — 회색 배경이 아님
- 각 탭 프레임: layoutSizingHorizontal: "FILL", layoutSizingVertical: "FILL" (균등 분배)
- 탭 라벨: fontSize 10, textAlignHorizontal: "CENTER"

### FAB + 탭바 절대 위치 규칙 (하단 고정 요소)
- **Tab Bar와 FAB는 반드시 `layoutPositioning: "ABSOLUTE"`로 하단 고정**
- Tab Bar: `constraints: { horizontal: "STRETCH", vertical: "MAX" }`, x: 0, y: (rootHeight - tabBarHeight)
- FAB: `constraints: { horizontal: "STRETCH", vertical: "MAX" }`, Tab Bar보다 위에 위치
- Content 프레임: `layoutSizingVertical: "FILL"` — 헤더와 하단 고정 요소 사이 남은 공간 채움

### FAB 구조
- FAB는 **HORIZONTAL** auto-layout, **HUG×HUG**, padding `12/12/20/20`, `itemSpacing: 8`, `cornerRadius: 28`
- 자식은 아이콘(24×24) + 텍스트 — 중간 래퍼 프레임 금지

### Blueprint 구조 패턴 (모바일 풀스크린)
```
Root (VERTICAL, FIXED 393×852)
├── Status Bar (FILL × FIXED 62)
├── Header (FILL × HUG, padding [12, 24])
├── Content (FILL × FILL ← 남은 공간 채움, padding [4, 24, 0, 24], gap 22)
│   ├── Card (FILL × HUG, cornerRadius, padding, gap)
│   ├── Section (FILL × HUG, gap 12)
│   │   ├── SectionHeader (FILL × HUG, SPACE_BETWEEN)
│   │   └── SectionList (FILL × HUG, VERTICAL, gap 8)
│   └── ...
├── FAB (ABSOLUTE, FILL × FIXED 56, y = 하단에서 tabBar 위)
└── Tab Bar (ABSOLUTE, FILL × FIXED 95, padding [12, 21, 21, 21])
```

### 색상 형식 규칙
- batch_build_screen blueprint에서 색상은 **`$token(토큰이름)`** 또는 **{r, g, b, a} 형식 (0–1 범위)**
- **DS 토큰 컬러 → `$token()` 참조 필수**: `"$token(bg-brand-solid)"`, `"$token(fg-primary)"` 등. `figma_mcp_client.py build`가 TOKEN_MAP.json에서 최신 hex → RGBA로 자동 변환
- **직접 RGBA는 기본색만 허용**: 흰색 `{r:1,g:1,b:1,a:1}`, 검정, 투명 등
- **CTA/강조 색상은 반드시 `$token(bg-brand-solid)` 사용**

### 색상 대비 최소 4:1 (WCAG AA)
- 모든 텍스트·아이콘은 배경 대비 **최소 4:1** 비율 필수
- 짙은 배경(brand-section 등)에 검정 아이콘/텍스트 금지 → 반드시 흰색(#FFF) 사용
- 연한 배경(brand-primary 등)에는 fg-brand-primary 이상의 대비 사용

### VERTICAL 카드형 레이아웃 텍스트 중앙 정렬
- 아이콘 + 텍스트 라벨이 세로로 쌓이는 카드에서 텍스트 라벨은 `textAlignHorizontal: "CENTER"` 필수

### 토글형 아이콘 active 상태 = solid(filled)
- bookmark, heart, star, bell 등 토글 가능한 아이콘은 **active 상태일 때 fill을 채워서 solid로 표현** 필수
- active: `set_stroke_color` + `set_fill_color` 동일 색상 적용 — `DESIGN_TOKENS.md`의 `fg-brand-primary` 토큰 조회 후 사용
- inactive: `set_stroke_color`만 회색(`{r:0.816, g:0.835, b:0.867}`), fill 없음 (outline만)
- @untitledui/icons는 stroke 기반이라 별도 solid 파일이 없음 → fill 색상으로 solid 효과 구현

### Badge/Tag는 반드시 HUG
- Badge, Tag, Chip 등 라벨 컨테이너는 **반드시 `layoutSizingHorizontal: "HUG"`** — FILL 금지
- auto-layout 부모 안에서 FILL이 되면 전체 너비로 늘어나서 디자인이 깨짐
- 예: 이벤트 배지, 포인트 태그, 카테고리 칩 등

### 이미지 fill scaleMode 규칙
- **히어로/배너 배경**: `scaleMode: "FILL"` (프레임 전체를 채움)
- **아이콘/그래픽/일러스트**: `scaleMode: "FIT"` (프레임 안에 맞춤, 잘림 없음)
- 이미지를 프레임에 채울 때 기본은 **FIT** — FILL은 히어로/배너만

### 카드형 CTA는 아이콘 대신 그래픽 이미지
- 랜덤박스, 기프트샵, 계산기 등 **카드형 CTA에서 핵심 비주얼이 하나인 경우** → 아이콘 대신 생성 이미지 사용
- UI 기능 표시(탭 바, 리스트 아이템, 네비게이션 등) → 아이콘 사용
- 이미지 생성 후 해당 프레임 내 아이콘 노드가 남아있으면 **반드시 삭제** (이미지를 가림)
- **그래픽 이미지가 들어가는 프레임의 cornerRadius는 반드시 0** — radius가 있으면 이미지가 잘림

### 히어로 이미지 생성 규칙
- `generate_image`에서 `isHero: true`는 **반드시 Banner Card 프레임**에 적용 — Section 프레임 아님
- Banner Card 높이는 항상 200px 고정 — MIN_HERO_SIZE 우회 불필요
- `isHero: false`는 배경 제거 모드 — 히어로/배너에 절대 사용 금지

### 히어로 배너 섹션 상단 여백
- Hero Banner Section은 `paddingTop: 20` 필수 — 위 요소와 배너 카드 사이에 시각적 간격 확보

### 소요시간 트래킹 (필수)
- 사용자가 "피그마로 보내줘"를 말한 시점부터 **시작 시각 기록**
- 최종 완료(QA 통과) 시점에서 **종료 시각 기록**
- 완료 보고 시 반드시 **총 소요시간**을 함께 표시
