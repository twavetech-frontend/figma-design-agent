# Reference-as-Template 재구성 기획서

**문서 버전**: v1.0
**작성일**: 2026-04-21
**상태**: Draft — 승인 대기
**범위**: figma-design-agent 전체 시스템 재설계

---

## 0. 핵심 요약 (TL;DR)

비디자이너가 PRD만 첨부하면 Figma 디자인이 자동 생성되는 배포용 시스템. 현재는 Agent(Claude)가 Blueprint를 **창작**하는 방식인데, 이 때문에 결과물이 **비결정적이고 레퍼런스와 전혀 다른 엉망**으로 나온다. 이 기획서는 **Agent의 창작 여지를 제거하고 "레퍼런스 복제 + 슬롯 치환"의 결정적 파이프라인**으로 전환하는 5단계 로드맵을 제시한다.

**핵심 전환**: `레퍼런스 = 참고 자료` → `레퍼런스 = 검증된 Blueprint JSON 그 자체`

---

## 1. 배경 & 문제 진단

### 1.1 프로젝트 목표
- **End-user**: 비디자이너 (PM, 기획자, 개발자)
- **입력**: PRD 문서 하나
- **출력**: 레퍼런스 수준의 Figma 디자인
- **운영**: Electron 앱으로 배포 → end-user가 다른 개입 없이 사용

### 1.2 현재 시스템 구조
```
PRD → Electron IPC → Agent Orchestrator(Claude Sonnet 4) → MCP Tools → Figma Plugin → Figma
                              ↑
                              시스템 프롬프트 (ds/*.md + 최근 추가된 docs/references/*)
```

### 1.3 2026-04-21 테스트에서 확인된 실패 패턴

| # | 증상 | 원인 | 영향 |
|---|------|------|------|
| F1 | Agent가 레퍼런스를 무시하고 자유 창작 | 시스템 프롬프트가 레퍼런스를 필수로 강제 안 함 | 결과물이 레퍼런스와 완전히 다른 톤 |
| F2 | 다크 DS 토큰이 라이트 레퍼런스 컬러를 오염 | 테마 일관성 검증이 시스템에 없음 | 다크 배경 + 검정 아이콘 = 가독성 붕괴 |
| F3 | 잘못된 템플릿 선택 (SummaryCardLinkRows → 홈 화면) | 템플릿에 "출신 레퍼런스" 메타 없음 | 구조 자체가 틀림 |
| F4 | DS에 없는 아이콘 이름 (flame, check) | whitelist 사전 검증 없음 | `_fallback:true` 별모양 박스로 대체 |
| F5 | 텍스트 노드 `width=0` → 별 아이콘 fallback | `textAutoResize`/`layoutSizingHorizontal` 누락 감지 없음 | 핵심 숫자(360) 사라짐 |
| F6 | batch_build_screen이 복잡 속성에서 파싱 실패 | `strokeAlign:OUTSIDE`, `layoutPositioning:ABSOLUTE+x/y`, `ellipse`, individual stroke weight 등 | 자식 노드가 루트 바깥으로 튀어나감 (구조 붕괴) |
| F7 | post-fix가 rootId 파싱 실패로 건너뛰어짐 | 빌드 응답 형식 비결정성 | 자동 수정 메커니즘 무력화 |
| F8 | "대부분 성공" 자기 평가로 엉망 결과가 통과 | Post-build QA에 레퍼런스 대비 비교 없음 | 비디자이너가 엉망 결과물을 받음 |

### 1.4 근본 원인 (3가지 구조적 결함)

1. **추상화 손실**: 레퍼런스가 JSX → 템플릿 → VS 규칙으로 추상화되며 비주얼 정보 손실. Agent는 추상화된 버전만 보고 창작 → 원본과 괴리.
2. **Agent의 창작 여지**: Agent가 Blueprint 구조·컬러·사이즈를 매번 재판단 → 비결정적. 같은 PRD → 다른 결과.
3. **파이프라인 fragility**: batch_build_screen의 속성 파싱이 fragile. 복잡 속성 조합에서 구조 붕괴. 시뮬레이션은 통과하나 실제 빌드 실패.

---

## 2. 목표 및 성공 지표

### 2.1 목표
- **결정성**: 같은 PRD + 같은 레퍼런스 → **항상 동일 결과물**
- **충실도**: 결과물이 매칭된 레퍼런스와 **시각적으로 80%+ 일치**
- **자동화**: 비디자이너의 추가 개입 0 — PRD 첨부만으로 완결
- **견고성**: 빌드 실패 확률 < 5%, 실패 시 명확한 원인 리포트

### 2.2 측정 가능 성공 지표
| 지표 | 현재 | 목표 |
|------|------|------|
| 빌드 성공률 | ~60% (구조 붕괴, 파싱 실패 포함) | ≥ 95% |
| 레퍼런스 시각 유사도 (LLM 판단) | ~30% | ≥ 80% |
| 동일 PRD 반복 시 결과 편차 | 매번 크게 다름 | 픽셀 단위 동일 |
| `_fallback:true` 노드 개수 | 빌드당 평균 8~12개 | 0개 |
| 비디자이너 수정 개입 필요도 | 거의 필수 | 0 |

---

## 3. 아키텍처 개요

### 3.1 현재 (Creation 모델)
```
PRD ──► Agent(Claude) ──► Blueprint를 창작 ──► batch_build_screen ──► Figma
                           ↑ fragile                ↑ fragile
                           추상 규칙 기반            복잡 속성 실패
```
- Agent가 "어떤 컬러, 어떤 구조, 어떤 템플릿"을 매번 재판단
- 실패 지점: Agent 판단 오류 + 빌드 파이프라인 버그

