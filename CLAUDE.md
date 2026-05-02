# Figma Design Agent — 프로젝트 가이드

## 언어
- 항상 한글로 설명할 것

## 권한
- 이 프로젝트에서 Bash 명령어는 **모두 자동 허용** — `.claude/settings.json`에 `"Bash"` 전체 허용 설정됨
- 별도 승인 요청 없이 바로 실행할 것

## 프로젝트 개요
AI 기반 Figma 디자인 생성 데스크톱 앱: Electron + React + Anthropic SDK

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
- `npm run build` → dist/ (CJS + ESM)

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

# 4. 로고 인스턴스 교체 (NavBar Logo Placeholder → 실제 로고)
# 5. 스크린샷 QA
# 6. ⚠️ 변수 바인딩 검증 (필수) — 아래 규칙 #26 참조
```

- **템플릿 파일**: `scripts/blueprint_templates.json` (5개 섹션, ~600줄)
- **효과**: NavBar+TabBar+FAB+Hero+Ribbon ~400줄 자동 생성 → Claude는 custom 섹션만 작성
- **변수 치환**: FAB(label/icon), Ribbon(text), Hero(banners[tag/title/imagePrompt]), TabBar(activeTab)

---

## 디자인 생성 — `docs/design.md` 룰 필수 적용

> **사용자가 PRD/와이어프레임/Figma 화면 만들기를 요청하는 즉시 [`docs/design.md`](docs/design.md)를 Read해서 모든 룰을 확인할 것.**
>
> 이 CLAUDE.md에는 룰 본문을 두지 않는다 — 컨텍스트 효율을 위해서다. 본문은 `docs/design.md`에서 한 번에 로드.

### 디자인 생성 트리거 키워드
- "디자인 생성/만들어줘/제작/그려줘"
- "PRD 디자인", "와이어프레임 → 디자인"
- "Figma에 만들어줘", "이 화면 그려줘"
- "blueprint 빌드", "post-fix 실행"
- imin-home / imin-stage-* 등 레퍼런스 작업
- 사용자가 Figma node URL/ID를 언급한 경우

### 🚨 세션 운영 규칙 (2026-05-01 명시 지시)
- **Prefetch는 세션당 1회만**: 새 세션의 첫 디자인 발화에서만 SessionStart hook의 룰 문서 + DS 컴포넌트 29개 병렬 prefetch 실행. 같은 세션 내 후속 디자인 작업에서는 **절대 재prefetch 금지** (이미 로드된 컨텍스트 재사용). 새 컴포넌트가 꼭 필요한 경우에만 해당 1개 페이지 타겟 WebFetch.
- **매핑표 후 사용자 확인 금지 → 자동 마무리**: Step 3에서 와이어프레임 ↔ DS 매핑표를 보고했더라도 "진행할까요?" / "이대로 OK면..." 같은 확인 질문 절대 던지지 말 것. 매핑표 출력 직후 곧장 Step 4 Blueprint 작성 → build → post-fix → token-bind → 스크린샷 QA → 최종 보고까지 **한 번에 자동 마무리**. 매핑이 정말 모호할 때만 AskUserQuestion 사용.
- **🚨 clone_node 절대 금지 — scratch에서 polished 디자인이 기본**: 와이어프레임/PRD → 디자인 작업에서 `clone_node`/`copy.deepcopy` 등으로 기존 빌드된 Figma 노드를 복사하는 행위 절대 금지. 룰 #23의 "deepcopy"는 sections-*.jsx 등 **코드/구조의 deepcopy**이지 빌드 결과물의 clone이 아님. production의 다른 사용자에겐 cloned 레퍼런스가 없으므로 **scratch에서 sections-*.jsx의 모든 micro-detail(gradient avatar / ABSOLUTE crown / card shadow / outline pill / FAB 52sq / brand 카드 alpha-white sub-component)을 정밀 재현하는 게 기본 기준선**. 위반 시 사용자 강력 분노. 자세한 체크리스트는 `docs/design.md` 룰 #37 참조.

### 디자인 생성 작업 시작 직후 필수 절차 (5단계 SOP — `docs/design.md` 상단 참조)
1. **Step 1 — 룰 로드**: `Read docs/design.md` + `docs/references/INDEX.md` (필요 시 `design-rules.md`)
2. **Step 2 — DS 카탈로그 사전 조회 필수**: `Read ds/DS_COMPONENT_DOCS.json` + `get_remote_components` / `get_local_components` + DS 문서 사이트 WebFetch
3. **Step 3 — 와이어프레임 UI ↔ DS 컴포넌트 매핑 표 자동 작성** (DS에 없는 unique 요소만 frame raw, 사용자 확인 없이 즉시 Step 4 진행)
4. **Step 4 — Blueprint 작성**: 모든 UI를 `type:"instance"` + `componentKey`로 명시. 카드 위계 한 단계씩(점프 금지). 와이어프레임 UI 모두 유지.
5. **Step 5 — 빌드 + 검증 + 보고**: 사용한 DS 컴포넌트 목록 + Token 바인딩 카운트 명시
- ⚠️ **Step 2 건너뛰기 절대 금지**. raw frame으로 Button/Pill/Avatar 시뮬레이션 = 사용자 분노 트리거.

### 룰 핵심 5개 (자세한 본문은 `docs/design.md`):
- 🚨 DS 문서 사이트(https://twavetech-frontend.github.io/design-system-docs/) WebFetch 우선 사용 — 컴포넌트 임의 발명 금지
- 🎨 컬러는 `1. Color modes` 시멘틱 토큰만 — _Primitives 스케일·`-disabled`·`_hover` 금지 (mobile은 hover 없음)
- 📐 카드 위계 (v2): `bg-primary` (#ffffff) > `bg-secondary` (#f3f4f6) > `bg-tertiary` (#e6e8ea) > `bg-quaternary` (#d2d6db)
- 🟣 Brand-bg(보라 카드) 위 sub-component: `alpha-white-10`(Pill/Panel) + `alpha-white-20`(Slider Track) + `#e6e8ea` 단단한 grey(Slider Fill/Thumb, Stepper btn)
- 📅 Day Card 4상태 / SummaryCard 헤더 = `[Title 좌측 / Pill 우측]` / Progress = `bg-tertiary` track + `#70f` fill — 자세한 패턴은 `docs/design.md` 룰 #30~#32
- ✅ 빌드 마지막 단계: Semantic Token Binding 검증 필수 — 사용자 보고 시 `Token 바인딩: colors=N numbers=M text=K` 카운트 명시

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
| [`docs/design.md`](docs/design.md) | **🚨 디자인 생성/수정 트리거 발견 즉시 필수** — 룰 #1~#29 + DS 검색 우선 + 빌드 파이프라인 + 보고 형식 |
| [`docs/ds-architecture.md`](docs/ds-architecture.md) | DS 토큰 조회, 변수 업데이트, MCP 도구 목록 확인, INSTANCE_SWAP 시 |
| [`docs/design-rules.md`](docs/design-rules.md) | VS1~VS8 시각 규칙 + 컴포넌트/타이포 스케일 (design.md와 별도, 보충 자료) |
| [`docs/references/imin-home/`](docs/references/imin-home/) | **공식 비주얼 스타일 레퍼런스** — 아임인 홈 화면 Figma Make export. `template.html` (토큰+구조), `sections-1.jsx` (Header/Tabs/Alert/Summary/Schedule/Limit), `sections-2.jsx` (Recommender/Stages/Attendance/Banner/Lounge/Cumulative/Nav). 시각 디테일이 모호할 때 참조 |
| [`docs/mobile-patterns.md`](docs/mobile-patterns.md) | 모바일 화면 디자인 시 — 레이아웃 패턴, 화면 사이즈, Status Bar |
| [`docs/qa-checklist.md`](docs/qa-checklist.md) | 디자인 완료 QA 시 — 13개 체크 항목, 스크린샷 촬영 방법, 완료 판단 기준 |
| [`docs/image-generation.md`](docs/image-generation.md) | Gemini 이미지 생성 시 — API 사용법, 스타일 기본값, rembg 파이프라인 |
| [`docs/multi-agent-design.md`](docs/multi-agent-design.md) | 복잡한 화면(섹션 3+, 이미지 1+) 디자인 시 — 멀티에이전트 모드 |
| [`docs/pencil-to-figma.md`](docs/pencil-to-figma.md) | "figma로 보내줘" 요청 시 — Pencil→Figma 변환 워크플로우, Blueprint 규칙 |
| [`docs/python-mcp-client.md`](docs/python-mcp-client.md) | batch_build_screen, DS 바인딩 등 대규모 작업 시 — Python HTTP 클라이언트 |
