# Figma Design Agent — 프로젝트 가이드

## 언어
- 항상 한글로 설명할 것

## 권한
- 이 프로젝트에서 Bash 명령어는 **모두 자동 허용** — `.claude/settings.json`에 `"Bash"` 전체 허용 설정됨
- 별도 승인 요청 없이 바로 실행할 것

## 프로젝트 개요
AI 기반 Figma 디자인 생성 데스크톱 앱: Electron + React + Anthropic SDK

## ⚠️ "디자인 생성 준비" 자동 트리거 (새 Windows 사용자)

> **새 Windows 사용자가 레포를 클론한 뒤 "디자인 생성 준비"(또는 "환경 준비", "준비해줘"
> 등 유사 표현)라고 하면 — 아래 절차를 질문 없이 처음부터 끝까지 자동 실행한다.**
>
> 새 Windows 머신은 Python·Node·의존성이 하나도 없다고 가정한다. 모든 설치는 winget
> 비대화식(silent)이므로 — **설치 방식·winget 사용 여부·버전 업그레이드 동의 등을 사용자에게
> 묻지 말 것.** 멈추지 말고 그냥 끝까지 진행한다. (이번 세션처럼 도구를 일일이 묻지 않는다.)

### 자동 실행 절차
1. **환경 설정** — 다음을 직접 실행한다(⚠️ `npm run ...`이 아니다 — 새 머신엔 npm조차 없음):
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts/setup-windows.ps1
   ```
   멱등 스크립트가 Python·Python 패키지·`PYTHONUTF8`·Node LTS·npm 의존성·sharp·빌드를
   한 번에 처리한다(없으면 winget 설치, 있으면 빠르게 통과). 출력의 `[OK]` 7줄 확인.
   도중에 멈추거나 사용자에게 묻지 말 것.
2. **브리지 기동** — `npm run bridge`를 백그라운드로 실행. 로그에
   `[FigmaWS] Server listening on port 8767` + `[MCP] HTTP server listening`이 뜨면 OK.
3. **MCP 접속 검증** — `figma_mcp_client.py init` 실행(아래 "함정"의 전체 경로 + `PYTHONUTF8=1`).
   `Ready.` + 실제 세션 ID가 나오면 OK (`Session initialized: None`이면 실패 → 브리지/패치 점검).
4. **플러그인 연결 확인** — 브리지 로그에 `Figma: connected`가 있으면 완료. 없으면 사용자에게
   *"Figma 데스크톱 앱에서 플러그인을 실행해 주세요"* 안내 (플러그인 실행은 자동화 불가 — 유일한 수동 단계).
5. **완료 보고** — 준비 완료를 알리고, 디자인할 화면의 PRD/요구사항을 요청한다.

### 멈춰서 사용자에게 보고해도 되는 경우 (이때만)
- winget 자체가 없음 → Microsoft Store "앱 설치 관리자"(App Installer) 설치 안내
- `setup-windows.ps1`이 에러로 종료 → 에러 원문과 함께 보고
- 그 외에는 멈추지 말고 끝까지 자동 진행한다

### setup-windows.ps1이 처리하는 항목 (멱등)
1. **Python 3.12** (winget) — `figma_mcp_client.py` 실행용
2. **Python 패키지** — `requests`, `Pillow` (`-InstallRembg` 옵션 시 `rembg` 추가)
3. **`PYTHONUTF8=1`** 사용자 환경변수 — 없으면 한글 출력이 cp949 `UnicodeEncodeError`
4. **Node.js LTS** (winget) — Vite 6는 Node 18+ 필수 (구버전이면 자동 업그레이드)
5. **npm 의존성** — `.npmrc`의 `legacy-peer-deps=true` (zod peer 충돌 회피)
6. **sharp 네이티브 모듈** — `@img/sharp-win32-x64` 플랫폼 패키지
7. **빌드** — `npm run build` → `out/`

> npm이 이미 있으면 `npm run setup:windows`로도 실행 가능. rembg 포함:
> `powershell -ExecutionPolicy Bypass -File scripts/setup-windows.ps1 -InstallRembg`

### Windows 함정 (스크립트가 처리하지만 참고)
- PATH의 `python3`/`python`은 Microsoft Store 별칭 stub — **실제 Python은 `%LOCALAPPDATA%\Programs\Python\Python3xx\python.exe`**. `figma_mcp_client.py` 호출 시 이 전체 경로 + `PYTHONUTF8=1` 환경변수 사용
- winget 설치 직후 같은 셸 세션은 PATH가 갱신 안 됨 — `node`/`npm`이 안 잡히면 `C:\Program Files\nodejs\` 전체 경로 사용
- 빌드 산출물은 `out/` (main/preload/bridge = CJS, renderer = Vite 번들)
- 브리지: `npm run bridge` — Electron 없이 WS 8767 + HTTP MCP 8769 동시 기동. Python 워크플로우는 이것만 있으면 됨
- `@hono/mcp` 패치: `npm install`의 postinstall이 `scripts/patch-hono-mcp.js`로 Accept 헤더 검사 제거 (없으면 MCP 호출이 406 에러). 패치 실패 로그가 보이면 `@hono/mcp` 버전 변경 — 스크립트 갱신 필요
- `scripts/*.ps1`은 **UTF-8 BOM 필수** — PowerShell 5.1은 BOM 없으면 cp949로 읽어 한글 파싱이 깨짐

## 빌드 & 실행
```bash
npm run dev     # 빌드 + electron 실행
npm run build   # tsup + vite 빌드만
npm start       # electron . (이미 빌드된 상태에서)
```

## 아키텍처
- **Main Process** (`src/main/`): Agent orchestrator (Claude Sonnet 4), FigmaWSServer (port 8767), 58+ 내장 MCP 도구, 4개 DS 조회 도구, Gemini 이미지 생성, 스트리밍 파서
- **Renderer** (`src/renderer/`): React 19, ChatPanel, AgentStatus, FigmaConnection, SettingsPanel, useAgent hook
- **Preload** (`src/preload/`): Context bridge (IPC 보안 통신)
- **Shared** (`src/shared/`): 타입 정의, IPC 채널 상수, DS 데이터 로더
- **Build**: tsup (main+preload → CJS) + Vite (renderer), ws/sharp external

## 주요 파일
| 파일 | 역할 |
|------|------|
| `src/main/index.ts` | Electron 메인 프로세스 진입점, IPC 핸들러 |
| `src/main/agent-orchestrator.ts` | Claude API 기반 에이전트 오케스트레이터 |
| `src/main/figma-ws-server.ts` | Figma 플러그인 WebSocket 서버 (8767) |
| `src/main/figma-mcp-embedded.ts` | 58+ Figma MCP 도구 레지스트리 |
| `src/main/image-generator.ts` | Gemini API 이미지 생성 (동적 API 키) |
| `src/main/settings-store.ts` | 설정 저장소 (userData/settings.json) |
| `src/main/ds-lookup-tools.ts` | 디자인 시스템 조회 도구 4종 |
| `src/shared/types.ts` | 공유 타입 및 IPC 채널 상수 |
| `src/preload/index.ts` | Context bridge (electronAPI 노출) |
| `src/renderer/App.tsx` | 루트 React 컴포넌트 |
| `src/renderer/hooks/useAgent.ts` | 에이전트 상태 관리 훅 |
| `src/renderer/components/SettingsPanel.tsx` | Gemini API 키 설정 UI |
| `src/renderer/components/FigmaConnection.tsx` | Figma 연결 상태 UI |

## 설정 저장 방식
- `electron-store` v10은 ESM 전용이라 tsup CJS 번들링 불가
- 대신 `app.getPath('userData')/settings.json` + fs 사용
- `src/main/settings-store.ts`에서 `getGeminiApiKey()` / `setGeminiApiKey()` 제공

## Plugin & Build
- Plugin code: `src/claude_mcp_plugin/code.js` (plain JS, Figma sandbox — no optional chaining `?.`)
- MCP server: TypeScript, built by `tsup` via `npm run build`
- `npm run build` → out/ (main/preload/bridge = CJS, renderer = Vite 번들)
- 배포용 앱 패키지: `npm run package` (electron-builder)

### Git Commit & Push 규칙
- `src/` 코드 변경이 포함된 커밋은 **`npm run build`로 빌드 검증 후** 커밋 (docs/ds/scripts만 변경 시 생략 가능)
- 순서: (필요 시 `npm run build`) → git add → git commit → git push

## 알려진 이슈
- DesignPreview 컴포넌트 참조되지만 미구현
- 테스트 없음 (단위/통합)
- Figma 도구 호출 캐싱 없음

---

## 디자인 빌드 빠른 워크플로우 (템플릿 기반)

> **새 화면 디자인 시 이 워크플로우를 우선 사용** — Blueprint 전체를 수작업으로 작성하지 말 것

```bash
# 1. 조립 설정 JSON 작성 (고정 섹션은 템플릿, PRD 고유 섹션만 직접 작성)
# → 템플릿: NavBar, TransactionRibbon, HeroSection, FAB, TabBar
# → custom: PRD에 따라 달라지는 섹션들

# 2. Blueprint 조립
python3 scripts/figma_mcp_client.py assemble scripts/my_config.json

# 3. 빌드 (+ 자동 post-fix + 자동 이미지 생성)
python3 scripts/figma_mcp_client.py build scripts/blueprint_assembled_XXX.json

# 4. Status Bar·로고는 빌드가 자동 처리 (규칙 1) — blueprint에 넣지 않으면
#    batch_build_screen이 DS Status Bar 자동 삽입, cmd_build가 로고 자동 교체
# 5. 스크린샷 QA
```

- **템플릿 파일**: `scripts/blueprint_templates.json` (5개 섹션, ~600줄)
- **효과**: NavBar+TabBar+FAB+Hero+Ribbon ~400줄 자동 생성 → Claude는 custom 섹션만 작성
- **변수 치환**: FAB(label/icon), Ribbon(text), Hero(banners[tag/title/imagePrompt]), TabBar(activeTab)

---

## 디자인 생성 필수 규칙

### 1. ⚠️ Status Bar는 blueprint에 넣지 말 것 — 빌드가 DS Status Bar를 자동 삽입
- **Status Bar를 텍스트/프레임으로 직접 그리거나 blueprint 노드로 넣지 말 것.**
- `batch_build_screen`은 blueprint root.children에 status bar 노드가 **없으면 DS "Status Bar" 인스턴스를 루트 첫 자식으로 자동 삽입**한다. blueprint에 "Status Bar" 같은 노드를 넣으면 빌드가 그걸 그대로 써서 직접 그린 status bar가 박힌다(= 버그).
- **규칙: blueprint root.children에 status bar를 절대 포함하지 않는다.** 빌드가 알아서 DS 인스턴스를 넣는다.
- **로고**: NavBar에 `"Logo Placeholder"` 프레임(80×32)을 넣으면 `cmd_build`가 DS 로고 인스턴스로 자동 교체한다(Step G). 텍스트로 로고를 그리지 말 것.
- **빌드 후 검증**: 루트 첫 자식이 INSTANCE `"Status Bar"`인지 확인.
- 참고: "Styles" 페이지(`276:1882`)에 마스터 인스턴스가 있다 — Status Bar `279:4758`, 로고 `279:4757`. 자동 삽입이 안 되는 특수 상황에서만 `clone_node`(인스턴스는 clone해도 인스턴스 유지) 후 `insert_child`로 수동 삽입.

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

### 7. Tab Bar 아이템 — vertical FILL + 텍스트 CENTER 정렬
- Tab Bar 내 모든 아이템: `layoutSizingVertical: "FILL"` (아이콘+텍스트 세로 정렬 일치)
- 모든 Tab Label 텍스트: `textAlignHorizontal: "CENTER"`, `layoutSizingHorizontal: "FILL"`
- HUG 텍스트 + FILL 아이템 혼용 시 아이콘과 텍스트 정렬이 어긋남

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

---

## 빌드 후 자동 후처리 (post-fix)

> `build` 명령 완료 시 자동으로 `post-fix`가 실행된다. 별도 실행도 가능:
> ```bash
> python3 scripts/figma_mcp_client.py post-fix <rootNodeId>
> ```

**post-fix가 자동 수정하는 항목 (5단계):**
```
1. FILL 검증/수정: 모든 FRAME 자식 → FILL (FAB/Tab Bar 제외, SPACE_BETWEEN 마지막 HUG 자식 보존)
   - _walk: 재귀적 FILL 수정 (parent_layout_mode 빈 문자열이면 skip 안 함)
   - 안전장치: 재귀적 FILL 강제 (depth 4까지, VERTICAL 부모의 모든 FRAME 자식)
2. 섹션 간격: 배경색 동일 + divider 없는 인접 섹션 → gap 0
3. Tab Bar/FAB: ABSOLUTE 배치 + 루트 하단 위치 + FAB width 복원 (HUG)
4. Tab Bar item FILL 통일 + Tab Row individual stroke (bottom-only)
5. zero-width 텍스트: width=0 TEXT → textAutoResize="WIDTH_AND_HEIGHT" + FILL (Banner Card 내부 텍스트는 FIXED 160px)
```

**cmd_build 루트 auto-layout 보호:**
```
- batch_build_screen 완료 후, 루트가 이미 VERTICAL이면 set_auto_layout 재호출 금지
- layoutMode 재설정 시 Figma가 자식 layoutSizingHorizontal을 HUG로 리셋하는 버그 방지
- 루트가 VERTICAL 아닐 때만 set_auto_layout 호출 (최초 설정용)
```

**post-fix가 수정하지 않는 항목 (수동 확인 필요):**
```
1. 캐로셀 구조: HORIZONTAL 래퍼 + clipsContent (Blueprint에서 올바르게 설정해야 함)
2. 텍스트 가시성: 색상 대비 (스크린샷으로 확인)
```

---

## 상세 문서 (작업 시 필요한 문서만 Read로 로드)

> 아래 문서는 **해당 작업을 수행할 때만** Read 도구로 로드한다. 매번 전부 읽지 않는다.

| 문서 | 언제 읽는가 |
|------|------------|
| [`docs/ds-architecture.md`](docs/ds-architecture.md) | DS 토큰 조회, 변수 업데이트, MCP 도구 목록 확인, INSTANCE_SWAP 시 |
| [`docs/design-rules.md`](docs/design-rules.md) | **디자인 생성/수정 시 필수** — 빌드 규칙, 컴포넌트, 색상, 타이포그래피, 이미지 생성 규칙 |
| [`docs/mobile-patterns.md`](docs/mobile-patterns.md) | 모바일 화면 디자인 시 — 레이아웃 패턴, 화면 사이즈, Status Bar |
| [`docs/qa-checklist.md`](docs/qa-checklist.md) | 디자인 완료 QA 시 — 13개 체크 항목, 스크린샷 촬영 방법, 완료 판단 기준 |
| [`docs/image-generation.md`](docs/image-generation.md) | Gemini 이미지 생성 시 — API 사용법, 스타일 기본값, rembg 파이프라인 |
| [`docs/multi-agent-design.md`](docs/multi-agent-design.md) | 복잡한 화면(섹션 3+, 이미지 1+) 디자인 시 — 멀티에이전트 모드 |
| [`docs/pencil-to-figma.md`](docs/pencil-to-figma.md) | "figma로 보내줘" 요청 시 — Pencil→Figma 변환 워크플로우, Blueprint 규칙 |
| [`docs/python-mcp-client.md`](docs/python-mcp-client.md) | batch_build_screen, DS 바인딩 등 대규모 작업 시 — Python HTTP 클라이언트 |
