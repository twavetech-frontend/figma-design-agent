# Blueprint Vibe-Tests 설계 (Phase 4 — Astryx vibe-tests 패턴 적용)

> 2026-07-08 설계. 참조: `facebook/astryx` `internal/vibe-tests/` (동일 프롬프트 배터리를
> 여러 구성에서 fresh 에이전트로 돌려 측정 — "design system docs as a measurable product").

## 1. 목적 — 무엇을 측정하나

**"fresh 세션의 에이전트가 와이어 콘텐츠를 받아 얼마나 룰을 지키면서도 창의적인 blueprint 를
만드는가"** 를 자동·반복 측정한다. 지금까지는 룰 개편(예: 2026-06-12 창의성 전면 개편)의 효과를
*다음 사용자 분노 여부*로만 확인했다 — 이걸 수치로 바꾼다.

측정이 생기면 가능해지는 것:
1. **룰 개편의 사전 검증** — CLAUDE.md 인덱스화(Phase 5)를 배터리 통과율 비교로 안전하게.
2. **회귀 감지** — 새 enforcer/게이트가 기존 케이스의 점수를 떨어뜨리면 즉시 노출.
3. **창의성 문제의 정량화** — "100번 생성하면 다 똑같다"를 시그니처 유사도 분포로.

**측정하지 않는 것 (v1 범위 밖):** 라이브 빌드 결과(post-fix/바인딩/스크린샷 QA) — Figma
플러그인이 필요해 CI 불가. v1 은 **blueprint 산출물만 오프라인 채점**한다.

## 2. 공정성 불변식 (Astryx Checker Protocol 차용 — 위반 시 측정 무효)

1. **공정한 채점기** — 모든 구성/케이스에 같은 채점 로직(결정적 Python, LLM 채점 없음).
2. **변인은 하나** — 같은 케이스·같은 프롬프트 구조. 구성(context variant)만 다르게.
3. **정답 비누출** — 케이스의 `expected`(기대 DS 컴포넌트/금지 패턴)는 채점 전용.
   생성 에이전트에게는 sanitized 케이스(콘텐츠 dict + PRD 요약)만 전달. 컴포넌트를 힌트하는
   사전 조회 명령도 프롬프트에 넣지 않는다 — 에이전트가 스스로 component/search 로 발견해야.
4. **대표성 있는 환경** — 에이전트는 실제 세션과 같은 것을 받는다: 레포 안에서 실행(CLAUDE.md
   자동 로드), `component`/`search`/`manifest` CLI 사용 가능, uibowl 레퍼런스 검색 가능.
   단 **build 실행 금지**(브리지/플러그인 불필요 — 산출물은 파일로만).
5. **컨텍스트 프리** — 케이스마다 fresh 서브에이전트(대화 이력 없음, fork 아님). 재사용 금지.

## 3. 아키텍처 — 3층

```
scripts/vibe_tests/
├── test-sets/default.json        # 배터리 (케이스 12개, expected 포함 — 커밋)
├── run.md                        # 오케스트레이션 절차 (메인 세션이 따르는 프로토콜)
├── evaluate.py                   # 결정적 오프라인 채점기 (Python, 브리지 불필요)
├── aggregate.py                  # 케이스/차원별 집계 + 마크다운 리포트
└── results/                      # (gitignore) results/<iter>/tasks|blueprints|scores
```

- **생성**: 메인 세션(Claude)이 Agent 도구로 케이스당 N개 fresh 서브에이전트 병렬 스폰.
  각 에이전트는 sanitized task 파일을 읽고 blueprint JSON 을 `results/<iter>/blueprints/`
  에 Write. (Astryx 의 "/vibe-test → spawn parallel subagents" 방식과 동일 — 코드가 아니라
  메인 세션이 오케스트레이터.)
- **채점**: `python3 scripts/vibe_tests/evaluate.py --iteration <iter>` — 결정적, LLM 없음.
- **집계**: `aggregate.py` — 케이스×차원 매트릭스 + 구성 간 비교 테이블.

## 4. 배터리 스키마 + v1 구성 (12케이스)

