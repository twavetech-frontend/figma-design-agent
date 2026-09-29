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
2. **브리지 기동** — 데몬 등록돼 있으면(`npm run bridge:install`, launchd) 이미 떠 있으므로 skip.
   아니면 `npm run bridge`를 백그라운드로 실행. 로그에
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
4.5. 🔴 **활성 페이지 인덱싱 (2026-09-02 사용자 룰 — 기존 본/에셋 탐색 가속)** — 플러그인이
   연결되면 **플러그인이 실행된 그 페이지 하나**를 스캔해 인덱스를 만들어 둔다 (파일 전체 금지 —
   너무 커짐). 절차: ① Figma MCP `get_metadata(fileKey)` 로 top-level 페이지 확인(⚠️ 노드의
   parentId 는 페이지가 아니라 SECTION 일 수 있음) → ② 활성 페이지 id 로
   `get_metadata(fileKey, nodeId=<pageId>)` XML 을 파일로 받아 →
   ③ `python3 scripts/index_figma_page.py <xml파일> --tag <파일태그>` 로
   `scripts/_figma_index_<tag>.json` 생성(화면/섹션/에셋/텍스트, gitignore 됨).
   ✅ **공식 Figma MCP 가 세션에 없으면(보통) 브리지 크롤러 원커맨드 (2026-09-04 영구화) —
   반드시 `run_in_background` 로 돌리고 5~6단계와 병렬 진행** (약 90~100s, 921화면 실측.
   포그라운드로 기다리지 말 것 — 준비 11분 회귀의 절반이 이것):
   ```bash
   python3 scripts/crawl_figma_page.py --out scripts/_figma_page_v216.xml && \
   python3 scripts/index_figma_page.py scripts/_figma_page_v216.xml --tag v216
   ```
   (콜별 25s 타임아웃 + 얕은 폴백 내장 — 거대 화면 1개가 300s 를 물고 전체를 죽이던 회귀 방지.
   페이지 이름이 바뀌면 `--page <pageId>`·태그를 맞출 것.)
   🔴 **완료 판정은 마지막 stats 라인 (2026-09-04 사용자 지적 "훨씬 작은 것 같은데")** —
   `"failed": 0` 이고 화면 수가 직전 실측(921)과 같은 자릿수여야 정상. 플러그인이 크롤 중 순간
   단절(1001)되면 섹션이 통째로 빠진다(95/921 화면 회귀). 지금은 크롤러가 MCP error 를 집계하고
   재접속을 최대 90s 기다려 재시도하며, 실패 ≥1 이면 `✗ 크롤 불완전` + exit 1 을 낸다 —
   exit 1 이면 인덱스를 만들지 말고 플러그인 연결 확인 후 재실행. 오프라인 테스트:
   `scripts/tests/test_crawl_figma_page.py`.
   이후 **변환/생성 요청마다 blueprint·조립 전에
   `python3 scripts/index_figma_page.py --grep <화면명·에셋 키워드> --tag <태그>` 가 기존 본
   전수 확인의 1순위** — 플러그인 find_nodes_by_name(0건 오탐 실적)·scan_text_nodes(60s
   타임아웃)보다 신뢰 경로. 벡터 에셋(ico_*/img_*)이 인덱스에 있으면 crop 이식 금지.
5. 🔴 **기획 문서 전체 학습 (맥락 100% — 2026-06-04 사용자 필수 룰)** — 디자인 생성 전,
   `src/기획/` 폴더의 **모든 기획 문서(유스케이스 스펙)를 읽어 imin 서비스 맥락을 완전히
   이해한 상태**로 만든다. 🔴 **목표: 준비가 끝나면 사용자가 곧바로 "메인화면 그려"라고만 해도
   맥락을 충분히 이해한 상태로 바로 그릴 수 있어야 한다** (2026-06-04 사용자). 그래서 준비
   단계에서 통독+ack 까지 끝낸다. 3-스텝(한 번씩만):
   ```bash
   # ① 학습 digest 생성 (플러그인 UI 에 '기획 문서 학습 중 (n/총)' progress 표시)
   python3 scripts/figma_mcp_client.py learn-planning
   ```
   🔵 **지원 형식 (2026-09-22 확장)** — **`.md` 권장**(구조 보존 + 토큰 최소: 기존 Notion HTML 36개는
   107만 자 중 실제 내용이 7만 4천 자(7%)뿐) · `.html/.htm`(Notion export) · `.markdown/.txt` ·
   `.docx`(zipfile 파싱, 외부 의존성 없음) · `.pdf`(pypdf → PyPDF2 → pdftotext 순). 그 외 확장자는
   학습 대상이 아니다. **추출 실패·깨짐은 조용히 넘기지 않는다** — 실패 파일은 digest 에
   `[읽기 실패]` 로, 폰트 매핑 없는 한글 PDF(다른 문자 영역으로 쏟아짐)는 `[추출 경고]` 로 남고
   stderr 에도 찍힌다(`_looks_garbled`). 경고가 보이면 원본을 HTML/Word 로 다시 내보내 넣을 것.
   회귀 테스트: `scripts/tests/test_planning_doc_formats.py`.
   🔴 **① 의 출력이 `통독 ack 유효 … 재통독 불필요` 면 ②③ 을 건너뛴다 (2026-09-04 수정).**
   기획 문서 fingerprint 가 그대로면 digest 를 재생성하지 않고 과거 ack 를 그대로 인정한다
   (8만 자 재통독 = 준비 시간 3~4분의 주범이었음). ②③ 은 `learn-planning` 이 "재통독 필요"
   라고 할 때만(문서 변경·최초).
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
     🔴 **2026-08-14 사용자 승인 개정 2건:** ① **ack 는 세션이 아니라 fingerprint 기준 영속** —
     기획 문서가 안 바뀌었으면 과거 세션의 유효 ack 로 재통독 없이 통과(새 세션마다 8만자
     재통독 강제 폐기. 문서 변경 시 learn-planning 이 ack 를 무효화하므로 "변경 시 재통독"은 유지).
     ② **비 imin_* root(캡처 1:1 변환 트랙 등)는 게이트 면제** — 창의 하드 게이트(S24~S27)가
     imin_* 만 대상인 것과 동일 기준.
   - 🔴 **변경 감지 + ack 무효화:** `learn-planning` 은 `src/기획/` fingerprint(파일+mtime+size)를
     `_planning_digest.txt.meta.json` 에 저장. **변경 없으면 재생성 스킵**(단 ack 안 됐으면 통독 안내),
     **변경되면 자동 재학습 + 이전 ack 무효화**(`_planning_digest.txt.read.json` 삭제) → 다시 통독+ack
     해야 빌드 통과. 강제 재학습: `learn-planning --force`. ⚠️ **2026-09-04 회귀 수정:** 2026-06-05
     "매번 새로 작성" 룰이 코드에서 스킵 분기를 없애고 ack 를 무조건 삭제해 매 세션 재통독을
     강제하고 있었다(이 서술과 불일치). 지금은 서술대로 동작하며, 재생성 시에도 read_token(본문
     sha1)이 같으면 ack 를 유지한다. 세션 도중 문서가 바뀌어도 빌드 게이트가
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
npm run bridge:install    # 🔵 브리지 상시 데몬 등록 (macOS launchd — 로그인 자동시작+사망시 자동재시작,
                          #    세션 종료와 무관. Windows: bridge:install:win. 해제: bridge:uninstall[:win])
                          # 등록돼 있으면 2단계(브리지 기동)는 불필요 — 이미 떠 있음
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

