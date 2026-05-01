# Semantic Token Binding Sweep — Design Spec

작성일: 2026-05-01
대상 파일: `scripts/figma_mcp_client.py`, `ds/TOKEN_MAP.json`
관련 도구: `batch_bind_variables`, `batch_set_text_style_id`, `set_effect_style_id`, `get_node_info`

## 배경

현재 디자인 빌드 파이프라인은 raw RGB / 픽셀 / 폰트 사이즈를 그대로 노드에 적용한다. DS는 `ds/TOKEN_MAP.json` (8089줄, COLOR 1254 / NUMBER 102 / TYPOGRAPHY 44 / BOXSHADOW 21 등)로 semantic 토큰을 보유하고 있고, MCP 도구도 이미 바인딩 기능을 제공하지만, **빌드 후 raw 값을 토큰명에 자동 연결하는 단계가 빠져 있어 매번 수동 binding이 필요**하다.

## 목표

빌드 직후 트리를 한 번 순회하면서 raw 값을 의미 토큰에 자동 바인딩한다. 단일 화면(80~150 노드) 기준 **30초 ~ 1분 30초** 내 완료한다.

## 적용 범위

| 속성 | 매칭 대상 | 도구 |
|---|---|---|
| fill / stroke (SOLID 컬러) | COLOR 1254 토큰 | `batch_bind_variables` |
| paddingTop/Right/Bottom/Left, itemSpacing | NUMBER 토큰 | `batch_bind_variables` |
| cornerRadius (4코너 개별 포함) | NUMBER 토큰 | `batch_bind_variables` |
| strokeWeight, strokeTop/Right/Bottom/LeftWeight | NUMBER 토큰 | `batch_bind_variables` |
| TEXT 노드 typography (font+size+lh+ls+weight) | TYPOGRAPHY 44 텍스트 스타일 | `batch_set_text_style_id` |
| effects (DROP_SHADOW) | BOXSHADOW 21 효과 스타일 | `set_effect_style_id` |

**제외**: width / height / x / y 좌표 (의미 토큰 아님), IMAGE/GRADIENT fill, mixed style text.

## 매칭 정책

### 컬러
- 거리: `ΔRGB = |Δr| + |Δg| + |Δb|` (정규화 후 0~765)
- 임계치: **ΔRGB ≤ 12** (RGB 0~255 단위)
- 우선순위: **semantic alias** (예: `--colors-fg-primary`, `--colors-bg-brand-solid`, `--colors-border-secondary`) 가 **primitive** (예: `--colors-grayLightMode-900`) 보다 우선
- 동률 (같은 우선순위 + 같은 거리) 시: 토큰명 사전순 첫 번째

### NUMBER (간격, 반경, 스트로크)
- 임계치: **±2px**
- 동률 시: raw값과 정확히 같은 토큰 우선, 그 다음 absolute distance 작은 것
- value=0 은 매칭 skip (의미 없는 zero)

### TextStyle (TYPOGRAPHY)
- fontFamily / fontWeight: **정확 일치 필수**
- fontSize: ±1px
- lineHeight: ±3% (lineHeight가 px일 때는 ±1px)
- letterSpacing: ±3% (또는 ±0.1px)
- 위 조건을 모두 만족하는 후보 중 거리 합 최소
- mixed style (한 노드 안에 여러 style) 은 skip

### BoxShadow
- color ΔRGB ≤ 12, alpha ±0.1
- offset.x ±1px, offset.y ±1px
- radius ±2px
- spread ±1px
- 모두 만족하는 후보 중 거리 합 최소

## 데이터 흐름

```
build 명령
  └── batch_build_screen
  └── post-fix 1~5
        1. FILL 검증/수정
        2. 섹션 간격
        3. Tab Bar/FAB ABSOLUTE
        4. Tab Bar item FILL + Tab Row stroke
        5. zero-width 텍스트
  └── ★ 6. _bind_semantic_tokens(rootId)  ← NEW
        ├── _load_token_index()           # 1회 캐시
        ├── get_node_info(rootId, recursive=true)
        ├── _collect_bindings(nodes)      # in-memory 매칭
        ├── _apply_bindings(queues)       # 배치 MCP 호출
        └── _report_unmapped(unmapped)
  └── 자동 이미지 생성
```

## 모듈 구성

`scripts/figma_mcp_client.py` 내 함수 (별도 파일 분리하지 않음 — 기존 post-fix 구조와 동일하게 유지):

### `_load_token_index() -> TokenIndex`
`ds/TOKEN_MAP.json` 1회 로드, 역인덱스 4종 빌드:

```python
{
  "color_index":  {(r,g,b,a) -> [(token_name, is_semantic)]},
  "number_index": {value -> [(token_name, is_semantic)]},
  "typography_list": [{name, family, weight, size, lh, ls}],
  "shadow_list":     [{name, color, offset, radius, spread}]
}
```
- semantic 판별: figmaPath 또는 token name이 `fg-/bg-/border-/text-` 등 의미 prefix를 포함하면 `is_semantic=True`
- 모듈 레벨 캐시 (process 동안 1회만 빌드)