### 3.2 제안 (Clone & Bind 모델)
```
PRD ──► Reference Matcher(code) ──► Reference blueprint.json 복제 ──► Content Binder(Agent) ──► Safe Build ──► Figma
                ↑                         ↑ 검증된 정답              ↑ 슬롯에 PRD 값만       ↑ 문제 속성
                결정적 분류                불변                       치환                     자동 우회
```
- Agent는 **값 매핑**만 담당 (PRD의 "모은 금액" → 레퍼런스 slot "earned.value")
- 구조/컬러/레이아웃은 사전 검증된 JSON에서 **불변 복제**
- 실패 지점: 슬롯 매핑 오류 정도 (단순)

### 3.3 데이터 흐름 다이어그램

```
┌───────────────────────────────────────────────────────────────┐
│                    Reference Package                          │
│  docs/references/imin-home/                                   │
│   ├─ screenshot.png    (비주얼 기준 — QA용)                    │
│   ├─ sections-*.jsx    (구현 참고 — 사람용)                    │
│   ├─ blueprint.json    (★ 검증된 Figma Blueprint — 시스템용)   │
│   ├─ slots.json        (★ 치환 가능한 slot 메타)               │
│   └─ meta.json         (★ 매칭 키: 화면 유형, 테마, 브랜드)     │
└───────────────────────────────────────────────────────────────┘
                              ↓
┌───────────────────────────────────────────────────────────────┐
│                       Runtime Pipeline                        │
│                                                               │
│  [1] PRD Parse (code)                                         │
│      → { screenType: "home", brand: "imin",                   │
│           contentValues: { earned: "...", owed: "..." } }     │
│                                                               │
│  [2] Reference Matcher (code)                                 │
│      → match prd.screenType ↔ meta.json                       │
│      → return referencePackage                                │
│                                                               │
│  [★] Coverage Gate (code, STRICT)                             │
│      → parse PRD sections (#### 섹션 N — 제목)                  │
│      → parse blueprint root children names                    │
│      → fuzzy match via SECTION_SYNONYMS + keyword overlap     │
│      → if coverage < 85%: throw Error → pipeline 중단         │
│                                                               │
│  [3] Content Binder (Agent — 제약된 역할)                     │
│      → map PRD fields → slots.json slots                      │
│      → apply replacements to blueprint.json                   │
│      → return finalBlueprint                                  │
│                                                               │
│  [4] Safe Build (code)                                        │
│      → sanitize blueprint (unsupported attrs stripped)        │
│      → batch_build_screen                                     │
│      → retry logic on failure                                 │
│                                                               │
│  [5] Visual QA (Agent + reference screenshot)                 │
│      → export result screenshot                               │
│      → LLM diff vs reference.png                              │
│      → if similarity < 80% → correction loop (max 2x)         │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

---

## 4. 단계별 상세 설계

### S1. Reference-as-Template (최우선, 모든 단계의 전제)

#### 4.1.1 목적
각 레퍼런스를 **"참고 자료"에서 "실행 가능한 정답 JSON"으로 승격**. 추상 해석이 아닌 **직접 복제** 가능하게 만듦.

#### 4.1.2 산출물 구조
기존 레퍼런스 폴더에 3개 파일 추가:

```
docs/references/imin-home/
├─ screenshot.png          (기존 유지)
├─ sections-1.jsx          (기존 유지)
├─ sections-2.jsx          (기존 유지)
├─ template.html           (기존 유지)
├─ blueprint.json          ← 신규: 검증된 Figma Blueprint
├─ slots.json              ← 신규: 치환 slot 메타
└─ meta.json               ← 신규: 매칭 키
```

#### 4.1.3 blueprint.json 스키마
```jsonc
{
  "_meta": {
    "referenceId": "imin-home",
    "theme": "light",
    "validatedOn": "2026-04-21",
    "validationNote": "Figma page 'GUI' node 43:XXX에서 빌드 성공 확인"
  },
  "rootName": "imin Home",
  "type": "frame",
  "width": 393,
  "height": 1800,
  "fill": { "r": 0.98, "g": 0.98, "b": 0.98, "a": 1 },
  "autoLayout": { "layoutMode": "VERTICAL", ... },
  "children": [
    // ... 실제 Figma 빌드 가능한 전체 구조 ...
    // 텍스트 노드에 PRD 고유 값은 그대로 두되 slot path로 표시 가능
  ]
}
```

#### 4.1.4 slots.json 스키마
치환 가능한 지점을 **JSON path 기반**으로 정의. Agent가 이 slot 이름만 채워넣으면 됨.

```jsonc
{
  "slots": [
    {
      "id": "summary.title",
      "path": "$.children[3].children[0].children[0].children[1].text",
      "type": "text",
      "default": "내 스테이지",
      "hint": "요약 카드 상단 타이틀"
    },
    {
      "id": "summary.earned.amount",
      "path": "$.children[3].children[0].children[1].children[0].children[1].text",
      "type": "text",
      "default": "14,420,320",
      "hint": "모은 금액 숫자 (쉼표 포함, 원 단위)",
      "format": "number_krw"
    },
    {
      "id": "summary.earned.label",
      "path": "$.children[3].children[0].children[1].children[0].children[0].children[1].text",
      "type": "text",
      "default": "모은 금액",
      "hint": "모은 금액 레이블"
    },
    // ... 나머지 슬롯
  ]
}
```

**slot path 규칙**:
- **JSONPath 문법** (`$.children[i].children[j]...`) — jsonpath-plus 라이브러리로 resolve
- **type**: `text | fill | icon | repeat`
- **repeat slot**: 반복 가능 요소 (예: day cards 5개, 스테이지 카드 N개) — template 서브트리 + count 지정

#### 4.1.5 meta.json 스키마
Reference Matcher가 PRD와 매칭할 때 사용.

```jsonc
{
  "referenceId": "imin-home",
  "screenType": ["home", "main", "tab-home"],
  "brand": "imin",
  "theme": "light",
  "features": ["summary-card", "schedule", "progress", "attendance", "bottom-nav"],
  "tabVariants": ["거래 현황", "내 스테이지"],
  "keywords": ["홈", "거래 현황", "스테이지", "미납", "납입", "지급"],
  "matchingHints": {
    "positiveSignals": ["홈 화면", "메인", "거래 현황"],
    "negativeSignals": ["상세", "모달", "바텀시트", "참여자"]
  }
}
```

#### 4.1.6 작업 목록 (S1)
각 4개 레퍼런스에 대해:
1. 기존 sections-*.jsx 코드를 기반으로 **단순화된 blueprint.json 초안** 작성 — S2 Safe Build 사양 준수 (아직 없으면 임시 최소 속성만)
2. batch_build_screen으로 **실제 Figma 빌드 테스트** → 성공 확인
3. 빌드된 노드 tree의 path를 참고하여 **slot path 추출**
4. **meta.json** 작성 (매칭 키)
5. 전체를 `docs/references/{id}/`에 커밋

#### 4.1.7 검증 기준
- [ ] 각 reference의 `blueprint.json`이 validate_blueprint 통과
- [ ] `batch_build_screen` 실행 → 루트 노드 ID 반환 + 모든 섹션이 루트 안에 포함 (바깥으로 튀어나가지 않음)
- [ ] 빌드 결과 스크린샷이 원본 screenshot.png와 시각적 유사 (LLM 판단 80%+)
- [ ] slots.json의 path가 실제 blueprint 구조와 일치 (automated path resolver test)

#### 4.1.8 리스크 및 대응
| 리스크 | 대응 |
|--------|------|
| 레퍼런스의 복잡 구조(히어로 캐로셀 등)가 slot path로 표현 불가 | path 기반 + sub-blueprint 조합. 복잡 섹션은 "이 섹션 전체를 교체" 단위 slot 허용 |
| 레퍼런스마다 slot 개수가 상이 → binding 로직 복잡 | 우선 imin-home 1개에 집중. 검증 후 다른 레퍼런스 확장 |
| jsonpath-plus로 mutable update가 난감 | immer + lodash set 조합 (path 문자열 parse 후 nested set) |

---

### S2. Safe Build Pipeline

#### 4.2.1 목적
batch_build_screen의 **속성 파싱 실패**로 인한 구조 붕괴 차단. 어떤 속성이 실패하는지 실증하고 자동 우회.

#### 4.2.2 진단 작업 (먼저 해야 할 실험)
**실험 1: 속성별 실패 테스트**
각 의심 속성을 개별적으로 빌드에 포함시켜 success/fail 판정:

| 속성 | 테스트 방법 | 우회 방법 |
|------|------------|---------|
| `strokeTopWeight`/`strokeBottomWeight` 등 individual stroke | 단일 frame에 적용 후 빌드 | 불가 시 전체 strokeWeight + 내부에 divider frame |
| `strokeAlign: "OUTSIDE"` | stroke 있는 frame에 적용 | 불가 시 부모 frame에 wrapping + padding |
| `layoutPositioning: "ABSOLUTE"` + `x`, `y` | frame에 적용 | 불가 시 wrapping frame + relative positioning |
| `type: "ellipse"` | 순수 ellipse 노드 | 불가 시 `rectangle` + `cornerRadius: 999` |
| `opacity: 0.55` | frame에 적용 | 불가 시 fill alpha 조정 |
| `textAutoResize: "WIDTH_AND_HEIGHT"` | text 노드에 적용 | 불가 시 명시 width |

**실험 2: 복잡도 한계 테스트**
- nest depth 2/3/4/5/6 trees로 빌드 → 어느 depth에서 실패하는지
- 한 화면 내 총 노드 수 50/100/200/500 → 한계 확인
- 비동기 텍스트 폰트 로딩 실패 여부

#### 4.2.3 산출물
**`docs/architecture/safe-build-spec.md`**:
- 지원 속성 whitelist
- 금지 속성 리스트 + 각 대체 패턴
- 복잡도 한계 (max nodes, max depth)
- 빌드 전 sanitize 함수 스펙

**`scripts/blueprint_sanitizer.py`**:
blueprint JSON을 받아 금지 속성을 **자동 대체**하는 함수. binder 실행 후 빌드 전 호출.

```python
def sanitize_blueprint(blueprint: dict) -> dict:
    """Return a batch_build_screen-safe blueprint.
    Replaces unsupported attrs with equivalent fallback patterns.
    """
    # 1. ellipse → rectangle + cornerRadius 999
    # 2. strokeAlign OUTSIDE → outer wrapper frame
    # 3. ABSOLUTE+x/y → MIN+itemSpacing approximation or strip
    # 4. individual strokeTop/Bottom/Left/Right → top level strokeWeight + divider
    # 5. text nodes missing width → add textAutoResize: WIDTH_AND_HEIGHT
    # 6. icon whitelist check → replace unknown with closest valid name
    return sanitized
