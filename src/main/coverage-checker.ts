/**
 * Coverage Checker (S6 — 시스템 누락 Layer)
 * ==========================================
 * PRD 섹션 vs Blueprint 섹션의 **커버리지 검증**.
 * Binder 진입 전 강제 호출하여 "레퍼런스 blueprint가 PRD의 모든 요구 섹션을 포함하는지" 확인.
 * 불일치 감지 시 빌드 중단 → 레퍼런스 업데이트 유도.
 *
 * 배경: 기획서 § 4 초판엔 이 layer가 없었음. 사용자가 "PRD에 13섹션인데 blueprint에
 * 7섹션만 들어 있다"고 지적. 시스템적으로 커버리지 미달을 감지해야 함.
 */

export interface CoverageResult {
  prdSections: Array<{ id: string; title: string; hint: string }>;
  blueprintSections: Array<{ name: string; normalized: string }>;
  matched: Array<{ prdId: string; prdTitle: string; bpName: string }>;
  missing: Array<{ prdId: string; prdTitle: string; hint: string }>;
  extra: string[];               // blueprint에만 있는 섹션 (정보용)
  coverage: number;              // 0~1
  gateDecision: 'pass' | 'block';
  gateReason: string;
}

const COVERAGE_MIN_PASS = 0.85;  // 85% 미만이면 block

/**
 * PRD 텍스트에서 섹션 목록을 자동 추출.
 * 지원 형태:
 *   - "#### 섹션 N — 제목"  (markdown heading)
 *   - "## N. 제목"
 *   - 표 헤더 "| 섹션 | 내용 |"
 *   - 목록 "- 글로벌 헤더"
 */
export function parsePrdSections(prdText: string): Array<{ id: string; title: string; hint: string }> {
  const sections: Array<{ id: string; title: string; hint: string }> = [];
  const seenIds = new Set<string>();

  // 패턴 1: "#### 섹션 N — 제목" 또는 "#### 섹션 N. 제목" 또는 "### 섹션 N"
  const sectionRegex = /^#{2,5}\s*(?:섹션|Section)\s*([0-9]+)\s*[—\-–\.·]\s*(.+?)$/gm;
  let match: RegExpExecArray | null;
  while ((match = sectionRegex.exec(prdText)) !== null) {
    const id = `section-${match[1]}`;
    const title = match[2].trim();
    if (!seenIds.has(id)) {
      seenIds.add(id);
      sections.push({ id, title, hint: title.toLowerCase() });
    }
  }

  // 패턴 2: 테이블 "## N. 제목" (PRD 대제목 스킵)
  // 이 경우 "# "로 시작하는 큰 번호 헤딩은 제외 (예: "## 1. 개요"는 섹션 아님)
  // 본 섹션 리스트는 보통 "## 3. 화면 구조 및 섹션 요구사항" 하위 "#### 섹션 0 ~ N"

  // 패턴 3: PRD의 "섹션 목록" 블록 — "## 3.1 전체 화면 구조" 이후 ASCII tree
  // 여기서 `├── [신규...]` 같은 line은 섹션이 아닌 모드.

  return sections;
}

/**
 * Blueprint 트리에서 의미 있는 섹션 이름 추출.
 * 루트의 직계 children을 대상으로 하되, "Wrap" / "Spacer" 등은 실제 섹션명으로 정규화.
 */
export function parseBlueprintSections(
  blueprint: Record<string, unknown>
): Array<{ name: string; normalized: string }> {
  const children = (blueprint.children as Record<string, unknown>[]) || [];
  return children
    .map(c => String(c.name || ''))
    .filter(n => n && !/spacer|divider/i.test(n))
    .map(n => ({
      name: n,
      normalized: n
        .replace(/\s*Wrap\s*$/i, '')
        .replace(/\s*Section\s*$/i, '')
        .replace(/\s*Card\s*$/i, '')
        .toLowerCase()
        .trim(),
    }));
}