# 2.5 🔴 prebuild — 빌드 전 필수 (2026-07-13 신설, 게이트 차단 왕복 제거)
#    validate + 빌드동일 lint + Step A.0 레퍼런스 사전 검색을 수 초에 실행.
#    출력된 썸네일들을 Read 로 학습해 두면 build 가 0-G 게이트 차단 없이 1회 통과.
#    ⚠️ 가이드 10종 밖 DS componentKey 는 사용자 승인 화면 노드 구조(get_nodes_info)
#    확인 or 단건 테스트 렌더로 실물 검증 후 사용 (2026-07-13 Select/Tag 렌더 붕괴 교훈).
python3 scripts/figma_mcp_client.py prebuild scripts/blueprint_assembled_XXX.json

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

0. **🔴 와이어 트레이싱 (세션마다 재발한 1순위 실패, 2026-07-14~15)** — 와이어 배치를 그대로
   옮기면 "디자인 생성을 맡길 이유가 없다". 콘텐츠 1:1 + 메트릭 승계(2-L) 위에서 **정보 구조·
   그룹핑·위계는 반드시 재설계**. 3중 코드 게이트가 차단: S26-structural(구조 어휘 ≥2)·
   R65(본문 맨몸 나열)·S27(재구성 맵 실물 대조 — 아래 표). 섹션별 카드 1:1 래핑도 트레이싱이다.
1. **R23 (×40) — DS 컴포넌트 패턴을 raw frame 으로 그리지 말 것.** 버튼/badge/체크박스/탭바/
   navbar/드롭다운/인풋/토글은 `component "<이름>"` 으로 키를 조회해 `type:"instance"` 로 작성.
   반대로 콘텐츠/장식 frame 은 DS 로 오인되지 않게 **중립 이름**을 쓴다(0-L — 이름에
   Badge/Pill/Chip/Tag/Button/Dropdown 단어 금지).
2. **규칙 8 / R10.1 (×21) — 모든 섹션·카드·리스트 FRAME 은 `layoutSizingHorizontal: "FILL"`.**
   FRAME 에 HUG 금지 — 아이콘·태그/칩/뱃지(HUG 필수)만 예외. 🔴 **TEXT 노드도 가로 FILL 기본
   + 부모 랩도 FILL (2026-08-24 사용자 룰 — HUG 허용은 칩/pill 라벨·HORIZONTAL 행 나란한 복수
   세그먼트만, verify `text-not-fill` 차단)**. 의도된 HUG/FIXED 는
   `_keepSizing: true`(8-B).
3. **R52 (×10, ERROR) — 이름에 lounge/product/shop/recommend/item 이 든 카드(≥100×100)는
   `imageQuery` 또는 시각 자식(icon/instance) 필수.** neutral bg + 텍스트만이면 회색 빈 박스라
   빌드 차단. 예: `"imageQuery": "cozy lounge cafe interior natural light"`. bypass:
   `_imagelessAllowed: "<reason>"` / CMS·동적 placeholder(0-E-3)면 `_placeholderAllowed: true`
   (와이어에 콘텐츠 없는 동적 카드는 흰 면+보더 placeholder 가 정답 — imageQuery 날조 금지).
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
| `_restructureMap` | `{"wireSections":[...≥3], "surfaces":[{"name":"<트리 노드명>","absorbs":[...]}]}` — 커버리지(전 섹션 흡수)·통합(≥1 표면이 2+ 흡수, 1:1 래핑 차단)·실재(트리 대조) 3종 코드 검증 | S27 |
| `_wireframeDivergence` | 와이어 대비 시각 발산 ≥3개(각 ≥10자), **이 중 ≥2개는 구조 레벨**(섹션 통합/카드 그룹핑/위계 역전/히어로 승격 — 코스메틱만이면 S26-structural 차단). 본문에 표면 그룹 없는 평면 나열은 R65 가 차단 | S26·R65 |