```

#### 4.2.4 `src/main/figma-mcp-embedded.ts` 수정
`batch_build_screen` 도구의 handler를 수정:
```typescript
async function batch_build_screen(args: ...) {
  // 1. Pre-validation (reject blueprint with banned attrs + clear error)
  const preflight = validateBlueprint(args.blueprint);
  if (preflight.errors.length > 0) {
    return { error: `Blueprint validation failed: ${preflight.errors.join('\n')}` };
  }

  // 2. Auto-sanitize
  const sanitized = sanitizeBlueprint(args.blueprint);

  // 3. Build (with retry on rootId parse failure)
  const maxRetries = 2;
  for (let i = 0; i < maxRetries; i++) {
    const result = await plugin.buildScreen(sanitized);
    if (result.rootId) return result;
    // retry with smaller chunks if response parse failed
  }
  return { error: 'Build failed after retries' };
}
```

#### 4.2.5 검증 기준
- [ ] 금지 속성이 포함된 blueprint가 sanitizer 후 전부 빌드 성공
- [ ] imin-home의 `blueprint.json`을 sanitize 없이도 빌드 성공 (즉 sanitize는 방어 수단일 뿐 blueprint 작성 시 자주 쓰는 속성은 처음부터 안전해야 함)
- [ ] Build 실패율 < 5% (10회 반복 빌드 중 9회 이상 성공)
- [ ] rootId 파싱 실패 시 자동 재시도 후 성공 또는 명확한 에러

#### 4.2.6 리스크 및 대응
| 리스크 | 대응 |
|--------|------|
| 실험으로 실패 속성 원인이 밝혀져도 우회 불가 (디자인 품질 타협) | 품질 타협이 불가피하면 Figma Plugin JS 소스 수정 (src/claude_mcp_plugin/code.js) |
| sanitizer가 원본 의도를 훼손 | sanitizer 적용 시 "warn" 로깅 → 기획자가 확인 후 blueprint 수정 |
| 복잡도 한계가 작아 대형 화면 실패 | 화면을 섹션 단위로 쪼개 순차 빌드 (parentId 사용) |

---

### S3. Reference Matcher (결정적 매칭)

#### 4.3.1 목적
**Agent가 아닌 코드**로 PRD ↔ 레퍼런스 매칭. 매번 같은 PRD → 같은 레퍼런스.

#### 4.3.2 구현 파일
**`src/main/reference-matcher.ts`** (신규)

```typescript
export interface MatchResult {
  referenceId: string;
  confidence: number;   // 0~1
  reasons: string[];    // 매칭 근거 (디버깅/로그용)
  fallbackUsed: boolean;
}

