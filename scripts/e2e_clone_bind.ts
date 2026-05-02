/**
 * E2E Clone&Bind dry-run
 * ======================
 * pipeline-orchestrator의 tryCloneAndBind 경로를 실제 PRD로 검증.
 * Anthropic API 호출을 피하기 위해 agentCall은 stub 사용 (빈 매핑 반환 → 모든 slot default 유지).
 *
 * 1. PRD 파일 읽기
 * 2. extractPRDFeatures → matchReference 확인 (confidence, 근거)
 * 3. loadReferencePackage
 * 4. bindReferenceToPRD(stub agentCall) → coverage gate 통과 여부 + finalBlueprint 생성
 * 5. 결과 요약
 */
import { readFile, writeFile } from 'fs/promises';
import { join } from 'path';
import {
  matchReference,
  extractPRDFeatures,
  isFallbackRequired,
} from '../src/main/reference-matcher';
import {
  loadReferencePackage,
  bindReferenceToPRD,
  createStubAgent,
} from '../src/main/content-binder';

const PROJECT_ROOT = join(__dirname, '..');

async function main() {
  const prdPath = process.argv[2] || '/Users/julee/Desktop/imin_home_PRD.md';
  console.log(`📄 PRD: ${prdPath}`);
  const prdText = await readFile(prdPath, 'utf-8');
  console.log(`   ${prdText.length} chars, ${prdText.split('\n').length} lines\n`);

  // ── Step A: 특징 추출 ──
  const prd = extractPRDFeatures(prdText, 'imin_home_PRD.md');
  console.log(`🔎 Parsed PRD features:`);
  console.log(`   screenType: ${prd.screenType}`);
  console.log(`   brand: ${prd.brand}`);
  console.log(`   keywords (top 10): ${prd.keywords.slice(0, 10).join(', ')}\n`);

  // ── Step B: 매칭 ──
  const match = await matchReference(prd, PROJECT_ROOT);
  console.log(`🎯 matchReference:`);
  console.log(`   winner: ${match.referenceId}`);
  console.log(`   confidence: ${match.confidence.toFixed(3)}`);
  console.log(`   fallbackUsed: ${match.fallbackUsed}`);
  console.log(`   reasons: ${match.reasons.join('; ')}`);
  console.log(`   all scores:`);
  for (const s of match.allScores) {
    console.log(`     - ${s.referenceId}: ${s.score.toFixed(3)} [${s.reasons.slice(0, 2).join(', ')}]`);
  }
  console.log();

  if (isFallbackRequired(match)) {
    console.log(`❌ confidence < 0.5 → pipeline would fall back to LLM creation.`);
    process.exit(0);
  }

  // ── Step C: 레퍼런스 package ──
  const pkg = await loadReferencePackage(PROJECT_ROOT, match.referenceId);
  console.log(`📦 Loaded reference package "${match.referenceId}":`);
  console.log(`   slots: ${pkg.slots.slots.length}`);
  console.log(`   blueprint root children: ${((pkg.blueprint as any).children as unknown[] | undefined)?.length ?? 0}\n`);

  // ── Step D: Stub agent → defaults만 유지 (실제 LLM 호출 없음) ──
  // 이 테스트의 목적은 coverage gate 통과 여부 + blueprint 구조 무결성 검증
  const stubAgent = createStubAgent({});

  try {
    const result = await bindReferenceToPRD(pkg, prdText, stubAgent);
    console.log(`✅ bindReferenceToPRD succeeded:`);
    console.log(`   coverage: ${(result.coverage.coverage * 100).toFixed(1)}% (${result.coverage.gateDecision})`);
    console.log(`   matched sections (${result.coverage.matched.length}):`);
    for (const m of result.coverage.matched) {
      console.log(`     - PRD "${m.prdTitle}" ↔ BP "${m.bpName}"`);
    }
    if (result.coverage.missing.length > 0) {
      console.log(`   missing PRD sections (${result.coverage.missing.length}):`);
      for (const m of result.coverage.missing) {
        console.log(`     - ${m.prdTitle}`);
      }
    }
    console.log(`   applied slots: ${result.applied.length} (stub returns empty → all defaults kept)`);
    console.log(`   skipped slots: ${result.skipped.length}`);
    console.log(`   PRD sections parsed: ${result.coverage.prdSections.length}`);
    console.log(`   BP sections parsed: ${result.coverage.blueprintSections.length}`);

    // final blueprint 저장 (Step 2 호환성 테스트용)
    const outPath = join(PROJECT_ROOT, 'scripts', 'e2e_clone_bind_final.json');
    await writeFile(outPath, JSON.stringify(result.finalBlueprint, null, 2), 'utf-8');
    console.log(`\n💾 Final blueprint: ${outPath}`);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.log(`\n🚫 bindReferenceToPRD threw (coverage gate or other):`);
    console.log(msg);
    process.exit(1);
  }
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