- **novelty 게이트**: 직전 빌드와 비주얼 시그니처 ≥80% 유사 또는 같은 `_designDirection.id` → 차단.
- **통독 게이트**: `src/기획` digest 통독+ack 없으면 빌드 차단 (learn-planning → Read 통독 → ack-planning).
- **S20/S21 — root `references[]` 도 필수** (빌드 전에 미리 넣을 것 — 없으면 lint ERROR 차단): 항목마다
  `{"section","ref":"<이미지 경로>","extract":"<실제 본 내용>","_searchLog":{"queries":[…],
  "candidates":[경로 ≥3],"chosen":"<ref 와 동일 경로>","copyNotes":"<무엇을 어떻게 반영했는지>"}}`.
  0-G 로 Read 한 썸네일들의 실제 검색 트레일로 채운다(날조 금지). bypass: `_referencesSkipped: "<reason>"`.
- **S22**: 이전 archetype config 재사용 금지 — 콘텐츠는 와이어에서 새로 추출.
- bypass(단순 재빌드 등 정당 사유만, 사유 문자열 필수): `_conceptSkipped` / `_designDirectionSkipped` /
  `_restructureMapSkipped` / `_wireframeDivergenceSkipped` / `_wireframeContentSkipped` / `_noveltySkipped`.
- **워크플로**: 레퍼런스 Read(0-G) + 같은 화면 기존/사용자 수정본 학습(0-G-2) → 방향을 직전과 다르게
  정하고 → 콘텐츠 영역의 레이아웃/컬러/간격/정렬/타이포를 **새로 설계** → 선언 4종 박아 빌드.
  새 화면/리디자인은 방향이 다른 **3안** 생성 권장. 결정형 생성기(gen_*.py)는 fallback 일 뿐 —
  비주얼은 매 세션 새로 도출(0-E-2).
- **0-E-3 (날조 금지)**: CMS/동적/외부주입 영역은 가짜 콘텐츠를 만들지 말고 **흰 면(bg-primary)+보더
  placeholder** + `_placeholderAllowed` 마커. 와이어에 없는 배너/카피/슬라이드 임의 생성 금지.

### 정합성 룰 인덱스 (하드 — 위반 시 빌드 차단 또는 자동 교정. 상세: `rule <id>`)

**화면 골격**
- **0-Z (2026-08-24 사용자 절대규칙 — 분노 ×3)** — **여기선 무조건 GUI 를 생성한다.**
  '문서형/보존 모드' 같은 우회를 임의로 만들지 말 것. 어떤 캡처(스크린샷 콜라주 포함)든
  산출물은 DS Status Bar/Tool Bar/HomeIndicator 인스턴스 + 전체 오토레이아웃(8-C) +
  실 텍스트/DS 아이콘으로 **재구성**. UI 조각 스크린샷 이미지(헤더/바/입력바 잘라 붙인 것)
  이식 금지 — 사진 콘텐츠 이미지만 허용.
- **0** — 루트 프레임 fill = `$token(bg-primary)` 필수. 화면 배경이 회색이면 버그.
- **1** — Status Bar 를 blueprint 에 넣지 말 것 — 빌드가 DS 인스턴스를 루트 첫 자식으로 자동 삽입.
  🔴 **한 화면 최상단에 정확히 1개 (2026-08-24 사용자 룰)** — 변환 시 오버레이 중복 bars 자동
  삭제(enforce_single_status_bar, HI 는 최하단 1개), verify `status-bar-duplicate`/`-not-top` FAIL.
- **2-F/18** — 루트 minHeight 852, 높이는 콘텐츠 전체(852 로 줄여 하단 잘리게 금지). 하단 바 bottom-pin 자동.
  **A-flow(2026-09-04)**: 루트 직계에 세로 FILL 콘텐츠 자식이 있으면 바를 ABSOLUTE 로 핀하지 않고
  flow 유지(루트 FIXED 852) — 핀하면 flow 자식(안내 문구)과 겹침. `_pick_root_height_mode`.