export async function matchReference(
  prd: ParsedPRD,
  projectRoot: string
): Promise<MatchResult> {
  // 1. 모든 레퍼런스의 meta.json 로드
  const refs = await loadAllReferenceMetas(projectRoot);

  // 2. PRD 특징 추출 (screen type, keywords, brand, etc.)
  const prdFeatures = extractPRDFeatures(prd);

  // 3. 각 레퍼런스와 점수 계산
  const scores = refs.map(ref => ({
    ref,
    score: calculateMatchScore(prdFeatures, ref.meta),
    reasons: explainMatch(prdFeatures, ref.meta)
  }));

  // 4. 최고 점수 선택, confidence 너무 낮으면 fallback 플래그
  const best = scores.sort((a, b) => b.score - a.score)[0];
  return {
    referenceId: best.ref.id,
    confidence: best.score,
    reasons: best.reasons,
    fallbackUsed: best.score < 0.6
  };
}
```

#### 4.3.3 매칭 알고리즘 (단순 규칙 기반, LLM 미사용)

**점수 계산**:
```typescript
function calculateMatchScore(prd: PRDFeatures, meta: ReferenceMeta): number {
  let score = 0;

  // 1. 화면 유형 정확 매칭 (가중치 0.5)
  if (meta.screenType.includes(prd.screenType)) score += 0.5;

  // 2. 브랜드 일치 (가중치 0.2)
  if (meta.brand === prd.brand) score += 0.2;

  // 3. 키워드 overlap (가중치 0.2)
  const keywordOverlap = overlap(prd.keywords, meta.keywords);
  score += 0.2 * (keywordOverlap.length / Math.max(prd.keywords.length, 1));

  // 4. positive signals (가중치 0.1)
  const positiveHits = meta.matchingHints.positiveSignals.filter(s =>
    prd.rawText.toLowerCase().includes(s.toLowerCase())
  ).length;
  score += 0.1 * Math.min(1, positiveHits / 2);

  // 5. negative signals 감산 (가중치 -0.3)
  const negativeHits = meta.matchingHints.negativeSignals.filter(s =>
    prd.rawText.toLowerCase().includes(s.toLowerCase())
  ).length;
  score -= 0.3 * Math.min(1, negativeHits / 2);

  return Math.max(0, Math.min(1, score));
}
```

**PRD 특징 추출** (`extractPRDFeatures`):
- 화면 유형: 제목/첫 섹션에서 "홈", "상세", "모달", "리스트" 등 키워드
- 브랜드: "aim" / "imin" / "Toss" 등 빈도 높은 고유명사
- 키워드: 문서 내 명사형 단어 중 빈도 상위 20

#### 4.3.4 Confidence 기반 분기
```typescript
if (match.confidence >= 0.8) {
  // 자동 진행
} else if (match.confidence >= 0.5) {
  // 사용자 확인 요청 (UI에 "imin-home 레퍼런스로 진행할까요?" diaog)
} else {
  // 명확한 에러: "PRD와 일치하는 레퍼런스가 없습니다. 레퍼런스 추가가 필요합니다."
}
```

#### 4.3.5 검증 기준
- [ ] imin-home PRD → imin-home 매칭 (confidence ≥ 0.85)
- [ ] 스테이지 탭 PRD → imin-stage-tab 매칭 (confidence ≥ 0.85)
- [ ] 알 수 없는 PRD → confidence < 0.5, UI에 적절한 에러

#### 4.3.6 리스크 및 대응
| 리스크 | 대응 |
|--------|------|
| 단순 키워드 매칭이 애매한 케이스 오분류 | 1차는 단순 규칙. 2차(필요 시)에만 LLM 보정 (optional Agent fallback) |
| 레퍼런스 confidence가 아슬아슬한 경우 사용자 confusion | UI에 매칭 이유 표시 (`reasons` 필드) |

---

### S4. Content Binder (슬롯 치환)

#### 4.4.1 목적
Agent의 역할을 **Blueprint 창작에서 "slot-to-PRD 값 매핑"으로 축소**. 창작 여지 차단.

#### 4.4.2 Agent 프롬프트 (S4용 micro-prompt)
Agent가 S4 단계에서 받는 입력:
```
[주어진 정보]
- 선택된 레퍼런스: imin-home
- 슬롯 정의 (slots.json): [ { id: "summary.earned.amount", default: "14,420,320", ... } ]
- PRD 내용 (요약): {...}

