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
   ✅ **2~4단계 + DS 맵 + 통독 게이트 상태는 `python3 scripts/figma_mcp_client.py doctor` 한 번으로
   통합 진단** (2026-07-08 신설, Astryx doctor 패턴) — 항목별 ✓/⚠/✗ + fix 안내, FAIL≥1 → exit 1,
   `--json` 지원. 준비 절차 검증·문제 발생 시 원인 파악에 이걸 먼저 실행할 것.
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
> **보존**: `blueprint_templates.json`(assemble 소스 템플릿),
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
python3 scripts/figma_mcp_client.py doctor  # 환경 통합 진단 (브리지/세션/플러그인/DS맵/통독 게이트, FAIL≥1 → exit 1)
python3 scripts/figma_mcp_client.py component "Tab bar" [--full]  # DS 컴포넌트 do/don't + componentKey 조회
python3 scripts/figma_mcp_client.py search "탭"                   # 가이드+카탈로그 통합 검색
python3 scripts/figma_mcp_client.py rule 0-J                     # 디자인 룰 상세 원문 조회 (rule --list 로 전체)
python3 scripts/figma_mcp_client.py manifest                     # CLI 명령 표면 자기서술 (27개)
```

> 🔵 **DS 컴포넌트 작성 전 `component` 조회 우선 (2026-07-08 신설, Astryx 패턴)** —
> Tab bar/Tool Bar/Badge/Segmented/CTA 등 DS 컴포넌트를 blueprint 에 쓰기 전에
> `component "<이름>"` 으로 **do/don't 가이드 + componentKey(ds_catalog 런타임 해석)** 를
> 조회한다. 소스는 `ds/COMPONENT_GUIDANCE.json`(우리 소유, 커밋 대상 — 자동 sync 아님).
> 이 문서의 키 테이블(0-M/0-W 등)과 동일 내용의 조회형 뷰 — **키를 기억/추측하지 말고 조회**.
> 컴포넌트 룰이 바뀌면 CLAUDE.md 와 COMPONENT_GUIDANCE.json 을 함께 갱신할 것.

> 🔴 **BUILD-SUMMARY-JSON — 빌드 결과는 stdout 마지막 블록의 JSON 으로 판독 (2026-07-08 신설, Astryx 패턴)**
>
> `build` 는 모든 종료 지점(게이트 차단·검증 실패·성공·빌드 실패)에서 **마지막 출력**으로
> `📋 BUILD-SUMMARY-JSON` 마커 + JSON 1개를 낸다. **빌드 로그를 tail 로 봐도 이 블록은 항상
> 걸린다** — 결과 판단은 사람용 로그 문장(prose)이 아니라 이 블록의 `code` 로 분기할 것.
> - `result`: `success` | `blocked` | `failed` · `code`/`codes`: `scripts/error_codes.py` 의
>   안정 코드(append-only — 의미 불변·삭제 금지. ERR_PLANNING_GATE, ERR_WIREFRAME_CONTENT_MISSING(S23),
>   ERR_NOVELTY_DUPLICATE, ERR_REFERENCE_READ_PENDING(0-G), ERR_SELF_VERIFY_PENDING(0-F) 등)
> - `requiredActions`: **반드시 수행할 후속 액션** — `type:"read"` 의 `paths`(레퍼런스 PNG,
>   digest)는 Read 도구로 열고, `type:"export_and_read"` 의 `nodeIds` 는 self-verify 재export.
>   성공 요약에도 0-G/0-F 액션이 실리므로 이 블록만 봐도 다음 할 일이 완결된다.
> - 새 하드 게이트 추가 시: ERROR_CODES 에 코드 + GATE_TAG_TO_CODE 에 태그 등록
>   (`test_error_codes.py` 드리프트 가드가 미등록 태그·요약 없는 exit(2)를 CI 에서 차단).

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

> 🔴 **DS 자동 sync 토큰 파일은 수동 커밋 금지 (2026-06-09 사용자 룰)**
>
> `ds/TOKEN_MAP.json` · `ds/DESIGN_TOKENS.md` · `ds/DS_COMPONENT_DOCS.json` 은 **별도 레포
> `twavetech-frontend/design-system` 의 `tokens.json` 에서 자동 동기화**되는 산출물이다
> (브리지 기동 시 `syncTokensFull()` → `scripts/sync-tokens-from-github.sh` 가 재생성, 디자인
> 생성 직전 `syncTokensIfNeeded()` 가 design-system 최신 SHA 비교 후 재동기화). **빌드는 이
> 로컬 재생성본을 읽으므로 토큰 최신성은 git 과 무관하게 항상 보장**된다(수정·신규 토큰 모두 반영).
>
> **운영 정책:**
> 1. **이 3개 파일을 사람이(=Claude 가) 수동 `git add`/커밋하지 않는다.** 자동 sync 봇의
>    `sync: design tokens updated from design-system` 커밋에만 맡긴다. 기능 커밋에 끼워 넣으면
>    봇 커밋과 **충돌**난다(2026-06-09 회귀: "전부 함께 커밋" 시 stale `ds/*` 를 끼워 넣어 rebase 충돌).
> 2. **추적(tracked)은 유지** — gitignore 하지 않는다. 새 클론 직후(첫 sync 전)·sync 실패·오프라인
>    시 `load_token_map()` 의 fallback 스냅샷으로 필요. (`ds/.last_sync_sha`·`ds/.icon-cache/` 는
>    이미 gitignore.)
> 3. 기능 커밋 시 `git add` 는 **변경한 파일을 명시적으로** 지정한다(`git add -A` 로 ds/* 자동
>    산출물까지 쓸어담지 말 것). working tree 에 ds/* 변경이 떠 있으면 `git checkout -- ds/<file>`
>    로 되돌리거나 그냥 스테이지에서 제외.
> 4. 원격 거부(non-fast-forward) 시 — 원격엔 보통 자동 sync 커밋이 쌓여 있다. `git rebase origin/main`
>    후 ds/* 충돌은 **원격(`--ours`, 권위 있는 최신 sync) 버전 채택**하고 continue.

## 알려진 이슈
- DesignPreview 컴포넌트 참조되지만 미구현
- 테스트 없음 (단위/통합)
- Figma 도구 호출 캐싱 없음

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

## 디자인 생성 룰 — 압축 인덱스

<!-- DESIGN-RULES-INDEX:START -->

> 🔴 **이 섹션은 룰의 *인덱스*다 (2026-07-09 Phase 5 인덱스화 — Astryx 압축 인덱스 철학).**
> 각 룰의 상세 원문(사용자 지시 원문·JSON 예시·시스템 강제 구현·회귀 사례·bypass 마커)은
> **`python3 scripts/figma_mcp_client.py rule <id>`** 로 조회한다 (예: `rule 0-J`, `rule 2-G`,
> `rule post-fix`, `rule --list`). 전체 원문: `docs/design-rules-detail.md`.
> 컴포넌트 키·blueprint 예시는 **`component "<이름>"` / `search "<쿼리>"`** 로 조회 —
> **키를 기억/추측하지 말고 조회.** 아래 한 줄들은 요약이다 — **blueprint 작성 전, 그 화면에
> 해당하는 룰을 `rule` 명령으로 반드시 펼쳐 볼 것** (탭 있으면 0-J, CTA 있으면 2-G, modal 이면
> 0-D/2-D, 캐로셀이면 10 …). 룰은 2계층: **정합성(하드 — enforcer/게이트 강제)** vs
> **스타일(기본값 — author 명시값이 항상 이김)**.

### 🔴 최다 위반 룰 스포트라이트 (vibe-tests 베이스라인 2026-07-09 실측 — 이것부터 지켜라)

독립 생성 24샘플에서 가장 많이 위반된 룰:

1. **R23 (×40) — DS 컴포넌트 패턴을 raw frame 으로 그리지 말 것.** 버튼/badge/체크박스/탭바/
   navbar/드롭다운/인풋/토글은 `component "<이름>"` 으로 키를 조회해 `type:"instance"` 로 작성.
   반대로 콘텐츠/장식 frame 은 DS 로 오인되지 않게 **중립 이름**을 쓴다(0-L — 이름에
   Badge/Pill/Chip/Tag/Button/Dropdown 단어 금지).
2. **규칙 8 / R10.1 (×21) — 모든 섹션·카드·리스트 FRAME 은 `layoutSizingHorizontal: "FILL"`.**
   FRAME 에 HUG 금지 — 텍스트 노드·아이콘·태그/칩/뱃지(HUG 필수)만 예외. 의도된 HUG/FIXED 는
   `_keepSizing: true`(8-B).
3. **R52 (×10, ERROR) — 이름에 lounge/product/shop/recommend/item 이 든 카드(≥100×100)는
   `imageQuery` 또는 시각 자식(icon/instance) 필수.** neutral bg + 텍스트만이면 회색 빈 박스라
   빌드 차단. 예: `"imageQuery": "cozy lounge cafe interior natural light"`. bypass:
   `_imagelessAllowed: "<reason>"`.
4. 소수 빈발: **R36** 가로 캐로셀은 마지막 카드 peek 이 보이게(카드 FIXED 폭 353, itemSpacing 12) ·
   **R21.1** 배경 위계 건너뛰기 금지(bg-primary 위에 bg-tertiary 직접 ❌ — secondary 경유) ·
   **R10.4** FAB 는 icon-only 56×56 원형(텍스트 라벨 금지) · **R27** 반복 장식 도형/아이콘 그룹
   노이즈 금지.

### 🔴 창의 프로세스 + 하드 게이트 (imin_* 빌드는 root 선언 없으면 빌드 차단)

**콘텐츠는 와이어 1:1, 비주얼은 매 시안 다르게** (2026-06-15/18 사용자 핵심 룰 — "100번 생성하면
100번 다 와이어와 똑같으면 디자인이 의미가 없다"). 와이어 레이아웃/정렬/크기 트레이싱 = 디자인
안 한 것(0-C/0-N/S26). blueprint root 에 4종 선언 필수:

| root 선언 | 요구 | 게이트 |
|-----------|------|--------|
| `_wireframeContent` | 와이어의 모든 텍스트/숫자/카운트 dict — 콘텐츠 1:1(누락 금지 0-E, 날조 금지 0-E-3) | S23 |
| `_concept` | `{"idea": "<핵심 차별 아이디어>", "diffs": ["직전 버전과 달라지는 점", …≥3]}` — 형식 통과용 공허한 값 금지 | S24 |
| `_designDirection` | `{"id","typography","color","layout","spacing"}` — 4축 중 ≥3축 구체 전략, id 는 직전 빌드와 다르게 | S25 |
| `_wireframeDivergence` | 와이어 대비 시각 발산 ≥3개(각 ≥10자) — 레이아웃/정렬/위계/크기/컬러를 *어떻게 다르게* 했는지 | S26 |

- **novelty 게이트**: 직전 빌드와 비주얼 시그니처 ≥80% 유사 또는 같은 `_designDirection.id` → 차단.
- **통독 게이트**: `src/기획` digest 통독+ack 없으면 빌드 차단 (learn-planning → Read 통독 → ack-planning).
- **S22**: 이전 archetype config 재사용 금지 — 콘텐츠는 와이어에서 새로 추출.
- bypass(단순 재빌드 등 정당 사유만, 사유 문자열 필수): `_conceptSkipped` / `_designDirectionSkipped` /
  `_wireframeDivergenceSkipped` / `_wireframeContentSkipped` / `_noveltySkipped`.
- **워크플로**: 레퍼런스 Read(0-G) + 같은 화면 기존/사용자 수정본 학습(0-G-2) → 방향을 직전과 다르게
  정하고 → 콘텐츠 영역의 레이아웃/컬러/간격/정렬/타이포를 **새로 설계** → 선언 4종 박아 빌드.
  새 화면/리디자인은 방향이 다른 **3안** 생성 권장. 결정형 생성기(gen_*.py)는 fallback 일 뿐 —
  비주얼은 매 세션 새로 도출(0-E-2).
- **0-E-3 (날조 금지)**: CMS/동적/외부주입 영역은 가짜 콘텐츠를 만들지 말고 **흰 면(bg-primary)+보더
  placeholder** + `_placeholderAllowed` 마커. 와이어에 없는 배너/카피/슬라이드 임의 생성 금지.

### 정합성 룰 인덱스 (하드 — 위반 시 빌드 차단 또는 자동 교정. 상세: `rule <id>`)

**화면 골격**
- **0** — 루트 프레임 fill = `$token(bg-primary)` 필수. 화면 배경이 회색이면 버그.
- **1** — Status Bar 를 blueprint 에 넣지 말 것 — 빌드가 DS 인스턴스를 루트 첫 자식으로 자동 삽입.
- **2-F/18** — 루트 minHeight 852, 높이는 콘텐츠 전체(852 로 줄여 하단 잘리게 금지). 하단 바 bottom-pin 자동.
- **0-H** — 새 root 는 기존 화면 우측 빈 공간에 자동 배치(겹침 금지).
- **0-D** — modal 기본형 = bottom-sheet: root `_screenType:"bottom-sheet"` → 852 FIXED + Dim Overlay +
  Modal Sheet(루트 풀폭·top radius 16·콘텐츠 가로 padding 20·상단 pad 8/하단 24 `_asymPad`) 자동.
- **2-D** — full modal(`_screenType:"modal"`): 상단 X 닫기만, Footer/TabBar/상단탭 없음, root HUG,
  홈 대시보드 섹션 유입 금지(R58 차단).

**DS 컴포넌트 (키·예시는 `component "<이름>"` 조회)**
- **0-M** — 하단 탭바 = DS **'Tab bar'** 인스턴스. active 탭(홈/커뮤니티/스테이지/라운지/나)의
  variant key 로 생성 — raw frame 금지.
- **0-W** — 상단 NavBar = DS **'Tool Bar'** 인스턴스(`SET:` 키). 메인=Type Home(로고 내장),
  서브=Type Detail view + `_navTitle`. 우측 버튼은 `_navIcons`(빈 배열 `[]` = 버튼 없음/empty,
  최대 2개). 검색바 등 표현 불가 케이스만 raw + `_customNavBar`.
- **0-J/0-V/5-B** — 콘텐츠/뷰 전환 탭(입금/지급·추천/전체·거래현황/누적거래 등)은 **underline tabs
  styled frame**(`_underlineTabs:true`, active=text-primary+fg-primary bar / inactive=text-tertiary+투명)
  이 기본. **Segmented_control 은 `_forceSegmented:true` 컴팩트 토글(주/월/년 등)만.** 헷갈리면 underline.
- **0-P** — Segmented_control 은 Size=md 기본(자동).
- **2-G** — 하단/전폭 CTA = DS **'Action Button'** 인스턴스. Size=lg 기본(자동 강제), 라벨은
  `_instanceText`. ⚠️ md Primary 키는 import 깨짐 → Secondary 키 + `instanceProperties:{"Hierarchy":"Primary"}`
  flip(빌드 후 자동 적용). 버튼 높이는 padding(상하 16)으로 확보(규칙 20).
- **2-G-2~5** — 액션바 안 버튼 높이 통일(자동) · NavBar 우측 액션 = 아이콘 버튼(텍스트 금지, R62) ·
  세로 연속 전폭 Primary CTA 는 더 중요한 것에 `_ctaKeepPrimary:true` 명시(나머지 Outline 자동) ·
  FAB 화면의 수평 반복 동일 라벨 CTA 는 Tertiary(자동).
- **2-I** — 폼 컨트롤(체크박스/토글/라디오/인풋/슬라이더/드롭다운) = DS 인스턴스 직접 작성 —
  raw frame 은 자동 swap 안 되는 케이스라 사용자 분노 회귀.
- **10** — 캐로셀/배너 인디케이터 = DS **'Pagination dot group'** 인스턴스(raw dot/bullet 금지).
- **0-K** — DS 인스턴스(내부 노드 포함)의 fill·stroke·라벨 색 **절대 변경 금지** — variant/prop 만.
  Badge 색 = `Color` prop 13종에서 선택(`set-badge-color`).
- **0-U** — 상단바/헤더의 아이콘 버튼은 무chrome(fill 박스/radius/stroke 금지) — 아이콘만.
  스타일 버튼 의도 시 `_buttonChrome:true`.

**토큰/타이포**
- 색은 전부 `$token(...)` — RGBA 하드코딩 금지(순수 흰/검/투명만 예외). 클래스 일치 필수:
  `fontColor`=`text-*` / `iconColor`=`fg-*` / `fill`=`bg-*` / `stroke`=`border-*`.
  primitive 스케일(`Spacing/5`, `Colors/Blue/500` 등)·state 변형(hover/pressed/disabled) 토큰 금지(R20/R41).
- **0-B** — `-alt`/`_alt` 변형 토큰 절대 금지 (`bg-secondary-alt` ❌ → `bg-secondary`).
- **2-C** — fontSize 는 DS 스케일만: **12/14/16/20/24/32/40/48**. 기본 본문 16 / 보조·타이틀 아래
  디스크립션 14 / 미세(푸터 fine print) 12(남용 금지) / HERO 금액·수치 24~32 Bold / 섹션 헤더 16~20 Bold.
  같은 카드 안 최소 3단계 위계.
- **0-S** — 텍스트 스타일 바인딩을 깨지 말 것 — 크기 변경은 raw set_font_size 가 아니라 더 큰/작은
  DS 텍스트 스타일 적용으로.
- **11/11-B** — 흰 배경 위 `fg-quaternary`/`text-quaternary` 금지(거의 흰색이라 안 보임 — 흐린 회색은
  secondary/tertiary). CTA 유도 caption(버튼 위 권유 문구)은 `text-secondary`.
- **R61/R47** — 텍스트/아이콘 자리에 이모지 절대 금지 — DS 아이콘(`type:"icon"`). 스테퍼 값·카운트·
  배지 숫자는 반드시 `type:"text"`.

**레이아웃**
- **8** — 모든 섹션/카드/리스트 FRAME 가로 FILL(최다 위반 — 위 스포트라이트). 태그/칩/뱃지는 HUG.
  의도 HUG/FIXED 는 `_keepSizing:true`(8-B).
- **0-Q** — radius>0 frame 은 `clipsContent:true` 필수. radius 값은 DS 스케일(4/6/8/10/12/14/16/20/24/
  28/32, 완전원형 999)로 — post-fix 가 radius-* 토큰 자동 바인딩.
- **3/6/7** — Tab Bar 아이템 FILL 균등 + 세로 FILL + 라벨 CENTER (자동 보정 있음 — 라벨 2줄 wrap 회귀 주의).
- **9** — Tab Bar 는 콘텐츠 하단 밀착·FAB 는 우측 20/위 20 에 ABSOLUTE(자동). FAB = icon-only 56×56
  원형 + `bg-brand-solid` + 아이콘 `fg-light`(강제).
- **10** — 히어로 배너 = 가로 캐로셀 구조 필수: VERTICAL 섹션 > "Banner Carousel"(HORIZONTAL,
  `clipsContent:true`, paddingLeft 20, itemSpacing 12) > Banner Card(FIXED 353×162) + peek.
- **12** — 같은 bg 인접 섹션 gap 0. bg 색 경계는 아래 섹션 paddingTop=좌우 padding, 자체 fill 밴드는
  상/하 24(자동).
- **13-B** — 홈 Content 섹션 스택 gap 20(spacing-2xl, 미지정 시 fill-in).
- **14** — 스테이지 카드 안 아이콘/이미지 금지(태그+금액+이율/기간+북마크만). **14-B** — 스테퍼
  (`− 값 +`) 2개 이상은 세로 2-row 스택 + 값 텍스트 FILL(가로 2-up 은 값 겹침).
- **20** — 텍스트 버튼 frame 은 autoLayout padding(상하 16)으로 높이 확보 — height 단독 지정 금지.
- **2-E** — "Section Divider" 노드 작성 금지(자동 삽입 폐기·자동 제거) — 경계는 카드 보더로.
  raw drop-shadow 도 금지(카드 그림자는 2-B-3 이 DS effect style 로 자동).
- spacing/padding/gap 은 DS 스케일 값(0/2/4/6/8/12/16/20/24/32/40/48)으로 — post-fix 가 `spacing-*`
  시맨틱 토큰 자동 바인딩(스케일 밖 값은 바인딩 안 됨).

**프로세스 (빌드 전후 의무 — 어기면 게이트 차단/신뢰 문제)**
- **0-G** — 빌드 로그 `📌 SECTION-REFERENCE-PNG` 의 썸네일 PNG 를 **전부 Read** 후 본 내용을
  references 에 반영. 빌드 로그를 tail/grep 으로 필터하지 말 것. 날조 금지.
- **0-G-2** — 같은 화면의 기존(특히 **사용자 수정**) 버전을 빌드 전 export+Read 학습 — 사용자 교정이
  최우선 레퍼런스. 컬러 시맨틱: **완료=success 계열, 브랜드 퍼플='나의 것' 한정**.
- **0-F** — 빌드 로그 `📸 SECTION-QA-PNG` → 섹션별 재export+Read+checklist(C01~C12) 채운 뒤에만
  보고. 1장 보고 "검증 ✅" 절대 금지. FAIL 있으면 fix 후 재검증 또는 솔직 보고.
- **0-F-2 / 0-R** — 작업 종료 시 `cleanup-qa` 1회(스크린샷·썸네일 삭제). 빌드 성공 시 사용한
  blueprint json 은 자동 삭제(재빌드는 새로 작성 — 의도된 동작).
- **19 / 22 / 22-B** — 스크린샷 QA 에서 PRD 전 섹션 1:1 확인(하나라도 누락 시 완료 선언 금지).
  빌드 로그의 `[QA] ⚠️`·`[smell] ⚠️` 라인 확인·수정.

### 스타일 기본값 (fill-in/advisory — author 명시값이 항상 이김. `[스타일-기본값]` 로그)

- **2-B** — 카드 표면 기본 = 흰 면(`bg-primary`)+보더. 보더 색은 뒤 배경 따라: 흰 배경 위
  `border-primary` / 그 외 `border-secondary`. 보더 자동부착은 흰-on-흰만. 보더리스 면 의도 시
  `_keepSurface:true`. Footer 는 배경·보더 없음.
- **2-B-3** — 흰 카드 elevation = DS `Shadows/shadow-basic` 자동 바인딩(`_noShadow`·placeholder 제외,
  개별 코너 radius 카드는 `_cardShadow:true` 로 강제).
- **13** — 섹션 강조 여부·색은 작성자 자율. 단 **회색(bg-secondary) 도배 = 칙칙(지양)**,
  **bg-brand-primary 면 = 자제** — 기본은 흰 면+보더, 강조는 타이포 위계·여백·그룹화·브랜드 퍼플
  *액센트*(텍스트/CTA/아이콘/dot)로. `_band:true` 는 풀폭 *구조* 마커일 뿐(색 아님).
- **2-H / 2-B-2** — 큰 면적 brand fill·브랜드 틴트 면 = advisory WARN (컬러 히어로 의도 허용,
  가독성은 대비 QA 가 방어). 틴트 면을 쓸 땐 `bg-brand-primary`(연한 라벤더)만.
- **2 / 2-J** — 색 절제: 브랜드 퍼플 = 단일 일관 액센트(CTA·active 탭·핵심 수치), 상태색(success/
  warning/error)은 진짜 상태에만 소량, **Aqua 자제**, 여러 색 난무 금지. 평면 그레이 나열도 금지
  (폴리시: 위계/대비/그룹화).
- **19-B** — 세로 패딩 큰 비대칭은 디자인 의도로 존중(≤4px 만 교정, `_asymPad:true` 로 침묵).
- **0-N/R63** — 다른 정보는 다른 시각 언어 — 인접 섹션이 동일 카드 구조면 WARN → 한쪽 재설계.

### 트러블슈팅/후처리 (필요 시 조회)

- post-fix 자동 체인 상세(FILL/위치/spacing·radius·아이콘색 토큰 바인딩/2-col 붕괴 복구/텍스트 박스
  패딩 등 12항): `rule post-fix`
- 텍스트 스타일 미적용(라이브러리 fallback)·batch_build_screen timeout 후속 복구: `rule troubleshooting`
- 환경/게이트 통합 진단: `python3 scripts/figma_mcp_client.py doctor`

<!-- DESIGN-RULES-INDEX:END -->

---

## 상세 문서 (작업 시 필요한 문서만 Read로 로드)

> 아래 문서는 **해당 작업을 수행할 때만** Read 도구로 로드한다. 매번 전부 읽지 않는다.

| 문서 | 언제 읽는가 |
|------|------------|
| [`docs/ds-architecture.md`](docs/ds-architecture.md) | DS 토큰 조회, 변수 업데이트, MCP 도구 목록 확인, INSTANCE_SWAP 시 |
| [`docs/design-rules-detail.md`](docs/design-rules-detail.md) | **디자인 룰 상세 원문** — 위 인덱스의 룰을 펼칠 때 (`rule <id>` 명령이 이 문서를 조회) |
| [`docs/mobile-patterns.md`](docs/mobile-patterns.md) | 모바일 화면 디자인 시 — 레이아웃 패턴, 화면 사이즈, Status Bar |
| [`docs/qa-checklist.md`](docs/qa-checklist.md) | 디자인 완료 QA 시 — 13개 체크 항목, 스크린샷 촬영 방법, 완료 판단 기준 |
| [`docs/multi-agent-design.md`](docs/multi-agent-design.md) | 복잡한 화면(섹션 3+, 이미지 1+) 디자인 시 — 멀티에이전트 모드 |
| [`docs/pencil-to-figma.md`](docs/pencil-to-figma.md) | "figma로 보내줘" 요청 시 — Pencil→Figma 변환 워크플로우, Blueprint 규칙 |
| [`docs/python-mcp-client.md`](docs/python-mcp-client.md) | batch_build_screen, DS 바인딩 등 대규모 작업 시 — Python HTTP 클라이언트 |
