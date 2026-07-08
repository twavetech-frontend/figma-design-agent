# vibe-tests 실행 프로토콜 (메인 세션 Claude 가 따르는 절차)

> 설계: `docs/vibe-tests-design.md`. Astryx `/vibe-test` 처럼 오케스트레이션은 메인 세션이,
> 채점은 결정적 Python 이 한다. **공정성 불변식 5개(설계 2장)를 위반하면 측정 무효.**

## 1. 이터레이션 준비 (토큰 0)

```bash
ITER=<날짜>-<a/b/c>   # 예: 20260708-a
mkdir -p scripts/vibe_tests/results/$ITER/{tasks,blueprints}
```

`test-sets/default.json` 의 각 케이스에 대해 **sanitized task** 를 생성한다 —
`id`/`screenName`/`prdBrief`/`wireframeContent` 만 복사 (⚠️ `expected` 절대 포함 금지):
`results/$ITER/tasks/<id>-<n>.json` (n = 1..samplesPerCase).

## 2. 생성 — fresh 서브에이전트 (케이스×샘플당 1개, 병렬)

Agent 도구(**fork 아님** — 컨텍스트 프리 불변식 5)로 스폰. 프롬프트 템플릿(모든 케이스 동일):

```
너는 imin 앱 화면의 Figma blueprint JSON 을 작성한다.
task: scripts/vibe_tests/results/<iter>/tasks/<id>-<n>.json 을 Read 하라
(prdBrief + wireframeContent — 콘텐츠는 이 dict 와 1:1 이어야 한다).
- 이 레포 CLAUDE.md 의 디자인 룰을 준수하라.
- DS 컴포넌트는 python3 scripts/figma_mcp_client.py component/search 로 조회해서 쓰라.
- 레퍼런스가 필요하면 python3 scripts/ref_search.py --archetype <화면> --thumbnail 후 Read.
- root 에 _wireframeContent(받은 dict 그대로) + _concept + _designDirection +
  _wireframeDivergence 를 실제 내용으로 선언하라.
- ⚠️ build/post-fix 를 실행하지 마라. 산출물은 blueprint JSON 1개를
  scripts/vibe_tests/results/<iter>/blueprints/<id>-<n>.json 에 Write 하는 것뿐.
```

금지: expected 힌트, 케이스별 코칭("underline tabs 를 써라" 등 — 룰 문서가 가르쳐야 함),
서브에이전트 재사용.

## 3. 채점 + 리포트 (토큰 0)

```bash
python3 scripts/vibe_tests/evaluate.py --iteration $ITER
# → results/$ITER/scores.json + report.md (케이스×차원 테이블 + 공통 위반 Top-N)
```

## 4. 베이스라인 비교

룰/문서 개편 전후 비교 시: 같은 배터리·같은 samplesPerCase 로 재실행 후 `report.md` 의
차원 평균을 `docs/vibe-baseline-<date>.md` 와 대조. **D2(룰 준수)·D5(DS 정합)가 떨어지면
개편 머지 금지** (설계 10장 — Phase 5 판정 기준).
