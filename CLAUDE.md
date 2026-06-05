# Figma Design Agent — 프로젝트 가이드

## 언어
- 항상 한글로 설명할 것

## 권한
- 이 프로젝트에서 Bash 명령어는 **모두 자동 허용** — `.claude/settings.json`에 `"Bash"` 전체 허용 설정됨
- 별도 승인 요청 없이 바로 실행할 것

## 프로젝트 개요
AI 기반 Figma 디자인 생성 도구. **실제 구동은 터미널 Claude Code CLI 기반 — Electron/React 앱이 아니다.**
흐름: 터미널 **Claude Code CLI** → Python 클라이언트(`scripts/figma_mcp_client.py`) → Node **브리지**(WS 8767 + HTTP MCP 8769) → **Figma 플러그인**(Figma 데스크톱 앱 *안에서* 실행) → Figma 파일.
(레포에 `electron`/`vite` 의존성·`dev`/`start` 스크립트 없음. `package.json`의 `main`은 `out/bridge/index.js`.)

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
   *"Figma 데스크톱 앱에서 **'Figma Design Agent'** 플러그인을 실행해 주세요"* 라고 안내한다
   (플러그인 실행은 자동화 불가 — 유일한 수동 단계).
   ⚠️ 플러그인 이름은 정확히 **"Figma Design Agent"** — "Claude MCP" 등 다른 이름으로 부르지 말 것.
5. 🔴 **기획 문서 전체 학습 (맥락 100% — 2026-06-04 사용자 필수 룰)** — 디자인 생성 전,
   `src/기획/` 폴더의 **모든 기획 HTML(유스케이스 스펙)을 읽어 imin 서비스 맥락을 완전히
   이해한 상태**로 만든다. 🔴 **목표: 준비가 끝나면 사용자가 곧바로 "메인화면 그려"라고만 해도
   맥락을 충분히 이해한 상태로 바로 그릴 수 있어야 한다** (2026-06-04 사용자). 그래서 준비
   단계에서 통독+ack 까지 끝낸다. 3-스텝(한 번씩만):
   ```bash
   # ① 학습 digest 생성 (플러그인 UI 에 '기획 문서 학습 중 (n/총)' progress 표시)
   python3 scripts/figma_mcp_client.py learn-planning
   ```
   → ② 생성된 `scripts/_planning_digest.txt` 를 **Read 도구로 처음부터 끝까지 통독**한다
   (HTML 태그 제거된 깨끗한 텍스트, ~8만 자 = Read 가 한 번에 안 읽히므로 **여러 번 offset 으로
   끝까지**. 36개 UC 의 메타정보·정상/예외 플로우·비즈니스 룰·**연결 화면(SCR-*)**·수용 기준·
   백엔드 API + 마스터 Product Spec/운영정책/약관). 파일 **맨 끝에 '통독 확인 토큰'** 이 있다.
   ```bash
   # ③ digest 맨 끝의 토큰으로 통독 확인 (이게 있어야 디자인 빌드가 통과)
   python3 scripts/figma_mcp_client.py ack-planning <digest 맨 끝 토큰>
   ```
   이후 사용자가 PRD/와이어/짧은 한마디("메인화면 그려")로 지시하면, **그 화면이 어느 유스케이스·
   플로우·상태에 속하는지, 비즈니스 룰·연결 화면을 충분히 반영**해 **바로** 생성한다.
   (폴더 없거나 0건이면 스킵 + 플러그인에 `status:done count:0` 알림.)
   - 🔴 **통독 하드 게이트 (시스템 강제 — references S20~S23 와 동일 철학):** `cmd_build` 시작 시
     `_enforce_planning_read_gate()` 가 **통독 ack 가 없거나 stale 하면 빌드를 차단**(exit 2)한다.
     즉 통독 안 하면 디자인을 못 만든다 — "매번 통독해서 이해도 높인 상태" 를 시스템이 보장.
     ack 의 토큰은 digest **맨 끝**에만 있어, 끝까지 통독해야만 정확한 토큰으로 ack 가능(cheat 방지).
     긴급 우회: `IMIN_SKIP_PLANNING_GATE=1`.
   - 🔴 **변경 감지 + ack 무효화:** `learn-planning` 은 `src/기획/` fingerprint(파일+mtime+size)를
     `_planning_digest.txt.meta.json` 에 저장. **변경 없으면 재생성 스킵**(단 ack 안 됐으면 통독 안내),
     **변경되면 자동 재학습 + 이전 ack 무효화**(`_planning_digest.txt.read.json` 삭제) → 다시 통독+ack
     해야 빌드 통과. 강제 재학습: `learn-planning --force`. 세션 도중 문서가 바뀌어도 빌드 게이트가
     stale 을 잡아 재통독을 강제한다.
6. **완료 보고** — 준비 완료(기획 문서 통독+ack 포함)를 알리고, 디자인할 화면의 PRD/요구사항을 요청한다.

> 🧹 **오래된 산출물 자동 정리 (생성 7일 경과 → 삭제)** — 1단계 setup 스크립트의
> **마지막 프로세스**로 `scripts/cleanup_old_blueprints.py` 가 자동 실행돼, 생성 **7일**
> 지난 blueprint(`scripts/blueprint_*.json`)·**디자인별 일회성 생성기(`scripts/gen_*.py`)**·
> 빌드 산출물(`json/*.json`)·QA 스크린샷(`scripts/qa_screenshots/`)·레퍼런스
> 썸네일(`scripts/ref_thumbnails/`)을 삭제한다.
> ⚠️ **`json/` frontend spec 생성은 폐기됨 (2026-06-05 사용자: "디자인 생성되면 json 폴더에
> json 생성되게 하는것도 삭제해. 생성할 필요없어졌어")** — 빌드의 옛 Step F(`_export_frontend_spec`
> → `json/<화면>_<날짜>.json`)와 `_export_frontend_spec` 함수를 제거했다. 이제 빌드가 `json/`
> 에 spec 을 만들지 않는다. `gen_frontend_spec.py` 도 더 이상 호출하지 않는다(파일은 잔존하나
> 미사용). `json/` 의 기존 산출물은 cleanup 이 정리하되 **PRD 입력 `json/*PRD*.json` 은 보존**.
> blueprint·산출물이 무한 누적되는 문제 방지. 기준은 파일 mtime(생성 후 미수정이라 ≈ 생성일).
> **보존**: `blueprint_templates.json`·`blueprint_unified_imin_home.json`(소스 템플릿),
> `gen_*.py`·`spec_*.json`·`wireframe_content_*.json`(패턴 밖이라 애초에 미대상),
> **PRD 입력 파일 `json/*PRD*.json`**(이름에 `PRD` 포함 시 삭제·추적 제외 모두 스킵 — 사용자 소스).
> 이 산출물들은 `.gitignore` 로 git 추적도 제외된다 — 레포엔 소스만 남는다.
> 수동 실행: `python3 scripts/cleanup_old_blueprints.py` (확인만: `--dry-run`, TTL 변경: `TTL_DAYS=14`).

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
8. **오래된 산출물 정리** (마지막 프로세스) — `scripts/cleanup_old_blueprints.py` 실행: 생성 **7일 경과** blueprint·빌드 산출물(json/QA/썸네일) 자동 삭제 (소스 템플릿·gen/spec/wireframe_content 보존)

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
8. **오래된 산출물 정리** (마지막 프로세스) — `scripts/cleanup_old_blueprints.py` 실행: 생성 **7일 경과** blueprint·빌드 산출물(json/QA/썸네일) 자동 삭제 (소스 템플릿·gen/spec/wireframe_content 보존)

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
npm run build   # tsup → out/ (bridge + yoga-cli, CJS). Vite/Electron 빌드 없음
npm run bridge  # 브리지 기동: WS 8767 + HTTP MCP 8769 (Node, Electron 없음)
npm test        # vitest
```
- 실제 디자인 생성은 **터미널 Claude Code CLI에서** `scripts/figma_mcp_client.py`를 호출해 진행한다(브리지가 떠 있어야 함).
- Figma 데스크톱에서 **"Figma Design Agent"** 플러그인을 실행해야 브리지와 연결된다(유일한 수동 단계).

## 아키텍처 (실제 런타임 — Electron 아님)
- **진입점**: 터미널 **Claude Code CLI** — 사용자 요청 입력 + AI 오케스트레이션(요구사항 해석)을 직접 수행
- **Python 클라이언트** (`scripts/figma_mcp_client.py`): 빌드 파이프라인/규칙 엔진. Claude가 Bash로 호출 (검증·조립·post-fix·자가검증)
- **브리지** (`src/bridge/index.ts` → `out/bridge/index.js`): Node 프로세스, **Electron 의존성 없음**. WS 8767(플러그인 ↔) + HTTP MCP 8769(클라이언트 ↔) 동시 기동
- **빌드 로직** (`src/main/`): FigmaWSServer, 58+ 내장 MCP 도구(figma-mcp-embedded), 4개 DS 조회 도구(ds-lookup-tools), MCP HTTP 서버(mcp-http-server), Yoga 레이아웃 시뮬레이터
- **공유** (`src/shared/`): 타입 정의, DS 데이터 로더
- **플러그인** (`src/figma-plugin/`): `code.js` — **Figma 데스크톱 앱 안에서** 실행, 브리지에 WS(`ws://localhost:8767`)로 연결
- **Build**: tsup (CJS, node18 타겟), `ws`/`yoga-layout` external. **Vite/renderer·Electron 빌드 없음**

## 주요 파일
| 파일 | 역할 |
|------|------|
| `scripts/figma_mcp_client.py` | 디자인 빌드 파이프라인 진입점 (CLI에서 호출) — 검증·조립·post-fix·자가검증 |
| `src/bridge/index.ts` | 브리지 진입점 (Node) — WS 8767 + HTTP MCP 8769 기동, Electron 없음 |
| `src/main/figma-ws-server.ts` | Figma 플러그인 WebSocket 서버 (8767) |
| `src/main/mcp-http-server.ts` | HTTP MCP 서버 (8769) — Python 클라이언트가 접속 |
| `src/main/figma-mcp-embedded.ts` | 58+ Figma MCP 도구 레지스트리 |
| `src/main/ds-lookup-tools.ts` | 디자인 시스템 조회 도구 4종 |
| `src/main/yoga-simulator.ts` | Yoga 기반 레이아웃 시뮬레이터 |
| `src/shared/ds-data.ts` | DS 데이터 로더 (토큰/컴포넌트 동기화) |
| `src/shared/types.ts` | 공유 타입 정의 |
| `src/figma-plugin/code.js` | Figma 플러그인 "Figma Design Agent" — Figma 데스크톱 내 실행 |
| `src/figma-plugin/manifest.json` | 플러그인 매니페스트 (id, WS 8767 dev 허용) |

## Plugin & Build
- Plugin code: `src/figma-plugin/code.js` (plain JS, Figma sandbox — no optional chaining `?.`). Figma 데스크톱에서 "Figma Design Agent" 플러그인으로 실행
- 브리지/도구: TypeScript, `tsup`으로 빌드 (`npm run build`)
- `npm run build` → `out/` (bridge + yoga-cli = CJS). **Vite/renderer 번들·Electron 패키징 없음**
- 배포/납품: 레포 클론 → `setup-mac.sh`/`setup-windows.ps1` → `npm run bridge` → Figma에서 플러그인 실행 (별도 앱 패키징 없음)

### Git Commit & Push 규칙
- `src/` 코드 변경이 포함된 커밋은 **`npm run build`로 빌드 검증 후** 커밋 (docs/ds/scripts만 변경 시 생략 가능)
- 순서: (필요 시 `npm run build`) → git add → git commit → git push

## 알려진 이슈
- DesignPreview 컴포넌트 참조되지만 미구현
- 테스트 없음 (단위/통합)
- Figma 도구 호출 캐싱 없음

## ⚠️ 텍스트 스타일(set_text_style_id) 적용 — 라이브러리 fallback (2026-06-01)
- **증상**: 빌드 후 variables(색/spacing)는 바인딩됐는데 **텍스트 스타일만 하나도 적용 안 됨**. 빌드 로그에 `[text-style] DS text style 인덱스 비어있음 — 건너뜀`.
- **원인**: `get_styles`(code.js)는 `getLocalTextStylesAsync`로 **로컬 스타일만** 조회. 작업 파일은 DS(`Imin Design System`)를 **라이브러리로 참조만** 하고 로컬 text style이 0개 → 인덱스 빔. Figma는 변수와 달리 **라이브러리 스타일 목록 API가 없음**.
- **해법 (이미 코드에 박힘 — 자동 동작)**: `_load_text_style_map`이 로컬 0건이면 `ds/TEXT_STYLE_MAP.json`(사전 추출본)을 fallback으로 사용. `set_text_style_id`는 `S:{key},` 형식이면 `importStyleByKeyAsync`로 라이브러리 스타일을 import해 적용하므로 **로컬 없어도 동작**.
- **`ds/TEXT_STYLE_MAP.json`이 없거나 stale하면**: plugin을 **DS 파일(Imin Design System)에 연결**한 뒤 `python3 scripts/figma_mcp_client.py sync-text-styles` 1회 실행 → 추출·저장 후 커밋. (variables의 `TOKEN_MAP.json`과 동일 패턴)
- **⚠️ Carmen sans 등 비-UI 폰트 제외 (필수)**: DS text style에 **Carmen sans**(영문 전용, UI 폰트 아님)가 섞여 있고, `ExtraBold`가 weight bucket `bold`로 분류돼 `(24,bold)`·`(16,bold)` 인덱스에서 Pretendard Bold를 덮어쓴다. 그러면 Pretendard 텍스트에 Carmen sans style이 매칭돼 plugin이 그 폰트 로드로 **22초+ hang → 미적용**. `_is_pretendard_text_style`이 **Pretendard 패밀리만 매칭**(Carmen 제외)하도록 막아둠. 사용자 명시: "Carmen sans는 UI 폰트가 아니다 — 제외."
- **재빌드 없이 기존 화면에 적용**: `python3 scripts/figma_mcp_client.py apply-text-styles <rootNodeId>`
- **참고**: `cmd_build`의 `batch_build_screen`이 client 300초 timeout으로 죽으면 그 뒤의 text style 단계(Step E.5.5)에 도달 못 함 → 이땐 `apply-text-styles`로 보완.