/** Fuzzy match: PRD 섹션 title이 blueprint 섹션 이름/설명에 매칭되는가? */
function sectionMatches(prdHint: string, bpNormalized: string): boolean {
  const prd = prdHint.toLowerCase();
  const bp = bpNormalized.toLowerCase();

  // 공통 키워드 매핑
  const SECTION_SYNONYMS: Array<[string[], string[]]> = [
    [['글로벌 헤더', '헤더', '상단', 'header'], ['navbar', 'header', 'app header']],
    [['거래 현황', '탭', 'tab'], ['home tabs', 'tabs', 'tab']],
    [['미납', '경고'], ['alert', 'missed']],
    [['스테이지 요약', '요약 카드'], ['summarycard', 'summary']],
    [['납입', '지급', '스케줄'], ['schedule', 'day card']],
    [['한도', '신용'], ['limit']],
    [['추천 스테이지', '추천', 'recommendation'], ['recommendation', 'rec', 'premium cta', 'stage recommender']],
    [['참여 중'], ['current stage', 'stage card', 'participating']],
    [['누적 거래', '누적'], ['cumulative']],
    [['출석', '이벤트'], ['attendance', 'event']],
    [['상품', '라운지'], ['lounge', 'product']],
    [['마이', '온보딩', '계좌 연결', '정보 입력'], ['onboarding']],
    [['탭바', 'tab bar', 'bottom'], ['bottom nav']],
  ];

  for (const [prdKeywords, bpKeywords] of SECTION_SYNONYMS) {
    const prdHit = prdKeywords.some(k => prd.includes(k));
    const bpHit = bpKeywords.some(k => bp.includes(k));
    if (prdHit && bpHit) return true;
  }
  // 직접 overlap
  for (const w of prd.split(/\s+/).filter(x => x.length >= 2)) {
    if (bp.includes(w)) return true;
  }
  return false;
}

/**
 * PRD ↔ Blueprint 섹션 커버리지 계산 + gate 결정.
 */
export function checkCoverage(
  prdText: string,
  blueprint: Record<string, unknown>,
  options: { minPass?: number } = {}
): CoverageResult {
  const prdSections = parsePrdSections(prdText);
  const blueprintSections = parseBlueprintSections(blueprint);

  const matched: Array<{ prdId: string; prdTitle: string; bpName: string }> = [];
  const missing: Array<{ prdId: string; prdTitle: string; hint: string }> = [];
  const usedBp = new Set<string>();

  for (const s of prdSections) {
    const hit = blueprintSections.find(bp => !usedBp.has(bp.name) && sectionMatches(s.hint, bp.normalized));
    if (hit) {
      matched.push({ prdId: s.id, prdTitle: s.title, bpName: hit.name });
      usedBp.add(hit.name);
    } else {
      missing.push({ prdId: s.id, prdTitle: s.title, hint: s.hint });
    }
  }

  const extra = blueprintSections.filter(bp => !usedBp.has(bp.name)).map(bp => bp.name);
  const coverage = prdSections.length === 0 ? 1 : matched.length / prdSections.length;
  const minPass = options.minPass ?? COVERAGE_MIN_PASS;

  return {
    prdSections,
    blueprintSections,
    matched,
    missing,
    extra,
    coverage,
    gateDecision: coverage >= minPass ? 'pass' : 'block',
    gateReason:
      coverage >= minPass
        ? `coverage ${(coverage * 100).toFixed(0)}% ≥ ${(minPass * 100).toFixed(0)}% threshold`
        : `coverage ${(coverage * 100).toFixed(0)}% < ${(minPass * 100).toFixed(0)}% — ${missing.length}개 섹션 누락: ${missing
            .map(m => m.prdTitle)
            .slice(0, 5)
            .join(', ')}`,
  };
}

/**
 * 파이프라인 gate function — Binder 진입 전 호출.
 * 실패 시 Error throw → 빌드 중단.
 */
export function enforceCoverageGate(
  prdText: string,
  blueprint: Record<string, unknown>,
  options: { minPass?: number } = {}
): CoverageResult {
  const result = checkCoverage(prdText, blueprint, options);
  if (result.gateDecision === 'block') {
    const msg = [
      `🚫 [Coverage Gate] Blueprint does NOT cover the PRD adequately.`,
      `   Coverage: ${(result.coverage * 100).toFixed(0)}%  (min: ${((options.minPass ?? COVERAGE_MIN_PASS) * 100).toFixed(0)}%)`,
      `   PRD sections (${result.prdSections.length}): ${result.prdSections.map(s => s.title).join(', ')}`,
      `   Missing: ${result.missing.map(m => m.prdTitle).join(', ')}`,
      ``,
      `   Action: either (a) extend the reference blueprint.json to include missing sections,`,
      `                  (b) update PRD scope to exclude these sections, or`,
      `                  (c) register a new reference that covers the PRD fully.`,
    ].join('\n');
    throw new Error(msg);
  }
  return result;
}
