/**
 * Content Binder (S4 — Phase B)
 * =============================
 * Agent의 역할을 "Blueprint 창작"에서 "slot ↔ PRD 값 매핑"으로 축소.
 *
 * 입력:
 *   - referencePackage: { blueprint, slots, meta }
 *   - prd: PRD 텍스트
 *   - agentCall: Claude API 호출 함수 (외부 주입)
 *
 * 출력:
 *   - finalBlueprint: slot 값 치환된 Blueprint (불변 복제)
 *
 * 기획서: docs/architecture/redesign-plan.md § 4.4
 */

import { readFile } from 'fs/promises';
import { join } from 'path';
import { enforceCoverageGate, type CoverageResult } from './coverage-checker';

/** lodash-path 기반 mutable set — "children[3].children[0].text" 형태 */
export function lodashSet(obj: unknown, path: string, value: unknown): void {
  const tokens = [...path.matchAll(/(\w+)|\[(\d+)\]/g)];
  let current: any = obj;
  for (let i = 0; i < tokens.length - 1; i++) {
    const [, key, idx] = tokens[i];
    current = idx !== undefined ? current[Number(idx)] : current[key];
  }
  const last = tokens[tokens.length - 1];
  if (last[2] !== undefined) current[Number(last[2])] = value;
  else current[last[1]] = value;
}

export function lodashGet(obj: unknown, path: string): unknown {
  const tokens = [...path.matchAll(/(\w+)|\[(\d+)\]/g)];
  let current: any = obj;
  for (const [, key, idx] of tokens) {
    current = idx !== undefined ? current[Number(idx)] : current[key];
  }
  return current;
}

export interface SlotSpec {
  id: string;
  path: string;
  type: 'text' | 'fill' | 'icon';
  default: string;
  hint?: string;
  format?: string;
}

export interface SlotsFile {
  _meta?: unknown;
  slots: SlotSpec[];
}

export interface ReferencePackage {
  referenceId: string;
  blueprint: Record<string, unknown>;
  slots: SlotsFile;
  meta: Record<string, unknown>;
}

export interface AgentCall {
  (opts: {
    systemPrompt: string;
    userPrompt: string;
    responseFormat: 'json_object';
  }): Promise<Record<string, string>>;
}

/**
 * Agent에게 전달하는 micro system prompt.
 * Blueprint 창작 여지를 완전 차단 — slot 매핑만 허용.
 */
const BIND_SYSTEM_PROMPT = `You are a content binder. Your ONLY task: map slot IDs to values from a PRD.

## Output
Respond with a single JSON object: { "slot.id": "value", ... }
- Only include slots whose values differ from defaults or are explicitly present in the PRD.
- Omit a slot → the default is kept.
- For slots whose values have a \`format\` (e.g. number_krw_comma), return raw data and the binder will format it.

## HARD RULES — STRICTLY FORBIDDEN
- DO NOT modify blueprint structure, color, layout, or any non-text property.
- DO NOT invent new slot IDs.
- DO NOT add explanations, comments, or markdown.
- DO NOT suggest improvements or alternatives.
- If PRD and reference default conflict on semantics (e.g. "빌린 금액" → "납입 예정액"), KEEP THE REFERENCE DEFAULT unless PRD explicitly names the new term.

Return the JSON object and nothing else.`;

function buildBindPrompt(slots: SlotsFile, prdText: string): string {
  const slotList = slots.slots
    .map(s => `  { id: "${s.id}", default: ${JSON.stringify(s.default)}${s.hint ? `, hint: ${JSON.stringify(s.hint)}` : ''} }`)
    .join(',\n');

  return `# Reference Slots
The following slots are the only fields you may fill:

[\n${slotList}\n]

# PRD (user-provided document)

${prdText.length > 8000 ? prdText.slice(0, 8000) + '\n...[truncated]' : prdText}

# Your Response
JSON object of slot.id → value (only slots to override from PRD).`;
}

/**
 * 포맷 변환 (format 필드 기반).
 */
function applyFormat(value: string, format?: string): string {
  if (!format) return value;
  if (format === 'number_krw_comma') {
    const n = Number(String(value).replace(/[^\d.-]/g, ''));
    if (isNaN(n)) return value;
    return n.toLocaleString('ko-KR');
  }
  if (format === 'number_krw_signed') {
    const n = Number(String(value).replace(/[^\d.-]/g, ''));
    if (isNaN(n)) return value;
    const sign = n < 0 ? '−' : '';
    return sign + Math.abs(n).toLocaleString('ko-KR');
  }
  return value;
}

/**
 * Blueprint 불변 복제. JSON round-trip으로 안전.
 */