- **0-H** — 새 root 는 기존 화면 우측 빈 공간에 자동 배치(겹침 금지). **0-H-2 (2026-08-20)** —
  Figma 선택 노드가 있으면 **같은 부모에 insert 후 선택 노드 바로 오른쪽(gap 50)** 이 우선
  (거대 페이지 maxRight 실종 + 섹션 상대/페이지 절대 좌표계 불일치 방지, 자동).
  🔴 **0-H-3 (2026-09-10 사용자 룰)** — **사용자가 위치를 명시하지 않으면("오른쪽에 생성" 등이
  없으면) 새 root 는 현재 보고 있는 뷰포트 중앙에 생성**한다. 기본값 = center(`get_viewport`
  center → 선택 노드의 부모 섹션 상대좌표로 변환, 없으면 페이지). "오른쪽에" 명시 시에만 0-H-2
  우측 배치 — `IMIN_PLACEMENT=right` / blueprint `_placement:"right"` / `place <rootId> --right`.
  build Step D.5·convert_screen·rebuild_track 이 `position_new_root` 로 통일, 수동 조립은
  `python3 scripts/figma_mcp_client.py place <rootId>`. 구버전 플러그인(get_viewport 없음)은 우측 폴백.
  🔴 **생성 후 `focus_node` 로 뷰포트를 디자인 쪽으로 옮기지 말 것 (2026-09-11 사용자: "그게 아니고 애초에
  처음 보여지는 그 곳에 디자인이 생성되어야 한다")** — 규칙은 '보고 있는 자리에 놓기'다. 엉뚱한 곳에
  생성됐으면 `place <rootId>` 로 디자인을 옮긴다. 플러그인이 구버전이면 재실행을 먼저 요청.
- **0-D** — modal 기본형 = bottom-sheet: root `_screenType:"bottom-sheet"` → 852 FIXED + Dim Overlay +
  Modal Sheet(루트 풀폭·top radius 16·콘텐츠 가로 padding 20·상단 pad 8/하단 24 `_asymPad`) 자동.
- **2-D** — full modal(`_screenType:"modal"`): 상단 X 닫기만, Footer/TabBar/상단탭 없음, root HUG,
  홈 대시보드 섹션 유입 금지(R58 차단).

**DS 컴포넌트 (키·예시는 `component "<이름>"` 조회)**
- **0-M** — 하단 탭바 = DS **'Tab bar'** 인스턴스. active 탭(홈/커뮤니티/스테이지/라운지/나)의
  variant key 로 생성 — raw frame 금지.
- **0-W** — 상단 NavBar = DS **'Tool Bar'** 인스턴스(`SET:` 키). 메인=Type Home(로고 내장),
  서브=Type Detail view + `_navTitle`. 🔴 **모달 X 헤더도 인스턴스 — View=modal variant +
  Back/Title/Num BOOLEAN off + `_navModal:true` (2026-08-04 사용자 룰, 구 'X헤더 제외' 폐기)**.
  🔴 **바텀시트 헤더에 Tool Bar 인스턴스를 쓰면 시트 프레임 `clipsContent:true` 필수
  (2026-08-14 사용자 룰)** — 안 켜면 Tool Bar 사각 모서리가 시트 상단 코너 radius(16)를 덮어
  라운드가 사라진다. convert_screen.py 시트 헤더 스왑이 자동 적용.
  🔴 **파일 내 import 캐시 마스터가 구버전일 수 있음(2026-08-06 타이틀 16px 회귀 ×2)** —
  타이틀은 Body xl/Semibold(20px)가 정본. `_enforce_tool_bar_title_style_live`(post-fix)와
  `_configure_tool_bar` 가 20px 재단언(백스톱). 근본 해결 = Figma 라이브러리 업데이트 수락(수동).
  Tool Bar 인스턴스를 수동 생성하는 흐름에서도 생성 직후 타이틀 크기 검증할 것.
  우측 버튼은 `_navIcons`(빈 배열 `[]` = 버튼 없음/empty,
  최대 2개). 검색바 등 표현 불가 케이스만 raw + `_customNavBar:"<사유>"` (🔴 boolean 금지 —
  R64 ERROR. **아이콘이 키맵에 없다는 건 우회 사유가 아님** — search_design_system 으로 키 확보 후
  ds_catalog.NAV_ICON_KEYS 등록이 정답, 2026-07-14 사용자 룰. edit-01 키 등록됨).
- **0-X** — **HomeIndicator 인스턴스는 가로 FILL** (2026-08-04 사용자 룰 — FIXED 360 잔존 회귀
  금지). post-fix `_enforce_home_indicator_fill_live` 가 FILL/루트 폭 재단언.
  **변환 트랙 자동 삽입(2026-09-04)**: `IMIN_CONVERT_TRACK=1` 빌드는 루트에 HI 가 없으면 페이지 내
  기존 인스턴스를 clone 해 flow 마지막 자식으로 넣는다(`_ensure_home_indicator_live`, 모달/시트 제외).
- **0-W-2 (2026-09-03 사용자 룰 ×2)** — 🔴 **병합 인스턴스(SB+Tool Bar 결합 등)를 그대로 쓰지
  말 것** — 필요에 따라 `detach_instance` 로 분해해 DS Status Bar/Tool Bar 를 **따로** 구성.
  convert_screen 의 `detach_merged_top_instances` 가 상단 병합 인스턴스를 자동 분해(플러그인
  재실행 필요). 상세: `rule 0-W-2`.
- **0-Y (2026-09-01 사용자 룰)** — 🔴 캡처/PRD/와이어에 **키보드가 보이면 raw 로 그리지 말 것**
  — DS **'Keyboard'** 인스턴스(iOS HIG, DS 파일 마스터 18498:5352). 키는
  `ds_catalog.COMPONENT_KEYS["Keyboard"]` 조회(미확보 시 파일 내 인스턴스 clone / 사용자에게
  DS 복사 요청 후 키 채움). 상세: `rule 0-Y`.
  🔴 **0-Y-2 (2026-09-07 사용자 룰)** — **키보드가 있는 화면은 최하단 HomeIndicator 를 넣지 않는다**
  (Keyboard 컴포넌트가 HI 영역까지 포함). 키보드가 flow 마지막 자식. post-fix
  `_remove_home_indicator_when_keyboard_live`·normalize `enforce_single_status_bar`·rebuild 트랙이
  자동 삭제/미삽입, verify `home-indicator-with-keyboard` FAIL.
- **0-J-2** — 🔴 **생애주기 상태 나열(준비중/참여중/진행중/스테이지 완료 등)은 탭이 아니라
  진행 step 표시다 (2026-07-14 사용자)** — underline tabs 로 그리지 말고 step indicator
  (현재 단계 강조 + 단계 도트/체크 + 연결 흐름)로. 기획서 생애주기(모집→마감→진행→종료)와 대조해 판별.
- **0-J/0-V/5-B** — 콘텐츠/뷰 전환 탭(입금/지급·추천/전체·거래현황/누적거래 등)은 **underline tabs
  styled frame**(`_underlineTabs:true`, active=text-primary+fg-primary bar / inactive=text-tertiary+투명)
  이 기본. **Segmented_control 은 `_forceSegmented:true` 컴팩트 토글(주/월/년 등)만.** 헷갈리면 underline.
- **0-P** — Segmented_control 은 Size=md 기본(자동).
  🔴 **0-P-2 (2026-09-08 사용자 룰)** — 캡처 1:1 변환에서 **공개/비공개 같은 pill 토글 칩은 Segmented_control 로
  바꾸지 말고 캡처 디자인대로 raw pill** (선택=bg-brand-solid+text-white / 비선택=bg-primary+border-brand+
  text-brand-primary, 14 Medium, h32). 부모 프레임 이름을 `… Options`(또는 Toggle/Selector)로 두면 verify
  `raw-badge-suspect` 가 선택 토글 그룹(형제 ≥2)으로 인식해 면제. Segmented_control 인스턴스는 생성 시 opacity 0.2
  로 들어오는 실측 결함도 있음(2026-09-08).
- **2-G** — 하단/전폭 CTA = DS **'Action Button'** 인스턴스. Size=2xl 기본(자동 강제 — 2026-08-04 사용자, 구 lg 개정), 라벨은
  `_instanceText`. ⚠️ md Primary 키는 import 깨짐 → Secondary 키 + `instanceProperties:{"Hierarchy":"Primary"}`
  flip(빌드 후 자동 적용). 버튼 높이는 padding(상하 16)으로 확보(규칙 20).
  **높이 백스톱(2026-09-04)**: post-fix `_enforce_action_button_height_live` 가 Action Button 인스턴스의
  세로 HUG/축소를 FIXED + Size 별 마스터 높이(sm24/md32/lg40/xl48/2xl56)로 복구 — 액션바 24px 붕괴 회귀.
- **2-G-2~5** — 액션바 안 버튼 높이 통일(자동) · NavBar 우측 액션 = 아이콘 버튼(텍스트 금지, R62) ·
  세로 연속 전폭 Primary CTA 는 더 중요한 것에 `_ctaKeepPrimary:true` 명시(나머지 Outline 자동) ·
  FAB 화면의 수평 반복 동일 라벨 CTA 는 Tertiary(자동).
- **2-I** — 폼 컨트롤(체크박스/토글/라디오/인풋/슬라이더/드롭다운) = DS 인스턴스 직접 작성.
  🔴 텍스트 인풋 = **'Input field'** 인스턴스(Size=md, State=Placeholder, 라벨·helper 는 밖에 raw —
  2026-08-05 사용자 실측 패턴) —
  raw frame 은 자동 swap 안 되는 케이스라 사용자 분노 회귀.
- **10** — 캐로셀/배너 인디케이터 = DS **'Pagination dot group'** 인스턴스(raw dot/bullet 금지).
- **0-K** — DS 인스턴스(내부 노드 포함)의 fill·stroke·라벨 색 **절대 변경 금지** — variant/prop 만.
  Badge 색 = `Color` prop 13종에서 선택(`set-badge-color`).
- **0-U** — 상단바/헤더의 아이콘 버튼은 무chrome(fill 박스/radius/stroke 금지) — 아이콘만.
  스타일 버튼 의도 시 `_buttonChrome:true`.
- **0-L-2 (2026-08-24)** — 레거시 아이콘 레이어명 `ico/...`(슬래시 경로) 금지 → `ic_` 스네이크로
  정규화(`ico/empty/chat` → `ic_empty_chat`). 변환은 자동(clone 직후 rename_legacy_icon_layers),
  잔존 시 verify `legacy-icon-name` FAIL.

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
  secondary/tertiary). CTA 유도 caption(버튼 위 권유 문구)은 `text-secondary`. 🔴 **2026-09-23**: caption 판정은
  권유 문구만 — 폼 컨트롤(Input field 등)은 CTA 아님, `*Label` 이름 TEXT 는 제외, 같은 이름 TEXT 색이
  갈리면 `[QA][consistency]` WARN(같은 레벨 정보 = 한 토큰). 상세: `rule 11-B`.