### `_walk_node_tree(rootId) -> List[Node]`
- `get_node_info(rootId)` 한 번 호출 — recursive 결과 필요. 도구가 recursive 옵션 미지원이면 BFS로 자식 순회 (노드 N개당 최대 N번 호출, 단일 화면 ~120회). 가능하면 도구에 recursive 옵션 추가 검토.
- 평면 list로 펼쳐서 반환.

### 매칭 함수
- `_match_color(rgb, alpha, color_index) -> token_name | None`
- `_match_number(value, number_index) -> token_name | None`
- `_match_textstyle(text_props, typography_list) -> style_id | None`
- `_match_shadow(effect, shadow_list) -> style_id | None`

각 함수는 임계치 안의 후보를 모은 뒤 위 정책으로 1개 선택. 임계치 밖이면 `None`.

### `_collect_bindings(nodes, indexes) -> Queues`

각 노드에서 추출:

```python
{
  "color_bindings": [{nodeId, field: "fills[0].color" | "strokes[0].color", token_name}],
  "number_bindings": [{nodeId, field: "paddingTop" | "itemSpacing" | "cornerRadius" | ..., token_name}],
  "textstyle_bindings": [{nodeId, style_id}],
  "effect_bindings":   [{nodeId, style_id}],
  "unmapped": {
    "colors":     [(nodeId, rgb, reason)],
    "numbers":    [(nodeId, field, value, reason)],
    "typography": [(nodeId, props, reason)],
    "shadows":    [(nodeId, effect, reason)]
  }
}
```

이미 다른 변수에 바인딩된 필드는 skip (덮어쓰기 방지). 단순화를 위해 `get_bound_variables`로 일일이 검증하지는 않고, plugin 측의 `batch_bind_variables` 동작이 기존 binding을 보존한다고 가정. (검증 결과 plugin이 덮어쓰면 후속 PR에서 사전 체크 추가.)

### `_apply_bindings(queues)`

- `batch_bind_variables` — 컬러 + NUMBER 큐를 합쳐 100개씩 청크 호출 (도구 timeout 300초)
- `batch_set_text_style_id` — textstyle 큐 일괄
- `set_effect_style_id` — 효과는 batch 도구 없으므로 개별 호출 (단일 화면 보통 1~5건)

### `_report_unmapped(unmapped)`

- 콘솔: 한 줄 요약 (예: `[token-bind] mapped 287, unmapped 12 (8 colors, 3 spacings, 1 shadow)`)
- 파일: `/tmp/unmapped-tokens-{rootId}.json` — 노드별 상세 (디버깅 / 토큰 추가 후보 발굴용)

## CLI / 옵션

- 기본: `build` 명령에 자동 통합. 별도 사용자 동작 불필요.
- `--skip-token-bind`: sweep 비활성화 (디버깅, 재실행 시).
- 추후 — retro-fit이 필요해지면 `python3 scripts/figma_mcp_client.py bind-tokens <rootId>` 별도 명령 추가 가능 (이번 spec 범위 외).

## 엣지 케이스

| 상황 | 처리 |
|---|---|
| 이미 바인딩된 필드 | skip (plugin이 보존) |
| fill 이 IMAGE / GRADIENT | 컬러 매칭 skip |
| paddingTop=0 같은 zero값 | NUMBER 매칭 skip |
| cornerRadius mixed (4코너 값 다름) | 4개 corner 개별 매칭 |
| TEXT mixed style | textstyle 매칭 skip + unmapped 보고 |
| 매칭 후보 없음 (임계치 초과) | unmapped 보고, raw 유지 |
| TOKEN_MAP 로드 실패 | 경고 로그 + sweep skip (빌드는 성공) |

## 성공 기준

1. iPhone 16 단일 화면 (~120 노드) 빌드 후 sweep 자동 실행.
2. 80% 이상의 컬러 fill / stroke이 semantic 토큰에 바인딩.
3. 80% 이상의 padding / itemSpacing / cornerRadius가 NUMBER 토큰에 바인딩.
4. TEXT 노드의 90% 이상이 TextStyle id에 매핑.
5. 전체 sweep 30초 ~ 1분 30초 내 완료.
6. 미매칭 raw값이 `/tmp/unmapped-tokens-*.json`에 정확히 기록.
7. 기존 빌드 동작 회귀 없음 (post-fix 1~5 결과 보존).

## 비목표 (이번 spec 범위 외)

- 새 토큰 자동 추가 / 제안
- DS Variables 직접 수정
- width / height / 절대 좌표 매핑
- 기존 빌드된 화면 retro-fit 명령 (`bind-tokens <rootId>`)
- semantic vs primitive 결정의 context-aware 모드 (옵션 C 안)

## 미해결 / 후속 검토

- `get_node_info`에 recursive 옵션 없으면 BFS 비용이 큼. 단일 화면 노드 수 검증 필요.
- plugin의 `batch_bind_variables`가 기존 binding을 덮어쓰는지 실제 동작 확인 필요. 덮어쓴다면 사전 `get_bound_variables` 캐싱 단계 추가.
- TYPOGRAPHY 44개의 figmaPath 구조에서 fontFamily/weight 정보 직접 추출 가능한지 확인 (불가능하면 별도 도구나 metadata 매핑 필요).
