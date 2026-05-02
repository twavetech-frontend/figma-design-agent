"use strict";

// scripts/e2e_clone_bind.ts
var import_promises3 = require("fs/promises");
var import_path3 = require("path");

// src/main/reference-matcher.ts
var import_promises = require("fs/promises");
var import_path = require("path");
var CONFIDENCE_CONFIRM = 0.5;
function extractPRDFeatures(prdText, attachmentName) {
  const lower = prdText.toLowerCase();
  let screenType = "unknown";
  const typePatterns = [
    [/홈\s*화면|home\s*screen|메인\s*화면|main\s*screen|거래\s*현황|내\s*스테이지/, "home"],
    [/스테이지\s*(목록|탭|추천|탐색)|추천\s*스테이지|stage\s*list|feed/, "stage-tab"],
    [/스테이지\s*상세|참여자\s*(리스트|목록)|참여\s*바텀시트/, "stage-detail"],
    [/모달|modal|바텀\s*시트|bottom\s*sheet|풀\s*모달|full\s*modal/, "modal"],
    [/리스트\s*화면|list\s*view|아이템\s*목록/, "list"],
    [/프로필|설정|마이|my\s*page|profile/, "profile"]
  ];
  for (const [rx, t] of typePatterns) {
    if (rx.test(prdText)) {
      screenType = t;
      break;
    }
  }
  let brand = "unknown";
  const brandCandidates = ["imin", "\uC544\uC784\uC778", "toss", "\uD1A0\uC2A4", "kakao", "\uCE74\uCE74\uC624", "aim"];
  for (const b of brandCandidates) {
    if (lower.includes(b.toLowerCase())) {
      brand = b.toLowerCase() === "\uC544\uC784\uC778" ? "imin" : b.toLowerCase();
      break;
    }
  }
  const tokens = prdText.replace(/[^\w가-힣]/g, " ").split(/\s+/).filter((t) => t.length >= 2 && t.length <= 10);
  const freq = {};
  for (const t of tokens) {
    freq[t] = (freq[t] || 0) + 1;
  }
  const keywords = Object.entries(freq).sort((a, b) => b[1] - a[1]).slice(0, 30).map(([k]) => k);
  return { rawText: prdText, screenType, brand, keywords, attachmentName };
}
function calculateMatchScore(prd, meta) {
  const reasons = [];
  let score = 0;
  const screenTypes = meta.screenType.map((t) => t.toLowerCase());
  if (screenTypes.some((t) => t === prd.screenType || t.includes(prd.screenType) || prd.screenType.includes(t))) {
    score += 0.5;
    reasons.push(`screen type match: ${prd.screenType}`);
  } else if (prd.screenType === "unknown") {
    score += 0.2;
    reasons.push(`screen type unknown \u2014 neutral`);
  }
  if (meta.brand.toLowerCase() === prd.brand) {
    score += 0.15;
    reasons.push(`brand match: ${prd.brand}`);
  }
  const metaKeywords = meta.keywords.map((k) => k.toLowerCase());
  const prdKeywordsLower = prd.keywords.map((k) => k.toLowerCase());
  const overlap = prdKeywordsLower.filter((k) => metaKeywords.some((mk) => mk.includes(k) || k.includes(mk)));
  if (overlap.length > 0) {
    const ratio = Math.min(1, overlap.length / Math.max(metaKeywords.length * 0.3, 3));
    score += 0.2 * ratio;
    reasons.push(`keyword overlap: ${overlap.slice(0, 5).join(", ")} (${overlap.length})`);
  }
  const positiveHits = meta.matchingHints.positiveSignals.filter(
    (s) => prd.rawText.toLowerCase().includes(s.toLowerCase())
  );
  if (positiveHits.length > 0) {
    score += 0.15 * Math.min(1, positiveHits.length / 2);
    reasons.push(`positive signals: ${positiveHits.slice(0, 3).join(", ")}`);
  }
  const negativeHits = meta.matchingHints.negativeSignals.filter(
    (s) => prd.rawText.toLowerCase().includes(s.toLowerCase())
  );
  if (negativeHits.length > 0) {
    const penalty = 0.3 * Math.min(1, negativeHits.length / 2);
    score -= penalty;
    reasons.push(`negative signals (\u2212${penalty.toFixed(2)}): ${negativeHits.slice(0, 3).join(", ")}`);
  }
  return {
    score: Math.max(0, Math.min(1, score)),
    reasons
  };
}
async function loadAllReferenceMetas(projectRoot) {
  const refDir = (0, import_path.join)(projectRoot, "docs", "references");
  let entries;
  try {
    entries = await (0, import_promises.readdir)(refDir);
  } catch {
    return [];
  }
  const metas = [];
  for (const entry of entries) {
    const metaPath = (0, import_path.join)(refDir, entry, "meta.json");
    try {
      const content = await (0, import_promises.readFile)(metaPath, "utf-8");
      const meta = JSON.parse(content);
      if (meta.referenceId) {
        metas.push(meta);
      }
    } catch {
    }
  }
  return metas;
}
async function matchReference(prd, projectRoot) {
  const metas = await loadAllReferenceMetas(projectRoot);
  if (metas.length === 0) {
    throw new Error("No reference meta.json files found in docs/references/");
  }
  const scored = metas.map((meta) => {
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
    allScores: scored
  };
}
function isFallbackRequired(match) {
  return match.confidence < CONFIDENCE_CONFIRM;
}

// src/main/content-binder.ts
var import_promises2 = require("fs/promises");
var import_path2 = require("path");

// src/main/coverage-checker.ts
var COVERAGE_MIN_PASS = 0.85;
function parsePrdSections(prdText) {
  const sections = [];
  const seenIds = /* @__PURE__ */ new Set();
  const sectionRegex = /^#{2,5}\s*(?:섹션|Section)\s*([0-9]+)\s*[—\-–\.·]\s*(.+?)$/gm;
  let match;
  while ((match = sectionRegex.exec(prdText)) !== null) {
    const id = `section-${match[1]}`;
    const title = match[2].trim();
    if (!seenIds.has(id)) {
      seenIds.add(id);
      sections.push({ id, title, hint: title.toLowerCase() });
    }
  }
  return sections;
}
function parseBlueprintSections(blueprint) {
  const children = blueprint.children || [];
  return children.map((c) => String(c.name || "")).filter((n) => n && !/spacer|divider/i.test(n)).map((n) => ({
    name: n,
    normalized: n.replace(/\s*Wrap\s*$/i, "").replace(/\s*Section\s*$/i, "").replace(/\s*Card\s*$/i, "").toLowerCase().trim()
  }));
}
function sectionMatches(prdHint, bpNormalized) {
  const prd = prdHint.toLowerCase();
  const bp = bpNormalized.toLowerCase();
  const SECTION_SYNONYMS = [
    [["\uAE00\uB85C\uBC8C \uD5E4\uB354", "\uD5E4\uB354", "\uC0C1\uB2E8", "header"], ["navbar", "header", "app header"]],
    [["\uAC70\uB798 \uD604\uD669", "\uD0ED", "tab"], ["home tabs", "tabs", "tab"]],
    [["\uBBF8\uB0A9", "\uACBD\uACE0"], ["alert", "missed"]],
    [["\uC2A4\uD14C\uC774\uC9C0 \uC694\uC57D", "\uC694\uC57D \uCE74\uB4DC"], ["summarycard", "summary"]],
    [["\uB0A9\uC785", "\uC9C0\uAE09", "\uC2A4\uCF00\uC904"], ["schedule", "day card"]],
    [["\uD55C\uB3C4", "\uC2E0\uC6A9"], ["limit"]],
    [["\uCD94\uCC9C \uC2A4\uD14C\uC774\uC9C0", "\uCD94\uCC9C", "recommendation"], ["recommendation", "rec", "premium cta", "stage recommender"]],
    [["\uCC38\uC5EC \uC911"], ["current stage", "stage card", "participating"]],
    [["\uB204\uC801 \uAC70\uB798", "\uB204\uC801"], ["cumulative"]],
    [["\uCD9C\uC11D", "\uC774\uBCA4\uD2B8"], ["attendance", "event"]],
    [["\uC0C1\uD488", "\uB77C\uC6B4\uC9C0"], ["lounge", "product"]],
    [["\uB9C8\uC774", "\uC628\uBCF4\uB529", "\uACC4\uC88C \uC5F0\uACB0", "\uC815\uBCF4 \uC785\uB825"], ["onboarding"]],
    [["\uD0ED\uBC14", "tab bar", "bottom"], ["bottom nav"]]
  ];
  for (const [prdKeywords, bpKeywords] of SECTION_SYNONYMS) {
    const prdHit = prdKeywords.some((k) => prd.includes(k));
    const bpHit = bpKeywords.some((k) => bp.includes(k));
    if (prdHit && bpHit) return true;
  }
  for (const w of prd.split(/\s+/).filter((x) => x.length >= 2)) {
    if (bp.includes(w)) return true;
  }
  return false;
}
function checkCoverage(prdText, blueprint, options = {}) {
  const prdSections = parsePrdSections(prdText);
  const blueprintSections = parseBlueprintSections(blueprint);
  const matched = [];
  const missing = [];
  const usedBp = /* @__PURE__ */ new Set();
  for (const s of prdSections) {
    const hit = blueprintSections.find((bp) => !usedBp.has(bp.name) && sectionMatches(s.hint, bp.normalized));
    if (hit) {
      matched.push({ prdId: s.id, prdTitle: s.title, bpName: hit.name });
      usedBp.add(hit.name);
    } else {
      missing.push({ prdId: s.id, prdTitle: s.title, hint: s.hint });
    }
  }
  const extra = blueprintSections.filter((bp) => !usedBp.has(bp.name)).map((bp) => bp.name);
  const coverage = prdSections.length === 0 ? 1 : matched.length / prdSections.length;
  const minPass = options.minPass ?? COVERAGE_MIN_PASS;
  return {
    prdSections,
    blueprintSections,
    matched,
    missing,
    extra,
    coverage,
    gateDecision: coverage >= minPass ? "pass" : "block",
    gateReason: coverage >= minPass ? `coverage ${(coverage * 100).toFixed(0)}% \u2265 ${(minPass * 100).toFixed(0)}% threshold` : `coverage ${(coverage * 100).toFixed(0)}% < ${(minPass * 100).toFixed(0)}% \u2014 ${missing.length}\uAC1C \uC139\uC158 \uB204\uB77D: ${missing.map((m) => m.prdTitle).slice(0, 5).join(", ")}`
  };
}
function enforceCoverageGate(prdText, blueprint, options = {}) {
  const result = checkCoverage(prdText, blueprint, options);
  if (result.gateDecision === "block") {
    const msg = [
      `\u{1F6AB} [Coverage Gate] Blueprint does NOT cover the PRD adequately.`,
      `   Coverage: ${(result.coverage * 100).toFixed(0)}%  (min: ${((options.minPass ?? COVERAGE_MIN_PASS) * 100).toFixed(0)}%)`,
      `   PRD sections (${result.prdSections.length}): ${result.prdSections.map((s) => s.title).join(", ")}`,
      `   Missing: ${result.missing.map((m) => m.prdTitle).join(", ")}`,
      ``,
      `   Action: either (a) extend the reference blueprint.json to include missing sections,`,
      `                  (b) update PRD scope to exclude these sections, or`,
      `                  (c) register a new reference that covers the PRD fully.`
    ].join("\n");
    throw new Error(msg);
  }
  return result;
}

// src/main/content-binder.ts
function lodashSet(obj, path, value) {
  const tokens = [...path.matchAll(/(\w+)|\[(\d+)\]/g)];
  let current = obj;
  for (let i = 0; i < tokens.length - 1; i++) {
    const [, key, idx] = tokens[i];
    current = idx !== void 0 ? current[Number(idx)] : current[key];
  }
  const last = tokens[tokens.length - 1];
  if (last[2] !== void 0) current[Number(last[2])] = value;
  else current[last[1]] = value;
}
var BIND_SYSTEM_PROMPT = `You are a content binder. Your ONLY task: map slot IDs to values from a PRD.

## Output
Respond with a single JSON object: { "slot.id": "value", ... }
- Only include slots whose values differ from defaults or are explicitly present in the PRD.
- Omit a slot \u2192 the default is kept.
- For slots whose values have a \`format\` (e.g. number_krw_comma), return raw data and the binder will format it.

## HARD RULES \u2014 STRICTLY FORBIDDEN
- DO NOT modify blueprint structure, color, layout, or any non-text property.
- DO NOT invent new slot IDs.
- DO NOT add explanations, comments, or markdown.
- DO NOT suggest improvements or alternatives.
- If PRD and reference default conflict on semantics (e.g. "\uBE4C\uB9B0 \uAE08\uC561" \u2192 "\uB0A9\uC785 \uC608\uC815\uC561"), KEEP THE REFERENCE DEFAULT unless PRD explicitly names the new term.

Return the JSON object and nothing else.`;
function buildBindPrompt(slots, prdText) {
  const slotList = slots.slots.map((s) => `  { id: "${s.id}", default: ${JSON.stringify(s.default)}${s.hint ? `, hint: ${JSON.stringify(s.hint)}` : ""} }`).join(",\n");
  return `# Reference Slots
The following slots are the only fields you may fill:

[
${slotList}
]

# PRD (user-provided document)

${prdText.length > 8e3 ? prdText.slice(0, 8e3) + "\n...[truncated]" : prdText}

# Your Response
JSON object of slot.id \u2192 value (only slots to override from PRD).`;
}
function applyFormat(value, format) {
  if (!format) return value;
  if (format === "number_krw_comma") {
    const n = Number(String(value).replace(/[^\d.-]/g, ""));
    if (isNaN(n)) return value;
    return n.toLocaleString("ko-KR");
  }
  if (format === "number_krw_signed") {
    const n = Number(String(value).replace(/[^\d.-]/g, ""));
    if (isNaN(n)) return value;
    const sign = n < 0 ? "\u2212" : "";
    return sign + Math.abs(n).toLocaleString("ko-KR");
  }
  return value;
}
function cloneDeep(x) {
  return JSON.parse(JSON.stringify(x));
}
async function loadReferencePackage(projectRoot, referenceId) {
  const refDir = (0, import_path2.join)(projectRoot, "docs", "references", referenceId);
  const [blueprint, slotsRaw, metaRaw] = await Promise.all([
    (0, import_promises2.readFile)((0, import_path2.join)(refDir, "blueprint.json"), "utf-8").then(JSON.parse),
    (0, import_promises2.readFile)((0, import_path2.join)(refDir, "slots.json"), "utf-8").then(JSON.parse),
    (0, import_promises2.readFile)((0, import_path2.join)(refDir, "meta.json"), "utf-8").then(JSON.parse)
  ]);
  return {
    referenceId,
    blueprint,
    slots: slotsRaw,
    meta: metaRaw
  };
}
async function bindContent(pkg, prdText, agentCall) {
  let rawMapping = {};
  try {
    rawMapping = await agentCall({
      systemPrompt: BIND_SYSTEM_PROMPT,
      userPrompt: buildBindPrompt(pkg.slots, prdText),
      responseFormat: "json_object"
    });
  } catch (err) {
    console.warn("[content-binder] Agent call failed, using all defaults:", err);
    rawMapping = {};
  }
  const blueprint = cloneDeep(pkg.blueprint);
  const applied = [];
  const skipped = [];
  for (const slot of pkg.slots.slots) {
    const rawValue = rawMapping[slot.id];
    if (rawValue !== void 0 && rawValue !== null && rawValue !== slot.default) {
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
function createStubAgent(mapping) {
  return async () => mapping;
}
async function bindReferenceToPRD(pkg, prdText, agentCall, options = {}) {
  const coverage = enforceCoverageGate(prdText, pkg.blueprint, {
    minPass: options.coverageMinPass
  });
  const bind = await bindContent(pkg, prdText, agentCall);
  return {
    coverage,
    finalBlueprint: bind.finalBlueprint,
    applied: bind.applied,
    skipped: bind.skipped,
    rawMapping: bind.rawMapping
  };
}

// scripts/e2e_clone_bind.ts
var PROJECT_ROOT = (0, import_path3.join)(__dirname, "..");
async function main() {
  const prdPath = process.argv[2] || "/Users/julee/Desktop/imin_home_PRD.md";
  console.log(`\u{1F4C4} PRD: ${prdPath}`);
  const prdText = await (0, import_promises3.readFile)(prdPath, "utf-8");
  console.log(`   ${prdText.length} chars, ${prdText.split("\n").length} lines
`);
  const prd = extractPRDFeatures(prdText, "imin_home_PRD.md");
  console.log(`\u{1F50E} Parsed PRD features:`);
  console.log(`   screenType: ${prd.screenType}`);
  console.log(`   brand: ${prd.brand}`);
  console.log(`   keywords (top 10): ${prd.keywords.slice(0, 10).join(", ")}
`);
  const match = await matchReference(prd, PROJECT_ROOT);
  console.log(`\u{1F3AF} matchReference:`);
  console.log(`   winner: ${match.referenceId}`);
  console.log(`   confidence: ${match.confidence.toFixed(3)}`);
  console.log(`   fallbackUsed: ${match.fallbackUsed}`);
  console.log(`   reasons: ${match.reasons.join("; ")}`);
  console.log(`   all scores:`);
  for (const s of match.allScores) {
    console.log(`     - ${s.referenceId}: ${s.score.toFixed(3)} [${s.reasons.slice(0, 2).join(", ")}]`);
  }
  console.log();
  if (isFallbackRequired(match)) {
    console.log(`\u274C confidence < 0.5 \u2192 pipeline would fall back to LLM creation.`);
    process.exit(0);
  }
  const pkg = await loadReferencePackage(PROJECT_ROOT, match.referenceId);
  console.log(`\u{1F4E6} Loaded reference package "${match.referenceId}":`);
  console.log(`   slots: ${pkg.slots.slots.length}`);
  console.log(`   blueprint root children: ${pkg.blueprint.children?.length ?? 0}
`);
  const stubAgent = createStubAgent({});
  try {
    const result = await bindReferenceToPRD(pkg, prdText, stubAgent);
    console.log(`\u2705 bindReferenceToPRD succeeded:`);
    console.log(`   coverage: ${(result.coverage.coverage * 100).toFixed(1)}% (${result.coverage.gateDecision})`);
    console.log(`   matched sections (${result.coverage.matched.length}):`);
    for (const m of result.coverage.matched) {
      console.log(`     - PRD "${m.prdTitle}" \u2194 BP "${m.bpName}"`);
    }
    if (result.coverage.missing.length > 0) {
      console.log(`   missing PRD sections (${result.coverage.missing.length}):`);
      for (const m of result.coverage.missing) {
        console.log(`     - ${m.prdTitle}`);
      }
    }
    console.log(`   applied slots: ${result.applied.length} (stub returns empty \u2192 all defaults kept)`);
    console.log(`   skipped slots: ${result.skipped.length}`);
    console.log(`   PRD sections parsed: ${result.coverage.prdSections.length}`);
    console.log(`   BP sections parsed: ${result.coverage.blueprintSections.length}`);
    const outPath = (0, import_path3.join)(PROJECT_ROOT, "scripts", "e2e_clone_bind_final.json");
    await (0, import_promises3.writeFile)(outPath, JSON.stringify(result.finalBlueprint, null, 2), "utf-8");
    console.log(`
\u{1F4BE} Final blueprint: ${outPath}`);
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.log(`
\u{1F6AB} bindReferenceToPRD threw (coverage gate or other):`);
    console.log(msg);
    process.exit(1);
  }
}
main().catch((e) => {
  console.error(e);
  process.exit(1);
});