- **2-N (2026-09-11 신설)** — 문단 안 부분 강조(브랜드 볼드 스팬·밑줄)는 텍스트를 쪼개지 말고 빌드 후
  MCP `set_text_range_style {nodeId,start,end,fontStyle,fillVariable:"K:<key>",textDecoration}` 로 범위
  스타일 적용(변수 바인딩 유지, verify PASS). 캡처 1:1 변환의 인라인 강조 정본.
- **R61/R47** — 텍스트/아이콘 자리에 이모지 절대 금지 — DS 아이콘(`type:"icon"`). 스테퍼 값·카운트·
  배지 숫자는 반드시 `type:"text"`.
  **아이콘 해석(2026-09-04)**: `type:"icon"` 은 번들 `@untitledui/icons` 패키지에서 오프라인 해석이
  1순위(GitHub 캐시/fetch 는 폴백) — 회색 placeholder(`icon-missing:*`)가 남으면 빌드 요약 code
  `ERR_ICON_UNRESOLVED` + `replace_icons` 액션, verify `icon-missing` FAIL.

**레이아웃**
- **8** — 모든 섹션/카드/리스트 FRAME 가로 FILL(최다 위반 — 위 스포트라이트). 태그/칩/뱃지는 HUG.
  의도 HUG/FIXED 는 `_keepSizing:true`(8-B). **8-C (2026-08-24, 개정: 루트 포함)** — 라이브 조립
  (MCP 직접 생성)은 **화면 루트를 포함해** 콘텐츠 컨테이너 전부 오토레이아웃
  (`ds_convert_lib.new_auto_frame` 헬퍼, 실측 좌표는 padding/gap 번역, 비균등 gap 은 투명 랩
  패딩으로). 오버레이(FAB/토스트/핀 CTA/HI)는 오토레이아웃 루트 안에서 ABSOLUTE 로 공존.
  plain frame 허용 = 오버레이 전용 컨테이너뿐 — verify `plain-frame-suspect` 가 차단
  (기존 변환본 루트는 소급 제외). 🔴 **Status Bar·Tool Bar 는 오버레이가 아니다 — flow 상단
  자식이 정본(개발 구현 동일), ABSOLUTE 금지** — verify `bar-absolute-positioning` 이 차단.