## ⚠️ batch_build_screen timeout 시 후속 단계 자동 복구 (2026-06-01) — 모든 회귀의 공통 뿌리
- **증상**: 빌드는 됐는데 **색 변수 바인딩·text style·post-fix 가 전부 안 됨** (화면 색/배치는 리터럴로 박혀 정상처럼 보이나 DS 변수 연결·스타일 없음).
- **원인**: `batch_build_screen` 은 plugin 이 노드 생성을 끝내도 응답을 못 보내 **client 300초 timeout** 이 잦다. 예전엔 이 예외로 `cmd_build` 가 중단되어 Step D~H(색 바인딩 E.5 / text style E.5.5 / post-fix)가 전부 스킵됐다. 이 세션의 3개 회귀(text style 미적용·색 바인딩 누락·post-fix 미실행)가 **모두 이 하나의 뿌리**.
- **해법 (코드에 박힘 — 자동)**: `cmd_build` 가 `batch_build_screen` 을 try/except 로 감싸고, timeout/예외 시 `_recover_built_root_id(blueprint.name)` 로 plugin 이 끝낸 root 를 `get_document_info` 폴링으로 찾아 `root_id` 를 복구한 뒤 **후속 단계를 그대로 잇는다**. `original_blueprint`(token 보존 deep copy)는 batch_build 전에 떠 있어 색 바인딩이 정상 동작.
- **수동 복구가 필요한 옛 빌드**: `auto-bind <rootId> <blueprint.json>`(색 변수) + `apply-text-styles <rootId>`(text style) + `post-fix <rootId>`.

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

> 🔴 **절대 규칙 0-K — DS 컴포넌트의 fill·stroke·label 색은 절대 변경 금지 (2026-06-01 사용자 명시)**
>
> 사용자 명시: *"1. badge fill, stroke color 절대 변경 금지 2. badge label text fill
> color 역시 절대 변경 금지 3. 모든 component의 fill, stroke, label color 변경하지 말 것!!"*
>
> **DS 컴포넌트 인스턴스(badge/button/tag/avatar/input 등)와 그 내부 노드(라벨 텍스트·
> 아이콘)의 색은 오직 master/variant/props 가 제어한다.** 토큰 바인딩·대비 보정·카드 표면
> 교정 등 어떤 일반 패스도 인스턴스 색을 덮으면 안 된다. 색을 바꾸고 싶으면 `set_instance_properties`
> 로 **variant/color prop 만** 선택한다.
>
> **🎨 Badge 색 변경 = `Color` prop 에서 선택 (2026-06-01 사용자 명시):**
> DS Badge 컴포넌트는 `Color` prop 에 **13개 옵션**이 있다 — fill/stroke 를 직접 바꾸지
> 말고 이 prop 에서 고른다. `set_instance_properties(nodeId, {"Color": "<옵션>"})`.
> 유효 옵션 (정확히 이 문자열):
> `Gray` · `Brand` · `Error` · `Warning` · `Success` · `Blue light` · `Blue` ·
> `Indigo` · `Purple` · `Pink` · `Orange` · `Blue gray` · `Gray blue`
> (코드 상수: `ds_catalog.BADGE_COLOR_PROP_OPTIONS`, 헬퍼: `figma_mcp_client.set_badge_color()`).
> R23 swap 시 라벨 의미(`_BADGE_COLOR_ROLE`)로 색 variant 를 고르고, 빌드 후 색을 바꿔야
> 하면 위 prop 으로만 바꾼다. **절대 fill/stroke 리터럴·토큰을 덮지 않는다.**
>
> **회귀 사례 (이번 뿌리)**: auto-bind 의 `_collect_bindings` 가 `original_blueprint`
> (R23 swap 전 복사본)를 보고 R23-swap 된 DS Badge Warning 을 raw frame 으로 오인 →
> 빌드된 INSTANCE 의 fills/0 에 bg-secondary, 내부 라벨에 text-tertiary 를 바인딩 →
> Warning variant 색이 깨짐.
>
> **시스템 강제 (코드 박힘, 자동):**
> 1. `figma_mcp_client.py call_tool` **중앙 가드**: `set_fill_color`/`set_stroke_color`/
>    `set_bound_variables(fills|strokes)` 의 대상이 **인스턴스 내부 노드(id 에 `;` =
>    `I{id};{sub}`)면 차단**한다. 의도적 enforcer(FAB 아이콘 fg-light 등)만 호출 args 에
>    `_allowComponentColor: True` 로 예외.
> 2. `_collect_bindings`: 빌드된 노드가 **INSTANCE 면 색 바인딩 안 함 + 자식 재귀도 skip**
>    (variant 가 제어하는 내부 색 보호). `original_blueprint` 가 swap 마커를 몰라도 안전.
> 3. `_strip_large_brand_fills`·`_auto_fix_invisible_text` 등 라이브 색 보정기는 이미
>    `;` 내부 노드 + INSTANCE type 을 skip.
>
> **빌드 후 검증:** badge/button 의 fill·stroke·라벨 색이 DS variant 기본값과 일치하는지
> (스크린샷). 회색으로 덮였으면 위반 — `_collect_bindings`/중앙 가드 점검.

> 🔴 **절대 규칙 0-J — 2-tab 이상 텍스트 탭 nav 는 DS Horizontal Tabs 인스턴스 강제 (2026-06-01 사용자 룰)**
>
> 사용자 명시: *"'거래현황', '누적거래' 2 tabs가 있는데 tabs component가 사용되지 않았다.
> 왜 사용하지 않았는지 원인을 찾고 재발하지 않도록 문제 수정해. 새 세션에서 생성했을때
> 또 지금과 같은 컴포넌트를 사용하지 않는 일이 없어야 된다."*
>
> **금지:** "Mode Tabs Wrap" / "Section Tabs" / "Top Tabs" / "Page Tabs" / "Underline Tabs"
> 등 이름의 HORIZONTAL frame 안에 raw tab cell frame 들을 직접 그리는 것. (e.g. 자식
> "Mode Tab Active" + "Mode Tab Inactive" 각각이 TEXT 만 들어있는 frame)
>
> 🔴 **2026-06-02 DS v7 → Imin Design System 마이그레이션 (사용자 룰):** 기존 DS v7
> "Horizontal tabs Underline"(`6b613d…` 등)은 **모바일에서 드롭다운으로 붕괴 + DS v7
> 라이브러리 의존** → 전면 폐기. Imin Design System 의 **`Segmented_control`** 으로 통일.
>
> **올바른 방법:** blueprint 에 `type: "instance"` + Segmented_control variant 키를 박는다.
>
> ```json
> {
>   "name": "View Tabs",
>   "type": "instance",
>   "componentKey": "47a01673a46dc3bc9bfd62948c10e5fa9f2e5e78",  // Segmented_control Style=hug
>   "_segLabels": ["거래 현황", "누적 거래"]
> }
> ```
>
 **빌드 후 설정 — 🔴 prop 기반 (2026-06-02 사용자: 텍스트 레이어를 컴포넌트 prop 으로):**
> 세그먼트 라벨/선택은 nested 텍스트 노드 id(variant 마다 달라 깨짐)가 아니라 **세그먼트
> 인스턴스의 컴포넌트 prop** 으로 설정한다 — 견고함:
> - 세그먼트 개수 = `set_instance_properties(ctrlId, {"Show Segment 3#16713:0": False, …})` (n=3..8, `#16713:{n-3}`)
> - 라벨 = 각 세그먼트 인스턴스(`I{ctrl};{segId}`)에 `Label#17537:11` TEXT prop
> - 선택 = 각 세그먼트 인스턴스에 `Active` = `on`/`off`
>
> **자동화:** blueprint 의 탭 인스턴스에 `"_segLabels": ["추천","전체"]`(+ 선택 시
> `"_segActive": 0`) 마커만 박으면 — `cmd_build` 가 `_configure_segmented_control` 로
> 위 prop 들을 자동 설정한다. 빌드 로그 `[seg-tabs] Segmented_control 설정 완료` 확인.
>
> **Imin DS Segmented_control 키:**
> | Variant | 컴포넌트 키 |
> |---------|------------|
> | Style=hug (기본) | `47a01673a46dc3bc9bfd62948c10e5fa9f2e5e78` |
> | Style=fill (전폭) | `2ee9d12d4c904650ab496b9bcdf874a648e73ceb` |
> | (set key, import 불가) | `143ee3e3fdd529c89c4360e3d70a583be4a83f53` |
>
> **시스템 강제 (4중 방어, 자동):**
> 1. `scripts/design_rules/R60_tabs_ds_instance.py`
>    - **L2 lint**: raw tab nav frame 발견 시 WARN
>    - **L3 inject**: 빌드 직전 자동 swap — `type: frame` → `instance`, componentKey 박기,
>      라벨/active idx 메타 저장, raw children → `_originalChildren` 보존
>    - **L4 post-fix**: 빌드된 instance 의 내부 TEXT 노드 findAll + 라벨 순서대로
>      `set_text_content` 호출 (텍스트 매핑 자동화)
>    - **L5 verify**: built tree 의 tab nav wrapper 가 INSTANCE 가 아니면 ERROR
> 2. `scripts/design_rules/ds_catalog.py` 의 COMPONENT_KEYS 에 6종 variant + 4종 alias
>    ("Mode Tabs", "Mode Tabs Wrap", "Section Tabs", "Top Tabs") 등록 — resolve_component_key 자동 매칭
>
> **빌드 후 검증:** 빌드 로그에 `[inject R60] Mode Tabs raw frame → DS Horizontal Tabs
> instance: N건` + `R60 Tabs instance: '<name>' 라벨 N개 매핑` 라인이 보이면 자동 처리 성공.
> 스크린샷에서 탭 영역이 DS Underline tabs 스타일로 표시되어야 한다.

> 🔴 **절대 규칙 0-M — 하단 Tab Bar = DS 'Tab bar' 인스턴스 (2026-06-02 사용자 룰)**
>
> 하단 바텀 네비게이션은 raw frame(아이콘+라벨 직접 그리기) 금지. DS **'Tab bar'**
> 컴포넌트 인스턴스를 쓴다. `Selected` variant 로 active 탭을 정한다 — **탭 구성 고정:
> 홈 / 커뮤니티 / 스테이지 / 라운지 / 나** (라벨·아이콘·색 모두 컴포넌트 내장, override 불필요).
>
> **active 탭에 해당하는 variant key 로 인스턴스 생성** (variant flip 불필요):
> | active | component key |
> |--------|---------------|
> | 홈 | `0faaa55563de4da617964ea93ba07f09bc1279f6` |
> | 커뮤니티 | `b7d390e90bae2d41059671f4474102a2bd92b7c1` |
> | 스테이지 | `a56726e0de4bc0e71875159662b320e9b2ac695c` |
> | 라운지 | `7dcb6d5d2b97d36e0b5d601441f22f87e2d26f5c` |
> | 나 | `740120b5e954cae262d21fefffa946afc26f2d63` |
> (set key `f7de125d1aa57be1b3c5ec0757c3b3803d435c7e`. catalog `COMPONENT_KEYS["Tab Bar …"]`.)
>
> **시스템 박힘:** `unified_blueprint._gen_tab_bar` 가 active 탭 variant key 로 instance emit.
> custom blueprint 는 `{"name":"Tab Bar","type":"instance","componentKey":"<active key>"}` 직접 작성.
> ⚠️ DS 라이브러리에 **publish(게시)된 상태**여야 import 됨 — 미게시면 `⚠ Tab Bar` 에러 프레임.

> 🔴 **절대 규칙 0-L — R23 auto-swap 은 '이름 힌트' 있을 때만 / 콘텐츠 frame 은 DS 이름 금지 (2026-06-02 사용자 분노)**
>
> 사용자 명시: *"새 세션에서 디자인 생성하라고 하면 또 이렇게 이상하게 생성할거 아냐?"* —
> hand-authored blueprint 의 콘텐츠/장식 frame(금액 강조 pill·회차 1~13 셀·필터 칩·
> 드롭다운 헤더)이 DS 컴포넌트 **모양**과 우연히 겹쳐 R23 이 인스턴스로 오스왑 → 콘텐츠
> 파괴(드롭다운이 "Account" 더미 / 금액이 보라 버튼 / 회차 바 붕괴)되던 회귀.
>
> **시스템 강제 (코드 박힘, 2026-06-02):** `ds_catalog.detect_ds_role_structural` 의 confident
> auto-swap 은 이제 **이름 힌트가 있을 때만** True:
> - button → 이름에 `button/btn/cta/submit/버튼`
> - badge/tag → 이름에 `badge/태그/tag/chip` **또는 라벨이 status 어**(진행중/완료/미납 등)
> - dropdown/input/toggle/checkbox/radio/slider/progress/avatar → 이름에 해당 단어
> - **bare 숫자/단일 문자**("1"~"13"·"A") → step·회차 마커로 보고 badge 검출 자체 제외
> 이름 힌트 없는 순수 모양 일치는 **WARN-only(swap 안 함)**. 진짜 status badge·이름 명시
> 컴포넌트는 여전히 swap.
>
> **blueprint 작성 규칙 (새 세션 필수):** 콘텐츠/장식 frame 에 DS 컴포넌트 단어
> (`Pill`·`Chip`·`Badge`·`Dropdown`·`Button`·`Tag`)를 **이름으로 쓰지 말 것** — 중립 이름
> (`Amount Box`·`Filter Opt`·`Filter Header` 등) 사용. 진짜 DS 컴포넌트가 필요하면
> `type:instance` + componentKey 로 **직접** 작성한다(모양 의존 금지).

