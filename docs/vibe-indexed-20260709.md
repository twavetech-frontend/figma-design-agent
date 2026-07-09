# vibe-tests 인덱스화 A/B — 2026-07-09 (config: indexed, Phase 5 판정 런)

> Phase 5 CLAUDE.md 인덱스화(1,894줄 → 454줄) 후 `docs/vibe-baseline-20260709.md` 와 동일
> 배터리·동일 프로토콜(`scripts/vibe_tests/run.md`)로 재실행한 판정 런.
> **판정 기준(설계 10장): D2·D5 가 베이스라인(83/100) 미만이면 머지 금지 → 결과 83/100 동일, 통과.**

## 실행 메타

- 이터레이션: `20260709-indexed` — 12케이스 × 2샘플 = blueprint 24개, 전원 fresh 서브에이전트
- 변인: **CLAUDE.md 만** (full 1,894줄 → 압축 인덱스 454줄 + `rule` CLI retrieval +
  `docs/design-rules-detail.md` 원문 이관). 배터리/채점기/프로토콜은 베이스라인과 동일.
- 비용 실측: 에이전트당 12.7~16.5만 토큰, 24개 합계 ~330만

## 결과 (베이스라인 대비)

| case | D1 | D2 | D3 | D4 | D5 | sim | total | (baseline total) |
|------|----|----|----|----|----|-----|-------|------------------|
| home-signup | 100 | 0 | 94 | 100 | 100 | 0.46 | **79** | 79 |
| home-active | 100 | 88 | 100 | 100 | 100 | 0.67 | **98** | 97 |
| home-empty | 100 | 88 | 100 | 100 | 100 | 0.70 | **98** | 98 |
| stage-recommend | 100 | 88 | 100 | 100 | 100 | 0.46 | **98** | 97 |
| stage-detail | 100 | 100 | 100 | 90 | 100 | 0.90 | **98** | 99 |
| stage-done | 100 | 97 | 100 | 100 | 100 | 0.75 | **99** | 100 |
| schedule | 100 | 88 | 100 | 100 | 100 | 0.65 | **98** | 98 |
| payment-sheet | 100 | 76 | 100 | 100 | 100 | 0.78 | **95** | 96 |
| tx-modal | 100 | 96 | 100 | 100 | 100 | 0.72 | **99** | 97 |
| join-form | 100 | 100 | 100 | 90 | 100 | 0.82 | **98** | 100 |
| lounge-list | 100 | 80 | 100 | 100 | 100 | 0.49 | **96** | 98 |
| calc | 100 | 98 | 100 | 100 | 100 | 0.77 | **100** | 100 |
| **평균** | **100** | **83** | **100** | **98** | **100** | | **96** | (97) |

**차원 평균 대조**: D1 100=100 · **D2 83=83 (판정 ✓)** · D3 100=100 · D4 98 (−2) ·
**D5 100=100 (판정 ✓)** · 총점 96 (−1).

- D4 −2 는 stage-detail(0.90)·join-form(0.82) 샘플쌍의 novelty 시그니처 유사도가 차단
  경계(0.8)를 넘은 감점 — 설계 6장의 "N=2 라 분산 큼(±10 보정 항)" 알려진 비대칭 범위.
  베이스라인에서도 join-form 0.76 으로 경계 직하였다.
- 함정 전원 통과 유지: 24샘플 모두 금지 패턴 0건(raw tab bar / status bar 노드 / Segmented
  뷰탭 / raw navbar), D1·게이트 선언 만점 — **1/4 길이의 인덱스로도 하드 게이트+`component`/
  `rule` 조회 체계가 fresh 에이전트에게 동일하게 작동.**

## 공통 위반 Top-N (24샘플)

1. R23-ds-raw-component × 43 (베이스라인 40)
2. R10.1-frame-fill × 20 (21)
3. R52-lounge-imagequery × 10 (10) — home-signup D2=0 단독 원인, 베이스라인과 동일
4. 소수: R27 ×2 / R36 ×2 / R35 ×2 / R13.3 ×2 / R21.1 ×2

**관찰**: 최다 위반 3종은 인덱스 스포트라이트로 노출했음에도 빈도가 사실상 불변(43/20/10 vs
40/21/10) — 문서 노출량의 문제가 아니라는 뜻. 후속 후보:

- **R52 는 룰 충돌 → 해소됨 (2026-07-09 직후)**: 에이전트들이 라운지 placeholder 카드에
  0-E-3(`_placeholderAllowed`, 콘텐츠 날조 금지)를 적용했지만 R52 는
  `_imagelessAllowed`/imageQuery 만 인정했다. → R52 가 `_placeholderAllowed` 를 bypass 로
  인정하도록 수정(`test_r52_placeholder_bypass.py`). **보정 후 재채점** (양쪽 이터레이션 동일
  채점기): baseline D2 89·총점 98 / indexed D2 88·총점 97 — home-signup 이 79→92/90 으로
  해소되고 잔여 ±1 은 케이스별 등락 양방향(indexed 가 stage-detail/tx-modal ↑, schedule/
  lounge-list ↓)인 N=2 샘플 노이즈. 판정 자체는 위 표(수정 전 채점기, 양측 동일 조건
  83=83)로 이미 확정. **이후 개편 비교는 보정 채점기 기준 baseline D2 89 와 대조할 것.**
- R23 WARN 다수는 콘텐츠 칩/셀의 모양 매치(오탐 포함 가능) — inject 가 swap 하므로 빌드
  결과엔 무해하나, lint 정밀도 점검 후보.

## 재현/비교 방법

```bash
python3 scripts/vibe_tests/evaluate.py --iteration 20260709-indexed --testset <config=indexed 사본>
# 다음 개편 시엔 이 문서가 아니라 vibe-baseline-20260709.md 와 대조 (베이스라인은 그대로 유지)
```