[Agent의 할 일 — 이것만]
1. 각 slot id가 PRD의 어떤 값에 대응되는지 JSON 객체로 응답:
   { "summary.earned.amount": "15,000,000", "summary.owed.amount": "4,200,000", ... }

2. PRD에 대응값 없으면 slot의 default 유지 (slot을 응답에서 누락하면 default)

3. PRD에만 있고 레퍼런스에 없는 정보는 무시 (레퍼런스가 정답)

[절대 금지]
- Blueprint 구조 변경
- 새 slot 생성
- 컬러/사이즈/레이아웃 변경
- "이 화면을 개선하면..." 같은 의견 제시
```

**프롬프트 토큰**: ~1K (레퍼런스/VS/템플릿 등 제외). 현재 시스템 프롬프트 대비 대폭 축소.

#### 4.4.3 구현 파일
**`src/main/content-binder.ts`** (신규)

```typescript
import { set as lodashSet, cloneDeep } from 'lodash';

export async function bindContent(
  referencePackage: ReferencePackage,
  prd: ParsedPRD,
  agentClient: AgentClient
): Promise<Blueprint> {
  // 1. Agent에게 slot ↔ PRD 매핑 요청 (제약된 프롬프트)
  const mapping: Record<string, string> = await agentClient.call({
    systemPrompt: BIND_SYSTEM_PROMPT,
    userPrompt: buildBindPrompt(referencePackage.slots, prd),
    responseFormat: 'json_object',
  });

  // 2. Blueprint 복제 (immutable)
  const blueprint = cloneDeep(referencePackage.blueprint);

  // 3. 각 slot의 path에 매핑된 값 치환
  for (const slot of referencePackage.slots.slots) {
    const value = mapping[slot.id] ?? slot.default;
    const transformedValue = applyFormat(value, slot.format);
    lodashSet(blueprint, pathToLodashPath(slot.path), transformedValue);
  }

  return blueprint;
}

function pathToLodashPath(jsonpath: string): string {
  // "$.children[3].children[0].text" → "children[3].children[0].text"
  return jsonpath.replace(/^\$\./, '');
}

function applyFormat(value: string, format?: string): string {
  if (format === 'number_krw') return formatKRW(Number(value));
  return value;
}
```

#### 4.4.4 에러 처리
- Agent가 잘못된 slot id 응답 → 해당 slot은 default
- Agent가 응답 자체 실패 → 모든 slot default → fully reference-faithful build (값만 default지만 구조는 정확)
- PRD에 예상치 못한 필드 → 무시 + 로그

#### 4.4.5 검증 기준
- [ ] imin-home PRD → blueprint의 텍스트 값들이 PRD 값으로 교체됨 (구조는 그대로)
- [ ] Agent가 빈 응답을 보내도 default로 빌드 성공
- [ ] 같은 PRD + 같은 reference → **Blueprint 결과 bit단위 동일** (cloneDeep + 결정적 path resolve)

---

### S5. Visual QA with Reference

#### 4.5.1 목적
빌드 후 결과 스크린샷과 레퍼런스 스크린샷을 **나란히 비교**하여 충실도 검증 + 자동 교정.

#### 4.5.2 구현 파일
**`src/main/visual-qa.ts`** (신규)

```typescript
export interface VisualQAResult {
  similarity: number;           // 0~1
  issues: string[];             // "레퍼런스에선 Summary가 2-col인데 결과는 1-col" 등
  diffRegions: DiffRegion[];    // 픽셀 diff 영역
  needsCorrection: boolean;     // similarity < threshold
}

export async function runVisualQA(
  builtRootId: string,
  referenceScreenshot: Buffer,
  agentClient: AgentClient
): Promise<VisualQAResult> {
  // 1. 결과 스크린샷 export
  const resultScreenshot = await exportNodeAsImage(builtRootId);

  // 2. LLM에게 레퍼런스와 결과를 나란히 제시
  const response = await agentClient.call({
    systemPrompt: QA_SYSTEM_PROMPT,
    userContent: [
      { type: 'image', source: referenceScreenshot, caption: '기준 레퍼런스' },
      { type: 'image', source: resultScreenshot, caption: '생성된 결과' },
      { type: 'text', text: QA_PROMPT }
    ],
    responseFormat: 'json_object',
  });

  return response as VisualQAResult;
}
```

#### 4.5.3 QA 프롬프트
```
[주어진 정보]
- 레퍼런스 이미지 (기준): 첨부1
- 생성된 결과 이미지: 첨부2

[검증 항목]
1. 섹션 개수 및 순서 일치?
2. 각 섹션의 레이아웃(grid, flex) 일치?
3. 컬러 톤(라이트/다크 모드) 일치?
4. 카드 구조(border, radius, padding) 일치?
5. 텍스트 위계(크기, weight) 일치?
6. 아이콘/이미지 영역 렌더링 정상?
7. fallback 박스(★ 등) 있음?