> 🔴 **절대 규칙 0-I — 섹션 타이틀 텍스트는 항상 좌측 정렬 (2026-06-01 사용자 룰)**
>
> 사용자 명시: *"다른 섹션들은 그렇게 되어 있는데 왜 이것만 중앙으로 배치했는지 이해가
> 되지 않는다."* — 섹션 헤더/타이틀 텍스트(예: "이번 달 일정", "추천 스테이지",
> "거래 스케줄", "추천 상품")는 **모두 좌측 정렬**(`textAlignHorizontal: LEFT` 또는
> 미명시=기본 LEFT)이어야 한다.
>
> **중앙 정렬을 만드는 두 패턴 (둘 다 금지):**
> 1. **TEXT 노드에 `textAlignHorizontal: "CENTER"` 직접 박힘** — blueprint 작성 실수.
> 2. **`primaryAxisAlignItems: SPACE_BETWEEN` + 자식 1개** — Figma 가 단일 자식을
>    row 정중앙에 배치한다. 다른 Title Row 들이 우측에 CTA("전체 보기" / 예치금 라벨)를
>    가진 것과 일관성 위해 자식 1개일 땐 `MIN`(=시작 정렬) 사용.
>
> **시스템 강제 (자동, 3중 방어):**
> 1. `scripts/design_rules/R59_section_title_left_align.py`
>    - **L2 lint**: blueprint 사전 검증 — CENTER align 또는 SPACE_BETWEEN+single-child 시 WARN
>    - **L3 inject**: 빌드 직전 blueprint 자동 교정 (CENTER→LEFT, SPACE_BETWEEN→MIN)
>    - **L4 post-fix**: 빌드 후 실제 노드에 `set_text_align(LEFT)` / `set_auto_layout(MIN)` 자동 호출
>    - **L5 verify**: 빌드 후 검증 — 여전히 위반이면 WARN
> 2. `scripts/design_rules/__init__.py` 의 자동 import — R59 자동 등록
>
> **스코프 (2026-06-01 좁힘 — 사용자 피드백 "갑자기 모든 정렬이 왼쪽 정렬로 고정된거 같다. 섹션 타이틀만 왼쪽 정렬이어야"):**
> - TEXT 의 `fontSize ≥ 15` (작은 라벨/본문 제외)
> - 부모 frame name 이 `Title Row` / `Header Row` 패턴
> - **ancestor 에 `empty` / `modal` / `dialog` / `sheet` / `popover` / `tooltip` 없음** —
>   Empty state / 모달 안내 텍스트는 와이어 의도(가운데 정렬)를 유지하기 위해 제외
> - `card` 는 의도적으로 ancestor 차단 hint 에서 제외 — "Day Strip Title" 처럼 카드 안에
>   있어도 섹션 타이틀로 인식되는 경우가 있음 (사용자 1차 요청)
>
> **빌드 후 검증:** 빌드 로그에서 `R59 inject:` 또는 `R59 section-title:` 라인이
> 보이면 자동 교정 성공. 스크린샷에서 화면 큰 섹션 타이틀만 LEFT, Empty/Modal 안내는
> 와이어 의도 정렬 유지.

> 🔴 **절대 규칙 0-H — 새 root frame 은 기존 화면 우측 빈 공간에 자동 배치 (2026-06-01 사용자 룰)**
>
> `batch_build_screen` 은 새로 만든 root frame 을 항상 **(0,0) 에 박는다.** 같은 페이지에
> 이미 화면이 있으면 **정확히 겹쳐서** 사용자가 결과를 구분할 수 없다. 절대 금지.
>
> **시스템 강제 (자동):**
> - `figma_mcp_client.py cmd_build` Step D.5 → `_position_new_root_to_right(root_id, gap=200)`
>   - batch_build_screen 직후, post-fix 전에 호출
>   - `get_document_info` 로 currentPage children + bounds 수집 → 다른 children(자기 자신 제외)
>     의 `maxRight = max(x + width)` 계산 → 새 root 를 `(maxRight + 200, 0)` 으로
>     `move_node` 자동 호출
>   - 페이지가 비었거나 bounds 정보가 부족하면 silent — (0,0) 유지 (첫 화면이라 OK)
> - `src/figma-plugin/code.js getDocumentInfo()` 는 children 매핑에 `x/y/width/height`
>   포함해 리턴 — 이 룰의 전제 조건. 제거하면 자동 배치가 silent fail 함.
>
> **빌드 후 검증:** 빌드 로그에 `[auto-position] ✓ 새 root → x=<N>, y=0` 라인이 보이면
> 자동 배치 성공. 없으면 페이지에 다른 화면이 없는 첫 빌드라 (0,0) 유지된 것 (OK).
>
> **수동 호출 (예: batch_build_screen 직접 호출 시):** 그 후 즉시
> `move_node({"nodeId": <root>, "x": maxRight + 200, "y": 0})` 호출 — Claude 가 수동
> 빌드 후에도 이 룰을 반드시 적용해야 한다.

> 🔴 **절대 규칙 0-G — references/uibowl REFERENCE READ 강제 (2026-05-28 사용자: "레퍼런스 이미지 검색은 하냐?")**
>
> `cmd_build` 빌드 로그에 **"📌 SECTION-REFERENCE-PNG"** 라인이 보이면, **빌드 진행
> 전에 반드시** 위에 출력된 PNG path 들 (`scripts/ref_thumbnails/*.png`) 을 모두
> **Read 도구로 열어 시각 학습**. 단순 path 만 보고 references[] 박지 말고
> **실제 이미지의 시각 위계/리듬/컬러 매핑/카드 패턴/CTA 위치를 참고**.
>
> **강제 절차:**
> 1. Step A.0 출력의 thumbPath 들 (보통 6장) `Read` 호출
> 2. 학습 결과를 references[] 의 `extract` / `copyNotes` 필드에 **실제 본 내용**으로 반영
>    (form 통과용 "card surface" 같은 공허한 값 금지)
> 3. 학습 결과로 archetype 별 polish 강화 — 시각 위계 / 컬러 절제 / 카드 패턴 직접 적용
> 4. **위반 신호**: PNG Read 0건 / extract 가 generic / references[] 가 path 만
>
> **시스템 박힘:** `figma_mcp_client.py _auto_search_uibowl_references()` (Step A.0)
> — `scripts/ref_search.py --archetype <imin_xxx> --thumbnail --limit 6` 자동 호출
> → `scripts/ref_thumbnails/` 에 LLM Read 가능 thumbnail (≤1200px) 자동 생성 →
> stdout 에 SECTION-REFERENCE-PNG 라인 출력 (사용자 화면에도 보임).
> Claude self-verify 의 마지막 방어선.

