# Refactor A — Unified Content Model

> 2026-05-28 사용자 분노 4회 후 결정. polish + mock + 와이어 콘텐츠 3-layer 가
> 분리되어 매번 충돌 → unified spec 으로 통합.

## A.1 — 현재 3-Layer 구조 분석

### Layer 1: 와이어 콘텐츠 (`_wireframeContent` dict)
- **위치**: blueprint root._wireframeContent
- **작성자**: 사용자 (Claude 가 와이어 PNG 분석 후 매번 작성)
- **형식**: `{"1.3 섹션이름": {"header": "...", "rows": [...]}}` — 자유형 nested dict
- **사용처**:
  - S22 lint (`_check_no_archetype_reuse`) — 이전 빌드와 70%+ 매치 시 ERROR
  - S23 lint (`_check_wireframe_content_required`) — imin_* archetype 빌드인데 dict 없으면 ERROR
  - `_detect_empty_state_scenario` (line 1144) — dict 안 "0건/0원/없어요" 키워드 카운트
- **한계**: dict 구조가 standardize 안 됨. 섹션마다 free-form schema. 코드가 parse 못 함

### Layer 2: Mock data 치환 (`_HARD_fill_mock_data_when_empty`)
- **위치**: cmd_build line 2813 (Step A.4)
- **호출 조건**: archetype `imin_*` AND `_detect_empty_state_scenario` True
- **동작**: blueprint TEXT 노드 walk → regex 패턴 매칭 → 치환
  - `_MOCK_FILL_PATTERNS_LONG` — 일반 영역 (긴 mock)
  - `_MOCK_DAY_STRIP_AMOUNTS` — Day Strip 좁은 cell 용 (짧은 mock)
- **한계**:
  - **TEXT 노드만 치환** — 섹션 구조 swap 불가 (예: empty card → grid card)
  - regex 기반 → 패턴 매칭 fragile (새 와이어 표현 추가 시 누락)
  - `_detect_empty_state_scenario` 가 mock 치환 후엔 False 반환 → polish 가 풀데이터로 인지 (의도 vs 결과 mismatch)

### Layer 3: Polish baseline (`_enrich_imin_home_polish`)
- **위치**: cmd_build line 2818 (Step A.5)
- **호출 조건**: archetype `imin_home` 만
- **7개 sub-함수**:

| Sub-함수 | is_empty 인지 | Detection 이름 매칭 | 문제 |
|---------|:-----------:|----------|------|
| `_inject_top_alert_banner` | ✓ (skip if empty) | "alert banner" / "top alert" | 안전 |
| `_enrich_day_strip_full` | ✓ (4단계 vs labels skipped) | "day strip" | 안전 |
| `_inject_screen_hero` | ✓ (invitation vs currency) | "screen hero" | 안전 |
| `_inject_subcard_cta` | ✓ (invitation vs points) | "sub-card" / "포인트" | 안전 |
| `_polish_recommend_hero_cta` | ✗ **인지 못함** | "Recommend Stage Card" | 무조건 polish → 와이어와 충돌 |
| `_polish_participation_grid` | ✗ **인지 못함** | "Participation Section" + (broad 매칭 박힘) | empty 시나리오에서 grid swap 누락 가능 |
| `_polish_lounge_real_products` | ✗ **인지 못함** | "Lounge Carousel" | 와이어 imageQuery 덮어쓸 위험 (idempotent 가드 박혔으나 fragile) |

### 충돌 지점 catalog

**충돌 1: is_empty 인지 누락** (3개 polish 함수)
- 시나리오: empty 와이어 + mock 데이터 치환 후 polish 호출
- 결과: `_polish_*` 가 풀데이터로 인지 → 무조건 polish 박음 → mock+polish 모순 (예: 1.3 카드 "3건" 인데 1.6 empty state — 사용자 분노 사례)

**충돌 2: Detection name fragile**
- 사용자 blueprint 의 섹션 이름 vs polish 함수의 hardcoded match name 미스매치
- 예: "Participation Section" 만 매칭하던 게 "Participating Wrap" 박힌 내 blueprint 인식 안 함
- 매번 새 케이스마다 broad 매칭 추가 → 반복

**충돌 3: Mock 단계와 Polish 단계 정보 비공유**
- `_HARD_fill_mock_data_when_empty` 가 어느 섹션이 mock 화 됐는지 polish 에게 안 알림
- polish 가 자기 판단으로 다시 detect → mock 치환 후 textual signal 사라져서 False 판단

**충돌 4: 와이어 콘텐츠 schema 자유형**
- `_wireframeContent` 가 nested dict 자유형 → 코드가 일관되게 parse 불가
- mock 치환은 TEXT 노드 walk → regex 매칭에 의존. 와이어 dict 자체를 활용 못함

## A.2 — Unified Content Model 설계

### 핵심 아이디어
**하나의 spec 에서 와이어 콘텐츠 + 시나리오 + polish 룰 모두 표현.** 그 spec 을 `_build_unified_blueprint(spec)` 가 받아서 blueprint 생성. polish/mock 함수들이 같은 spec 을 인지 → 충돌 없음.

### Spec 형식 (Python dict / JSON)