```json
{
  "id": "home-signup-1",
  "category": "home-dashboard",
  "complexity": "complex",
  "screenName": "imin_signup_home_vibe",
  "prdBrief": "가입 전 사용자 홈 — 시작 유도 + 현황 + 출석/초대. 하단 탭바(홈 active) + FAB.",
  "wireframeContent": { "...": "섹션별 텍스트/숫자/카운트 1:1 dict (0-E 포맷)" },
  "expected": {
    "dsComponents": ["Tab Bar", "Tool Bar", "Action Button"],
    "forbiddenPatterns": ["raw-tab-bar-frame", "status-bar-node", "segmented-view-tabs"],
    "notes": "채점 전용 — 에이전트 비노출"
  }
}
```

**v1 케이스 12개** (과거 실제 화면 기반 — 콘텐츠 dict 는 기존 자산/기획 문서에서 추출):

| # | id | category | complexity | 씨앗 |
|---|----|----------|------------|------|
| 1 | home-signup | home-dashboard | complex | `wireframe_content_imin_home_v14.json` (실자산) |
| 2 | home-active | home-dashboard | complex | archetype_specs/imin_home.json + 메모리 |
| 3 | home-empty | empty-state | moderate | 0건/0원 와이어 (S23 empty 케이스) |
| 4 | stage-recommend | list-recommend | moderate | 추천 스테이지 리스트 (0-J 뷰탭 함정 포함) |
| 5 | stage-detail | detail | complex | 스테이지 상세 (색 시맨틱: brand=내 것) |
| 6 | stage-done | detail | moderate | 완료 화면 (완료=success 시맨틱) |
| 7 | schedule | detail | moderate | 내 스케줄 (입금/지급 뷰 탭 → underline 함정) |
| 8 | payment-sheet | bottom-sheet | moderate | 납입 바텀시트 (0-D 패턴) |
| 9 | tx-modal | full-modal | moderate | 거래 스케줄 full modal (R58 함정) |
| 10 | join-form | form | simple | 참여 폼 (Checkbox/Input DS 인스턴스 2-I) |
| 11 | lounge-list | list-recommend | simple | 라운지 리스트 |
| 12 | calc | tool | simple | 모으기 계산기 (스테퍼 14-B 함정) |

카테고리마다 **알려진 회귀 함정**(위 표의 괄호)을 심는다 — 배터리가 곧 회귀 스위트가 된다.

## 5. 생성 프로토콜

- 케이스당 **N=2 샘플** (다양성 측정용 — D4). 12케이스 × 2 = 24 에이전트/이터레이션.
- 서브에이전트 프롬프트 템플릿 (모든 케이스 동일 구조, Astryx 불변식 2):

```
너는 imin 앱 화면의 Figma blueprint 를 작성한다.
task 파일: scripts/vibe_tests/results/<iter>/tasks/<id>-<n>.json (prdBrief + wireframeContent)
- 이 레포의 CLAUDE.md 디자인 룰을 준수하라.
- DS 컴포넌트가 필요하면 python3 scripts/figma_mcp_client.py component/search 로 조회하라.
- 레퍼런스가 필요하면 scripts/ref_search.py 를 써라 (thumbnail Read 가능).
- ⚠️ build 를 실행하지 마라. 산출물은 blueprint JSON 1개를
  scripts/vibe_tests/results/<iter>/blueprints/<id>-<n>.json 에 Write 하는 것뿐이다.
- root 에는 빌드 게이트가 요구하는 선언(_wireframeContent, _concept, _designDirection,
  _wireframeDivergence)을 실제 내용으로 채워라.
```

- **구성(config) 축**: v1 은 `full`(현 CLAUDE.md) 1개만. 하네스는 config 필드를 스키마에
  두어 Phase 5 에서 `indexed`(개편 CLAUDE.md) A/B 비교를 지원한다. (Astryx 의 4-target
  비교와 동일 구조 — 우리 target 은 context variant.)

## 6. 채점 5차원 (모두 결정적·오프라인)

