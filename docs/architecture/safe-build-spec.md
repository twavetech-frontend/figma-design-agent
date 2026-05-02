# Safe Build Spec — batch_build_screen 안전 속성 사양

**문서 버전**: v1.0
**작성일**: 2026-04-22
**연결 기획**: [`redesign-plan.md`](redesign-plan.md) § 4.2 (S2)
**실험 로그**: `/tmp/s2_tests/` (run_experiments.py, run_letterspacing.py, run_text_styles.py)

---

## 0. 개요

이 문서는 **`batch_build_screen` 호출 시 안전하게 사용할 수 있는 속성 목록**과, 실패하는 속성의 **자동 우회 패턴**을 정의한다. `scripts/blueprint_sanitizer.py` 구현의 스펙이 되며, 새 레퍼런스 blueprint를 작성할 때 기준이 된다.

---

## 1. 실험 결론 요약

2026-04-22 실험에서 **25개 속성 조합 테스트** 수행 (baseline + 의심 속성 추가). 실패한 것은 **`letterSpacing` 객체/문자열 포맷 단 하나**.

### 1.1 이전 빌드 실패 (v2)의 진짜 원인
v2 blueprint에서 수십 개 텍스트 노드에 `letterSpacing: {value: -2, unit: "PERCENT"}`을 사용 → 모든 빌드가 구조 붕괴 (rootId 파싱 실패, 자식 노드가 루트 바깥으로 튀어나감).

**Figma Plugin API의 정식 LetterSpacing 타입은 `{value: number, unit: "PIXELS" | "PERCENT"}` 객체**지만, 현재 `batch_build_screen` 파서는 이 객체를 직렬화/파싱하지 못한다. **raw number**(예: `-0.02`)만 지원.

---

## 2. 안전 속성 Whitelist

### 2.1 Frame 속성
| 속성 | 타입 | 예시 | 비고 |
|------|------|------|------|
| `type` | string | `"frame"` | |
| `name` | string | `"NavBar"` | |
| `width` / `height` | number | `393`, `852` | |
| `fill` | `{r,g,b,a}` | `{r:1,g:1,b:1,a:1}` | 0~1 범위, alpha 0 허용 |
| `stroke` | `{r,g,b,a}` | | |
| `strokeWeight` | number | `1`, `2` | |
| `strokeTopWeight`, `strokeBottomWeight`, `strokeLeftWeight`, `strokeRightWeight` | number | | individual stroke OK |
| `strokeAlign` | `"OUTSIDE"` / `"INSIDE"` / `"CENTER"` | | OK (실험 확인) |
| `cornerRadius` | number | | |
| `opacity` | number 0~1 | `0.55` | |
| `autoLayout` | object | — | 아래 참조 |
| `layoutSizingHorizontal` | `"FILL"` / `"HUG"` / `"FIXED"` | | |
| `layoutSizingVertical` | 동일 | | |
| `layoutPositioning` | `"AUTO"` / `"ABSOLUTE"` | | |
| `x`, `y` | number (음수 허용) | `-2`, `100` | ABSOLUTE일 때만 의미 |
| `clipsContent` | boolean | | |
| `children` | array | | |

### 2.2 Auto Layout 속성 (`autoLayout` 객체 내부)
| 속성 | 타입 | 값 |
|------|------|-----|
| `layoutMode` | string | `"VERTICAL"` / `"HORIZONTAL"` / `"NONE"` |
| `primaryAxisAlignItems` | string | `"MIN"` / `"CENTER"` / `"MAX"` / `"SPACE_BETWEEN"` |
| `counterAxisAlignItems` | string | `"MIN"` / `"CENTER"` / `"MAX"` / `"BASELINE"` |
| `itemSpacing` | number | |
| `paddingTop`/`Bottom`/`Left`/`Right` | number | 개별 padding OK |

### 2.3 Text 속성
| 속성 | 타입 | 예시 | 비고 |
|------|------|------|------|
| `text` | string | `"모은 금액"` | |
| `fontSize` | number | `14` | |
| `fontName` | `{family, style}` | `{family: "Pretendard", style: "Bold"}` | ✅ OK |
| `fontFamily` | string | `"Pretendard"` | alternative to fontName |
| `fontWeight` | number | `100`~`900` | alternative |
| `fontColor` | `{r,g,b,a}` | | |
| `textAlignHorizontal` | `"LEFT"` / `"CENTER"` / `"RIGHT"` | | |
| `textAlignVertical` | `"TOP"` / `"CENTER"` / `"BOTTOM"` | | |
| `textAutoResize` | `"WIDTH_AND_HEIGHT"` / `"HEIGHT"` / `"TRUNCATE"` | | TRUNCATE 시 `maxLines` 필수 |
| `maxLines` | number | `2` | TRUNCATE와 함께 |
| `lineHeight` | object 또는 number | `{value: 150, unit: "PERCENT"}`, `{unit: "AUTO"}`, `1.5` | ✅ 모든 포맷 OK |
| `textDecoration` | `"NONE"` / `"UNDERLINE"` / `"STRIKETHROUGH"` | | ✅ OK |
| `letterSpacing` | **number only** ⚠️ | `-0.02` | ⚠️ **object 금지** |

