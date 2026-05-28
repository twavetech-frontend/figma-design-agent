# Figma Design Agent — 프로젝트 가이드

## 언어
- 항상 한글로 설명할 것

## 권한
- 이 프로젝트에서 Bash 명령어는 **모두 자동 허용** — `.claude/settings.json`에 `"Bash"` 전체 허용 설정됨
- 별도 승인 요청 없이 바로 실행할 것

## 프로젝트 개요
AI 기반 Figma 디자인 생성 데스크톱 앱: Electron + React + Anthropic SDK

## ⚠️ "디자인 생성 준비" 자동 트리거 (새 사용자 — Windows / macOS)

> **새 사용자가 레포를 클론한 뒤 "디자인 생성 준비"(또는 "환경 준비", "준비해줘"
> 등 유사 표현)라고 하면 — 아래 절차를 질문 없이 처음부터 끝까지 자동 실행한다.**
>
> OS는 `uname` 또는 환경 정보로 자동 판단한다. Windows면 `setup-windows.ps1`, macOS면
> `setup-mac.sh`를 실행한다. 두 스크립트 모두 멱등(이미 설치된 항목은 건너뜀)이며
> 비대화식(silent)이다 — **설치 방식·패키지 매니저(winget/brew) 사용 여부·버전 업그레이드
> 동의 등을 사용자에게 묻지 말 것.** 멈추지 말고 그냥 끝까지 진행한다.

### 자동 실행 절차 (공통)
1. **환경 설정** — OS에 맞는 스크립트를 직접 실행한다(⚠️ `npm run ...`이 아니다 — 새 머신엔
   npm조차 없을 수 있음).
   - **Windows**:
     ```powershell
     powershell -ExecutionPolicy Bypass -File scripts/setup-windows.ps1
     ```
   - **macOS**:
     ```bash
     bash scripts/setup-mac.sh
     ```
   멱등 스크립트가 패키지 매니저(winget/brew)·Python·Python 패키지·Node LTS·npm 의존성·
   sharp 네이티브 모듈·빌드를 한 번에 처리한다. 출력의 `[OK]` 라인들을 확인.
   도중에 멈추거나 사용자에게 묻지 말 것.
2. **브리지 기동** — `npm run bridge`를 백그라운드로 실행. 로그에
   `[FigmaWS] Server listening on port 8767` + `[MCP] HTTP server listening`이 뜨면 OK.
3. **MCP 접속 검증** — `figma_mcp_client.py init` 실행.
   `Ready.` + 실제 세션 ID가 나오면 OK (`Session initialized: None`이면 실패 → 브리지/패치 점검).
4. **플러그인 연결 확인** — 브리지 로그에 `Figma: connected`가 있으면 완료. 없으면 사용자에게
   *"Figma 데스크톱 앱에서 플러그인을 실행해 주세요"* 안내 (플러그인 실행은 자동화 불가 — 유일한 수동 단계).
5. **완료 보고** — 준비 완료를 알리고, 디자인할 화면의 PRD/요구사항을 요청한다.

### 멈춰서 사용자에게 보고해도 되는 경우 (이때만)
- **Windows**: winget 자체가 없음 → Microsoft Store "앱 설치 관리자"(App Installer) 설치 안내
- **macOS**: Homebrew 자동 설치가 sudo 비밀번호 입력 실패로 종료 → 사용자에게 Homebrew
  수동 설치 안내 (`/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`)
- 셋업 스크립트가 그 외 에러로 종료 → 에러 원문과 함께 보고
- 그 외에는 멈추지 말고 끝까지 자동 진행한다

### setup-windows.ps1이 처리하는 항목 (멱등)
1. **Python 3.12** (winget) — `figma_mcp_client.py` 실행용
2. **Python 패키지** — `requests`, `Pillow`
3. **`PYTHONUTF8=1`** 사용자 환경변수 — 없으면 한글 출력이 cp949 `UnicodeEncodeError`
4. **Node.js LTS** (winget) — Vite 6는 Node 18+ 필수 (구버전이면 자동 업그레이드)
5. **npm 의존성** — `.npmrc`의 `legacy-peer-deps=true` (zod peer 충돌 회피)
6. **sharp 네이티브 모듈** — `@img/sharp-win32-x64` 플랫폼 패키지
7. **빌드** — `npm run build` → `out/`

> npm이 이미 있으면 `npm run setup:windows`로도 실행 가능.

### setup-mac.sh가 처리하는 항목 (멱등)
1. **Homebrew** — 없으면 비대화식 설치 시도(`NONINTERACTIVE=1`). sudo 입력 필요할 수 있음
2. **Python 3** — 시스템 `python3`(3.9+) 우선, 없으면 `brew install python@3.12`
3. **Python 패키지** — `requests`, `Pillow`. PEP 668 환경(Homebrew Python)에서는
   `--break-system-packages` → 실패 시 `--user` 폴백
4. **Node.js LTS** (Homebrew) — Vite 6는 Node 18+ 필수
5. **npm 의존성** — `.npmrc`의 `legacy-peer-deps=true`
6. **sharp 네이티브 모듈** — Apple Silicon은 `@img/sharp-darwin-arm64`, Intel은 `darwin-x64`
   (`uname -m`으로 자동 판단)
7. **빌드** — `npm run build` → `out/`

> npm이 이미 있으면 `npm run setup:mac`으로도 실행 가능.