- **8-D (2026-09-03 사용자 채택)** — 🔴 소스가 **기존 벡터 디자인**(구형 트리)이고 스택 번역
  불가(겹침/절대배치) 그룹이 많으면 트리 변형 금지 → **rebuild 트랙**: 캡처 Read(시각 참조)
  + `extract_content_spec` 트리 실측(콘텐츠 1:1, OCR 금지) → blueprint 새로 작성(DS 문법) →
  build → 벡터/번역불가 블록만 원본 clone 이식(`list_transplant_blocks`) → bind+verify+대조.
  🔴 **2026-09-04 개정(사용자: "차단되면 원커맨드가 소용없다"): convert_screen 이 판별 후 멈추지
  않고 `scripts/rebuild_track.py` 로 rebuild 트랙을 끝까지 자동 수행**(트리 실측 → blueprint 자동
  생성 → build → 벡터 이식(placeholder 래퍼) → 이식 페인트 토큰/스타일 바인딩 → bind·verify·
  region_diff). 스테이지 색은 DS 페인트 스타일(`set_fill_style_id`/`set_stroke_style_id`)로.
  bypass `--force-convert`(변형 트랙). 상세: `rule 8-D`.
  🔴 **생성 SLA (2026-09-04 사용자: "다시 생성 20분은 용납 불가")** — 생성 요청은 **5분 내 산출물**.
  파이프라인이 막히면 가장 빠른 기존 경로(clone/`--force-convert`/수동 blueprint)로 화면부터 내고,
  인프라 수정은 **별도 작업으로 선언 후** 진행. 같은 요청에서 파이프라인 재실행 ≤2회(3회째면 현 상태
  보고). 휴리스틱 수정은 `scripts/tests/test_rebuild_track.py`(fixture 오프라인, 1초)로 먼저 검증 —
  실물 export+Read 왕복으로 디버그하지 말 것. rebuild 트랙은 `selfcheck`(굵기 히스토그램·이식 bbox·
  allow 없는 verify)를 자동 실행해 CONVERT-SUMMARY flags 로 노출하고, 총 소요가 `sla_s` 를 넘으면 경고.
- **8-E (2026-09-03)** — 🔴 **MCP 도구 계약 함정 목록** — 수동 조립(변환/개조 트랙)은 post-fix 가
  없는 지대: batch_build 의 layoutMode/width/padding 무시·기본 흰 fill, resize 후 FILL 자식 stale,
  오토레이아웃 자식 move 무시 등. batch_build 직후 `assert_spec_applied` 의무. 🔴 **완료 게이트 =
  `python3 scripts/qa_sweep.py <genId> <refId>` 원커맨드**(토큰+면·색+아이콘+TEXT 인벤토리 4차원) —
  requiredActions 의 이미지 전부 Read + CHECK 전 항목 해소/설명해야 완료 보고 가능. 상세: `rule 8-E`.
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
  **면제(2026-09-04)**: `IMIN_CONVERT_TRACK=1` 또는 root `_referencesSkipped:"<사유>"` 면 Step A.0
  검색과 Read 게이트를 건너뜀(`_should_skip_reference_step`) — 1:1 변환은 레퍼런스가 캡처 자체.