### 2.4 Icon / Clone / Instance
| 타입 | 필수 속성 | 비고 |
|------|---------|------|
| `icon` | `iconName` (+ `size` or `width/height`), `iconColor` | DS whitelist 이름만 |
| `clone` | `sourceNodeId` | |
| `instance` | `component` + `variant` 또는 `componentKey` | |
| `ellipse` | `width`, `height`, `fill` | ✅ OK |
| `rectangle` | `width`, `height`, `fill`, `cornerRadius` | |

---

## 3. Blacklist (실패 속성)

### 3.1 `letterSpacing` 객체/문자열 포맷 ⚠️ CRITICAL
**증상**: rootId 파싱 실패 + 자식 노드가 루트 바깥으로 튀어나감 (구조 붕괴)

**실패 케이스**:
```json
"letterSpacing": {"value": -2, "unit": "PERCENT"}   ❌
"letterSpacing": {"value": 2, "unit": "PIXELS"}     ❌
"letterSpacing": {"value": 0, "unit": "PERCENT"}    ❌
"letterSpacing": "-2%"                              ❌
```

**우회 (이것만 사용)**:
```json
"letterSpacing": -0.02     ✅  // raw number (em-relative)
"letterSpacing": 1.5       ✅  // raw number (pixels)
// 또는 속성 생략
```

**sanitizer 변환 규칙**:
- `{value: N, unit: "PERCENT"}` → `N / 100` (예: -2% → -0.02)
- `{value: N, unit: "PIXELS"}` → 생략 (raw pixel은 의도 불명, 스킵이 안전)
- `"N%"` → `N / 100`
- raw number → 그대로 유지

---

## 4. 일반 안전 규칙

### 4.1 텍스트 노드 필수
- **`textAutoResize` 또는 명시 `width`가 반드시 있어야 함** — 없으면 width=0 fallback으로 별 아이콘이 렌더됨
- 부모 frame의 auto-layout 방향에 따라:
  - VERTICAL 부모 + 가로 공간 채워야 할 때 → `layoutSizingHorizontal: "FILL"`
  - VERTICAL 부모 + 내용 길이만큼 → `textAutoResize: "WIDTH_AND_HEIGHT"`
  - HORIZONTAL 부모 안 텍스트 → `textAutoResize: "WIDTH_AND_HEIGHT"` 권장

### 4.2 아이콘 노드 필수
- `iconName`은 **DS whitelist 내** 이름만 사용
- whitelist 소스: `ds/ds-1-icons.json`
- 미존재 이름(`flame`, `fire`, `check` 등) → `_fallback: true` 박스가 별 모양으로 렌더
- sanitizer가 유사 이름 자동 매핑 (예: `flame` → `fire-01`, `check` → `check-circle` 등)

### 4.3 구조 제약 (실험 확인)
- **Nest depth 5+ OK** — deep nesting 자체는 문제 없음
- **`layoutPositioning: "ABSOLUTE"` + 음수 x/y OK** — 배지 overlay 등 안전
- 단 ABSOLUTE 자식의 렌더링 위치는 부모의 relative 기준이므로 auto-layout 부모 내부에서 의도와 다를 수 있음 → wrapping frame 권장

### 4.4 색상 규칙
- `fill`, `stroke`, `fontColor`, `iconColor`는 모두 `{r, g, b, a}` 객체 (0~1 범위)
- hex 문자열(`"#fef3f2"`) 금지 — sanitizer가 자동 변환

---

## 5. Sanitizer 구현 스펙

### 5.1 함수 시그니처
```python
# scripts/blueprint_sanitizer.py

def sanitize_blueprint(blueprint: dict, *, strict: bool = False) -> tuple[dict, list[str]]:
    """
    Args:
        blueprint: 원본 Blueprint dict (in-place 변경 안 함)
        strict: True면 fix 가능한 이슈도 raise. False(기본)면 best-effort 수정.

    Returns:
        (sanitized_blueprint, warnings_list)
    """
```