function cloneDeep<T>(x: T): T {
  return JSON.parse(JSON.stringify(x));
}

/**
 * 레퍼런스 package 로드 헬퍼.
 */
export async function loadReferencePackage(
  projectRoot: string,
  referenceId: string
): Promise<ReferencePackage> {
  const refDir = join(projectRoot, 'docs', 'references', referenceId);
  const [blueprint, slotsRaw, metaRaw] = await Promise.all([
    readFile(join(refDir, 'blueprint.json'), 'utf-8').then(JSON.parse),
    readFile(join(refDir, 'slots.json'), 'utf-8').then(JSON.parse),
    readFile(join(refDir, 'meta.json'), 'utf-8').then(JSON.parse),
  ]);
  return {
    referenceId,
    blueprint: blueprint as Record<string, unknown>,
    slots: slotsRaw as SlotsFile,
    meta: metaRaw as Record<string, unknown>,
  };
}

/**
 * Content Binding — Agent가 제공한 매핑을 blueprint에 주입.
 * 실제 LLM 호출은 agentCall에 의존하여 테스트 용이.
 */
export async function bindContent(
  pkg: ReferencePackage,
  prdText: string,
  agentCall: AgentCall
): Promise<{
  finalBlueprint: Record<string, unknown>;
  applied: string[];
  skipped: string[];
  rawMapping: Record<string, string>;
}> {
  let rawMapping: Record<string, string> = {};

  try {
    rawMapping = await agentCall({
      systemPrompt: BIND_SYSTEM_PROMPT,
      userPrompt: buildBindPrompt(pkg.slots, prdText),
      responseFormat: 'json_object',
    });
  } catch (err) {
    console.warn('[content-binder] Agent call failed, using all defaults:', err);
    rawMapping = {};
  }

  const blueprint = cloneDeep(pkg.blueprint);
  const applied: string[] = [];
  const skipped: string[] = [];

  for (const slot of pkg.slots.slots) {
    const rawValue = rawMapping[slot.id];
    if (rawValue !== undefined && rawValue !== null && rawValue !== slot.default) {
      const formatted = applyFormat(String(rawValue), slot.format);
      try {
        lodashSet(blueprint, slot.path, formatted);
        applied.push(slot.id);
      } catch (e) {
        console.warn(`[content-binder] Failed to set ${slot.id}:`, e);
        skipped.push(slot.id);
      }
    } else {
      skipped.push(slot.id);
    }
  }

  return { finalBlueprint: blueprint, applied, skipped, rawMapping };
}

/**
 * Stub agent call — 실제 환경에서는 Claude API로 교체.
 * 테스트/개발용으로 고정 매핑을 리턴하는 헬퍼.
 */
export function createStubAgent(mapping: Record<string, string>): AgentCall {
  return async () => mapping;
}

/**
 * Clone & Bind 전체 파이프라인 — 비디자이너가 PRD를 주고 디자인을 받는 단일 진입점.
 *
 * 순서 (모든 단계 강제):
 *   1. Coverage Gate (enforceCoverageGate)     — PRD 섹션이 blueprint에 충분히 포함됐는지 검증.
 *                                                 < 85% 커버 시 Error throw → 파이프라인 즉시 중단.
 *                                                 사용자가 레퍼런스 확장 or PRD 스코프 축소를 선택해야 함.
 *   2. Content Binding (bindContent)           — Agent가 slot ↔ PRD 값 매핑, blueprint에 주입.
 *   3. 반환: { coverage, bind, finalBlueprint }
 *
 * 이 함수를 **반드시 bindContent 직접 호출 대신 사용**해야 "시스템이 누락 감지 실패"
 * 시나리오를 차단할 수 있다. 상위 파이프라인(ex. HTTP API, CLI)은 이 함수 하나만 호출.
 */
export async function bindReferenceToPRD(
  pkg: ReferencePackage,
  prdText: string,
  agentCall: AgentCall,
  options: { coverageMinPass?: number } = {}
): Promise<{
  coverage: CoverageResult;
  finalBlueprint: Record<string, unknown>;
  applied: string[];
  skipped: string[];
  rawMapping: Record<string, string>;
}> {
  // 1. Coverage Gate — 미달 시 throw Error로 파이프라인 중단
  const coverage = enforceCoverageGate(prdText, pkg.blueprint, {
    minPass: options.coverageMinPass,
  });

  // 2. Content Binding
  const bind = await bindContent(pkg, prdText, agentCall);

  return {
    coverage,
    finalBlueprint: bind.finalBlueprint,
    applied: bind.applied,
    skipped: bind.skipped,
    rawMapping: bind.rawMapping,
  };
}