[응답 형식 — JSON]
{
  "similarity": 0.0 ~ 1.0,
  "issues": ["string", ...],  // 불일치 항목 구체적으로
  "diffRegions": [{ "section": "summary", "severity": "high" }],
  "needsCorrection": true/false
}
```

#### 4.5.4 교정 루프
- similarity < 0.8 → S4 Content Binder 재실행 (slots 매핑 교정 제안)
- Agent에게 QA issues를 전달 → slot 재매핑 시도
- 최대 2회 루프 후 사용자에게 결과 리포트 + 명확한 원인

#### 4.5.5 검증 기준
- [ ] imin-home 빌드 결과가 원본 screenshot.png 대비 similarity ≥ 0.8
- [ ] fallback 박스 감지 시 즉시 이슈 리포트
- [ ] 섹션 누락 감지 (레퍼런스 대비 적은 섹션)

---

### S6. Coverage Gate (PRD ↔ Blueprint 누락 자동 감지)

#### 4.6.1 배경 — 왜 필요한가
초판 기획서(§ 4)에는 S1~S5 5개 레이어만 있었음. 그러나 2026-04-22 테스트에서 **시스템이 PRD의 누락 섹션을 감지 못하는 문제**가 발견됨:

- **증상**: PRD는 13개 섹션을 요구하지만 레퍼런스 blueprint에 7개 섹션만 있는데도 파이프라인이 정상 진행. 결과물에 6개 섹션이 누락된 상태로 완료 보고됨.
- **사용자 피드백 (2026-04-22)**:
  > "내가 없는 걸 또 찾아내서 너한테 추가해달라고 하는 건 시스템이 실패한 거야."
- **근본 원인**: S3(Matcher)는 "이 레퍼런스로 갈지" 결정할 뿐 "이 레퍼런스가 PRD를 충분히 커버하는지"는 검증 안 함. S4(Binder)는 무조건 실행.

**S6는 비디자이너가 놓친 빈틈을 시스템이 스스로 감지하는 강제 gate**이다.

#### 4.6.2 구현 파일
**`src/main/coverage-checker.ts`** (신규, 187 LOC, LLM 불필요)

```typescript
export function enforceCoverageGate(
  prdText: string,
  blueprint: Record<string, unknown>,
  options: { minPass?: number } = {}
): CoverageResult {
  const result = checkCoverage(prdText, blueprint, options);
  if (result.gateDecision === 'block') {
    throw new Error(`🚫 Coverage Gate: ${missing}개 섹션 누락 ...`);
  }
  return result;
}
```

#### 4.6.3 동작 원리
1. **PRD 섹션 추출** — markdown heading 정규식 (`#### 섹션 N — 제목`)으로 PRD에서 요구 섹션 목록 파싱.
2. **Blueprint 섹션 추출** — blueprint 루트의 직계 children 이름을 정규화 (Wrap/Section/Card suffix 제거, Spacer/Divider 제외).
3. **Fuzzy Match** — `SECTION_SYNONYMS` 매핑 (예: "글로벌 헤더" ↔ "NavBar", "추천 스테이지" ↔ "Recommendation") + 키워드 overlap.
4. **커버리지 계산** — `matched / prdSections.length`. 85% 미만이면 `'block'` 결정.
5. **Gate 강제** — `block` 시 Error throw → 파이프라인 즉시 중단, 누락 섹션 리스트 + 3가지 해결책 제시.

#### 4.6.4 파이프라인 통합 지점
**`src/main/content-binder.ts`의 `bindReferenceToPRD` 단일 진입점**:

```typescript
export async function bindReferenceToPRD(pkg, prdText, agentCall, options) {
  // 1. Coverage Gate (강제) — 미달 시 throw
  const coverage = enforceCoverageGate(prdText, pkg.blueprint, {
    minPass: options.coverageMinPass,
  });
  // 2. Content Binding
  const bind = await bindContent(pkg, prdText, agentCall);
  return { coverage, ...bind };
}
```

이 진입점을 **반드시 `bindContent` 직접 호출 대신 사용**. 상위 파이프라인(HTTP API, CLI)은 이 함수 하나만 호출하면 S6→S4가 강제 순서로 실행됨.

#### 4.6.5 검증 결과 (2026-04-22)
- **실전 테스트 1**: imin-home PRD vs. 원본 blueprint(7 섹션) → **25% coverage → BLOCK** ✅ 시스템이 자동 감지.
- **자동 복구 유도**: 사용자가 blueprint를 15 섹션으로 확장 → **88% coverage → PASS** ✅.
- **무관한 PRD 테스트**: 가상화폐 거래소 PRD (8 섹션) → imin-home blueprint → **0% coverage → BLOCK** ✅ 명확한 에러 메시지.

#### 4.6.6 정책 — 미달 시 사용자 액션
Gate가 block을 throw하면 시스템은 아래 3가지 선택지를 제시:
```
Action: either (a) extend the reference blueprint.json to include missing sections,
               (b) update PRD scope to exclude these sections, or
               (c) register a new reference that covers the PRD fully.
```
비디자이너는 (b)/(c)를 선택할 가능성이 높음. 디자이너는 (a)로 레퍼런스 컬렉션을 점진적으로 확장.

#### 4.6.7 검증 기준
- [x] PRD에 없는 섹션을 blueprint에 추가해도 false positive 없음 (extra는 정보용)
- [x] PRD에 있는 섹션이 blueprint에 없으면 항상 감지
- [x] gate 실행 비용 < 50ms (LLM 불필요, 정규식만)
- [x] `bindReferenceToPRD`로 호출 시 gate 강제 실행

---

## 5. 마이그레이션 전략

### 5.1 현재 자산 처리