```python
{
    "archetype": "imin_home",
    "scenario": "auto",  # "active" | "empty" | "auto" (auto 면 wire_content 기반 판단)
    "wire_content": {
        # 와이어 추출 데이터. mock 치환 후에도 "원본 와이어" 로 보존
        "1.3 stage_progress": {
            "count": 0,           # 와이어 원본 수치
            "saved": "+0원",
            "borrowed": "-0원",
            "day_strip": [{"day": "14일", "value": "0원"}, ...],
        },
        "1.6 participating": {"count": 0, "cards": []},
        ...
    },
    "mock_data": {
        # 시나리오 active 일 때 표시할 mock. 와이어 0건이어도 이거 박힘
        "1.3 stage_progress": {
            "count": 3,
            "saved": "+1,240,000원",
            "borrowed": "-340,000원",
            "day_strip": [{"day": "14일", "value": "+24만", "status": "예정"}, ...],
        },
        "1.6 participating": {
            "count": 4,
            "cards": [
                {"status": "진행중", "amount": "월 10만원", "subtitle": "13개월 · 6.9%", "progress": 38, "round": "5회차 / 13"},
                ...
            ]
        },
        ...
    },
    "polish": {
        # polish baseline 적용 여부 (per-section)
        "top_alert_banner": True,
        "screen_hero": True,
        "day_strip_4layer": True,
        "subcard_cta": True,
        "recommend_hero_cta": True,
        "participation_grid": True,
        "lounge_real_products": True,
    },
    "sections": [
        # 섹션 순서. 각 entry 는 type + spec ref
        {"type": "nav_bar"},
        {"type": "mode_tabs", "tabs": ["거래 현황", "누적 거래"], "active": 0},
        {"type": "stage_progress_card", "data_ref": "1.3 stage_progress"},
        {"type": "attendance_banner", "data": {"streak": 7, "headline": "연속 7일째 출석 체크 중", ...}},
        {"type": "calc_callout"},
        {"type": "recommend_stage_card", "data": {...}},
        {"type": "participating_section", "data_ref": "1.6 participating"},
        {"type": "lounge_section", "data": {...}},
        {"type": "footer_policy"},
        {"type": "fab", "icon": "plus"},
        {"type": "tab_bar", "active": "홈"},
    ],
}
```

### 핵심 함수 인터페이스

```python
def _build_unified_blueprint(spec: dict) -> dict:
    """unified spec → blueprint dict.

    1. scenario 결정 (auto → wire_content 기반 판단)
    2. effective_data = scenario == "empty" ? wire_content : mock_data
    3. sections[] walk → 각 type 별 generator 함수 호출
    4. polish 플래그 별 polish 적용
    5. _wireframeContent (원본 와이어), _scenario, _mockApplied 메타 박음
    """
    ...

def _section_generator(section_type: str, data: dict, polish: dict) -> dict:
    """섹션 type 별 blueprint subtree 생성. polish 룰 함께 적용."""
    ...
```

### 기존 코드와의 호환

- 기존 cmd_build 흐름에서 spec 이 있으면 `_build_unified_blueprint(spec)` 으로 blueprint 생성
- 없으면 기존 polish/mock 함수 fallback
- 단계별 마이그레이션 — sections[] 의 type 하나씩 unified 로 옮김

## A.3 — Incremental 마이그레이션 plan

| Phase | 작업 | 검증 |
|------|------|------|
| A.3.1 | `_build_unified_blueprint` 기본 구조 + section_generator dispatch | 빈 spec → 빈 blueprint |
| A.3.2 | nav_bar / mode_tabs / footer / tab_bar / fab (template-driven) generator | 5 섹션 spec → 5 섹션 blueprint |
| A.3.3 | stage_progress_card generator (mock+wire 통합) | active spec → mock 박힌 카드 / empty spec → 0원 카드 |
| A.3.4 | participating_section generator (empty/grid swap 통합) | active → 4 grid / empty → empty state |
| A.3.5 | recommend_stage_card / attendance_banner / calc_callout / lounge_section | 각각 active/empty 시나리오 |
| A.3.6 | 기존 polish 함수들 → 새 generator 가 호출하는 helper 로 마이그레이션 | 같은 spec → 같은 output |
| A.3.7 | cmd_build 에서 unified mode 우선, fallback to legacy | 기존 빌드 회귀 0건 |

## A.4 — pytest 회귀 케이스

```python
# scripts/tests/test_unified_content_model.py

def test_empty_scenario_active_mock():
    spec = {...}  # empty wire + active mock
    bp = _build_unified_blueprint(spec)
    assert "3건" in _all_texts(bp)  # mock 적용
    assert "참여 중인 스테이지가 없습니다" not in _all_texts(bp)  # empty state swap

def test_active_scenario_no_polish_duplication():
    spec = {...}  # active 와이어 + hero 이미 있음
    bp = _build_unified_blueprint(spec)
    heroes = _find_all_currency_heroes(bp)
    assert len(heroes) == 1  # 중복 hero 없음

def test_participation_grid_swap():
    spec = {"scenario": "active", "mock_data": {"1.6 participating": {"count": 4, ...}}}
    bp = _build_unified_blueprint(spec)
    assert _find_node_by_name(bp, "Stage Card") is not None
    assert _find_node_by_name(bp, "Empty Card") is None
```

---

**다음 단계**: A.2 spec 형식을 사용자와 확정한 후 A.3.1 코드 박기 시작.