### Windows 함정 (스크립트가 처리하지만 참고)
- PATH의 `python3`/`python`은 Microsoft Store 별칭 stub — **실제 Python은 `%LOCALAPPDATA%\Programs\Python\Python3xx\python.exe`**. `figma_mcp_client.py` 호출 시 이 전체 경로 + `PYTHONUTF8=1` 환경변수 사용
- winget 설치 직후 같은 셸 세션은 PATH가 갱신 안 됨 — `node`/`npm`이 안 잡히면 `C:\Program Files\nodejs\` 전체 경로 사용
- 빌드 산출물은 `out/` (main/preload/bridge = CJS, renderer = Vite 번들)
- 브리지: `npm run bridge` — Electron 없이 WS 8767 + HTTP MCP 8769 동시 기동. Python 워크플로우는 이것만 있으면 됨
- `@hono/mcp` 패치: `npm install`의 postinstall이 `scripts/patch-hono-mcp.js`로 Accept 헤더 검사 제거 (없으면 MCP 호출이 406 에러). 패치 실패 로그가 보이면 `@hono/mcp` 버전 변경 — 스크립트 갱신 필요
- `scripts/*.ps1`은 **UTF-8 BOM 필수** — PowerShell 5.1은 BOM 없으면 cp949로 읽어 한글 파싱이 깨짐

### macOS 함정 (스크립트가 처리하지만 참고)
- Homebrew 경로는 아키텍처별로 다름 — **Apple Silicon은 `/opt/homebrew`, Intel은 `/usr/local`**. 스크립트가 `uname -m`으로 자동 판단
- Homebrew 설치 직후 같은 셸 세션은 PATH가 갱신 안 됨 — 스크립트가 `brew shellenv`로 즉시 적용
- macOS 12+의 시스템/Homebrew Python은 **PEP 668(externally-managed-environment)** 적용 → `pip install` 시 `--break-system-packages` 또는 `--user` 필요. 스크립트가 자동 처리
- 시스템 `/usr/bin/python3`은 Xcode CLT 번들이라 버전이 고정됨 — Homebrew Python이 있으면 그것을 우선 사용
- macOS는 기본 UTF-8 로케일이라 `PYTHONUTF8` 불필요
- sharp 네이티브 모듈: nvm 사용자는 Node 메이저 버전 바뀔 때마다 `node_modules` 삭제 + 재설치 필요할 수 있음

## 빌드 & 실행
```bash
npm run dev     # 빌드 + electron 실행
npm run build   # tsup + vite 빌드만
npm start       # electron . (이미 빌드된 상태에서)
```

## 아키텍처
- **Main Process** (`src/main/`): Agent orchestrator (Claude Sonnet 4), FigmaWSServer (port 8767), 58+ 내장 MCP 도구, 4개 DS 조회 도구, 스트리밍 파서
- **Renderer** (`src/renderer/`): React 19, ChatPanel, AgentStatus, FigmaConnection, useAgent hook
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
| `src/main/ds-lookup-tools.ts` | 디자인 시스템 조회 도구 4종 |
| `src/shared/types.ts` | 공유 타입 및 IPC 채널 상수 |
| `src/preload/index.ts` | Context bridge (electronAPI 노출) |
| `src/renderer/App.tsx` | 루트 React 컴포넌트 |
| `src/renderer/hooks/useAgent.ts` | 에이전트 상태 관리 훅 |
| `src/renderer/components/FigmaConnection.tsx` | Figma 연결 상태 UI |

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

# 3. 빌드 (+ 자동 post-fix)
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

> 🔴 **절대 규칙 0-E — 와이어프레임 콘텐츠 1:1 추출 의무 / archetype config 재사용 금지 (2026-05-27 사용자 분노)**
>
> 새 세션에서 와이어프레임을 받아 디자인을 빌드할 때, **와이어의 실제 텍스트/숫자/카운트
> 를 그대로 빌드에 박는다.** v12 같은 이전 archetype 빌드의 config(`config_*.json`)를
> 복사해 새 v13으로 재사용하지 말 것 — **콘텐츠가 v12 더미 데이터 그대로 박혀서 와이어 의도
> 무시 + 사용자 격분**.
>
> **사례 (이번 회귀)**:
> - 와이어: "진행중인 **0건**의 스테이지 내역 / 모은 금액 **+0원** / 빌린 금액 **-0원**"
> - 빌드(v13=v12 reuse): "3건 / +14,420,320원 / -5,240,020원" (v12 더미 그대로)
> - 와이어: Day Strip "**14~19일 6 cell × +0원**" / 빌드: "미납 28일/오늘 4일/지급 12일/예정 18일" (다른 컨셉)
> - 와이어 1.5: "**10만원 stepper + 13개월 stepper + 1~13 회차 round selector + 1회차 + 납입 후 목적 수령 + 총 1300만원 모으기 도전**"
> - 빌드: "예상 수령 금액/총 1,300만원/회차 stepper 3개" (1~13 round selector 누락)
>
> **워크플로우 — 무조건 이 순서**:
> 1. **와이어 export** (`mcp__figma-tools__export_node_as_image`) → 사람이 읽을 수 있는 이미지
> 2. **콘텐츠 추출 dict 작성** — 섹션별로 모든 텍스트/숫자/카운트/아이콘 종류를 추출:
>    ```json
>    {
>      "1.3 진행 현황 카드": {
>        "header": "진행중인 0건의 스테이지 내역",
>        "more": "자세히 >",
>        "rows": [{"label": "모은 금액", "value": "+0원"}, {"label": "빌린 금액", "value": "-0원"}],
>        "dayStrip": ["14일", "15일", "16일", "17일(today)", "18일", "19일"],
>        "dayValues": ["0원", "0원", "0원", "0원", "0원", "0원"],
>        "calcCTA": "얼마까지 모을 수 있는 지 확인해보세요"
>      },
>      ...
>    }
>    ```
> 3. **blueprint root._wireframeContent 필드에 dict 박기** — `cmd_build` Step E.6.5 의
>    `_qa_wireframe_content_match` 가 blueprint TEXT characters 와 dict 매치 검증. 미스매치 ≥30% 시 build 차단
> 4. **config 는 처음부터 작성** — `cp config_*.json` 금지. 와이어 dict 기반으로 새 config 작성
> 5. 그 다음 assemble → build → post-fix → token bind → QA 2 pass
>
> **자동 강제 (코드 박힘)**:
> 1. `figma_mcp_client.py cmd_build` Step E.0 `_check_no_archetype_reuse` (S22) —
>    config 의 textual 패턴이 이전 빌드 산출물과 70%+ 일치 시 build 차단(ERROR)
> 2. `cmd_build` Step E.0 `_check_wireframe_content_required` (S23) —
>    imin_* archetype 빌드인데 root._wireframeContent dict 도 _wireframeContentSkipped 도
>    없으면 build 차단(ERROR). bypass: `"_wireframeContentSkipped": "<reason>"`
> 3. `cmd_build` Step E.6.5 `_qa_wireframe_content_match` —
>    blueprint TEXT characters 가 root._wireframeContent dict 와 매치 검증. 30%+ 미스매치 시 WARN, 50%+ 시 ERROR
>
> **Why**: 새 세션 컨텍스트 부족 → "imin_home은 v12 있으니 base 가져가자" 본능 → 더미 데이터 박힘 → 사용자가 "와이어 무시"라고 분노. 시스템이 와이어 콘텐츠 추출을 강제하지 않으면 매번 새 세션마다 회귀.
>
> **참고**: 메모리 [feedback_no_wireframe_clone] 은 **시각 위계** 만 재해석하라는 뜻 — 카드 그림자/타이포/그룹화 같은 디자인 판단. **콘텐츠(텍스트/숫자/카운트)는 와이어 1:1**.

> 🔴 **절대 규칙 0 — 루트 프레임(화면 최상위 프레임) 배경색은 반드시 `bg-primary`**
>
> 루트 프레임의 `fill`은 **무조건 `$token(bg-primary)`**(`#fcfcfd`, 거의 흰색)여야 한다.
> `bg-secondary`(`#f3f4f6`, 회색) 등 다른 값을 쓰면 **버그**다. 화면 배경이 회색으로
> 보이면 무조건 이 규칙 위반이다.
>
> - blueprint 작성 시 root `fill`을 처음부터 `$token(bg-primary)`로 쓸 것.
> - 이 규칙은 빌드 파이프라인 **3곳에서 자동 강제**된다 — 그래도 blueprint에서 직접 지킬 것:
>   1. `figma_mcp_client.py cmd_build` → `_enforce_root_bg_primary()`: 빌드 전 blueprint root fill을 `$token(bg-primary)`로 강제 교정
>   2. `figma_mcp_client.py post-fix` → `_enforce_root_bg_primary_live()`: 빌드된 루트 노드 배경을 bg-primary로 런타임 강제(리터럴 + DS 변수 바인딩)
>   3. `figma-mcp-embedded.ts enhanceBlueprint`: 모든 `batch_build_screen` 호출에서 root fill을 bg-primary로 교정
> - **빌드 후 검증**: 스크린샷에서 콘텐츠 카드 바깥 배경이 회색이 아닌 흰색(`bg-primary`)인지 확인.

> 🔴 **절대 규칙 0-D — Modal 기본형 = Bottom Sheet (2026-05-27)**
>
> Modal 의 **기본형은 bottom sheet** — 화면 세로의 절반 정도로 표시되고, 뒤에 원래
> 화면 위 **dimmed overlay** 가 깔린 채 **bottom 에 붙어서** 슬라이드업.
>
> Blueprint 작성 시 `_screenType: "bottom-sheet"` 명시. 빌드 후 자동:
> 1. Root 852 FIXED (디바이스 viewport)
> 2. 1st 자식 = **Dim Overlay** (FILL, alpha-black 50%) — 위쪽 가용 공간 채움
> 3. 2nd 자식 = **Modal Sheet** (FILL, HUG, bg-primary, top-rounded 24px) — 콘텐츠 wrap
>
> 강제 함수: `_enforce_bottom_sheet_pattern` (cmd_build pre-process)
> 회귀 테스트: `scripts/tests/test_bottom_sheet_pattern.py` 14개 케이스
>
> **Modal 두 가지 구분:**
> - `_screenType: "bottom-sheet"` (기본형) — 반 화면 + dim overlay + bottom anchor
> - `_screenType: "modal"` (full modal) — 전체 화면 modal, X 닫기만 (Footer/Tab 제거)
>
> ⚠️ 새 modal 빌드는 기본 `bottom-sheet` 사용. full modal 필요시에만 `modal` 명시.

> 🔴 **절대 규칙 0-C — 와이어프레임 1:1 복제 금지, 창의적 재해석 의무 (2026-05-27)**
>
> 와이어프레임의 **레이아웃 · 정보 위계 · 포인트 컬러**를 그대로 베끼면 안 된다.
> 와이어프레임은 **콘텐츠 source**일 뿐 layout/visual blueprint 가 아니다.
>
> **금지:**
> - 와이어프레임의 회색 박스 배치를 그대로 frame 배치로 옮기는 것
> - 와이어프레임의 글자 크기 위계를 그대로 fontSize 로 옮기는 것 (예: 와이어 본문이 다 같은 크기여도 디자인에선 hero/section/body 차등)
> - 와이어프레임의 포인트 컬러(빨강·파랑 등) 를 그대로 brand 외 컬러로 옮기는 것
>
> **필수:**
> - **가독성 / 시인성 / 미학** 우선으로 시각 위계 재구성
> - 핵심 수치는 hero size (28~36px Bold), 카드 그룹화로 정보 위계 차등
> - 반복 요소(카드 리스트 등)는 첫 번째를 강조하거나 차등 적용
> - **약간의 창의적 컬러 사용**: 상태 표시(성공/완료/주의) 에 brand tint + 시맨틱 액센트 소량 (브랜드 일관)
> - 와이어프레임에 없는 폴리시(카드 그림자/elevation, 도형-배경 대비, 강한 타이포 위계) 추가
>
> **Why:** 와이어프레임을 그대로 옮기면 "디자인을 한 게 아니라 와이어를 강화한 것"이 된다.
> 사용자가 디자이너에게 기대하는 건 **콘텐츠를 받아 디자인적 판단을 더한 결과물**이지,
> 와이어를 px-perfect 로 옮기는 게 아니다.
>
> **검증 (사람이 확인):**
> - 빌드 후 스크린샷을 와이어프레임 옆에 놓고 비교 — 시각 위계/그룹화/액센트가 **달라야** 정상
> - 똑같으면 룰 위반 → 재구성
>
> 코드로 자동 검출 불가능 (의미적 판단). 매 디자인 빌드 시 사람(Claude)이 자체 검증.

> 🔴 **절대 규칙 0-B — `-alt` / `_alt` 변형 토큰은 절대 쓰지 말 것**
>
> `bg-secondary-alt`, `border-secondary-alt` 같은 `-alt` 토큰은 **금지**다.
> `bg-secondary`가 필요하면 **반드시 `$token(bg-secondary)`** — 절대 `-alt`를 붙이지 말 것.
> (figmaPath에서는 `_alt`(언더스코어)로 표기되지만 blueprint에는 `-alt`·`_alt` 둘 다 쓰지 않는다.)
>
> - 빌드 파이프라인이 `$token(...-alt)` / `$token(..._alt)`를 자동으로 기본 토큰으로 교정한다:
>   1. `figma_mcp_client.py` `resolve_token_ref` / `_token_to_figma_path` → `_strip_alt_token()`으로 `-alt` 제거 + **마지막 세그먼트 '정확 일치' 우선 매칭**
>   2. `figma-mcp-embedded.ts` `set_bound_variables` → 바인딩 경로의 `_alt`/`-alt` 접미사 제거
> - ⚠️ 과거 버그: 토큰 매칭이 `startswith(name + "_")`를 허용해 `$token(bg-secondary)`가
>   `bg-secondary_alt`로 오매칭됐다 — 이제 '정확 일치' 우선이라 해결됨.

### 1. ⚠️ Status Bar는 blueprint에 넣지 말 것 — 빌드가 DS Status Bar를 자동 삽입
- **Status Bar를 텍스트/프레임으로 직접 그리거나 blueprint 노드로 넣지 말 것.**
- `batch_build_screen`은 blueprint root.children에 status bar 노드가 **없으면 DS "Status Bar" 인스턴스를 루트 첫 자식으로 자동 삽입**한다. blueprint에 "Status Bar" 같은 노드를 넣으면 빌드가 그걸 그대로 써서 직접 그린 status bar가 박힌다(= 버그).
- **규칙: blueprint root.children에 status bar를 절대 포함하지 않는다.** 빌드가 알아서 DS 인스턴스를 넣는다.
- **로고**: NavBar에 `"Logo Placeholder"` 프레임(80×32)을 넣으면 `cmd_build`가 DS 로고 인스턴스로 자동 교체한다(Step G). 텍스트로 로고를 그리지 말 것.
- **빌드 후 검증**: 루트 첫 자식이 INSTANCE `"Status Bar"`인지 확인.
- 참고: "Styles" 페이지(`276:1882`)에 마스터 인스턴스가 있다 — Status Bar `279:4758`, 로고 `279:4757`. 자동 삽입이 안 되는 특수 상황에서만 `clone_node`(인스턴스는 clone해도 인스턴스 유지) 후 `insert_child`로 수동 삽입.

### 2-H. ⚠️ 큰 면적 frame에 brand color 채우기 금지 (2026-05-27 사용자 명시)
- **"추천 스테이지 섹션같이 버튼이 아니면서 면적이 큰 frame에 brand color를 채우지마!"**
- 이전 룰 폐기 — "Recommend Brand Card = brand-solid hero" 패턴 (`bg-brand-solid` 보라색 큰 카드) 사용자 분노.
- **새 표준**: 큰 카드 = `bg-primary` + `border-secondary` 1px. brand 는 **작은 액센트**(텍스트, 버튼 label, 작은 dot)만.
- **사용자 reference 패턴** (17380:48334 분석):
  - Recommend Brand Card: `bg-primary` 흰 + border (이전 brand-solid)
  - Eyebrow / Headline: `text-primary` 다크 / `fg-secondary` (이전 fg-white)
  - **숫자 hero** "1,300,000": `text-brand-primary` 보라 (강조)
  - **CTA Primary** "참여하기": `bg-primary` + label brand
  - Detail Card: `bg-secondary` 회색 (위계 역전 — 흰 hero 안 회색 inset)
  - CTA Secondary: `fill=none` + label `text-tertiary`
- **시스템 강제 (3단 박힘):**
  1. `_enforce_no_large_brand_fill(blueprint)` — blueprint 단계: `$token(bg-brand-*)` + (cornerRadius≥12 ∧ children≥2 ∨ children≥3) frame 자동 `bg-primary` + border 교체
  2. `_strip_large_brand_fills(root_id)` — 빌드 트리 단계: brand RGB heuristic + 면적 ≥ 100×60 frame 검출 + 교정
  3. `cmd_post_fix` 끝에서 매 실행 자동 — 회귀 차단 (`_auto_fix_invisible_text` 가 내부 흰 텍스트 다크로 연쇄 fix)
- **실측 검증**: brand card fill을 일부러 깨뜨린 후 post-fix → 1건 frame + 8건 텍스트 자동 회복 로그 확인.

### 2. ⚠️ 색상 — 절제된 단일 액센트 + 폴리시 (2026-05-23 갱신)
- **브랜드 컬러는 앱의 단일 일관 액센트** — 주 액션(CTA)·active 탭/네비·핵심 수치·중요 링크/아이콘 등 **의도된 여러 지점**에 일관되게 사용한다. 회사가 거부한 건 "여러 색 난무"이지 브랜드 컬러 자체가 아니다. 단, 모든 카드·태그·통계에 무분별하게 깔지는 말 것.
- **피드백(상태) 컬러는 소량·차분하게** — 미납·완료·주의 등 **진짜 상태 정보**에 한해 `success`/`warning`/`error` 계열을 절제된 톤으로 소량 사용 가능. 장식·태그·통계 전반에 색을 까는 건 금지.
- **폴리시 필수 (와이어프레임 탈피)** — 평평한 그레이 박스만 나열하면 와이어프레임처럼 보인다. **카드 그림자/elevation, 흰 카드 ↔ 연한 그레이 면의 도형-배경 대비, 강한 타이포 위계(히어로 수치는 크게·Bold)**로 "디자인된" 느낌을 만든다.
- **베이스는 뉴트럴 그레이** — `bg-/fg-/border-` 그레이 계열 중심이되, 완전 무채색 평면은 금지.
- **Why**: 회사가 "브랜드/피드백 컬러 난무"를 거부 → 절제. 그러나 완전 그레이톤 + 버튼 1개는 "와이어프레임 같다"고 재피드백 (2026-05-23). 적정선 = 절제된 단일 액센트 + 상태 컬러 소량 + 입체감 폴리시.

### 2-B. ⚠️ 카드 표면 — bg-primary + 보더 (root 위 카드, 2026-05-23 룰)
- **루트 위 최상위 카드의 표면 = `$token(bg-primary)` fill + `$token(border-secondary)` 1px 보더** — `bg-secondary`(회색)로 채우지 말 것. 흰 카드를 보더(+ 자동 주입되는 subtle shadow)로 정의한다.
- 카드 안의 인셋·서브카드는 대상 아님 (필요 시 `bg-secondary`/`bg-tertiary` 유지). 브랜드 컬러 카드(`bg-brand-solid` 등)도 그대로 둔다.
- **예외 — 맨 아래 Footer**: Footer는 `$token(bg-secondary)` fill + **보더 없음**(그림자도 없음). 페이지를 닫는 회색 띠이지 카드가 아니다.
- `cmd_build`의 `_enforce_card_surface`가 최상위 그레이 카드를 bg-primary + border-secondary로 자동 교정하고, Footer는 bg-secondary + 보더 제거로 처리 — blueprint에서 어떻게 쓰든 빌드가 바로잡는다.

### 2-C. ⚠️ 타이포 위계 — 크기·굵기로 시각 리듬 (2026-05-23 룰)
- **컬러가 절제될수록 시각 위계는 폰트 크기·굵기로 강화한다.** 표준 type scale:
  - **HERO** (카드 안 핵심 금액·수치) — `28~36px Bold`
  - **TITLE** — `22~26px Bold`
  - **SECTION** (섹션 헤더) — `17~19px Bold`
  - **BODY** — `14~16px Medium/SemiBold`
  - **CAPTION** (라벨·메타) — `11~13px Medium/Regular`, 컬러 `fg-tertiary`
- 같은 카드 안에 **최소 3단계 이상 차이**를 둔다 — HERO 금액은 본문(BODY)의 2배 안팎이어야 리듬이 산다. 16px 본문 옆에 16px Bold 금액 = 단조로움(금지).
- `cmd_build`의 `_enforce_text_hierarchy`가 카드 안의 통화 hero(부호 `+/−` 또는 천단위 콤마가 있는 금액 텍스트)를 자동으로 **30px Bold**로 승격 — 본문이 hero보다 작게 작성되어 있어도 hero가 본문 위로 올라온다.

### 2-D. ⚠️ Modal 화면 패턴 — 상단 X만, Footer·Tab Bar·상단 탭 없음 (2026-05-24 룰)
- **Full modal** (홈 위로 슬라이드업되는 단일 화면, 예: 거래 스케줄 상세) 은:
  - **상단 헤더 = X(닫기) 버튼만** — 로고·알림·채팅·검색 등 nav 아이콘 없음. X 는 우측 상단(NavBar `primaryAxisAlignItems: MAX`).
  - **Footer 없음 · Tab Bar 없음 · 상단 Tab 메뉴(거래현황/누적거래 등) 없음** — 모달은 단일 컨텍스트.
  - 루트 높이는 콘텐츠에 HUG (불필요한 빈 공간 금지).
- Blueprint root 에 `"_screenType": "modal"` 명시 → `cmd_build`의 `_enforce_modal_pattern` 이 자동 강제: Footer / Tab Bar / 상단 탭(`Tab Row`/`Top Tab`/`Section Tab` 포함) / non-X nav 아이콘(`Logo`/`bell`/`chat` 등) 을 빌드 전에 제거하고 NavBar 를 우측 정렬한다.
- 모달이 아닌 일반 화면은 기존대로 (NavBar 풀세트 + Tab Bar + Footer).

### 2-G. ⚠️ 하단 CTA = DS Button 컴포넌트 인스턴스 우선 (2026-05-24 룰)
- **하단 CTA 버튼(Bottom Action Bar 의 Primary CTA / Submit Button / 참여하기 등) 은 무조건 DS `Action Button` 컴포넌트 인스턴스로 만든다.** raw frame 으로 그리지 말 것.
- DS Button 으로 표현이 안 되는 특수 케이스(이중 버튼, 그라데이션 CTA 등)에 한해 직접 그릴 수 있음 — 그 외는 항상 instance.
- **사용할 키 (scripts/design_rules/ds_catalog.py):**
  - `Action Button md Primary` (`ed0032bcf28f03da97e4b3006f54d30a0fbe5914`) — 기본 CTA
  - `Action Button md Secondary` / `Tertiary` / `Outline` / `Ghost` — 위계별
  - `Action Button sm` (`a8a4d7eb7874c469ab89105cc342fad85a3d28ce`) — 보조 CTA
- **사이즈 / 상태:** Bottom Action Bar 의 대형 CTA 는 `Size: lg`, 비활성 상태는 `State: Disabled` (variant 로 적용 — opacity 0.5 자동).
- **라벨:** `componentProperties` 의 텍스트 슬롯에 override (e.g., "참여하기"). 아이콘 토글(`⬅️ Icon leading` / `➡️ Icon trailing`) 은 기본 false.
- **시스템 강제 (기존):** R23 inject 의 `detect_button_shape` 가 raw button frame 을 자동 swap. 2026-05-24 — `Primary CTA` 같이 VERTICAL 로 잘못 작성된 케이스도 잡도록 name 매칭(`cta` / `button` / `submit`) 시 layoutMode 무관 인정. catalog 미스 시 build ERROR.
- Blueprint 작성 시: `{"type":"instance","componentKey":"ed0032bcf28f03da97e4b3006f54d30a0fbe5914","properties":{"Size":"lg","State":"Disabled","label":"참여하기"}}` 패턴.

### 2-F. ⚠️ 루트 minHeight=852 + 하단 바 bottom-pin (2026-05-24 룰)
- 루트 프레임 **min height = 852** (iPhone 16 뷰포트). 콘텐츠가 늘어나면 그에 따라 같이 늘어남.
- 콘텐츠 합이 852 보다 짧을 때, 화면에 고정된 하단 바(**Bottom Action Bar / Tab Bar / CTA Bar / FAB**) 는 **루트 하단(y = 852 - bar.height)에 bottom-align** — 콘텐츠 끝에 붙어 떠 있지 않게 한다.
- **시스템 강제:** `cmd_post_fix` 의 `_enforce_root_min_height` (scripts/figma_mcp_client.py, 2026-05-24) — 루트 높이 < 852 시 852 로 늘리고, 이름에 `tab bar`/`tabbar`/`bottom action bar`/`action bar`/`cta bar`/`fab` 포함된 자식을 ABSOLUTE + bottom constraint MAX 로 새 루트 하단에 재배치. 콘텐츠가 852 보다 길면 손대지 않음 (콘텐츠 끝이 곧 바의 위치).

### 2-E. ⛔ Section Divider 자동 삽입 폐기 (2026-05-27 사용자 명시)
- **"frame에 border를 추가하라니깐 엉뚱하게 섹션 사이에 선을 넣고있냐!!!"** — 섹션 사이에 1px divider 라인 자동 삽입 금지. 이전(2026-05-24) 룰 폐기.
- 정보 그룹 경계는 **카드 자체의 border** 로 표현한다 — `_enforce_white_card_border`(fill=`bg-primary` frame 에 `border-secondary` 1px 자동) + 카드별 stroke 토큰 바인딩이 담당.
- **시스템 강제:** `_enforce_section_dividers` 는 폐기 (no-op + 입력 divider 노드 자동 제거). `cmd_post_fix` 끝에 `_strip_section_dividers` 가 빌드 트리의 모든 "Section Divider" 노드 자동 삭제 — 회귀 차단.
- Blueprint 에 명시적으로 "Section Divider" 노드 작성하지 말 것. drop-shadow 도 함께 금지 ([[feedback_no_drop_shadow]] 참조).

### 3. Tab Bar 아이템은 반드시 FILL 균등 분배
- Tab Bar 내 모든 아이템: `layoutSizingHorizontal: "FILL"`, `layoutSizingVertical: "FILL"`
- HUG/FIXED 혼용 금지 — 아이템 간격이 불균등해짐
- 빌드 후 반드시 Tab Bar 아이템 사이징 검증할 것

### 5-B. ⚠️ 상단 모드 탭 = Underline Tab (RECTANGLE underline 자식, 2026-05-27 사용자 명시)
- 이전 룰 폐기 — "white pill on grey track" (R29) 폐기. 새 표준은 **Underline Tab v2**.
- **컨테이너 (Tabs Wrap)**: HORIZONTAL, `paddingLeft/Right=24`, `paddingBottom=8`, `itemSpacing=22`, `counterAxisAlignItems=MAX` (베이스라인 정렬), `fill=$token(bg-primary)`, `clipsContent=true`, `layoutSizingHorizontal=FILL`, `layoutSizingVertical=HUG`
- **각 탭**: VERTICAL HUG×HUG, `paddingTop=16`, `itemSpacing=12`, `counterAxisAlignItems=CENTER`
  - **label (TEXT)**: 16px / lineHeight 24px
    - Active: Bold + `text-primary` 바인딩
    - Inactive: Medium + `text-tertiary` 바인딩
  - **underline (RECTANGLE)**: height 2.5, `layoutSizingHorizontal=FILL`, `layoutSizingVertical=FIXED`
    - Active: `fill=$token(bg-brand-solid)`
    - Inactive: 투명 (fill 없음) — 자리만 유지해 높이 일치
- **레퍼런스 노드**: `17382:48541` (Mode Tabs). clone 후 라벨 override + 부모 swap 패턴 사용 가능.
- 코드 강제: R29 폐기, blueprint 작성 시 위 구조 그대로. 별도 R 룰 미구현 — 메모리 [[feedback_underline_tab_v2]] 참조.

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
- **배치 원칙**: Tab Bar는 **콘텐츠 하단에 밀착**(빈 흰 띠/데드밴드 금지), FAB는 **콘텐츠/Tab Bar 위로 떠서** 우측 하단에 위치한다. FAB는 floating 버튼이므로 마지막 섹션과 겹쳐도 정상이다.
- **위치 계산** (`post-fix` `_fix_layout_and_positions`가 자동 적용):
  1. 마지막 콘텐츠 요소의 bottom (y + height) = `content_bottom`
  2. Tab Bar: `y = content_bottom` (콘텐츠에 밀착 — 사이에 빈 공간 두지 말 것), `x = 0`
  3. **FAB (2026-05-27 사용자 룰)**: icon-only 56×56 원형
     - `x = root_width - 56 - 20` (우측 20px)
     - `y = (Tab Bar_y or content_bottom) - 56 - 20` (Tab Bar 위 20px gap; Tab Bar 없으면 콘텐츠 마지막 요소 위 20px gap)
  4. Root height: `Tab Bar_y + 73`
- ⚠️ **데드밴드 금지**: 예전엔 `FAB y = content_bottom + 24`, `Tab Bar y = FAB_y + 60`으로 둬서 콘텐츠와 Tab Bar 사이에 ~76px 빈 흰 띠가 생겼다 — 이제 Tab Bar가 콘텐츠에 밀착하고 FAB가 그 위로 뜬다.
- Tab Bar: `set_layout_positioning(positioning: "ABSOLUTE")` → `move_node(x: 0, y: 계산값)`
- FAB: `set_layout_positioning(positioning: "ABSOLUTE")` → `move_node(x: 317, y: 계산값)` (393−56−20=317)
- **FAB 크기 (2026-05-27 사용자 룰)**: **icon-only 56×56 원형**, `cornerRadius: 28`. 라벨 텍스트 금지 — 아이콘만. 라벨이 필요한 케이스는 별도 pill variant 사용 (drop-down 메뉴 / 라벨 hint 등).
- **🔴 FAB 아이콘 (2026-05-27 사용자 강력 명시)**: **이모티콘 절대 사용 금지** (💰 🔍 ❤️ ⭐ 등). 반드시 DS icon component 인스턴스. DS instance 색 override 실패 시 fallback: Pretendard Bold ASCII 텍스트 ("+", "→" 등) — emoji 폰트 사용 금지.
- **🔴 FAB 위치 (2026-05-27 사용자 강력 명시)**: Tab Bar 또는 마지막 bottom 요소 **위 20px** + 우측 20px. Tab Bar 위치 변경 시 FAB 같이 옮겨야 함 — `python3 scripts/figma_mcp_client.py post-fix <rootId>` 재실행 시 자동 동기화.
- **FAB 컬러**: PRD에 특정 색상이 지정되어 있으면 해당 색상 사용 (config에서 fill 오버라이드). 미지정 시 브랜드 컬러 `$token(bg-brand-solid)` 사용 — FAB는 화면에서 가장 중요한 버튼이므로 브랜드 컬러가 기본
- **빌드 후 검증**: Tab Bar가 콘텐츠 하단에 밀착했는지, FAB가 우측 20px / Tab Bar 위 20px 위치에 있는지 확인

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
- 🔴 **`fg-quaternary`(#f9fafb)·`text-quaternary`(#d2d6db)는 거의 흰색** — 흰 배경 위 텍스트/아이콘에 **절대 사용 금지**(안 보임). 비활성 탭·보조 텍스트 등 "흐린 회색"이 필요하면 `fg-secondary`/`text-secondary`(#687079) 또는 `fg-tertiary`/`text-tertiary`(#b1b6be)를 쓸 것.

### 12. 섹션 간 간격 — 배경색 동일 + divider 없으면 gap 0
- 인접한 섹션의 배경색이 동일(둘 다 투명/white)이고 사이에 divider가 없으면 **gap 0px** — 섹션 내부 padding이 여백 역할
- 배경색이 다르거나(컬러 → white 등) 사이에 divider가 있으면 gap 유지

### 14. ⚠️ 스테이지 카드 — 아이콘/이미지 삽입 금지
- Stage Card 안에 아이콘, 이미지를 **절대 넣지 말 것**
- Stage Card 구성: 태그(포인트/기프티콘) + 금액 텍스트 + 이율/기간 정보 + 북마크 — **이것만**
- 아이콘/이미지를 넣으면 카드가 복잡해지고 PRD 의도에서 벗어남

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

### 21. ⚠️ 숫자/짧은 텍스트는 아이콘으로 변환되면 안 됨 — 빌드 후 QA로 검증
- `enhanceBlueprint`의 이모지→아이콘 자동변환은 **숫자만 있는 텍스트**(스테퍼 값 `"5"`,
  카운트, 배지 숫자 등)를 이모지로 오인해 `star-01` 아이콘으로 바꾸는 버그가 있었다.
  - 원인: 정규식 `\p{Emoji}` 는 숫자 `0-9`·`#`·`*` 도 매칭한다.
  - 수정: `isEmojiOnlyText`에 `글자/숫자(\p{L}\p{N})가 하나라도 있으면 이모지 아님` 가드 추가.
- **빌드 후 QA 강제** — `cmd_build` Step E.6 `_qa_blueprint_integrity()`:
  원본 blueprint와 빌드 트리를 1:1 대조해 **blueprint가 `type:"text"`인데 빌드 결과가
  TEXT가 아닌 노드**를 잡아낸다. 위반 시 같은 부모의 TEXT 형제를 복제·텍스트 교체로 자동 교정.
- blueprint 작성 시 스테퍼 값·카운트·배지 숫자는 반드시 `type:"text"`로 명시할 것.

### 22. ⚠️ 빌드 후 QA — 대비(가시성) + 레이아웃 자동 검사
- `cmd_build` Step E.7 `_qa_visual_checks()` — 사람 눈에 의존하지 않고 빌드 트리를 분석:
  - **대비 검사**: 텍스트/아이콘 색을 배경과 WCAG 상대휘도로 비교, 대비 비율 `< 1.8`이면
    경고 (안 보이는 텍스트/아이콘 차단 — 예: `fg-quaternary` on white). `fg-tertiary`(~1.98)는 통과.
  - **레이아웃 검사**: 마지막 콘텐츠와 Tab Bar 사이 데드밴드(빈 띠 24px↑), 콘텐츠가
    Tab Bar 뒤로 가려짐, Tab Bar 잘림/루트 하단 빈 공간을 감지.
- 빌드 로그의 `[QA] ⚠️ 시각 검사` 라인을 반드시 확인하고, 잡힌 항목을 수정할 것.
- ※ 측정 가능한 항목만 자동화된다 — "디자인이 PRD 의도에 맞나"는 여전히 사람이 확인.

---

## 빌드 후 자동 후처리 (post-fix)

> `build` 명령 완료 시 자동으로 `post-fix`가 실행된다. 별도 실행도 가능:
> ```bash
> python3 scripts/figma_mcp_client.py post-fix <rootNodeId>
> ```

**post-fix가 자동 수정하는 항목:**
```
1. FILL 검증/수정: 모든 FRAME 자식 → FILL (FAB/Tab Bar 제외, SPACE_BETWEEN 마지막 HUG 자식 보존)
   - _walk: 재귀적 FILL 수정 (parent_layout_mode 빈 문자열이면 skip 안 함)
   - 안전장치: 재귀적 FILL 강제 (depth 4까지, VERTICAL 부모의 모든 FRAME 자식)
2. 섹션 간격: 배경색 동일 + divider 없는 인접 섹션 → gap 0
3. Tab Bar/FAB: ABSOLUTE 배치 + 루트 하단 위치 + FAB width 복원 (HUG)
4. Tab Bar item FILL 통일 + Tab Row individual stroke (bottom-only)
5. zero-width 텍스트: width=0 TEXT → textAutoResize="WIDTH_AND_HEIGHT" + FILL (Banner Card 내부 텍스트는 FIXED 160px)
6. DS Effect Style (Shadows/*) 자동 바인딩: frame.effects 가 raw 값으로 박혀 있어도
   첫 DROP_SHADOW fingerprint(offset.y, radius) → Shadows/shadow-{xs,sm,md,lg,xl,2xl}
   가장 가까운 DS effect style 에 `set_effect_style_id` 로 바인딩.
   인스턴스 내부 노드(`I…;…`) 와 이미 styles.effect 가 채워진 노드는 skip.
   - 수동 재바인딩: `python3 scripts/figma_mcp_client.py bind-effect-styles <rootNodeId>`
[규칙] 루트 프레임 배경 = bg-primary 강제 (절대 규칙 0 — 리터럴 + DS 변수 바인딩)
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
| [`docs/design-rules.md`](docs/design-rules.md) | **디자인 생성/수정 시 필수** — 빌드 규칙, 컴포넌트, 색상, 타이포그래피 |
| [`docs/mobile-patterns.md`](docs/mobile-patterns.md) | 모바일 화면 디자인 시 — 레이아웃 패턴, 화면 사이즈, Status Bar |
| [`docs/qa-checklist.md`](docs/qa-checklist.md) | 디자인 완료 QA 시 — 13개 체크 항목, 스크린샷 촬영 방법, 완료 판단 기준 |
| [`docs/multi-agent-design.md`](docs/multi-agent-design.md) | 복잡한 화면(섹션 3+, 이미지 1+) 디자인 시 — 멀티에이전트 모드 |
| [`docs/pencil-to-figma.md`](docs/pencil-to-figma.md) | "figma로 보내줘" 요청 시 — Pencil→Figma 변환 워크플로우, Blueprint 규칙 |
| [`docs/python-mcp-client.md`](docs/python-mcp-client.md) | batch_build_screen, DS 바인딩 등 대규모 작업 시 — Python HTTP 클라이언트 |