### 5.2 수정 항목 (우선순위 순)
1. **letterSpacing 정규화**
   - `{value, unit: "PERCENT"}` → `value / 100`
   - `"-2%"` 같은 문자열 → 숫자로 파싱 후 /100
   - `{value, unit: "PIXELS"}` → 제거 (재현 불가 위험)

2. **텍스트 width 보정**
   - text 노드에 `textAutoResize`가 없고 부모가 HORIZONTAL auto-layout이면 `textAutoResize: "WIDTH_AND_HEIGHT"` 자동 삽입
   - text 노드에 `layoutSizingHorizontal`이 없고 부모가 VERTICAL이면 `layoutSizingHorizontal: "HUG"` 삽입 (단, text 너비가 부모 폭 이상일 가능성 있으면 FILL)

3. **hex 문자열 → RGBA 변환**
   - `fill: "#ffffff"` → `fill: {r:1, g:1, b:1, a:1}`
   - `stroke`, `fontColor`, `iconColor` 동일

4. **아이콘 이름 whitelist 검증**
   - `iconName`이 DS whitelist 밖 → 유사 이름 매핑 또는 fallback 대체
   - 매핑 테이블:
     ```python
     ICON_ALIASES = {
       "flame": "fire-01",
       "fire": "fire-01",
       "check": "check-circle",
       "warning": "alert-triangle",
       # ... 확장 예정
     }
     ```

5. **금지 속성 제거**
   - 이 문서 § 3 Blacklist에 추가되는 속성을 자동 삭제

### 5.3 경고 메시지 형식
```
WARN text node 'amount-earned': letterSpacing {value:-2, unit:"PERCENT"} converted to -0.02
WARN icon 'flame-bubble': iconName 'flame' → 'fire-01' (DS alias)
WARN text node 'unit-text': added textAutoResize='WIDTH_AND_HEIGHT' (missing width)
```

사용자가 확인할 수 있도록 경고 모두 로깅 후 빌드 계속. 치명적 에러만 raise.

---

## 6. batch_build_screen 통합

### 6.1 호출 체인
```
Blueprint (raw)
  → sanitize_blueprint(bp)         # scripts/blueprint_sanitizer.py
  → validate_blueprint(sanitized)  # 기존 함수 (figma_mcp_client.py)
  → batch_build_screen(sanitized)  # MCP tool
```

### 6.2 `src/main/figma-mcp-embedded.ts` 수정
`batch_build_screen` handler에서 호출 체인 위 순서대로 실행. Python sanitizer는 별도 subprocess로 돌리거나 TS로 포팅.

권장: **TS로 포팅** (`src/main/blueprint-sanitizer.ts` 신규). Node 런타임에서 즉시 실행 가능.

### 6.3 실패 시 리트라이
- batch_build_screen이 rootId 파싱 실패 반환 → 1회 재시도 (일시적 response 문제일 수도)
- 2회 실패 → 명확한 에러 리포트 (어느 섹션이 문제인지 binary search 제안)

---

## 7. 테스트 커버리지

### 7.1 sanitizer 단위 테스트 (필수)
- letterSpacing object → number 변환
- hex string → RGBA
- 아이콘 이름 매핑
- textAutoResize 자동 주입
- 금지 속성 제거

### 7.2 통합 테스트
- 의도적으로 오염된 blueprint (letterSpacing object + hex color + 잘못된 아이콘명) → sanitize 후 빌드 성공

---

## 8. 변경 이력

| 버전 | 날짜 | 변경 내용 |
|------|------|----------|
| v1.0 | 2026-04-22 | 초판 — letterSpacing 킬러 발견 + 25개 속성 whitelist 확정 |

---

## 부록 A. 실험 결과 로그

### A.1 속성별 테스트 (`run_experiments.py`)
12개 테스트 중 11개 PASS, 1개 FAIL (T11 letterSpacing object)

### A.2 letterSpacing 변형 (`run_letterspacing.py`)
8개 variant 중 2개 PASS (none, raw -0.02), 6개 FAIL (object/string 모두)

### A.3 Text 스타일 (`run_text_styles.py`)
13개 variant 전부 PASS — lineHeight object, textDecoration, fontName object, textAutoResize 등 모두 안전

### A.4 Yoga Simulation 관찰
Yoga pre-simulation은 letterSpacing object를 **문제 없이 통과**. 즉 시뮬레이션이 실제 빌드 실패를 감지 못함 → simulation만 신뢰하면 안 됨.

**시사점**: validate_blueprint의 "pre-flight check"가 현재는 부실. sanitizer가 실질적 방어선.