| 현재 자산 | 처리 |
|----------|------|
| `docs/references/INDEX.md` | 유지 (S1의 meta.json 요약 역할로 축소) |
| `docs/references/{id}/sections-*.jsx` | 유지 (사람용 참고) |
| `docs/references/{id}/screenshot*.png` | 유지 (S5 QA 기준) |
| `docs/design-rules.md` VS1~VS30 | **사용 중단** (추상 규칙이 S1 blueprint로 대체됨). 단, 향후 신규 레퍼런스 등록 시 패턴 참고용으로만 |
| `scripts/blueprint_templates.json` | **사용 중단** (레퍼런스별 blueprint.json이 대체). 범용 템플릿은 새 레퍼런스 작성 시 initial draft로만 |
| 시스템 프롬프트 (`src/main/system-prompt-builder.ts`) | 대폭 축소. S4 BIND_SYSTEM_PROMPT + S5 QA_SYSTEM_PROMPT만 유지 |
| `scripts/figma_mcp_client.py` (validate_blueprint, sanitize) | 유지 + S2 확장 |

### 5.2 단계적 배포 (Feature Flag)
```typescript
// src/main/pipeline-orchestrator.ts
if (settings.useCloneAndBindPipeline) {  // default false
  await runCloneAndBindPipeline(prd);
} else {
  await runLegacyCreationPipeline(prd);  // 기존 방식
}
```
- S1+S2+S3 구현 후 `useCloneAndBindPipeline: false` 유지하며 개발
- `--use-clone-and-bind` CLI 플래그로 테스트
- 신뢰도 검증 후 default로 전환

### 5.3 후퇴 옵션
새 파이프라인이 실패 시 자동으로 legacy로 fallback (confidence-based). 배포 중 안전.

---

## 6. 일정 및 마일스톤

### 6.1 권장 순서
**Phase A (Foundation — 3~5일)**: S1 imin-home + S2
- Day 1: S2 실패 속성 진단 (실험)
- Day 2~3: imin-home blueprint.json 작성 + 빌드 검증 + slots.json
- Day 4: `scripts/blueprint_sanitizer.py` + `src/main/figma-mcp-embedded.ts` sanitizer 통합
- Day 5: Phase A end-to-end 테스트 (imin-home PRD → 수동 bind → build 검증)

**Phase B (Matcher & Binder — 3~4일)**: S3 + S4
- Day 6~7: `src/main/reference-matcher.ts` + unit tests
- Day 8~9: `src/main/content-binder.ts` + Agent micro-prompt + integration

**Phase C (Visual QA — 2일)**: S5
- Day 10~11: `src/main/visual-qa.ts` + 교정 루프

**Phase D (Expansion — 2~4일)**: 나머지 레퍼런스 S1 확장
- 각 레퍼런스에 blueprint/slots/meta 추가 (레퍼런스당 0.5~1일)

**Phase E (Production — 2일)**: Feature flag off → on 전환, 레거시 fallback 검증

**총 예상**: 약 **2주 (실작업 10~15일)**. 버퍼 포함 3주.

### 6.2 진행 체크포인트
각 Phase 종료 시:
- [ ] 해당 단계의 "검증 기준" 전부 통과
- [ ] 사용자(프로젝트 오너) 확인
- [ ] 다음 단계 진행 승인

---

## 7. 리스크 분석

### 7.1 Top 리스크

| # | 리스크 | 확률 | 영향 | 대응 |
|---|--------|------|------|------|
| R1 | batch_build_screen의 본질적 제약으로 레퍼런스 blueprint 작성 불가 | 중 | 치명적 | Figma Plugin 소스(`code.js`) 수정 옵션 확보. 필요 시 plugin API를 한 단계 올려 활용 |
| R2 | 레퍼런스별 slot 수가 너무 많아 Agent 매핑 비용/오류 증가 | 중 | 중간 | slot 개수를 핵심 텍스트 10~20개로 제한. 나머지는 default 유지 |
| R3 | PRD가 완전 신규 스타일이라 매칭 실패 — 모든 레퍼런스 점수 < 0.5 | 중 | 낮음 | UI에 "레퍼런스 추가 워크플로우" 안내 → 사용자가 신규 reference package를 수동 등록 |
| R4 | Visual QA의 LLM similarity 판단이 부정확 | 중 | 중간 | 픽셀 diff + LLM 조합. 픽셀 diff로 50%+ 차이 감지는 결정적 |
| R5 | blueprint.json 자체가 Figma 변경으로 stale 됨 | 낮 | 중간 | `_meta.validatedOn` 추적. CI에 주기적 재빌드 검증 가능 |
| R6 | 재구성 중 현재 시스템 완전 중단 | 낮 | 중간 | Feature flag로 legacy/new 병행. 새 파이프라인이 안정될 때까지 legacy default |

### 7.2 장기 리스크
- **레퍼런스 다양성 부족**: 새 화면 유형이 계속 추가되면 매번 reference package 추가 필요 → 장기 운영 부담. **완화**: "가장 유사한 레퍼런스 + 변형 지시" 허용하는 하이브리드 모드를 S6로 추가 검토.

---

## 8. Open Questions

### 8.1 구조적 질문
| Q | 결정 필요자 | 상태 |
|---|-----------|------|
| Slot path는 JSONPath vs lodash-path 어느 것 채택? | 개발자 | 미결 |
| Visual QA의 similarity threshold 기본값 (0.7 or 0.8 or 0.85)? | 프로덕트 | 미결 |
| Feature flag를 사용자에게 노출 vs 내부만? | 프로덕트 | 미결 |
| 레퍼런스 신규 추가 시 blueprint.json을 Claude Code 세션에서 생성 vs 별도 툴 | 프로덕트 | 미결 |