> 🔴 **절대 규칙 0-F — SELF-VERIFY 강제 (2026-05-28 옵션 B / 사용자 신뢰 파탄 후 박힘)**
>
> `cmd_build` 빌드 로그에 **"📸 SECTION-QA-PNG"** 라인이 보이면, **사용자에게 어떤
> 보고도 하기 전에 반드시 아래 절차 수행**. 1장 screenshot 만 보고 "검증 ✅" 보고
> 절대 금지 — 이전 5회 거짓 보고로 신뢰 파탄됨.
>
> **강제 절차:**
> 1. stdout 의 `📋 Checklist: scripts/qa_screenshots/<root>/self_verify_checklist.json` 경로 확인
> 2. `exported_sections[]` 의 모든 nodeId 를 `mcp__figma-tools__export_node_as_image` (scale=2) 로 재 export + **Read 강제**
> 3. checklist 12개 항목 (C01~C12) 각각 **PASS / FAIL / NA** + **evidence 1줄 인용** 채움
> 4. FAIL ≥1 건 → 즉시 라이브 fix 시도 → 재 export → 재 Read → checklist 갱신. 미 fix 시 사용자에게 **솔직 보고** (PASS X / FAIL Y / NA Z 명시)
> 5. **위반 신호**: 전체 1장만 보고 OK 보고 / PNG export 만 하고 Read skip / checklist 비워둠 / FAIL 있는데 "완료" 보고
>
> **시스템 박힘:** `figma_mcp_client.py _self_verify_section_qa_export()` (Step H)
> — 6장 PNG auto-export + checklist JSON 자동 생성 + stdout 강력 경고.
> 코드는 Claude 행동 강제 못하지만 stdout 경고가 사용자 화면에도 표시되므로
> Claude 의 self-verify skip 이 사용자에게 즉시 드러남.

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
> 1. **Root 852 FIXED** (디바이스 viewport) — 🔴 HUG 아님(2026-06-04 사용자: "root frame
>    높이는 852여야함"). 시트를 하단에 고정하려면 root 가 고정 높이여야 함.
> 2. 1st 자식 = **Dim Overlay** (FILL×FILL, alpha-black 50%) — 위쪽 가용 공간을 **세로로
>    채워** 시트를 화면 하단으로 민다(bottom 밀착).
> 3. 2nd 자식 = **Modal Sheet** (가로 FILL = **root 와 동일 풀폭**, 세로 HUG, bg-primary,
>    🔴 **top-left/top-right radius = 16**(2026-06-04 사용자 절대규칙), bottom radius 0) —
>    콘텐츠 wrap. 🔴 **시트 가로 = root 풀폭**(2026-06-04 사용자: "가로는
>    root frame과 동일"). **콘텐츠 가로 padding 20 은 Modal Sheet 가 가짐**(root 가로 padding=0
>    이라야 dim·시트가 풀폭). 사용자: "가로에 padding값을 20이 있어야하고".
>
> 강제 함수: `_enforce_bottom_sheet_pattern` (cmd_build pre-process — root 852 FIXED +
> 가로 padding 0, Modal Sheet 가로 padding 20) + 라이브 후처리 `_fix_layout_and_positions`
> 의 bottom-sheet 분기(`_is_bottom_sheet_screen_type` → root 852 FIXED 재단언 + Dim FILL).
> 🔴 bottom-sheet 는 `_HUG_SCREEN_TYPES`(=modal 만)에서 **제외** — modal 처럼 root HUG 로
> 강제하면 dim 이 붕괴해 시트가 하단 밀착 안 됨. 회귀 테스트: `scripts/tests/test_bottom_sheet_pattern.py`.
>
> **Modal 두 가지 구분:**
> - `_screenType: "bottom-sheet"` (기본형) — root 852 FIXED + dim(FILL) + 시트 하단 밀착·풀폭·콘텐츠 padding 20
> - `_screenType: "modal"` (full modal) — 전체 화면 modal, root **HUG**, X 닫기만 (Footer/Tab 제거)
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

> 🔴 **절대 규칙 0-N — 다른 정보는 다른 레이아웃/UI / 와이어 1:1 복제 금지 (2026-06-04 사용자 룰)**
>
> 사용자 명시: *"다른 정보인데 같은 레이아웃, UI로 표현하지 말것! 똑같아서 같은 정보
> 같잖아. 와이어프레임 그대로 레이아웃과 정렬 및 크기 생성하지 말것!"*
>
> **두 가지 의무:**
> 1. **인접 섹션 시각 언어 차별화** — 내용이 다른 두 섹션을 **동일한 카드 구조**(같은
>    2-up 그리드 + 같은 [아이콘 원 + 제목 + 부제] 패턴)로 그리면 같은 정보처럼 보인다.
>    한쪽의 시각 언어를 바꾼다: **2-up 그리드 ↔ 리스트 행**, 카드 크기·틴트·아이콘 배치
>    차등, 강조 카드 등. (사례: '시작 방법 카드' vs '출석/초대 카드' 가 똑같던 회귀 →
>    시작=틴트 2-up 그리드, 출석/초대=흰 리스트 행으로 분리.)
> 2. **와이어프레임 레이아웃/정렬/크기 1:1 복제 금지** — 와이어는 **콘텐츠 source**일 뿐
>    레이아웃 blueprint 가 아니다(절대 규칙 0-C). 와이어의 박스 배치·정렬·크기를 그대로
>    옮기지 말고 **가독성·시각 위계·미학** 기준으로 재구성한다. 콘텐츠(텍스트/숫자)는 1:1
>    (0-E), **레이아웃/스타일은 창의적 재해석**.
>
> **시스템 강제 (코드 박힘):**
> - `scripts/design_rules/R63_distinct_section_ui.py` — **L2 lint**: root 직계 섹션 중
>   '카드 그리드'를 가진 인접 두 섹션의 구조 시그니처(텍스트/색 무시, layout mode +
>   rounded + 자식 구조)가 같으면 WARN("동일한 카드 레이아웃 — 시각 언어 차별화하라").
>   자동 차단 X(디자인 판단) — blueprint 작성 시 Claude 가 차별화.
> - 와이어 1:1 복제는 코드 자동검출 불가(와이어 ref 없음) — 매 빌드 시 사람(Claude)이
>   스크린샷을 와이어 옆에 놓고 **레이아웃/위계/액센트가 달라야 정상**임을 자체 검증(0-C).
>
> **빌드 후 검증:** 빌드 로그에 `R63-distinct-section-ui` WARN 이 보이면 인접 섹션 UI 가
> 똑같다는 뜻 → 한쪽 재설계. 스크린샷에서 인접 카드 영역이 서로 다른 시각 언어인지 확인.

> 🔴 **절대 규칙 0-O — 상단 NavBar 스타일 (2026-06-04 사용자 룰)**
>
> 1. **NavBar frame 의 fill = `$token(bg-primary)`** (투명/회색 금지). 상단 네비게이션 바 배경은
>    항상 흰색(bg-primary).
> 1-b. **NavBar frame 자체에 stroke(보더) 가 없어야 한다.** (상단 바에 테두리 금지.)
> 2. **NavBar 안 좌측 back 버튼 frame 에도 stroke(보더) 가 없어야 한다.** (흰 배경 위 back
>    아이콘 버튼에 테두리 금지 — fill 만 또는 fill 도 없이 아이콘만.)
>
> **시스템 강제 (코드 박힘, 자동):** `figma_mcp_client.py _enforce_navbar_style_live`
> (cmd_post_fix 맨 끝 + build Step E.7.7 — AUTO_FIX·white-card-border *이후* 라야 stroke 가
> 재부착 안 됨) — NavBar(이름에 navbar/nav bar/app bar/top bar/header bar 포함 HORIZONTAL frame)의
> fill 을 bg-primary 로 강제(리터럴+변수 바인딩) + NavBar frame 자체 stroke 제거 + NavBar 서브트리의
> back 버튼(이름에 back/뒤로, 또는 chevron-left/arrow-left 아이콘 든 frame) stroke 를 `strokeWeight 0`
> 으로 제거. 빌드 후 검증: NavBar 배경 흰색 + NavBar·back 버튼 테두리 없음.

> 🔴 **절대 규칙 0-P — Segmented_control 은 기본 Size=md (2026-06-04 사용자 룰)**
>
> DS **Segmented_control** 인스턴스는 **특수한 상황이 아니면 props 의 `Size` 를 `md` 로 고정**한다
> (기본 import 가 `sm` 이라 작게 나옴). 특수 케이스만 다른 size.
>
> **시스템 강제:** `_configure_segmented_control` (cmd_build, seg-tabs 설정 시) 이 인스턴스의
> `Size` variant 를 `md` 로 자동 설정(`config.size` 로 override 가능). blueprint 의 탭 인스턴스에
> `_segLabels` 마커만 박으면 라벨·선택과 함께 Size=md 가 자동 적용된다.

> 🔴 **절대 규칙 0-Q — radius 있는 frame 은 꼭 clipsContent=true (2026-06-04 사용자 룰)**
>
> 사용자 명시: *"frame에 radius 값을 넣으면 꼭!! Clip content 옵션 체크가 되어야 한다."*
>
> **cornerRadius(또는 개별 코너 radius)가 0보다 크면** 그 frame 의 `clipsContent` 는 **반드시
> true** — 둥근 모서리가 콘텐츠를 클립해야 내부 image/색 영역이 모서리 밖으로 안 삐져나온다.
> (예전엔 cr≥8 카드만 강제 → 2026-06-04 모든 radius>0 으로 확대.)
>
> **시스템 강제 (코드 박힘, 자동 — 3중):**
> 1. `_enforce_radius_clip_blueprint(bp)` (cmd_build pre-process) — blueprint 의 radius>0 FRAME 에
>    `clipsContent:true` 박음(batch_build 가 `spec.clipsContent` 반영). 명시 false 는 존중.
> 2. `_enforce_rounded_card_clip_live` (cmd_post_fix, R45 직후) — 라이브 백스톱(균일 cornerRadius).
> 3. 🔴 `_enforce_radius_clip_live(root_id, _collect_radius_clip_paths(bp))` (**Step E.7.7, AUTO_FIX
>    이후**) — R45 가 post-fix·AUTO_FIX 두 곳에서 시트/카드 clip 을 false 로 끄는데, **개별 코너
>    radius**(topLeftRadius 등)를 쓰는 frame(Modal Sheet)은 `get_nodes_info` 가 코너를 None 으로
>    직렬화해 R45 의 rounded 예외·라이브 검출이 모두 놓친다 → blueprint name-path 로 매칭해 clip=true
>    를 **최종 재단언**. (개별 코너 radius 회귀의 진짜 해법.) DS INSTANCE·root 제외.
> 빌드 후 검증: Modal Sheet 등 둥근 frame 의 Clip content 가 체크됨(내부 영역이 모서리 밖으로 안 튀어나옴).
> 테스트: `scripts/tests/test_radius_clip.py`.
>
> 🔴 **추가 (2026-06-04): radius 값은 `radius-*` DS 토큰에 바인딩.** cornerRadius(균일·개별
> 코너 모두)를 스케일 일치 `radius-*` 토큰에 자동 바인딩 — `_bind_radius_tokens_live`(post-fix,
> spacing 바인더 직후). 0=none 4=xxs 6=xs 8=sm 10=md 12=lg 14=xl 16=2xl 20=3xl 24=4xl 28=5xl
> 32=6xl, ≥100=full. 위 post-fix 항목 7-b 참조. blueprint 의 radius 는 이 스케일 값으로 쓸 것.

> 🔴 **절대 규칙 0-R — 디자인 생성 완료 시 사용한 blueprint json 자동 삭제 (2026-06-05 사용자 룰)**
>
> 사용자 명시: *"디자인 생성이 완료되면 디자인 생성 시 만들었던 블루프린트 json 파일은 자동 삭제
> 되도록 할 것! 코드로도 강제해."*
>
> 빌드가 끝나면 화면은 Figma 에 생성됐으니 그 빌드에 쓴 **blueprint/spec json 은 불필요** →
> `scripts/` 에 산출물이 쌓이지 않도록 **빌드 직후 즉시 자동 삭제**한다(생성 7일 대기하는
> `cleanup_old_blueprints.py` 와 별개 — 이건 즉시).
>
> **시스템 강제 (코드 박힘, 자동):** `figma_mcp_client.cmd_build` 가 빌드 성공(root_id 존재) 시
> 맨 끝에서 `_cleanup_build_input(blueprint_file)` 호출. 삭제 대상 = 빌드 입력으로 쓴
> `blueprint_*.json` · `spec_*.json` · `*assembled*.json` · `*_blueprint.json`.
> 🔴 **보존(소스/입력 자산은 삭제 안 함):** `blueprint_templates.json` ·
> `blueprint_unified_imin_home.json`(소스 템플릿) · `archetype_specs/*.json`(unified spec 소스) ·
> 이름에 `PRD`(사용자 입력) · `wireframe_content`(와이어 콘텐츠 dict).
>
> **빌드 후 검증:** 빌드 로그에 `🧹 [cleanup] 빌드 완료 — 사용한 blueprint json 자동 삭제: <파일>`
> 라인이 보이면 자동 삭제 성공. 단위 테스트로 삭제 대상/보존 분기 검증됨.
> ⚠️ blueprint 가 삭제되므로 동일 화면을 다시 빌드하려면 blueprint 를 새로 작성/조립해야 한다
> (의도된 동작 — 화면은 Figma 에 이미 있고 source 만 정리).

> 🔴 **절대 규칙 0-T — 하단 월렛 바는 top-left/top-right radius 16 (2026-06-05 사용자 룰)**
>
> 하단 고정 **월렛 바('마이 월렛')** 는 시트처럼 **위쪽 두 코너만 둥글게(topLeftRadius=topRightRadius=16
> = radius-2xl)**, 아래 두 코너는 0. 평평한 사각형 금지. blueprint 작성 시 월렛 바 frame 에
> `topLeftRadius:16, topRightRadius:16, clipsContent:true` 명시.
>
> **시스템 강제 (코드 박힘, 자동):** `_enforce_wallet_bar_radius(root_id)` (cmd_post_fix, section-bg-gap
> 직후) — 이름에 'wallet'/'월렛' 든 frame 의 top-left/top-right radius 를 16 으로 강제(`set_corner_radius`
> corners=[T,T,F,F]). radius>0 이라 0-Q 클립 enforcer 가 clipsContent=true 보장, 16 은 radius 바인더가
> radius-2xl 토큰으로 자동 바인딩. 생성기 6종 wallet_bar 에도 topLeftRadius/topRightRadius=16 박음.
> ⚠️ 이전엔 이 룰이 **없어서** 월렛 바가 평평했음(위반이 아니라 미구현) — 이제 박혔으니 재빌드에도 유지.

> 🔴 **절대 규칙 0-S — 텍스트 스타일 바인딩을 절대 깨지 말 것 (2026-06-05 사용자 룰)**
>
> 사용자 명시: *"텍스트 크기만 조절하려고 텍스트 스타일 바인딩이 깨졌는데 좀더 큰 사이즈를
> 적용하려면 텍스트 스타일에서 좀 더 큰걸 쓰면 되. 바인딩을 깨면 안된다!"*
>
> **텍스트 크기를 바꿀 때 raw `set_font_size` 로 styled 텍스트의 크기를 덮어쓰지 말 것** —
> 그러면 DS text style 바인딩이 detach(깨짐)된다. 크기를 키우려면 **같은 weight 의 더 큰
> DS 텍스트 스타일을 `set_text_style_id` 로 적용**한다(바인딩 유지). 줄이는 것도 동일.
>
> **시스템 강제 (코드 박힘, 자동):**
> - `_enforce_min_text_size_live(root_id)` (cmd_post_fix) 는 **절대 `set_font_size` 를 쓰지
>   않는다.** 작은 텍스트의 (size, weight) 를 읽어 floor 이상이 되는 DS 텍스트 스타일을
>   `set_text_style_id` 로 입힌다. DS 인스턴스 내부(';')·장식 기호 제외.
> - 🔴 **stale 맵 대응 — 실제 적용 크기 검증 + 에스컬레이션:** `ds/TEXT_STYLE_MAP.json` 이
>   stale 하면 (예: '14px' 키가 라이브 DS 에선 12px 로 import 됨) 적용 후 실제 size 가 floor
>   미달일 수 있다. 그래서 적용 후 `get_nodes_info` 로 실제 size 를 검증하고, 미달이면 다음
>   DS 스케일(16…)로 올려 재적용한다 — 항상 `set_text_style_id` 만 사용(바인딩 유지).
> - blueprint pre-process `_enforce_min_text_size` 는 fontSize 숫자만 올리고(텍스트 스타일
>   매핑 *전*), 이후 text-style 단계가 그 크기의 스타일을 바인딩 → raw size 가 남지 않는다.
>
> ⚠️ **TEXT_STYLE_MAP.json stale 시 (Pretendard 14px 등 일부 tier 가 깨졌을 때) 근본 해결:**
> 플러그인을 **DS 파일('Imin Design System')에 연결**한 뒤 `python3 scripts/figma_mcp_client.py
> sync-text-styles` 1회 실행 → 최신 키로 재추출·커밋. (variables 의 sync-variable-keys 와 동일 패턴.)
>
> **빌드 후 검증:** 텍스트 노드가 **size ≥ 하한 + textStyle 바인딩 유지**(get_nodes_info 의
> `styles.text` 존재) 인지 확인. raw fontSize 만 박히고 styles.text 가 빈 노드 = 위반.

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

### 2-J. ⚠️ Aqua 컬러 사용 자제 (2026-06-05 정책 재반전)
> 🔴 사용자 명시 (2026-06-05): *"전에 아쿠아 컬러 사용하라고 했었는데 이젠 아쿠아 컬러 사용을
> 자제하도록 규칙과 코드 수정해."* → 2026-06-02 의 **"Aqua 보조 액센트 권장"을 폐기**한다.
> 이제 **Aqua 컬러 사용을 자제**한다.
>
> ⚠️ **정책 이력 (3번 반전):** 2026-05-05 "aqua 쓰지마"(차단) → 2026-06-02 "Aqua 보조 액센트
> 권장"(반전) → **2026-06-05 "Aqua 자제"(재반전, 현재)**.
>
> - **주 액센트 = 브랜드 퍼플** (그대로): 주 액션(CTA)·active 탭/네비·핵심 hero 수치·진행바.
> - **상태색 = 진짜 상태에만** 소량: success(완료/곧 수령)·warning(미납/D-day)·error(연체).
> - **Aqua 는 자제** — 꼭 필요한 특수 케이스가 아니면 쓰지 않는다. 단조로움이 우려되면 Aqua
>   대신 **중립(`bg-secondary`/`bg-tertiary`/`text-secondary`)** 으로 카드·섹션을 차별화하거나
>   **brand tint(`bg-brand-secondary`/`text-brand-primary`)** 를 절제 사용한다. 🔴 **인접 섹션
>   시각 언어 차별화(0-N)는 색이 아니라 레이아웃·구조로도 한다** — 굳이 Aqua 같은 별도 색을
>   끌어오지 말 것.
> - **"여러 색 난무" 금지** 는 그대로.
>
> **시스템 강제 (코드 박힘):**
> 1. `scripts/design_rules/R26_second_accent.py` (rule_id `R26-aqua-restraint`) — **L2 lint
>    advisory**: Aqua 토큰이 화면에 쓰이면 WARN("Aqua 자제 — 중립/brand tint 로 대체"). 차단은
>    안 함(자제이지 완전 금지는 아님).
> 2. `figma_mcp_client.py _enforce_color_restraint` — 빌드 로그 `[색상]` 에 Aqua N곳 집계 +
>    N>0 이면 자제 권고 출력. (구: Aqua=0 단조 경고 → **폐기**.)
> 3. `figma_mcp_client.py _normalize_aqua_token` — **유지**. Aqua 를 정말 써야 할 특수 케이스
>    에서 올바른 색으로 해석·바인딩하기 위함(`utility-blue`=파랑 오염 방지). Aqua 토큰 자체가
>    죽은 건 아니다 — 자제할 뿐.
> 4. `scripts/design_rules/schema.py` — `aqua` 명시 토큰의 primitive-prefix ban 예외도 유지.
>
> **빌드 후 검증:** 빌드 로그 `[색상]` 에 Aqua 가 **0곳이거나 최소**인지 + 스크린샷에 청록색이
> 거의 없는지(브랜드 퍼플 + 상태색 + 중립 위주) 확인.

### 2-B. ⚠️ 카드 표면 — bg-primary + 보더 (root 위 카드, 2026-05-23 룰 / 2026-06-02 보더색 갱신)
- **루트 위 최상위 카드의 표면 = `$token(bg-primary)` fill + 보더 1px** — `bg-secondary`(회색)로 채우지 말 것. 흰 카드를 보더로 정의한다.
- 🔴 **보더 색 = 뒤(배경) fill 에 따라 결정 (2026-06-02 사용자 룰):**
  - **뒤 배경이 `bg-primary`(흰색)면 보더는 `$token(border-primary)`** — 흰 배경 위 흰 카드는
    연한 `border-secondary` 로는 경계가 거의 안 보여, **더 진한 `border-primary`(#d2d6db)** 로 정의한다.
  - 뒤 배경이 `bg-secondary`/`bg-tertiary` 등 비-흰색이면 보더는 `$token(border-secondary)`.
  - 사용자 명시: *"뒤에 fill color가 bg-primary일때 바로 위 frame의 border color는 border-primary를 사용할 것!"*
- 카드 안의 인셋·서브카드는 대상 아님 (필요 시 `bg-secondary`/`bg-tertiary` 유지). 브랜드 컬러 카드(`bg-brand-solid` 등)도 그대로 둔다.
- **예외 — 맨 아래 Footer (2026-06-05 사용자 룰: 배경색 없음)**: Footer는 **배경색 없음**(`$token(bg-primary)` = 루트와 블렌딩, 회색 띠 X) + **보더 없음**(그림자도 없음). 사용자 명시 *"footer의 bg color는 없는게 나을거 같다."* 강제: `_enforce_card_surface` 의 footer 분기가 footer fill 을 `bg-primary` 로 설정(과거 bg-secondary 회색 띠 폐기).
- **시스템 강제 (자동):** `_enforce_white_card_border_live`(post-fix)가 walk 하며 **각 카드의 뒤
  배경 fill 을 추적** — bg-primary 위면 border-primary, 그 외면 border-secondary 로 stroke 강제 +
  DS 변수 바인딩. 기존에 border-secondary 가 박힌 흰-배경 카드도 border-primary 로 업그레이드(idempotent).
  blueprint 에서 어떻게 쓰든 빌드가 바로잡는다.

### 2-B-2. ⚠️ 브랜드 틴트 '면'(블록/카드 표면)은 `bg-brand-primary` (2026-06-05 사용자 룰)
- 사용자 명시: *"이런건 컬러를 `bg-brand-primary` 를 사용게 시각적으로 맞아."* (강조된 '오늘'
  스케줄 블록 등 브랜드 틴트 면을 가리키며)
- **브랜드 틴트를 '면'(자식을 담는 블록/카드 표면)으로 쓸 때는 `$token(bg-brand-primary)`(#f4ecff,
  연한 라벤더)** 를 쓴다. **`bg-brand-secondary`(#e6d4ff)·`bg-brand-secondary-hover`(#cfaeff) 는 더
  진해 면 표면에 쓰면 시각적으로 무겁다 → 면에는 금지.** secondary 계열은 작은 액센트/상태(badge·
  dot·hover 등)에만.
- 적용 예: '오늘' 입금/지급 강조 블록, '차근차근 모을게요' 같은 틴트 카드 표면 → 모두 bg-brand-primary.
- **시스템 강제 (자동, 2중):**
  1. `_enforce_brand_tint_surface_primary(blueprint)` (cmd_build pre-process, no-large-brand-fill 직후) —
     **children 을 가진 frame** 의 fill 이 `$token(bg-brand-secondary[-hover])`/`bg-brand-primary_alt`
     면 `$token(bg-brand-primary)` 로 교정.
  2. `_enforce_brand_tint_surface_primary_live(root_id)` (cmd_post_fix, white-card-border *직전*) —
     라이브 트리에서 children 가진 FRAME 의 fill 이 #e6d4ff/#cfaeff 면 #f4ecff(bg-brand-primary)로
     교정 + 토큰 바인딩. DS 인스턴스·내부(`;`) 노드 제외.
- **빌드 후 검증:** 빌드 로그에 `[규칙] 브랜드 틴트 면 N건 → bg-brand-primary` 또는
  `[brand-tint-surface-live] ✓` 라인 확인. 틴트 블록/카드가 진한 보라(secondary)가 아니라 연한
  라벤더(primary)인지 스크린샷 확인.

### 2-C. ⚠️ 타이포 위계 — 크기·굵기로 시각 리듬 (2026-05-23 룰 / 2026-06-05 크기 정책 갱신)
- **컬러가 절제될수록 시각 위계는 폰트 크기·굵기로 강화한다.** 표준 type scale:
  - **HERO** (카드 안 핵심 금액·수치) — `28~36px Bold`
  - **TITLE** — `22~26px Bold`
  - **SECTION** (섹션 헤더) — `17~19px Bold`
  - **BODY (기본)** — `16px Medium/SemiBold` (DS `Body md`) ← 🔴 **기본 텍스트는 16**
  - **보조 (라벨·캡션·부제)** — `14px` (DS **`Body sm`**) ← 🔴 **간혹 쓰는 보조 크기**
  - **미세 (푸터·법적 고지·정말 작아야 하는 fine print)** — `12px` (DS `Body xs`) ← 🔴 **정말 작게 표현해야 할 때만**
- 🔴 **보조 텍스트는 DS `Body sm`(14) 스타일 (2026-06-05 사용자 룰):** 현황 라벨("총 스테이지 수
  86,696개"), 안내/재참여 문구("함께 모은 목돈, 다시 모아볼까요?"), 한도 디테일("한도 … 이용 중
  잔여 …"), 리스트 부제("출석 체크하고 포인트 받아요") 같은 보조 텍스트는 **`Body sm`(14px)** 이
  적절하다. (기본 본문=`Body md` 16, 미세=`Body xs` 12.)
- 🔴 **타이틀 아래 디스크립션 텍스트는 `Body sm`(14) ~ `Body xs`(12) (2026-06-05 사용자 룰):**
  사용자 명시 *"타이틀 아래 디스크립션 텍스트들은 sm, xs 정도로 쓰면 된다."* 섹션/카드 타이틀 바로
  아래 부제·설명("목돈을 이만큼 모았어요", "매월 얼마나 모을까요?", "어떤 방법으로 시작할까요?",
  리스트 부제 등)은 **16(Body md)으로 키우지 말고 `Body sm`(14) 또는 `Body xs`(12)** 로 둔다.
  타이틀(16~18)보다 작아야 위계가 산다 — 디스크립션을 16으로 올리면 타이틀과 동급이 돼 단조로움.
  - ⚠️ `ds/TEXT_STYLE_MAP.json` 이 stale 하면 Pretendard `Body sm`(14) 키가 빠져 있어(파일의 옛
    'Text sm' 키가 라이브 DS 에선 `Body xs`/12 로 import 됨) **Body sm 을 바인딩할 수 없다** →
    플러그인을 DS 파일('Imin Design System')에 연결 후 `sync-text-styles` 로 재추출해야 Body sm
    키가 맵에 들어온다(절대 규칙 0-S 참조). 재싱크 후엔 enforcer 의 (14,bucket) 조회가 Body sm 을
    바인딩한다.
- 같은 카드 안에 **최소 3단계 이상 차이**를 둔다 — HERO 금액은 본문(BODY)의 2배 안팎이어야 리듬이 산다.
- 🔴 **크기 하한 정책 (2026-06-05 사용자 룰): 기본 16 / 보조 14 / 12 는 정말 작은 경우(푸터·미세 문구)만.**
  사용자: *"기본이 16이고 아래 14를 간혹 쓰고 12는 정말 작게 표현해야 되는 경우일때만. 12pt 텍스트가
  너무 많이 쓰이고 있어."* → **일반 텍스트에 12pt 남용 금지.** 12/13pt 라벨은 14 로 올린다. 11/10pt 는
  쓰지 않는다(푸터 fine print 도 최소 12).
- **시스템 강제 (자동, 2중):**
  1. `_enforce_min_text_size(blueprint)` (cmd_build pre-process, font weight 정규화 직후) — 일반 텍스트
     fontSize < 14 → 14, 푸터(조상 이름 'footer') 안 미세 문구 < 12 → 12 로 상향. 장식 기호(●/>/−/+ 등
     단일문자·비문자)·제목·hero 는 제외. text-style 매핑 *전* 에 올려 올바른 DS 스타일 버킷이 선택됨.
  2. `_enforce_min_text_size_live(root_id)` (cmd_post_fix, 브랜드 틴트 면 직전) — 라이브 백스톱.
     get_nodes_info(batch)는 styled 텍스트 fontSize 를 None 으로 주므로 **TEXT 노드별 get_node_info 로
     실제 fontSize 를 읽어** 하한 미만이면 `set_font_size` 로 상향. DS 인스턴스 내부(';') 제외.
- `cmd_build`의 `_enforce_text_hierarchy`가 카드 안의 통화 hero(부호 `+/−` 또는 천단위 콤마가 있는 금액 텍스트)를 자동으로 **30px Bold**로 승격 — 본문이 hero보다 작게 작성되어 있어도 hero가 본문 위로 올라온다.

### 2-D. ⚠️ Modal 화면 패턴 — 상단 X만, Footer·Tab Bar·상단 탭 없음 (2026-05-24 룰)
- **Full modal** (홈 위로 슬라이드업되는 단일 화면, 예: 거래 스케줄 상세) 은:
  - **상단 헤더 = X(닫기) 버튼만** — 로고·알림·채팅·검색 등 nav 아이콘 없음. X 는 우측 상단(NavBar `primaryAxisAlignItems: MAX`).
  - **Footer 없음 · Tab Bar 없음 · 상단 Tab 메뉴(거래현황/누적거래 등) 없음** — 모달은 단일 컨텍스트.
  - 루트 높이는 콘텐츠에 HUG (불필요한 빈 공간 금지).
- Blueprint root 에 `"_screenType": "modal"` 명시 → `cmd_build`의 `_enforce_modal_pattern` 이 자동 강제: Footer / Tab Bar / 상단 탭(`Tab Row`/`Top Tab`/`Section Tab` 포함) / non-X nav 아이콘(`Logo`/`bell`/`chat` 등) 을 빌드 전에 제거하고 NavBar 를 우측 정렬한다.
- 🔴 **모달은 unified imin_home 베이스를 쓰지 말 것 — 와이어에 있는 것만 처음부터 custom blueprint 로.** 홈 대시보드 섹션(Screen Hero/Top Alert/Recommend/Lounge/Attendance/Mode Tabs/Tab Bar/FAB/Footer)을 끌어오면 **R58 (`design_rules/R58_modal_no_home_sections.py`) 가 build 를 차단**한다 (2026-05-28 사용자 분노). 와이어에 진짜 있는 드문 경우만 `_modalAllowSections:[...]` 로 허용.
- 🔴 **루트 높이 = HUG 필수** — 모달 root 가 FIXED(852)면 하단 CTA 가 잘린다. `layoutSizingVertical: "HUG"` 로 콘텐츠 전체 + CTA 가 보이게.
- 모달이 아닌 일반 화면은 기존대로 (NavBar 풀세트 + Tab Bar + Footer).

### 2-G. ⚠️ 하단 CTA = DS Button 컴포넌트 인스턴스 우선 (2026-05-24 룰)
- **하단 CTA 버튼(Bottom Action Bar 의 Primary CTA / Submit Button / 참여하기 등) 은 무조건 DS `Action Button` 컴포넌트 인스턴스로 만든다.** raw frame 으로 그리지 말 것.
- DS Button 으로 표현이 안 되는 특수 케이스(이중 버튼, 그라데이션 CTA 등)에 한해 직접 그릴 수 있음 — 그 외는 항상 instance.
- **사용할 키 (scripts/design_rules/ds_catalog.py):**
  - `Action Button md Primary` (`ed0032bcf28f03da97e4b3006f54d30a0fbe5914`) — 기본 CTA
  - `Action Button md Secondary` / `Tertiary` / `Outline` / `Ghost` — 위계별
  - `Action Button sm` (`a8a4d7eb7874c469ab89105cc342fad85a3d28ce`) — 보조 CTA
- **🔴 사이즈 — 하단에 고정되거나 보이는 CTA 버튼은 `Size: lg` 가 기본 (2026-05-28 사용자 명시).** 비활성은 `State: Disabled`.
  - **코드 강제:** blueprint 의 `properties:{Size:lg}` 는 빌드 때 무시되므로, `_enforce_ds_button_sizing` (post-fix) 가 **VERTICAL 부모의 전폭 CTA 의 Size variant 를 lg 로 자동 강제** → `set_instance_properties`. 매 빌드 자동 적용.
- **라벨:** Action Button 라벨은 nested TEXT("Button CTA") 라 `properties.label` 로 **안 바뀐다**. `set_text_content` 또는 inject 의 `_instanceText` / label_map 로 override. ⚠️ Size 등 **variant 변경 후엔 라벨 재확인** (variant swap 이 override 를 리셋할 수 있음).
- **시스템 강제 (기존):** R23 inject 의 `detect_button_shape` 가 raw button frame 을 자동 swap. catalog 미스 시 build ERROR.
- Blueprint 작성 시: `{"type":"instance","componentKey":"ed0032bcf28f03da97e4b3006f54d30a0fbe5914","_instanceText":"참여하기","properties":{"Size":"lg","State":"Disabled"}}` 패턴.
- 🔴 **instanceProperties(variant flip) 자동 적용 — 수동 flip 영구 제거 (2026-06-04):**
  `batch_build_screen` 의 `create_component_instance` 는 blueprint 의 `instanceProperties`/
  `_instanceVariants`(Hierarchy=Primary, Color=Warning, Size=lg 등)를 **적용하지 않는다**(인스턴스만 생성).
  그래서 'Action Button md Secondary' 키로 import 후 Hierarchy=Primary 로 flip 하려던 CTA 가
  매 빌드 Secondary(연보라)로 남아 **매번 수동 flip** 하던 회귀가 있었다. → `_collect_instance_variant_paths`
  + `_enforce_ds_instance_variants`(post-fix, ds-button-sizing **직전** 실행)가 경로 매칭으로
  `set_instance_properties` 자동 적용. blueprint 인스턴스에 `"instanceProperties":{"Hierarchy":"Primary",...}`
  박으면 빌드 후 자동 flip(로그 `[ds-instance-variant] ✓`). [[ds-action-button-primary-key-broken]] 우회 자동화.

> 🔴 **2-G-2. ⚠️ 하단 액션바 버튼 높이 통일 — 제일 큰 것에 맞춤 (2026-06-02 사용자 룰)**
>
> 사용자 명시: *"버튼의 높이가 왜 다르지? 제일 큰거와 같아야 되. 이건 수정하고 규칙 강화하고 코드에 박아."*
>
> **하단 액션바(Bottom Action Bar / Action Bar / CTA Bar) 안의 모든 버튼·아이콘 박스는 높이가
> 같아야 한다 — 그 중 제일 큰 것의 높이로 통일.** (북마크·채팅 아이콘 박스가 DS CTA 버튼보다
> 낮게 찌부러지는 회귀 차단.)
>
> **회귀 원인:** 아이콘 박스(VERTICAL HUG)는 콘텐츠 높이(아이콘 ~22 / 아이콘+라벨 ~37)로
> 붕괴하는데 옆 DS CTA 버튼은 ~44~56 라 높이 제각각.
>
> **시스템 강제 (코드 박힘, 자동):** `_enforce_action_bar_equal_height(root_id)` (cmd_post_fix,
> **size-invariant 이후**에 실행해 최종 권한 — size-invariant 의 icon-box 정사각화가 한쪽만
> 키우는 충돌 방지). 액션바 직계 버튼/박스 중 최대 높이 H 계산 → 낮은 것들을 vertical FIXED +
> height=H 로 통일. ⚠️ Bottom **Tab Bar** 는 `_enforce_tab_bar_children_fill_live` 가 따로 처리(제외).
>
> 🔴 **함정 (2026-06-04 회귀): `resize_node` 는 폭·높이 둘 다 FIXED 로 박는다.** height 통일
> 하려고 전폭 CTA 버튼에 `resize_node` 를 호출하면 **가로 FILL 이 깨져 폭이 고정 → "참여하기"
> 라벨이 잘린다**(이미지에 "참"만 보임). 그래서 이 룰은 CTA(액션바 최대폭 자식 / INSTANCE /
> 이름에 btn·button·cta·submit·참여)에 대해선 height 조정 후 **무조건 `horizontal=FILL` 재단언**
> 한다. ⚠️ '원래 가로 모드 보존' 방식은 NG — 직전 패스에서 이미 FIXED 가 된 버튼의 FIXED 를
> 그대로 보존하는 버그가 있었다. 전폭 CTA 는 항상 FILL 로 강제.
>
> 🔴 **target = CTA 버튼 높이 기준 (2026-06-04 재정의):** 처음엔 'max 높이'를 target 으로
> 썼는데, size-invariant 가 아이콘 박스(단일자식)를 정사각(56)으로 키우면 박스(56) > CTA(44) 가
> 되어 역전 → 사용자 원래 의도("작은 아이콘 박스를 **CTA 높이에 맞춰라**")와 어긋났다. 이제
> **target = CTA 높이**, 아이콘 박스가 거기 맞추고 **CTA 자신은 높이 안 건드림**(DS 버튼은
> 억지로 키우면 안 붙음). CTA 없으면 max 폴백.

> 🔴 **2-G-3. ⚠️ 상단 NavBar 우측 액션 = 아이콘 버튼 (텍스트는 특수 케이스만, 2026-06-04 사용자 룰)**
>
> 사용자 명시: *"상단 네비게이션바 우측에 일반적으로 아이콘 버튼이 위치하는데 지금처럼 텍스트
> 버튼이 들어가면 안되. 아주 특수한 경우에만 텍스트 버튼을 사용할거야."*
>
> NavBar 우측의 액션 라벨(공유/완료/편집/저장/닫기/취소/다음/더보기/검색/알림 등)은 **텍스트가
> 아니라 아이콘 버튼**. **아주 특수한 경우**만 텍스트 — 매핑에 없는 라벨이거나 노드에
> `"_navTextAllowed": true` 마커가 있으면 텍스트 유지.
>
> **시스템 강제 (코드 박힘):** `scripts/design_rules/R62_navbar_icon_action.py`
> - L2 lint: NavBar 안 액션 라벨 TEXT 발견 시 WARN.
> - L3 inject: 알려진 액션 라벨(`_ACTION_ICON` 맵: 공유→share-07, 완료/저장→check, 편집→edit-02,
>   닫기/취소→x-close, 다음→arrow-right, 더보기→dots-vertical, 검색→search-lg …)에 **정확히 일치**
>   하는 TEXT 를 ICON 노드로 교체 → build 가 svg_icon 생성. **제목(매핑에 없음)은 안전하게 유지.**
> - L5 verify: 빌드 후에도 액션 라벨 텍스트가 남으면 WARN.
> - blueprint 작성 시 NavBar 우측에 "공유" 같은 액션은 처음부터 `{"type":"icon","iconName":"share-07"}`
>   로 써도 되고, 텍스트로 써도 R62 가 자동 교체한다. 새 액션 라벨은 `_ACTION_ICON` 맵에 추가.

> 🔴 **2-G-4. ⚠️ 연속된 전폭 CTA 는 위계 차등 — 덜 중요한 것은 Outline/Tertiary (2026-06-05 사용자 룰)**
>
> 사용자 명시: *"CTA 버튼이 위 아래 연속적으로 있을땐 좀 더 덜 중요한 버튼의 위계를 tertiary 나
> outline 으로 설정하도록 규칙 추가하고 코드에 박아."*
>
> 세로로 인접한 전폭 DS Action Button **Primary** 인스턴스가 2개 이상이면 한 화면에 같은 강조색
> CTA 가 위계 없이 경쟁한다(예: 월렛 "목돈 출금하기" 바로 아래 납입 "지금 납입하기" 둘 다 보라).
> → **화면 맥락상 더 중요한 액션 1개만 Primary 로 두고 나머지를 `Outline`(실패 시 Tertiary→
> Secondary 폴백)으로 자동 다운그레이드**한다.
>
> 🔴 **어느 게 더 중요한가 = 맥락 판단 (2026-06-05 사용자: "화면상에서 맥락을 고려해 더 중요한
> 액션은 primary 로"):** 코드가 의미를 완벽히 알 순 없으므로 **3단 우선순위**로 keeper(=Primary
> 유지) 를 정한다:
> 1. **blueprint `_ctaKeepPrimary: true` 마커 (최우선·원칙)** — 🔴 Claude 가 blueprint 작성 시
>    화면 맥락(어느 액션이 더 긴급·의무·핵심인가)을 판단해 더 중요한 CTA 에 직접 박는다. 예:
>    D-1 납입(의무·놓치면 미납/i-CSS 하락) > 월렛 출금(선택) → 납입에 마커.
> 2. **라벨 의미 휴리스틱** — 마커 없으면 라벨로 추론: '주 액션' 동사(납입/결제/제출/참여/신청/
>    확인/시작/완료/동의/송금/주문/가입…)가 '보조'(출금/취소/나중에/더보기/공유/저장/닫기…)보다
>    우선. 그룹 일부만 주 액션이면 그것을 Primary 유지.
> 3. **맨 아래 폴백** — 둘 다 판단 불가(모두 주 액션 / 모두 중립)일 때만 맨 아래(엄지 영역) 유지.
>
> **시스템 강제 (코드 박힘, 자동):** `figma_mcp_client._enforce_consecutive_cta_hierarchy(root_id, bp)`
> — cmd_post_fix chain 의 **multicol-fill *뒤*** 에 실행(button-sizing 직후엔 set_layout_sizing(FILL)
> 리렌더 전이라 전폭 width 가 stale → 못 잡음. 모든 width/sizing 강제가 끝난 뒤라야 신뢰성 있음).
> 전폭 = absoluteBoundingBox width ≥ 250. '연속' = 두 전폭 Primary CTA 사이 세로 간격 < 320px
> (카드 1개 경계 정도). 멀리 떨어진(스크롤상 다른 맥락) CTA·캐로셀 카드 안 CTA(폭 < 250) 는 제외.
> 라벨은 인스턴스의 `Label#…` prop 에서 읽는다.
>
> **빌드 후 검증:** 빌드 로그에 `[cta-hierarchy] '<name>' Primary → Outline` 라인이 보이면 자동
> 적용 성공. 스크린샷에서 **맥락상 더 중요한 CTA 가 채움(Primary), 덜 중요한 것이 테두리(Outline)**
> 인지 확인. 🔴 **새 화면 작성 시 연속 전폭 CTA 가 생기면 Claude 가 반드시 더 중요한 쪽에
> `_ctaKeepPrimary` 를 명시**한다(휴리스틱·맨아래 폴백에 의존하지 말 것).

> 🔴 **2-G-5. ⚠️ 수평 연속 동일 성격 CTA = Tertiary (FAB 있는 화면, 2026-06-05 사용자 룰)**
>
> 사용자 명시: *"fab 버튼도 있는 화면에서 수평으로 연속된 버튼 같은 경우는 성격까지 같다면
> 버튼 위계를 tertiary 로 설정되게 규칙 추가하고 코드에 박아."*
>
> 캐로셀 등에서 **가로로 나열된 DS Action Button 이 2개 이상 + 라벨(성격)이 동일**하면(예:
> 추천 카드 2장의 "참여하기" × 2) 위계 경쟁이 무의미하고, FAB(brand 주 액션)가 이미 화면의
> brand 강조점이라 **brand 과다**가 된다 → 그 CTA 들을 전부 **Tertiary**(폴백 Outline→Secondary)로
> 자동 다운그레이드한다. **FAB 가 있는 화면에만** 적용(brand 강조점이 이미 있다는 전제).
>
> **세로 규칙(2-G-4)과 구분:** 2-G-4 는 전폭(width≥250) 세로 연속 CTA 의 위계 차등(주 액션 1개만
> Primary). 2-G-5 는 캐로셀 카드 안 **수평 반복 동일 라벨** CTA(폭<250 라 2-G-4 대상 아님)를 전부
> Tertiary. 두 규칙은 대상이 갈려 충돌 없음.
>
> **시스템 강제 (코드 박힘, 자동):** `figma_mcp_client._enforce_horizontal_repeated_cta_tertiary(root_id)`
> — cmd_post_fix chain 의 `_enforce_consecutive_cta_hierarchy`(세로) 직후. 같은 라벨(`Label#` prop)
> CTA 들의 top 편차 < 40px(같은 행) + x 가 서로 다름 → 수평 반복으로 보고 Tertiary flip. FAB(이름에
> 'fab') 없는 화면은 skip.
>
> **빌드 후 검증:** 빌드 로그 `[cta-horiz-tertiary] '<name>' (<라벨>) → Tertiary` 라인 확인.
> 스크린샷에서 캐로셀 반복 CTA 가 채움(Primary)이 아니라 약한 위계(Tertiary)이고 FAB 만 brand
> 강조점인지 확인.

### 2-I. ⚠️ 폼 컨트롤(체크박스/토글/라디오/인풋)은 DS 컴포넌트 인스턴스 — raw frame 금지 (2026-05-28 사용자 분노)
- **체크박스를 raw 원형/사각 frame + check 아이콘으로 그리지 말 것.** DS 컴포넌트 인스턴스 사용:
  - `Checkbox md` (`bbd5c20958464e51295e73c3c90ef7d54c0b0b69`, 20×20, unchecked) / `Checkbox md checked` (`73691ec35c62c70735d61722347dfd995b32c5ec`)
  - 토글/라디오/인풋/슬라이더/드롭다운도 동일 — `_VERIFIED_AUTOSWAP_ROLES` 의 DS 컴포넌트로.
- Blueprint: `{"type":"instance","componentKey":"bbd5c20958464e51295e73c3c90ef7d54c0b0b69"}` 패턴.
- R23 의 `detect_checkbox_shape` 는 현재 key UNVERIFIED → WARN only 라 자동 swap 안 됨 — **작성 시 직접 instance 로 쓸 것** (raw frame 으로 그리면 사용자 분노).

### 2-F. ⚠️ 루트 minHeight=852 + 하단 바 bottom-pin (2026-05-24 룰)
- 루트 프레임 **min height = 852** (iPhone 16 뷰포트). 콘텐츠가 늘어나면 그에 따라 같이 늘어남.
- 콘텐츠 합이 852 보다 짧을 때, 화면에 고정된 하단 바(**Bottom Action Bar / Tab Bar / CTA Bar / FAB**) 는 **루트 하단(y = 852 - bar.height)에 bottom-align** — 콘텐츠 끝에 붙어 떠 있지 않게 한다.
- **시스템 강제:** `cmd_post_fix` 의 `_enforce_root_min_height` (scripts/figma_mcp_client.py, 2026-05-24) — 루트 높이 < 852 시 852 로 늘리고, 이름에 `tab bar`/`tabbar`/`bottom action bar`/`action bar`/`cta bar`/`fab` 포함된 자식을 ABSOLUTE + bottom constraint MAX 로 새 루트 하단에 재배치. 콘텐츠가 852 보다 길면 손대지 않음 (콘텐츠 끝이 곧 바의 위치).

### 2-E-5. ⚠️ 행 셀 그룹 세로 사이징 통일 — baseline 어긋남 차단 (2026-06-02 사용자)
- **사례**: 회차 셀렉터 "Round Cell 1~13" 중 **2자리(10~13)만 빌드가 FIXED h=36 으로 키워**(1~9 는 HUG h=23), 더 높은 셀 안 숫자가 ~6px 아래로 내려가 정렬이 틀어짐. ⚠️ **blueprint 는 13개 전부 HUG 로 올발랐다 — 빌드 단계가 일부 셀만 키운 회귀**(그래서 blueprint 만 고쳐선 못 막음 → post-fix 가드 필수).
- **시스템 강제** — `_normalize_row_cell_vertical_sizing_live(root_id)` (`cmd_post_fix` chain):
  1. HORIZONTAL parent 의 직계 FRAME 자식 중, 이름 끝 숫자를 뗀 **prefix 가 같은 셀 그룹**(예 'Round Cell')이 3개+ 인 경우 감지
  2. 그 그룹의 `layoutSizingVertical` 이 섞였거나 height 가 2px 초과로 다르면 → **다수 사이징으로 통일**(다수가 FIXED 인데 height 들쭉날쭉이면 HUG 로 — 텍스트 셀은 HUG 가 정답)
  3. idempotent — 일관되면 no-op
- **회귀 신호**: 숫자/날짜 셀 행에서 일부 셀(보통 2자리)의 텍스트만 위/아래로 어긋남, 언더라인이 두 높이로 끊김
- 🔴 **2026-06-02 원형 셀 찌부 회귀 + 근본 버그 fix (사용자 "왜 순번 블록들이 찌부되어있지?"):**
  - **증상**: 원형 순번 셀(cornerRadius 999, 32×32)이 세로 HUG 로 붕괴해 **h=14 타원(pill)** 이 됨.
    한 행에서 셀 개수 다르면(1~9 행 vs 10~13 행) 타원 폭도 달라 보임.
  - **뿌리 1 — size-invariant 가드 무력화**: `_enforce_fixed_size_invariants_final`(원형→정사각 복원
    최종 가드)이 `node.get("width")` 를 읽었는데, **`get_nodes_info` 는 width/height 를 top-level 이
    아니라 `absoluteBoundingBox` 에만 담아 반환** → 항상 `None` → 가드가 **통째로 0건** 동작.
    → `_node_wh(n)` 헬퍼 신설(absoluteBoundingBox 폴백)로 수정 → 이제 정상 복원.
  - **뿌리 2 — HUG 룰이 원형 셀까지 붕괴**: `_enforce_horizontal_row_hug_v_live`(HORIZONTAL + 자식
    전부 TEXT → HUG)가 원형 셀을 HUG 로 만듦. `_qualifies` 에 **원형(cornerRadius≥w/2) · 작은
    정사각(폭≤60, |w−h|≤8) 셀 예외** 추가 — FIXED 정사각 유지.
  - blueprint 의 round_cell 은 FIXED 32×32 로 작성하면 됨(post-fix 가드가 보장).
- 🔴 **2026-06-04 참여자 아바타 원형 붕괴(가로만 좁아짐) — size-invariant min-width 버그:**
  - **증상**: 참여자 썸네일 아바타(원형 36×36)가 가로만 FIXED→**HUG 로 붕괴해 폭=아이콘폭(16px)**,
    세로 30 그대로 → 세로로 긴 좁은 pill. (셀이 가로로 줄어든 케이스 — 위 round 셀은 세로 붕괴.)
  - **뿌리**: `_enforce_fixed_size_invariants_final._is_circle_iconbox` 가 `20 <= w` 를 요구해,
    **한 축이 16px(<20)로 붕괴한 원형을 감지 못 함** → 복원 누락. → `max(w,h)` 기준으로 범위
    체크하고 `cornerRadius>=100`(999 류) 이면 붕괴해도 원형으로 인식하도록 수정 → max(w,h) 정사각 복원.
  - **참여자/멤버 아바타는 랜덤 이미지 사용** (사용자 OK): blueprint 아바타 frame 에
    `"imageQuery":"portrait,face,person"` 박으면 `apply_image_queries` 가 loremflickr 랜덤 사진을
    `set_image_fill` + placeholder 아이콘 제거. `clipsContent:true` + cornerRadius 999 로 원형 클립.
- 🔴 **2026-06-04 얇은 pill/드래그 핸들/dot 이 거대 원으로 폭주 — size-invariant min 가드:**
  - **증상**: 바텀시트 드래그 핸들(40×4)·월 셀 dot(5×5)이 빌드 후 셀을 가득 채우는 **거대한
    원**이 됨. 핸들=40×40 원, dot=75×75 원.
  - **뿌리**: 장식 요소가 cornerRadius 999 인데 FILL enforcer 가 한 축을 늘리면(핸들→풀폭,
    dot→셀폭) `_enforce_fixed_size_invariants_final._is_circle_iconbox` 가 `max(w,h)` 정사각
    복원 대상으로 잡아 거대 원으로 만든다. → 순수 함수 `_is_circle_square_target(w,h,cr,childType)`
    에 **`min(w,h) >= 12` 가드** 추가: 얇은 pill/핸들/dot(min ≤ 5) 제외, 진짜 붕괴 원형
    아바타(min ~16)는 보존. 테스트 `scripts/tests/test_circle_square_target.py` 10케이스.
  - **blueprint 팁**: 작은 dot 인디케이터는 frame(원형) 대신 **text bullet "●"** 로 — 프레임
    enforcer 의 FILL/정사각화에 면역. 드래그 핸들은 `layoutSizingHorizontal/Vertical:"FIXED"`.

> 🔴 **2026-06-04 — `isTabBar` 가 'nav' 든 컨트롤 프레임을 하단 탭바로 오인 → 흰 fill+보더 강제:**
> `enhanceBlueprint`(figma-mcp-embedded.ts)의 `isTabBar` 가 이름에 **'nav'/'bottom'** 만 들어가도
> (자식 3~6 + 텍스트) 하단 탭바로 보고 **흰 fill(1,1,1) + top border(0.95,0.96,0.96)** 를 강제했다.
> → 'Year Nav'(연도 네비)·상단 'NavBar' 가 카드처럼 흰 박스+보더로 깨짐(사용자 분노). 절대규칙
> 0-O(상단 NavBar 룰)와 **다른 별개 버그**. 수정: `isTabLike` 를 하단 탭바 전용 표현만 매칭
> (`tab`/`탭`/`bottom nav`/`bottom tab`/`하단`)으로 좁힘 — 바 `nav`/`bottom` 제외. ⚠️ TS 변경이라
> `npm run build` + 브리지 재시작 후 적용. 컨트롤/네비 행은 의도치 않은 fill/stroke 를 받지 않는다.

### 2-E-4. ⚠️ Bottom Tab Bar 자식 FILL + 라벨 wrap 차단 (2026-05-28 사용자 분노)
- **사례**: Bottom Tab Bar 5개 자식 (Tab 홈/커뮤니티/스테이지/라운지/나) 이 HUG horizontal 로 박혀, tab-label TEXT 가 width=24 (아이콘 width 따라가서) 좁아져 "커뮤/니티", "스테/이지", "라운/지" 같이 두 줄 wrap. R13.3 inject 후에도 회귀 가능.
- **시스템 강제** — `_enforce_tab_bar_children_fill_live(root_id)` (`cmd_post_fix` chain):
  1. 이름에 'tab bar' / 'tabbar' / 'bottom tab' / 'bottom nav' 포함 HORIZONTAL parent + 자식 3+ frame 감지
  2. parent → layoutMode=HORIZONTAL + primaryAxisAlignItems=MIN + counterAxisAlignItems=CENTER + itemSpacing=0
  3. 각 tab 자식 frame → layoutSizingHorizontal=FILL (5등분 균등)
  4. tab 자식 안 TEXT (tab-label) → textAutoResize=HEIGHT + textAlignHorizontal=CENTER + layoutSizingHorizontal=FILL
- **회귀 신호**: Tab Bar 라벨이 두 줄로 wrap 되거나 width 가 24px 정도로 좁아짐

### 2-E-3. ⚠️ 작은 cell (width ≤ 60) 안 TEXT — 중앙 정렬 + 모서리 잘림 차단 (2026-05-28 사용자 명시)
- **사례**: Month Cell Jan Active (44×44) 안 "Jan/1" 흰 텍스트가 좌측 정렬되어 cell 가장자리에 박힘. 다른 month cells "Oct/Nov/Dec/Feb/Mar/Apr" 도 cornerRadius=20(원형) + 텍스트 width=cell width 가득 → 좌우 둥근 모서리에 의해 "Jct/Vov/Jec" 처럼 잘림.
- **룰 (3단)**:
  1. **작은 cell 안 TEXT 는 textAlignHorizontal/Vertical=CENTER 강제** — width ≤ 60 frame 안 TEXT 자식은 무조건 중앙. blueprint 에 명시 안 했어도 post-fix 가 강제
  2. **작은 cell 의 cornerRadius 가 width/3 이상 + 텍스트 가득 시 cornerRadius 축소** — 원형 cell 안 텍스트 가득은 좌우 잘림 → cornerRadius = max(8, width/5) (rounded square 로 변경)
  3. **3-col label/value grid (Summary Grid 등) — 균등 분포 + 컬럼 안 텍스트 중앙 정렬 강제** — HORIZONTAL parent 안 라벨/값 VERTICAL stack col ≥ 2 패턴 감지 시: parent layoutMode=HORIZONTAL + primaryAxisAlignItems=MIN + counterAxisAlignItems=CENTER, 각 col → FILL horizontal + VERTICAL + counterAxisAlignItems=CENTER, col 안 TEXT 자식 textAlign=CENTER. 컬럼이 카드 width 균등 분배 + 텍스트 컬럼 중앙
- **시스템 강제 (cmd_post_fix 자동)**:
  - `_center_text_in_small_cells_live(root_id)` — 작은 cell 안 TEXT 중앙 정렬
  - `_fix_text_clip_in_small_round_cells(root_id)` — 원형 cell 잘림 차단
  - `_fix_space_between_col_baseline(root_id)` — SPACE_BETWEEN col baseline MIN 통일
- **회귀 신호**: cell 안 텍스트가 좌측·우측에 박혀있음, 셀 모서리에서 글자가 잘림, 3-col grid 라벨이 다른 y 위치

### 2-E-2. ⚠️ Rounded card (cornerRadius ≥ 8) 는 clipsContent=true 유지 (2026-05-28 사용자 명시)
- **R45 가 모든 비-carousel frame 의 clipsContent=false 를 강제하던 부작용**: 라운지 카드처럼 cornerRadius=16인 카드 안 image/색 영역(예: 보라 Lounge Image 120px)이 카드 라운드 모서리 밖으로 튀어나와 **상단이 각져 보이는 버그**.
- **룰**: `cornerRadius ≥ 8` (또는 individual `top*Radius` 중 하나라도 ≥ 8) frame 은 `clipsContent=true` 유지. R45 의 clip-false 강제 대상에서 제외.
- **시스템 강제 (2단)**:
  1. `_disable_section_clipping` (R45) 의 `is_rounded_card()` 가드 — cornerRadius ≥ 8 frame skip
  2. `_enforce_rounded_card_clip_live(root_id)` 가 R45 직후 chain — rounded card 의 clipsContent=true 강제 (generator/manual fix 가 false 박아도 복구)
- shadow 는 어차피 `_strip_all_drop_shadows` 가 다 제거하므로 R42(shadow clearance)와 충돌 없음.
- 회귀 신호: 카드 안 보라/이미지 영역의 **상단** 모서리가 직각으로 보임 (카드 모서리는 둥근데 내부만 각짐).

### 2-E. ⛔ Section Divider 자동 삽입 폐기 (2026-05-27 사용자 명시)
- **"frame에 border를 추가하라니깐 엉뚱하게 섹션 사이에 선을 넣고있냐!!!"** — 섹션 사이에 1px divider 라인 자동 삽입 금지. 이전(2026-05-24) 룰 폐기.
- 정보 그룹 경계는 **카드 자체의 border** 로 표현한다 — `_enforce_white_card_border`(fill=`bg-primary` frame 에 `border-secondary` 1px 자동) + 카드별 stroke 토큰 바인딩이 담당.
- **시스템 강제:** `_enforce_section_dividers` 는 폐기 (no-op + 입력 divider 노드 자동 제거). `cmd_post_fix` 끝에 `_strip_section_dividers` 가 빌드 트리의 모든 "Section Divider" 노드 자동 삭제 — 회귀 차단.
- Blueprint 에 명시적으로 "Section Divider" 노드 작성하지 말 것. drop-shadow 도 함께 금지 ([[feedback_no_drop_shadow]] 참조).

### 3. Tab Bar 아이템은 반드시 FILL 균등 분배
- Tab Bar 내 모든 아이템: `layoutSizingHorizontal: "FILL"`, `layoutSizingVertical: "FILL"`
- HUG/FIXED 혼용 금지 — 아이템 간격이 불균등해짐
- 빌드 후 반드시 Tab Bar 아이템 사이징 검증할 것

### 5-B. ⚠️ 상단 모드 탭 = Imin DS Segmented_control (2026-06-02 DS v7 폐기)
- 🔴 **DS v7 "Horizontal tabs"(129dd87…/dda7a104…) 전면 폐기** — 모바일에서 드롭다운("My details")으로 붕괴 + DS v7 라이브러리 의존. 사용자 룰(2026-06-02)에 따라 Imin DS **`Segmented_control`** 으로 통일. 절대 규칙 0-J 참조.
- **컴포넌트 키** (Imin Design System): Style=hug `47a01673a46dc3bc9bfd62948c10e5fa9f2e5e78` / Style=fill `2ee9d12d4c904650ab496b9bcdf874a648e73ceb` (set `143ee3e3…` import 불가).
- **생성기**: `unified_blueprint.py _gen_mode_tabs` 가 Mode Tabs Wrap 안에 Segmented_control 인스턴스 1개 emit + **`_segLabels:[…]` + `_segActive:N`** 마커.
- **✅ 완전 자동화 (prop 기반, 2026-06-02)**: `cmd_build` 의 `_configure_segmented_control` 가 자동으로 — `Show Segment 3~8#16713:{n-3}` 불리언으로 세그먼트 개수 + 각 세그먼트 인스턴스의 `Label#17537:11` TEXT prop 으로 라벨 + `Active` on/off prop 으로 선택. nested 텍스트노드 id 가 아니라 **prop** 으로 설정해 견고(텍스트노드 id 는 variant 마다 달라 깨짐). 수동 단계 불필요.
- 회귀 신호: 탭이 "전체/전체" / 드롭다운 / DS v7 키(129dd87…) 사용. 상세 → 메모리 [[segmented-control-prop-labels]].

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
- **🔴 FAB 아이콘 컬러 (2026-05-28 사용자 강력 명시)**: **무조건 `$token(fg-light)`** (`#ffffff`). brand-solid 보라 위 흰 아이콘이 정석. `fg-white`(alias — silent skip 위험) / `fg-primary_on-brand` / 검정 / raw RGB 모두 금지. **시스템 강제 3단:**
  1. blueprint inject: `R57_fab_icon_fg_light.py` 가 FAB 자손 icon/vector 의 `iconColor`/`fill`/`stroke`/`strokeColor` 를 자동으로 `$token(fg-light)` 교정
  2. cmd_post_fix 끝: `_enforce_fab_icon_color_live(root_id)` 가 라이브 트리 FAB 자손 VECTOR/ICON 의 `fills/0`·`strokes/0` 을 fg-light 로 강제 + 바인딩
  3. 두 곳 모두 idempotent — 새 세션 회귀 차단
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
- 🔴 **인디케이터(dot)는 DS `Pagination dot group` 컴포넌트 인스턴스 (2026-06-05 사용자 룰):**
  캐로셀/배너 인디케이터는 raw bullet("●")·dot frame 으로 그리지 말고 **Imin DS `Pagination dot group`**
  인스턴스를 쓴다. 사용자 명시 *"imin DS에 Pagination dot group component가 있어서 그걸 쓰면 돼."*
  - 기본 키 (Style=Dot, Framed=False): **lg** `2ac006ab01ff82ad9b74c16d4cf6c17609a02d79` /
    md `347badbada16ce6814540e82246101d2dc65a295` (catalog `COMPONENT_KEYS["Pagination dot group"]`).
  - blueprint: `{"name":"Indicator","type":"instance","componentKey":"2ac006ab…","layoutSizingHorizontal":"HUG"}`.
  - **시스템 강제:** 홈 생성기(`gen_*home*.py`)의 캐로셀 Indicator 를 이 인스턴스로 **직접 작성**(explicit)
    + `ds_catalog.COMPONENT_KEYS["Pagination dot group"]` 에 키 등록. 새 blueprint 작성 시 캐로셀
    인디케이터는 반드시 이 인스턴스로 쓸 것. (스케줄 dot 등 **캐로셀이 아닌** 작은 dot 은 인디케이터가
    아니므로 text bullet 유지 — 캐로셀 인디케이터만 이 컴포넌트.)

### 11. ⚠️ 카드 내 레이블/버튼 텍스트는 반드시 가시적으로
- 카드 내 텍스트가 배경색과 비슷하면 안 보임
- 텍스트 컬러: `$token(fg-primary)` 또는 `$token(fg-secondary)` 사용 (어두운 색)
- 카드 배경이 밝은 색이면 텍스트는 Bold + 어두운 색 필수
- **빌드 후 검증**: 스크린샷에서 모든 레이블/버튼 텍스트가 눈에 보이는지 확인
- 🔴 **`fg-quaternary`(#f9fafb)·`text-quaternary`(#d2d6db)는 거의 흰색** — 흰 배경 위 텍스트/아이콘에 **절대 사용 금지**(안 보임). 비활성 탭·보조 텍스트 등 "흐린 회색"이 필요하면 `fg-secondary`/`text-secondary`(#687079) 또는 `fg-tertiary`/`text-tertiary`(#b1b6be)를 쓸 것.

### 12. 섹션 간 간격 — 배경색 동일 + divider 없으면 gap 0
- 인접한 섹션의 배경색이 동일(둘 다 투명/white)이고 사이에 divider가 없으면 **gap 0px** — 섹션 내부 padding이 여백 역할
- 배경색이 다르거나(컬러 → white 등) 사이에 divider가 있으면 gap 유지
- 🔴 **섹션 bg 색 경계 = 아래 섹션 상단 padding 증가 (2026-06-05 사용자 룰):** 인접 섹션의 배경색이
  다를 때(예: 그레이 밴드 → 흰 섹션) **아래 섹션의 paddingTop 을 그 섹션의 좌우 padding 값과 동일하게(대칭)** 맞춘다 — 과하게 늘리지
  말 것. 사용자 명시 *"섹션간 bg color가 다를때 아래 frame의 상단 padding값을 늘려야한다 → 상단
  padding은 좌우 패딩값과 똑같으면 된다."* **시스템 강제 (코드 박힘):** `_enforce_section_bg_gap_padding(root_id)`
  (cmd_post_fix, brand-tint 직후) — 루트 직계 섹션을 위→아래로 훑어 위 섹션과 보이는 SOLID 배경색이
  다르면: **채워진 밴드(자체 bg fill)면 상/하 padding=24(`_BAND_VPAD`=spacing-3xl)**, 빈/흰 섹션이면
  **paddingTop=paddingLeft**(대칭) 로 설정. 같은 색/무배경 경계·고정 바(NavBar/Tab Bar/Wallet)·pl=0 섹션 제외.
- 🔴 **채워진 풀폭 밴드 섹션 = 상/하 padding 24(spacing-3xl) + 토큰 바인딩 (2026-06-05 사용자 룰):**
  자체 bg fill 을 가진 풀폭 밴드(시작유도·추천 등)는 상단=좌우(20)가 아니라 **상/하 24(대칭)**. 사용자:
  *"위아래 패딩값 24로 맞추고 토큰 바인딩도 해."* 24 는 post-fix `_bind_spacing_tokens_live` 가
  **spacing-3xl 토큰으로 자동 바인딩**(절대값 아님). 위 enforcer 의 '밴드' 분기가 강제 → 재빌드에도 유지.

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
7. padding/gap → "3. Spacing"/spacing-* 시맨틱 DS 변수 자동 바인딩 (2026-05-28 "절대값 말고
   spacing- 토큰 박아" / 🔴 2026-05-29 "primitive(Spacing/) 쓰면 안돼. 3. Spacing 의 spacing- 토큰으로"):
   `_bind_spacing_tokens_live`가 post-fix 가장 마지막(모든 레이아웃 강제 후)에 라이브 트리의
   auto-layout paddingLeft/Right/Top/Bottom · itemSpacing · counterAxisSpacing 최종 값을 읽어,
   디자인 스케일에 **정확히 일치하는 값만** "3. Spacing" 컬렉션의 시맨틱 토큰에 바인딩한다.
   🔴 **primitive 스케일(`Spacing/5 (20px)` 등) 절대 금지** — 반드시 `spacing-*`:
   0=`spacing-none` 2=`spacing-xxs` 4=`spacing-xs` 6=`spacing-sm` 8=`spacing-md` 12=`spacing-lg`
   16=`spacing-xl` 20=`spacing-2xl` 24=`spacing-3xl` 32=`spacing-4xl` 40=`spacing-5xl` 48=`spacing-6xl`...
   `_load_spacing_map`이 figmaPath 소문자 `spacing-` 시작 토큰만 사용(primitive `Spacing/` 제외).
   토큰 value == 현재 값이라 시각 변화 0. DS 인스턴스 + 인스턴스 내부 노드(`I…;…`)는 제외.
   스케일 밖 값(10/14/18/22/28 등)은 토큰이 없어 리터럴 유지 — 임의 snap 금지(레이아웃 보존).
   → blueprint 의 padding/gap 은 스케일 값(0/2/4/6/8/12/16/20/24/32/40/48...)으로 쓰면 전부 바인딩됨.
7-b. 🔴 cornerRadius → `radius-*` DS 변수 자동 바인딩 (2026-06-04 사용자 "radius값 왜 토큰
   바인딩 안해? radius- 로 시작하는 토큰 있다"): `_bind_radius_tokens_live`가 spacing 바인더
   직후 실행 — 라이브 트리의 cornerRadius(균일)와 **개별 코너**(시트 top 16/bottom 0; blueprint
   값으로, get_nodes_info 가 개별 코너를 None 으로 줘서)를 스케일 일치 `radius-*` 토큰에 바인딩.
   스케일: 0=`radius-none` 4=`radius-xxs` 6=`radius-xs` 8=`radius-sm` 10=`radius-md` 12=`radius-lg`
   14=`radius-xl` 16=`radius-2xl` 20=`radius-3xl` 24=`radius-4xl` 28=`radius-5xl` 32=`radius-6xl`,
   **완전 둥근(≥100, 999/9999 류)=`radius-full`**(Figma 가 절반-사이즈 clamp → 동일). figmaPath
   소문자 `radius-` 시작 토큰만. 토큰 value==현재 radius 라 시각 변화 0. DS 인스턴스·내부(`I…;…`)
   제외. 스케일 밖(7/13/18 등)은 리터럴 유지. 4코너 각각 `topLeftRadius`…로 바인딩(plugin
   `rectangleCornerRadii`). 테스트 `test_radius_token_binding.py`.
8. 2-col FILL 붕괴 자동 복구 (2026-06-04 사용자 "코드에 박아"): `_enforce_multicol_fill_live`가
   모든 sizing 강제 *뒤*에 실행 — HORIZONTAL row 의 FILL 컬럼이 **1px 로 붕괴**하고 형제가
   전폭(FIXED)을 먹는 batch_build_screen 버그([[two-col-fill-card-collapse]])를 라이브에서 교정.
   직계 frame 자식 중 width ≤ 3px(붕괴 신호)가 보이면, 작은 고정 요소(아이콘/버튼 ≤56px FIXED)를
   제외한 모든 컬럼 자식을 `set_layout_sizing(FILL)` 로 균등 복원. 붕괴 없으면 no-op.
   회귀 사례: 추천 스테이지 '기간/월 입금' 2-col 스테퍼에서 기간이 1px 로 사라짐 → 자동 복원.
9. 텍스트 박스 상하 여백 복원 (2026-06-04 사용자 "프레임 안 텍스트 위아래 딱 붙으면 안 된다"):
   `_enforce_text_box_padding_live`가 multicol-fill *뒤*에 실행 — batch_build 가 HORIZONTAL row
   안 **FILL 박스의 세로 패딩을 0 으로** 떨어뜨려(stat 박스 '완료한 스테이지/3,000개' 가 패딩 0 →
   텍스트가 박스 모서리에 밀착) 발생하는 회귀를 교정. 대상: **VERTICAL FRAME + 보이는 SOLID fill
   + cornerRadius≥6 + 직계 TEXT≥2** 인데 세로 패딩 < 12 또는 itemSpacing < 6 → paddingTop/Bottom
   = max(현재,14), itemSpacing = max(현재,6) 로 복원. 투명 텍스트 그룹(fill 없음/cornerRadius 0)·
   DS 인스턴스 내부는 제외. 판별: `_text_box_needs_padding` (회귀 테스트 `test_text_box_padding.py`).
10. ⭐ blueprint 명시 FIXED 폭/padding 최종 복원 — **AUTO_FIX 이후** (2026-06-04 "내 스케줄" 회귀 뿌리):
   🔴 **순서가 핵심**: `design_rules:AUTO_FIX`(Step E.7.5)가 **cmd_post_fix 보다 *나중*에** 돌면서
   author 레이아웃을 다시 덮어쓴다. 그래서 cmd_post_fix 안에서 폭/padding 을 고쳐도 무력화됐다.
   → **Step E.7.7**(`cmd_build`, AUTO_FIX + size-invariant *이후*, 모든 단계 맨 끝)에서
   `_enforce_fixed_widths`(blueprint `layoutSizingHorizontal:"FIXED"`+width)·`_enforce_blueprint_padding`
   (blueprint autoLayout padding)을 **무조건 재단언**해 최종 권한을 갖는다. (get_nodes_info 의 padding
   직렬화가 None/stale 이라 '바뀐 것만' 판정이 카드를 놓쳐 → 멱등 재단언.)
   회귀 사례: 2-line Date Cell 이 FILL 로 늘어남(56→161) / Sched 카드 paddingLeft 0(본문 우측 밀림).
11. col-baseline 오매칭 차단 (2026-06-04): `_fix_space_between_col_baseline`(3-col stat grid 중앙정렬)이
   '내 스케줄' 같은 **리스트 행**(작은 날짜셀 56 + 넓은 본문 267)을 grid 로 오인해 본문을 FILL+가운데
   정렬시키던 회귀. → 컬럼 폭이 크게 불균등(max>2.2×min)하거나 작은 셀(≤72px)이 섞이면 list row 로
   보고 skip. (진짜 균등 3-col 요약만 중앙정렬.)
12. padding `... or 0` None 버그 (2026-06-04): get_nodes_info 가 paddingLeft 등을 **None 으로 누락**
   직렬화 → `node.get("paddingLeft") or 0` = 0 으로 실제 16 패딩을 파괴(paddingLeft 만 0 회귀).
   → padding 재설정 enforcer 들(col-baseline·`_restore_content_section_padding`)은 **숫자로 확인된
   필드만 set_auto_layout 에 전달, 모르는 필드는 생략**(code.js 가 기존값 보존). multicol-fill 의
   작은요소 제외도 sizingH 플래그 대신 **폭(≤64px) 기준**으로 판별(플래그 직렬화 불안정 대응).
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