| 차원 | 산출 | 소스 |
|------|------|------|
| **D1 구조 유효성** (0~100) | `validate_blueprint` ERROR 0건=100, 건당 -20 | 기존 함수 재사용 |
| **D2 룰 준수** (0~100) | `design_rules.REGISTRY.run_lint` — ERROR 건당 -15, WARN 건당 -3 | 기존 REGISTRY |
| **D3 콘텐츠 충실도** (0~100) | wireframeContent dict string value 들의 blueprint TEXT 커버리지 % (0-E). **날조 페널티**: 와이어에 없는 마케팅 카피 휴리스틱(0-E-3)은 v1 보류 | 순수 워커 신규 |
| **D4 창의 발산** (0~100) | ① 게이트 선언 품질: _concept.diffs≥3·_designDirection 3축·_wireframeDivergence≥3 (형식+최소 구체성: 항목 길이/중복) ② 같은 케이스 N샘플 간 novelty 시그니처 유사도 — ≥80% 면 감점 ("다 똑같다" 정량화) | 기존 novelty 시그니처 함수 재사용 |
| **D5 DS 정합** (0~100) | expected.dsComponents 의 인스턴스 사용 커버리지 + forbiddenPatterns 검출(raw tab bar frame, status bar 노드, non-forced `_segLabels` 뷰탭 등 — 구조 매처) | ds_catalog + 신규 매처 |

- 케이스 점수 = 5차원 평균. 이터레이션 점수 = 케이스 평균 + 차원별 분해 테이블.
- **알려진 비대칭 문서화** (Astryx "Known Accepted Asymmetries"): D4-② 는 N=2 라 분산이 큼
  (참고 지표로 취급, 케이스 점수 가중치 낮게 시작: D4-② 는 ±10 보정 항).

## 7. 리포트 포맷

```
iteration: 2026-07-08-a  config: full  cases: 12×2
        D1   D2   D3   D4   D5   총점
home-signup   100   82   94   71  100   89
...
차원 평균:  D2 룰 준수가 최저 (WARN 다발: R10.1-frame-fill ×14)
전 케이스 공통 위반 Top3: ...  ← 룰 문서/enforcer 개선 후보
```

집계가 **"전 케이스 공통 위반 Top-N"** 을 뽑는 게 핵심 — CLAUDE.md 의 어떤 룰이 안 지켜지는지
데이터로 나온다 (Phase 5 인덱스화 때 "최다 에러 유발 룰 6개" 선정 근거).

## 8. 비용/운영

- 1 이터레이션 = 24 fresh 서브에이전트 (레퍼런스 Read 포함 에이전트당 대략 30~80k 토큰).
  스모크는 3케이스×2=6 에이전트로 먼저.
- 채점/집계는 토큰 0 (Python).
- results/ 는 gitignore, 리포트 markdown 만 선택 커밋.
- 수동 트리거 (cron 아님) — 룰 개편 전후, 또는 요청 시.

## 9. 구현 순서

1. **4a — 채점기 먼저** (`evaluate.py` + 케이스 스키마 + 테스트): 손으로 만든 blueprint
   2~3개(good/bad fixture)로 채점기 자체를 검증. 에이전트 0명 — 토큰 비용 없음.
2. **4b — 배터리 12케이스 작성**: 콘텐츠 dict 추출(기존 자산 + 기획 digest). 이건 사람/Claude
   가 한 번 하는 작업.
3. **4c — 스모크 런**: 3케이스×2 에이전트 → 채점 → 리포트 포맷 확정.
4. **4d — 풀 런 + 베이스라인 고정**: 12×2 실행, 점수를 `baseline-<date>.md` 로 기록.
   이후 룰 개편은 이 베이스라인과 비교.
5. **4.5 (후순위) — degradation 모드**: 10턴 대화(필러/방해 턴) 후 같은 태스크 재수행 —
   세션 후반 룰 준수 저하 측정. v1 범위 밖.

## 10. Phase 5 연결

CLAUDE.md 인덱스화는 **4d 베이스라인 확보 후**: `config: indexed` 로 같은 배터리 재실행 →
차원별 점수가 베이스라인 대비 유지/상승할 때만 머지. 특히 D2(룰 준수)와 D5(DS 정합)가
인덱스화로 떨어지지 않는지가 판정 기준.