- **0-G-2** — 같은 화면의 기존(특히 **사용자 수정**) 버전을 빌드 전 export+Read 학습 — 사용자 교정이
  최우선 레퍼런스. 컬러 시맨틱: **완료=success 계열, 브랜드 퍼플='나의 것' 한정**.
  🔴 **0-G-3 하드 게이트 (2026-09-11 사용자: "현재 페이지에 같은 디자인이 존재하는데 검색하지 않고 처음부터
  다시 디자인했다")** — build/prebuild 가 blueprint 의 `_navTitle`·`_wireframeContent` 타이틀·
  `_existingSearchKeys` 로 페이지 인덱스(`scripts/_figma_index_*.json`)를 자동 검색해 같은 화면(이름 부분
  일치·TEXT 일치)이 있으면 **`ERR_EXISTING_DESIGN_UNREVIEWED` 로 차단**. 통과 = 그 노드를 export+Read 하고
  root 에 `_existingReviewed:[id…]` + `_existingDecision:{mode:"clone"|"redesign", reason}` 선언.
  **기존 DS 본이 있으면 clone/변환 트랙이 기본**, 새로 그리는 건 reason 이 있어야 한다. 우회
  `_existingReviewedSkipped:"<사유>"`. (4.5 인덱스 grep 이 재량 단계라 건너뛰던 것을 코드 게이트로.)
  🔴 **0-G-4 clone 트랙 원커맨드 (2026-09-11 사용자: "8분이나 걸렸어?")** — 기존 DS 본이 있는 변형
  화면은 손으로 clone·치환·verify 를 반복하지 말고 **`python3 scripts/figma_mcp_client.py clone-variant
  <spec.json>`** 한 번(clone → 트리 1회 → 텍스트 치환/삭제/styleFrom → viewport·pinBottom →
  **인원수별 스테이지 색** → bind 1회 → 배치 → verify 1회, 실측 ≤2분). 수동 8분의 원인 = 색 재작업
  2분 + verify 6회 2분 + 도구 탐색 1.5분. **스테이지 상세 계열 색은 브랜드 퍼플이 아니라
  `ds_catalog.STAGE_COLOR_STYLES`(13 pink/9 mint/7 purple/5 gray 로컬 페인트 스타일, 총 입금 n회 =
  n명)** — `stageMembers:"auto"` 가 텍스트에서 추정. 상세: `rule 0-G-4`.
- **0-F** — 빌드 로그 `📸 SECTION-QA-PNG` → 섹션별 재export+Read+checklist(C01~C12) 채운 뒤에만
  보고. 1장 보고 "검증 ✅" 절대 금지. FAIL 있으면 fix 후 재검증 또는 솔직 보고.
- **0-F-3 (2026-09-08 사용자 룰 — "왜 자꾸 눈으로 보고 판단하지??")** — 🔴 **크기·굵기·간격·정렬은
  눈으로만 보고 판단하지 말 것 — 반드시 숫자로 잰다.** 스크린샷 배율 착각(2x 를 1x 로)으로 도트를
  3회 연속 틀린 사고. 원본 대조·사용자 지적 대응·완료 보고에서 치수를 말할 땐 ① 노드 메트릭
  (`get_node_info` width/height/strokeWeight/itemSpacing) 또는 ② 픽셀 실측
  (`python3 scripts/pixel_measure.py <genId> <refId>` — 4x export 연결성분 지름·굵기 히스토그램 대조,
  `--band y0:y1` 집중 측정) 결과를 **표로 병기**. "≈8px 로 보임" 류의 눈대중 서술 금지. qa_sweep ⑤
  차원이 소형 반복 요소(≤16px) 규격 불일치를 CHECK 로 차단. 상세: `rule 0-F-3`.
  🔴 **0-F-4 (2026-09-11 사용자: "floating box 에 drop shadow 가 없는데 확인이 안 되는 거냐 빼먹은 거냐")** —
  그림자는 카드 박스 *바깥* 픽셀에만 나타나 텍스트 밴드·소형 성분·region_diff 어느 것에도 안 잡힌다.
  `python3 scripts/shadow_check.py <genId> <refId>` = 카드(흰+보더+radius≥8, 폭≥200) 경계 바깥 밝기
  램프 Δ(먼 배경−경계 인접) 를 ref↔gen 대조(ref Δ≥6 인데 gen 없음 → 불일치), qa_sweep ⑦ 차원이 CHECK.
  **DS 스타일 선택도 실측**: ref 램프(아래/좌/우 Δ + 퍼짐 px)와 `ds/SHADOW_RAMP_CALIBRATION.json`(스타일별
  실측 시그니처, `--calibrate <cardId>` 로 재측정)의 거리 최소 스타일을 shadow_check 가 **권장**하고
  `--apply` 가 즉시 바인딩 — 눈으로 고르지 않는다. 캡처 실측 시 박스 안만 재지 말고 경계 바깥 램프도 잰다. 한글 글리프 높이→폰트 크기는 **타이틀
  20px 실측 비율(≈0.875)** 로 환산(0.72 로 계산하면 한 단계 크게 잡음 — 내 스케줄 화면 실사고). 상세: `rule 0-F-4`.
- **0-DESC (2026-09-23 사용자 룰)** — 🔴 **화면마다 우측 디스크립션 + 영역 넘버 마커는 `describe <spec.json>`
  원커맨드**(홈 우측 `description` 인스턴스 140:64004 + `Description Num` 140:70842). 디스크립션 x=화면 x+폭+82,
  마커 x=화면 x−2, 행=기능 영역(위→아래, 최대 19), 본문=`제목 / [기능] · 불릿 (UC·BR·AF 근거) / [예외처리]`,
  미결정은 `{…: 확인 필요}`, 다른 화면은 상대 위치("우측 화면") 대신 화면 이름으로. 상세: `rule 0-DESC`.
- **0-DESC-2 (2026-09-23 사용자 룰)** — 🔴 **화면 root 선택 + "마커 재생성" = `regen-markers` 즉시 실행** —
  마커를 현재 영역 y 로 다시 찍고, 새 영역은 마커 + 디스크립션 초안 행(`(초안 — 작성 필요)`, 실물 텍스트·버튼만
  나열) 자동 추가, 사라진 영역은 제거. 마커↔영역 추적 = 마커 이름 `Description [n] <영역id>[+id…]`(옛 마커는 y 순서 DP 귀속, 백필은 `--fold`).
  요소 추가·영역 크기 변경 뒤엔 항상 실행. 상세: `rule 0-DESC-2`.
- **0-FLOW (2026-09-23 사용자 룰)** — 🔴 **flow 화살표는 `flow <spec.json>` 원커맨드** — 선택 섹션/노드의 flow 는
  **현재 페이지 `my tool box` 섹션의 도형·화살표를 템플릿으로 복제해서만** 쓴다(원본 소비 금지). 복제는 플러그인
  clone·⌘D 가 아니라 **focus_node + macOS 메뉴 Edit › Duplicate 클릭**(duplicate_via_menu) →
  `set_connector` 로 버튼 RIGHT → 다음 화면 LEFT, 라벨 `동작 → 결과 (UC)`, 조건 ◇/진입점 □/외부 절차 ▱.
  🔴 도형 텍스트가 잘리면 안 됨 — `fit_shape` 가 텍스트에 맞춰 도형을 키움(기존 섹션은 `flow --fit <sectionId>`).
  🔴 3슬롯 이상 BOTTOM→BOTTOM 금지(화면 가로지름) — 슬롯 인접시켜 RIGHT→LEFT. 상세: `rule 0-FLOW`.
- **0-FLOW-2 (2026-09-23 사용자 룰, 등록 진행 중)** — 🔴 **화살표는 용도별 템플릿만** — `scripts/flow_arrow_catalog.json`
  (`arrow-register <type> --purpose …` 로 선택 커넥터 등록, `arrow-list` 조회). `flow` edge 의 `type` 이 템플릿을 고르고,
  미등록 type·제약 위반(예: `cond-yes` 는 시작이 ◇, **예=◇ RIGHT / 아니오=◇ BOTTOM 에서만**)은 ERROR. 등록: `tap`(파랑, 사용자 탭 — **default**) · `auto`(회색, 시스템 자동 전이) · `input-done`(진회색, 입력 완료 전이) · `cond-yes`(녹색, ◇ 네) · `cond-no`(빨강, ◇ 아니요). 상세: `rule 0-FLOW-2`.
- **0-F-2 / 0-R** — 작업 종료 시 `cleanup-qa` 1회(스크린샷·썸네일 삭제). 빌드 성공 시 사용한
  blueprint json 은 자동 삭제(재빌드는 새로 작성 — 의도된 동작).
- **19 / 22 / 22-B** — 스크린샷 QA 에서 PRD 전 섹션 1:1 확인(하나라도 누락 시 완료 선언 금지).
  빌드 로그의 `[QA] ⚠️`·`[smell] ⚠️` 라인 확인·수정.

### 스타일 기본값 (fill-in/advisory — author 명시값이 항상 이김. `[스타일-기본값]` 로그)

- **2-B** — 카드 표면 기본 = 흰 면(`bg-primary`)+보더. 보더 색은 뒤 배경 따라: 흰 배경 위
  `border-primary` / 그 외 `border-secondary`. 보더 자동부착은 흰-on-흰만. 보더리스 면 의도 시
  `_keepSurface:true`. Footer 는 배경·보더 없음.
- **2-B-3** — 흰 카드 elevation = DS `Shadows/shadow-basic` 자동 바인딩(`_noShadow`·placeholder 제외,
  개별 코너 radius 카드는 `_cardShadow:true` 로 강제). 🔴 **2026-09-11 회귀 수정**: cmd_build 가 post-fix 뒤에
  돌리는 전역 drop-shadow strip 이 방금 바인딩한 shadow-basic 을 도로 지우고 있었다(빌드 로그에 "✓ 2개
  바인딩" 과 "2건 제거" 가 함께 찍힘). 이제 strip 은 DS effect style 바인딩(`_is_ds_bound_shadow`:
  effectStyleId / INNER+DROP 조합 / DS fingerprint 일치)을 보존 — raw 단일 DROP_SHADOW 만 제거.
- **13** — 섹션 강조 여부·색은 작성자 자율. 단 **회색(bg-secondary) 도배 = 칙칙(지양)**,
  **bg-brand-primary 면 = 자제** — 기본은 흰 면+보더, 강조는 타이포 위계·여백·그룹화·브랜드 퍼플
  *액센트*(텍스트/CTA/아이콘/dot)로. `_band:true` 는 풀폭 *구조* 마커일 뿐(색 아님).
- **2-H / 2-B-2** — 큰 면적 brand fill·브랜드 틴트 면 = advisory WARN (컬러 히어로 의도 허용,
  가독성은 대비 QA 가 방어). 틴트 면을 쓸 땐 `bg-brand-primary`(연한 라벤더)만.
- **2 / 2-J** — 색 절제: 브랜드 퍼플 = 단일 일관 액센트(CTA·active 탭·핵심 수치), 상태색(success/
  warning/error)은 진짜 상태에만 소량, **Aqua 자제**, 여러 색 난무 금지. 평면 그레이 나열도 금지
  (폴리시: 위계/대비/그룹화).
- **2-K** — 🔴 **다크 면(bg-primary-solid 등)을 기본값으로 쓰지 말 것 (2026-07-10 사용자 룰).**
  기본 밸런스 = 뉴트럴 베이스(흰 카드+보더) + 브랜드 퍼플 *액센트*. 다크 히어로/앵커는 색 축
  로테이션의 한 카드일 뿐 — `_designDirection.color` 는 같은 화면의 직전 빌드뿐 아니라 **최근
  다른 화면들의 색 축과도** 겹치지 않게. 레퍼런스도 다크 히어로만 골라 근거 삼지 말 것. 상세: `rule 2-K`.
- **2-L** — 🔴 **승인본 메트릭 = 기준선 (2026-07-13 사용자 룰 — "매번 opus 문법으로 말 안 해도 되게").**
  같은 화면의 사용자 승인본이 있으면 그 타이포 스케일(16 베이스+12 디테일)·패딩·컨테이너 문법·
  figure-ground 를 **±20% 이내 승계** (`get_nodes_info` 로 메트릭 표 대조). 발산(S24~S26)의 대상은
  와이어지 승인본이 아님. blueprint 확정 직전 **fable 셀프체크 4항**: 다크 앵커?/타이포 극대비
  (24↔14)?/밀도 상승(칩 44h·셀 34h 미달)?/컨셉 끼워맞춤? — YES 면 완화. 고정 높이 셀은 height 가
  아니라 **상하 패딩**으로. 상세: `rule 2-L`.
- **19-B** — 세로 패딩 큰 비대칭은 디자인 의도로 존중(≤4px 만 교정, `_asymPad:true` 로 침묵).
- **0-N/R63** — 다른 정보는 다른 시각 언어 — 인접 섹션이 동일 카드 구조면 WARN → 한쪽 재설계.
- **2-M (2026-08-24 사용자 수정 학습)** — 비교/전후 2-up 카드는 **구조 문법 통일**(전폭 밴드
  헤더·라벨 20 SemiBold·상단 정렬 대칭) + **색으로만 차등**(열세 gray / 우세 브랜드) — 열세 쪽
  구조 격하(좁은 pill·처짐) 금지. 설명 문단 강조 = 키워드 부분 SemiBold(색 유지). 카드 안
  서브 헤더 = 14 SemiBold text-primary. 상세: `rule 2-M`.

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
