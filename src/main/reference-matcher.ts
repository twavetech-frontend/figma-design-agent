/**
 * Reference Matcher (S3 — Phase B)
 * ================================
 * PRD → 레퍼런스 결정적 매칭. LLM 미사용 — 단순 규칙 기반 점수.
 *
 * 흐름:
 *   1. PRD 텍스트에서 특징 추출 (화면 유형, 브랜드, 키워드)
 *   2. `docs/references/<id>/meta.json` 전수 조회
 *   3. 점수 계산: screenType match + brand + keyword overlap + positive/negative signals
 *   4. confidence 임계값 분기:
 *      - ≥0.8 자동 선택
 *      - 0.5~0.8 사용자 확인 요청
 *      - <0.5 레퍼런스 없음 에러
 *
 * 기획서: docs/architecture/redesign-plan.md § 4.3
 */

import { readFile, readdir } from 'fs/promises';
import { join } from 'path';

export interface ReferenceMeta {
  referenceId: string;
  displayName?: string;
  screenType: string[];
  brand: string;
  theme: 'light' | 'dark';
  features: string[];
  keywords: string[];
  matchingHints: {
    positiveSignals: string[];
    negativeSignals: string[];
  };
  targetPersona?: string[];
  containedSections?: string[];
}

export interface ParsedPRD {
  rawText: string;
  screenType: string;
  brand: string;
  keywords: string[];
  attachmentName?: string;
}

export interface MatchResult {
  referenceId: string;
  confidence: number;
  reasons: string[];
  fallbackUsed: boolean;
  allScores: Array<{ referenceId: string; score: number; reasons: string[] }>;
}

const CONFIDENCE_AUTO = 0.8;
const CONFIDENCE_CONFIRM = 0.5;

/**
 * PRD 본문에서 특징 추출. LLM 없이 단순 키워드/빈도 기반.
 */
export function extractPRDFeatures(prdText: string, attachmentName?: string): ParsedPRD {
  const lower = prdText.toLowerCase();

  // 화면 유형 추측 — 제목/첫 섹션 기반 키워드 매칭
  let screenType = 'unknown';
  const typePatterns: Array<[RegExp, string]> = [
    [/홈\s*화면|home\s*screen|메인\s*화면|main\s*screen|거래\s*현황|내\s*스테이지/, 'home'],
    [/스테이지\s*(목록|탭|추천|탐색)|추천\s*스테이지|stage\s*list|feed/, 'stage-tab'],
    [/스테이지\s*상세|참여자\s*(리스트|목록)|참여\s*바텀시트/, 'stage-detail'],
    [/모달|modal|바텀\s*시트|bottom\s*sheet|풀\s*모달|full\s*modal/, 'modal'],
    [/리스트\s*화면|list\s*view|아이템\s*목록/, 'list'],
    [/프로필|설정|마이|my\s*page|profile/, 'profile'],
  ];
  for (const [rx, t] of typePatterns) {
    if (rx.test(prdText)) {
      screenType = t;
      break;
    }
  }

  // 브랜드 추출 — 가장 자주 나오는 고유명사 (단순 화이트리스트)
  let brand = 'unknown';
  const brandCandidates = ['imin', '아임인', 'toss', '토스', 'kakao', '카카오', 'aim'];
  for (const b of brandCandidates) {
    if (lower.includes(b.toLowerCase())) {
      brand = b.toLowerCase() === '아임인' ? 'imin' : b.toLowerCase();
      break;
    }
  }

  // 키워드 추출 — 의미 있는 단어 상위 N (매우 단순)
  const tokens = prdText
    .replace(/[^\w가-힣]/g, ' ')
    .split(/\s+/)
    .filter(t => t.length >= 2 && t.length <= 10);
  const freq: Record<string, number> = {};
  for (const t of tokens) {
    freq[t] = (freq[t] || 0) + 1;
  }
  const keywords = Object.entries(freq)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 30)
    .map(([k]) => k);

  return { rawText: prdText, screenType, brand, keywords, attachmentName };
}

/**
 * PRD와 레퍼런스 meta.json 사이 매칭 점수 계산.
 * 반환: 0~1 점수 + 근거 리스트.
 */