### 8.2 디자인 질문
| Q | 노트 |
|---|------|
| 다크/라이트 테마를 DS가 동시 지원하면 레퍼런스 blueprint는 어느 테마로? | 현재 모든 레퍼런스가 라이트. DS는 다크. **결정**: blueprint는 레퍼런스 테마 그대로, DS 테마와 분리 |
| 신규 레퍼런스를 사용자가 직접 추가할 수 있는 UI 필요한가? | Phase E에 포함 검토. 초기엔 파일 시스템 수동 추가 |
| 레퍼런스 meta.json의 키워드를 수동 vs AI 자동 추출? | Phase E에 자동 추출 기능 추가 검토. 초기엔 수동 |

### 8.3 운영 질문
| Q | 노트 |
|---|------|
| batch_build_screen 제약이 해결 불가한 레퍼런스가 나오면? | Plugin 소스 수정 (code.js) — 프로젝트 유지보수 가능 |
| End-user 피드백으로 "이 레퍼런스 결과가 이상하다"는 제보 받으면? | V1: 개발자가 blueprint.json 직접 수정. V2 (향후): 사용자 피드백 기반 slot override |

---

## 9. 성공 판단 기준 (최종)

재구성 완료 후 아래 시나리오 전부 통과:

### 시나리오 1: imin-home PRD 재현
```
입력: /Users/julee/Desktop/imin_home_PRD.md
기대 출력: 사용자가 공유한 "정답" 스크린샷과 시각 80% 이상 일치
```

### 시나리오 2: 반복 결정성
```
동일 PRD를 3회 연속 실행
기대: Blueprint JSON이 bit 단위 동일, Figma 빌드 결과도 동일
```

### 시나리오 3: 신규 PRD (기존 레퍼런스와 약간 다름)
```
입력: 미납 2건 + 모은 금액 다른 값 + 유저 이름 "지훈"
기대: imin-home 구조 유지 + PRD 값만 올바르게 반영
```

### 시나리오 4: 매칭 실패 케이스
```
입력: 스테이지 상세 화면 PRD
기대: imin-stage-detail 매칭 (confidence ≥ 0.8), 레퍼런스 구조로 빌드
```

### 시나리오 5: 빌드 실패 복구
```
입력: 임의로 복잡 속성 섞인 blueprint (sanitize 테스트)
기대: sanitizer가 자동 우회, 빌드 성공
```

---

## 10. 부록

### 10.1 전체 파일 변경 요약

#### 신규 파일
```
docs/architecture/redesign-plan.md             (이 문서)
docs/architecture/safe-build-spec.md           (S2 산출물)
docs/references/{id}/blueprint.json            (S1 — 4개 레퍼런스)
docs/references/{id}/slots.json                (S1 — 4개 레퍼런스)
docs/references/{id}/meta.json                 (S1 — 4개 레퍼런스)
scripts/blueprint_sanitizer.py                 (S2)
src/main/reference-matcher.ts                  (S3)
src/main/content-binder.ts                     (S4)
src/main/visual-qa.ts                          (S5)
```

#### 수정 파일
```
src/main/figma-mcp-embedded.ts                 (batch_build_screen sanitize + retry)
src/main/pipeline-orchestrator.ts              (feature flag + new pipeline 분기)
src/main/system-prompt-builder.ts              (S4/S5 micro-prompt으로 축소)
```

#### 사용 중단 (유지하되 참조 해제)
```
docs/design-rules.md (VS1~VS30)                (유지 — 신규 레퍼런스 작성 참고용)
scripts/blueprint_templates.json               (유지 — 참고용)
```

### 10.2 샘플: imin-home slots.json (축약)
```jsonc
{
  "_meta": { "referenceId": "imin-home", "slotCount": 14 },
  "slots": [
    { "id": "navbar.logo.text", "path": "$.children[0].children[0].children[1].text", "type": "text", "default": "imin" },
    { "id": "tabs.active.label", "path": "$.children[1].children[0].children[0].text", "type": "text", "default": "거래 현황" },
    { "id": "alert.title", "path": "$.children[2].children[0].children[1].children[0].text", "type": "text", "default": "미납 1건 · 4월 18일" },
    { "id": "alert.sub", "path": "$.children[2].children[0].children[1].children[1].text", "type": "text", "default": "지금 납입하지 않으면 연체 이자가 발생해요" },
    { "id": "summary.pill.text", "path": "$.children[3].children[0].children[0].children[0].children[0].text", "type": "text", "default": "3건 진행 중" },
    { "id": "summary.title", "path": "$.children[3].children[0].children[0].children[1].text", "type": "text", "default": "내 스테이지" },
    { "id": "summary.earned.amount", "path": "$.children[3].children[0].children[1].children[0].children[1].text", "type": "text", "default": "14,420,320", "format": "number_krw" },
    { "id": "summary.owed.amount", "path": "$.children[3].children[0].children[1].children[1].children[1].text", "type": "text", "default": "5,240,020", "format": "number_krw" }
    // ... 생략
  ]
}
```

### 10.3 샘플: Content Binder Agent 응답
```jsonc
{
  "navbar.logo.text": "imin",
  "tabs.active.label": "거래 현황",
  "alert.title": "미납 2건 · 4월 22일",
  "alert.sub": "지금 납입하지 않으면 연체 이자가 발생해요",
  "summary.pill.text": "5건 진행 중",
  "summary.title": "내 스테이지",
  "summary.earned.amount": "18,500,000",
  "summary.owed.amount": "3,200,000"
}
```

---

## 11. 다음 단계 (승인 후 착수)

1. **이 기획서 리뷰 및 승인** ← 현재 여기
2. **Open Questions 결정** (특히 8.1 4가지)
3. **Phase A 착수** (S2 실패 속성 진단 실험 먼저)
4. **각 Phase 종료 시 진척 리포트**

---

**이 문서는 시스템 재구성의 청사진입니다. 구현자는 각 Phase의 "검증 기준"을 통과한 후에만 다음 Phase로 진행해야 하며, Open Questions는 해당 Phase 착수 전에 결정되어야 합니다.**