export function calculateMatchScore(
  prd: ParsedPRD,
  meta: ReferenceMeta
): { score: number; reasons: string[] } {
  const reasons: string[] = [];
  let score = 0;

  // 1. 화면 유형 정확 매칭 (가중치 0.5)
  const screenTypes = meta.screenType.map(t => t.toLowerCase());
  if (screenTypes.some(t => t === prd.screenType || t.includes(prd.screenType) || prd.screenType.includes(t))) {
    score += 0.5;
    reasons.push(`screen type match: ${prd.screenType}`);
  } else if (prd.screenType === 'unknown') {
    // 화면 유형 추출 실패 시 중립
    score += 0.2;
    reasons.push(`screen type unknown — neutral`);
  }

  // 2. 브랜드 일치 (가중치 0.15)
  if (meta.brand.toLowerCase() === prd.brand) {
    score += 0.15;
    reasons.push(`brand match: ${prd.brand}`);
  }

  // 3. 키워드 overlap (가중치 0.2)
  const metaKeywords = meta.keywords.map(k => k.toLowerCase());
  const prdKeywordsLower = prd.keywords.map(k => k.toLowerCase());
  const overlap = prdKeywordsLower.filter(k => metaKeywords.some(mk => mk.includes(k) || k.includes(mk)));
  if (overlap.length > 0) {
    const ratio = Math.min(1, overlap.length / Math.max(metaKeywords.length * 0.3, 3));
    score += 0.2 * ratio;
    reasons.push(`keyword overlap: ${overlap.slice(0, 5).join(', ')} (${overlap.length})`);
  }

  // 4. Positive signals (가중치 0.15)
  const positiveHits = meta.matchingHints.positiveSignals.filter(s =>
    prd.rawText.toLowerCase().includes(s.toLowerCase())
  );
  if (positiveHits.length > 0) {
    score += 0.15 * Math.min(1, positiveHits.length / 2);
    reasons.push(`positive signals: ${positiveHits.slice(0, 3).join(', ')}`);
  }

  // 5. Negative signals 감산 (가중치 -0.3)
  const negativeHits = meta.matchingHints.negativeSignals.filter(s =>
    prd.rawText.toLowerCase().includes(s.toLowerCase())
  );
  if (negativeHits.length > 0) {
    const penalty = 0.3 * Math.min(1, negativeHits.length / 2);
    score -= penalty;
    reasons.push(`negative signals (−${penalty.toFixed(2)}): ${negativeHits.slice(0, 3).join(', ')}`);
  }

  return {
    score: Math.max(0, Math.min(1, score)),
    reasons,
  };
}

/**
 * docs/references/ 디렉토리에서 모든 meta.json 로드.
 */
export async function loadAllReferenceMetas(projectRoot: string): Promise<ReferenceMeta[]> {
  const refDir = join(projectRoot, 'docs', 'references');
  let entries: string[];
  try {
    entries = await readdir(refDir);
  } catch {
    return [];
  }

  const metas: ReferenceMeta[] = [];
  for (const entry of entries) {
    const metaPath = join(refDir, entry, 'meta.json');
    try {
      const content = await readFile(metaPath, 'utf-8');
      const meta = JSON.parse(content) as ReferenceMeta;
      if (meta.referenceId) {
        metas.push(meta);
      }
    } catch {
      // meta.json 없는 디렉토리는 skip (레거시 레퍼런스)
    }
  }
  return metas;
}

/**
 * PRD ↔ 등록된 레퍼런스 중 최적 매칭 반환.
 */
export async function matchReference(
  prd: ParsedPRD,
  projectRoot: string
): Promise<MatchResult> {
  const metas = await loadAllReferenceMetas(projectRoot);
  if (metas.length === 0) {
    throw new Error('No reference meta.json files found in docs/references/');
  }

  const scored = metas.map(meta => {
    const { score, reasons } = calculateMatchScore(prd, meta);
    return { referenceId: meta.referenceId, score, reasons };
  });

  scored.sort((a, b) => b.score - a.score);
  const best = scored[0];

  return {
    referenceId: best.referenceId,
    confidence: best.score,
    reasons: best.reasons,
    fallbackUsed: best.score < CONFIDENCE_CONFIRM,
    allScores: scored,
  };
}

/**
 * Confidence 기반 진행 결정 분기.
 */
export function shouldAutoProceed(match: MatchResult): boolean {
  return match.confidence >= CONFIDENCE_AUTO;
}

export function needsConfirmation(match: MatchResult): boolean {
  return match.confidence >= CONFIDENCE_CONFIRM && match.confidence < CONFIDENCE_AUTO;
}

export function isFallbackRequired(match: MatchResult): boolean {
  return match.confidence < CONFIDENCE_CONFIRM;
}
