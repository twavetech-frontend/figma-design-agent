# Yoga 레이아웃 시뮬레이터 구현 계획

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Blueprint를 Figma에 보내기 전에 Yoga WASM으로 레이아웃을 메모리에서 사전 계산하여, post-fix 네트워크 왕복을 제거하고 빌드 속도/정확도를 개선한다.

**Architecture:** `yoga-layout` npm 패키지를 Electron main process에 통합하여, Blueprint JSON → Yoga 트리 → 레이아웃 계산 → 문제 탐지/자동 수정 파이프라인을 구축한다. `simulate_layout` MCP 도구로 노출하여 Python 클라이언트가 빌드 전에 호출할 수 있게 한다.

**Tech Stack:** yoga-layout 3.2.1 (Meta, 296KB WASM), TypeScript (tsup CJS, dynamic import), vitest, Python (figma_mcp_client.py)

**Yoga API 참고:** `yoga-layout/load` 모듈은 ESM named export만 제공. `loadYoga` 함수로 Yoga 인스턴스 로드. enum은 별도 named export (`Direction`, `FlexDirection`, `Justify`, `Align`, `Edge`, `Gutter`, `Wrap`, `Overflow`, `PositionType`, `MeasureMode`).

---

## 파일 구조

| 파일 | 역할 | 상태 |
|------|------|------|
| `src/main/yoga-simulator.ts` | Blueprint → Yoga 변환, 레이아웃 계산, 이슈 탐지 | 신규 |
| `src/main/yoga-simulator.test.ts` | 시뮬레이터 단위 테스트 | 신규 |
| `src/main/figma-mcp-embedded.ts` | `simulate_layout` MCP 도구 등록 | 수정 (L619 근처) |
| `scripts/figma_mcp_client.py` | `cmd_build`에 시뮬레이션 통합 | 수정 (L494-677) |
| `tsup.config.ts` | yoga-layout external 추가 | 수정 |
| `package.json` | yoga-layout + vitest 의존성 추가 | 수정 |

---

## Chunk 1: Yoga 시뮬레이터 코어

### Task 1: yoga-layout 패키지 설치 및 빌드 설정

**Files:**
- Modify: `package.json`
- Modify: `tsup.config.ts`

- [ ] **Step 1: yoga-layout + vitest 설치**

```bash
cd /Users/julee/figma-design-agent
npm install yoga-layout@3.2.1 --legacy-peer-deps
npm install -D vitest --legacy-peer-deps
```

`--legacy-peer-deps`는 `@anthropic-ai/claude-agent-sdk`의 zod@^4 peer dependency 충돌을 우회한다.

`package.json` scripts에 추가:
```json
"test": "vitest run",
"test:watch": "vitest"
```

- [ ] **Step 2: tsup.config.ts에 yoga-layout을 external로 추가**

yoga-layout은 ESM-only + WASM 포함 패키지이므로, tsup CJS 번들에 포함시키지 않고 런타임에 dynamic import로 로드한다. tsup은 prefix match를 지원하므로 `'yoga-layout'`만으로 `yoga-layout/load`도 자동 external 처리된다.

```typescript
// tsup.config.ts
external: [
  'electron',
  'ws',
  'sharp',
  'bufferutil',
  'utf-8-validate',
  'yoga-layout',  // ESM-only, dynamic import 사용 (yoga-layout/load 포함)
],
```

- [ ] **Step 3: dynamic import 동작 확인**

```bash
node -e "import('yoga-layout/load').then(m => m.loadYoga()).then(y => { const n = y.Node.create(); n.setWidth(100); n.setHeight(200); n.calculateLayout(undefined, undefined, 1); console.log('OK:', n.getComputedWidth(), n.getComputedHeight()); n.freeRecursive(); })"
```

Expected: `OK: 100 200`

주의: `m.loadYoga()` (named export), `1` = Direction.LTR, `freeRecursive()` 사용.

- [ ] **Step 4: 빌드 확인**

```bash
npm run build:main
```

Expected: 빌드 성공, yoga-layout 관련 에러 없음

- [ ] **Step 5: Commit**

```bash
git add package.json package-lock.json tsup.config.ts
git commit -m "feat: add yoga-layout dependency for layout simulation"
```

---

### Task 2: yoga-simulator.ts 코어 모듈 — 타입 + Yoga 로딩 + 매핑 헬퍼

**Files:**
- Create: `src/main/yoga-simulator.ts`

- [ ] **Step 1: 타입 정의 + Yoga 싱글턴 로더 + 매핑 헬퍼 작성**

```typescript
// src/main/yoga-simulator.ts

/**
 * Yoga WASM 기반 Blueprint 레이아웃 시뮬레이터.
 *
 * OpenPencil layout.ts의 Figma↔Yoga 매핑 로직을 참고하여 구현.
 * Figma에 보내기 전에 레이아웃을 사전 계산하고, FILL/HUG 이슈를 탐지/수정한다.
 */

// --- Types ---

export interface BlueprintNode {
  name?: string;
  type?: string;
  width?: number;
  height?: number;
  x?: number;
  y?: number;
  layoutSizingHorizontal?: string;
  layoutSizingVertical?: string;
  layoutPositioning?: string;
  autoLayout?: {
    layoutMode?: string;
    itemSpacing?: number;
    paddingTop?: number;
    paddingBottom?: number;
    paddingLeft?: number;
    paddingRight?: number;
    primaryAxisAlignItems?: string;
    counterAxisAlignItems?: string;
    clipsContent?: boolean;
    layoutWrap?: string;
  };
  text?: string;
  fontSize?: number | string;
  lineHeight?: number;
  children?: BlueprintNode[];
}

export interface SimulatedNode {
  name: string;
  path: string;
  width: number;
  height: number;
  x: number;
  y: number;
  sizing: { horizontal: string; vertical: string };
}

export interface LayoutIssue {
  path: string;
  name: string;
  type: 'FILL_REQUIRED' | 'ZERO_WIDTH_TEXT' | 'HEIGHT_OVERFLOW';
  message: string;
  fix?: { field: string; from: string; to: string };
}

export interface SimulationResult {
  nodes: SimulatedNode[];
  issues: LayoutIssue[];
  layout: {
    rootWidth: number;
    rootHeight: number;
    contentBottom: number;
    suggestedFabY: number | null;
    suggestedTabBarY: number | null;
    suggestedRootHeight: number | null;
  };
  fixedBlueprint: BlueprintNode | null;
  elapsed_ms: number;
}

// --- Yoga Singleton ---
// yoga-layout/load는 ESM named export만 제공: { loadYoga, Direction, ... }

type YogaMod = typeof import('yoga-layout/load');
type YogaInstance = Awaited<ReturnType<YogaMod['loadYoga']>>;

let _yoga: YogaInstance | null = null;
let _yogaMod: YogaMod | null = null;

export async function getYoga(): Promise<{ yoga: YogaInstance; mod: YogaMod }> {
  if (_yoga && _yogaMod) return { yoga: _yoga, mod: _yogaMod };
  _yogaMod = await import('yoga-layout/load') as YogaMod;
  _yoga = await _yogaMod.loadYoga();
  return { yoga: _yoga, mod: _yogaMod };
}

// --- Mapping helpers ---
// Enum 값은 mod에서 가져온다 (yoga 인스턴스에는 없음)

function mapJustify(mod: YogaMod, align?: string): number {
  switch (align) {
    case 'CENTER': return mod.Justify.Center;
    case 'MAX': return mod.Justify.FlexEnd;
    case 'SPACE_BETWEEN': return mod.Justify.SpaceBetween;
    default: return mod.Justify.FlexStart;
  }
}

function mapAlign(mod: YogaMod, align?: string): number {
  switch (align) {
    case 'CENTER': return mod.Align.Center;
    case 'MAX': return mod.Align.FlexEnd;
    case 'STRETCH': return mod.Align.Stretch;
    case 'BASELINE': return mod.Align.Baseline;
    default: return mod.Align.FlexStart;
  }
}

function configureContainer(mod: YogaMod, yogaNode: any, al: NonNullable<BlueprintNode['autoLayout']>) {
  const isRow = (al.layoutMode || 'VERTICAL') === 'HORIZONTAL';
  yogaNode.setFlexDirection(isRow ? mod.FlexDirection.Row : mod.FlexDirection.Column);

  if (al.layoutWrap === 'WRAP') yogaNode.setFlexWrap(mod.Wrap.Wrap);
  yogaNode.setJustifyContent(mapJustify(mod, al.primaryAxisAlignItems));
  yogaNode.setAlignItems(mapAlign(mod, al.counterAxisAlignItems));

  if (al.clipsContent) yogaNode.setOverflow(mod.Overflow.Hidden);

  if (al.paddingTop != null)    yogaNode.setPadding(mod.Edge.Top, al.paddingTop);
  if (al.paddingBottom != null) yogaNode.setPadding(mod.Edge.Bottom, al.paddingBottom);
  if (al.paddingLeft != null)   yogaNode.setPadding(mod.Edge.Left, al.paddingLeft);
  if (al.paddingRight != null)  yogaNode.setPadding(mod.Edge.Right, al.paddingRight);

  // Gap — HORIZONTAL: itemSpacing→Column gap, VERTICAL: itemSpacing→Row gap
  if (al.itemSpacing != null) {
    yogaNode.setGap(isRow ? mod.Gutter.Column : mod.Gutter.Row, al.itemSpacing);
  }
}

function setMainAxisSizing(mod: YogaMod, yogaNode: any, axis: 'width' | 'height', sizing: string | undefined, fixedValue: number | undefined) {
  if (sizing === 'FILL') {
    yogaNode.setFlexGrow(1);
    yogaNode.setFlexShrink(1);
    yogaNode.setFlexBasis(0);
  } else if (sizing === 'FIXED' && fixedValue != null) {
    if (axis === 'width') yogaNode.setWidth(fixedValue);
    else yogaNode.setHeight(fixedValue);
  }
  // HUG: 아무것도 안 함 (Yoga가 content 기반 자동 계산)
}

function setCrossAxisSizing(mod: YogaMod, yogaNode: any, axis: 'width' | 'height', sizing: string | undefined, fixedValue: number | undefined) {
  if (sizing === 'FILL') {
    yogaNode.setAlignSelf(mod.Align.Stretch);
    // FILL 교차축에서는 명시적 크기를 설정하지 않음 (stretch가 크기를 결정)
  } else if (sizing === 'FIXED' && fixedValue != null) {
    if (axis === 'width') yogaNode.setWidth(fixedValue);
    else yogaNode.setHeight(fixedValue);
  }
  // HUG: 아무것도 안 함
}
```

- [ ] **Step 2: Commit**

```bash
git add src/main/yoga-simulator.ts
git commit -m "feat: yoga-simulator types, loader, and Figma-Yoga mapping helpers"
```

---

### Task 3: Blueprint → Yoga 트리 변환 (`buildYogaTree`)

**Files:**
- Modify: `src/main/yoga-simulator.ts`

- [ ] **Step 1: buildYogaTree 재귀 함수 + 텍스트 추정 작성**

```typescript
// --- Build Yoga Tree (append to yoga-simulator.ts) ---

interface YogaTreeNode {
  yogaNode: any;
  blueprint: BlueprintNode;
  path: string;
  children: YogaTreeNode[];
}

function buildYogaTree(
  mod: YogaMod, yoga: YogaInstance,
  bp: BlueprintNode, parentLayoutMode: string | null, path: string
): YogaTreeNode {
  const yogaNode = yoga.Node.create();
  const children: YogaTreeNode[] = [];
  const al = bp.autoLayout;
  const isContainer = al && al.layoutMode;
  const nodeType = (bp.type || 'frame').toLowerCase();

  // 1. ABSOLUTE 노드 처리
  if (bp.layoutPositioning === 'ABSOLUTE') {
    yogaNode.setPositionType(mod.PositionType.Absolute);
    if (bp.x != null) yogaNode.setPosition(mod.Edge.Left, bp.x);
    if (bp.y != null) yogaNode.setPosition(mod.Edge.Top, bp.y);
    if (bp.width != null) yogaNode.setWidth(bp.width);
    if (bp.height != null) yogaNode.setHeight(bp.height);
  }

  // 2. 사이징 설정 (부모 auto-layout 기준, ABSOLUTE가 아닐 때)
  if (parentLayoutMode && bp.layoutPositioning !== 'ABSOLUTE') {
    const isParentRow = parentLayoutMode === 'HORIZONTAL';
    const hSizing = bp.layoutSizingHorizontal || inferHSizing(bp, parentLayoutMode);
    const vSizing = bp.layoutSizingVertical || inferVSizing(bp);

    // 교차축 FILL일 때는 해당 축의 명시적 크기를 설정하지 않음
    // (C5 fix: alignSelf(Stretch)와 setWidth가 충돌)
    if (isParentRow) {
      // width = 주축, height = 교차축
      setMainAxisSizing(mod, yogaNode, 'width', hSizing, bp.width);
      setCrossAxisSizing(mod, yogaNode, 'height', vSizing, bp.height);
      // 주축이 FIXED이고 명시적 width가 있으면 설정
      if (hSizing !== 'FILL' && bp.width != null) yogaNode.setWidth(bp.width);
    } else {
      // width = 교차축, height = 주축
      setCrossAxisSizing(mod, yogaNode, 'width', hSizing, bp.width);
      setMainAxisSizing(mod, yogaNode, 'height', vSizing, bp.height);
      // 주축이 FIXED이고 명시적 height가 있으면 설정
      if (vSizing !== 'FILL' && bp.height != null) yogaNode.setHeight(bp.height);
    }
  } else if (!parentLayoutMode) {
    // 루트 노드: 크기 직접 설정
    if (bp.width != null) yogaNode.setWidth(bp.width);
    if (bp.height != null) yogaNode.setHeight(bp.height);
  }

  // 3. auto-layout 컨테이너 설정
  if (isContainer) configureContainer(mod, yogaNode, al);

  // 4. 텍스트 노드 크기 추정
  if (nodeType === 'text' && bp.text) {
    const est = estimateTextSize(bp);
    if (!bp.width) yogaNode.setWidth(est.width);
    yogaNode.setHeight(est.height);
  }

  // 5. 자식 재귀
  const childLayoutMode = isContainer ? (al.layoutMode || 'VERTICAL') : null;
  if (bp.children) {
    for (let i = 0; i < bp.children.length; i++) {
      const childBp = bp.children[i];
      const childPath = `${path}/${childBp.name || `child${i}`}`;
      const childTree = buildYogaTree(mod, yoga, childBp, childLayoutMode, childPath);
      yogaNode.insertChild(childTree.yogaNode, i);
      children.push(childTree);
    }
  }

  return { yogaNode, blueprint: bp, path, children };
}

function inferHSizing(bp: BlueprintNode, parentLayoutMode: string): string | undefined {
  const nodeType = (bp.type || 'frame').toLowerCase();
  if (parentLayoutMode === 'VERTICAL' && (nodeType === 'frame' || nodeType === 'instance')) {
    return 'FILL';
  }
  return undefined;
}

function inferVSizing(bp: BlueprintNode): string | undefined {
  if (bp.autoLayout && !bp.height) return 'HUG';
  return undefined;
}

/** 텍스트 크기 추정 — 한글 전각 문자 고려 */
function estimateTextSize(bp: BlueprintNode): { width: number; height: number } {
  const text = bp.text || '';
  const fontSize = typeof bp.fontSize === 'string' ? parseInt(bp.fontSize) || 16 : (bp.fontSize || 16);
  const lineHeight = bp.lineHeight || Math.ceil(fontSize * 1.4);

  // 한글 포함 여부에 따른 글자 너비 조정
  const hasKorean = /[\uAC00-\uD7AF]/.test(text);
  const charWidth = fontSize * (hasKorean ? 0.95 : 0.6);
  const singleLineWidth = Math.ceil(text.length * charWidth);

  const maxWidth = bp.width || 361;  // 393 - 16*2 padding
  if (singleLineWidth > maxWidth) {
    const lines = Math.ceil(singleLineWidth / maxWidth);
    return { width: maxWidth, height: Math.ceil(lines * lineHeight) };
  }
  return { width: singleLineWidth, height: lineHeight };
}
```

- [ ] **Step 2: Commit**

```bash
git add src/main/yoga-simulator.ts
git commit -m "feat: buildYogaTree — Blueprint to Yoga tree with Korean text estimation"
```

---

### Task 4: 레이아웃 계산 + 이슈 탐지 (`simulateLayout`)

**Files:**
- Modify: `src/main/yoga-simulator.ts`

- [ ] **Step 1: 결과 수집 + 이슈 탐지 + 자동 수정**

```typescript
// --- Simulation (append to yoga-simulator.ts) ---

function collectResults(tree: YogaTreeNode): SimulatedNode[] {
  const results: SimulatedNode[] = [];
  function walk(node: YogaTreeNode) {
    results.push({
      name: node.blueprint.name || '(unnamed)',
      path: node.path,
      width: node.yogaNode.getComputedWidth(),
      height: node.yogaNode.getComputedHeight(),
      x: node.yogaNode.getComputedLeft(),
      y: node.yogaNode.getComputedTop(),
      sizing: {
        horizontal: node.blueprint.layoutSizingHorizontal || 'FIXED',
        vertical: node.blueprint.layoutSizingVertical || 'FIXED',
      },
    });
    for (const child of node.children) walk(child);
  }
  walk(tree);
  return results;
}

function detectIssues(tree: YogaTreeNode): LayoutIssue[] {
  const issues: LayoutIssue[] = [];
  const ICON_KEYWORDS = /icon|chevron|dot|indicator|vector|arrow/i;
  const SKIP_NAMES = /fab|tab\s*bar/i;
  const reported = new Set<string>();  // 중복 방지

  function walk(node: YogaTreeNode, parentLayoutMode: string | null, parentAlign?: string, isLastChild?: boolean) {
    const bp = node.blueprint;
    const name = bp.name || '';
    const nodeType = (bp.type || 'frame').toLowerCase();
    const hSizing = bp.layoutSizingHorizontal;
    const al = bp.autoLayout;
    const childLayoutMode = al?.layoutMode || null;
    const isAbsolute = bp.layoutPositioning === 'ABSOLUTE';

    // R1: VERTICAL 부모의 FRAME 자식이 FILL이 아닌 경우
    // SPACE_BETWEEN 부모의 마지막 HUG 자식은 제외
    const isSpaceBetweenLastHug = parentAlign === 'SPACE_BETWEEN' && isLastChild && (!hSizing || hSizing === 'HUG');
    if (parentLayoutMode === 'VERTICAL'
        && (nodeType === 'frame' || nodeType === 'component')
        && !isAbsolute
        && hSizing !== 'FILL'
        && !ICON_KEYWORDS.test(name)
        && !SKIP_NAMES.test(name)
        && (bp.width == null || bp.width > 60)
        && !isSpaceBetweenLastHug
        && !reported.has(node.path)) {
      reported.add(node.path);
      issues.push({
        path: node.path,
        name,
        type: 'FILL_REQUIRED',
        message: `FRAME '${name}' has ${hSizing || 'no'} horizontal sizing, should be FILL in VERTICAL parent`,
        fix: { field: 'layoutSizingHorizontal', from: hSizing || 'HUG', to: 'FILL' },
      });
    }

    // R2: 텍스트 너비 0 감지
    if (nodeType === 'text' && node.yogaNode.getComputedWidth() < 1) {
      issues.push({
        path: node.path,
        name,
        type: 'ZERO_WIDTH_TEXT',
        message: `TEXT '${name}' computed width is ${node.yogaNode.getComputedWidth()}px`,
      });
    }

    // 재귀
    const childAlign = al?.primaryAxisAlignItems;
    const childrenList = node.children;
    for (let i = 0; i < childrenList.length; i++) {
      walk(childrenList[i], childLayoutMode, childAlign, i === childrenList.length - 1);
    }
  }

  walk(tree, null);
  return issues;
}

function computeLayoutInfo(tree: YogaTreeNode): SimulationResult['layout'] {
  const rootYoga = tree.yogaNode;
  const rootWidth = rootYoga.getComputedWidth();
  let contentBottom = 0;
  let hasFab = false;
  let hasTabBar = false;

  for (const child of tree.children) {
    const name = (child.blueprint.name || '').toLowerCase();
    if (/fab/.test(name)) { hasFab = true; continue; }
    if (/tab\s*bar/.test(name)) { hasTabBar = true; continue; }
    if (child.blueprint.layoutPositioning !== 'ABSOLUTE') {
      const y = child.yogaNode.getComputedTop();
      const h = child.yogaNode.getComputedHeight();
      contentBottom = Math.max(contentBottom, y + h);
    }
  }

  let suggestedFabY: number | null = null;
  let suggestedTabBarY: number | null = null;
  if (hasFab) {
    suggestedFabY = contentBottom + 24;
    suggestedTabBarY = hasTabBar ? suggestedFabY + 44 + 16 : null;
  } else if (hasTabBar) {
    suggestedTabBarY = contentBottom + 24;
  }

  const suggestedRootHeight = suggestedTabBarY != null
    ? suggestedTabBarY + 73
    : (suggestedFabY != null ? suggestedFabY + 44 + 24 : contentBottom);

  return { rootWidth, rootHeight: rootYoga.getComputedHeight(), contentBottom, suggestedFabY, suggestedTabBarY, suggestedRootHeight };
}

function applyFixes(bp: BlueprintNode, issues: LayoutIssue[]): BlueprintNode {
  const fixed = JSON.parse(JSON.stringify(bp)) as BlueprintNode;
  const fixMap = new Map<string, LayoutIssue['fix']>();
  for (const issue of issues) {
    if (issue.fix && !fixMap.has(issue.path)) fixMap.set(issue.path, issue.fix);
  }

  function walk(node: BlueprintNode, path: string) {
    const fix = fixMap.get(path);
    if (fix) (node as any)[fix.field] = fix.to;
    if (node.children) {
      for (let i = 0; i < node.children.length; i++) {
        walk(node.children[i], `${path}/${node.children[i].name || `child${i}`}`);
      }
    }
  }
  walk(fixed, 'root');
  return fixed;
}
```

- [ ] **Step 2: 메인 `simulateLayout` 공개 함수 작성**

```typescript
// --- Public API (append to yoga-simulator.ts) ---

export async function simulateLayout(blueprint: BlueprintNode): Promise<SimulationResult> {
  const start = performance.now();
  const { yoga, mod } = await getYoga();

  const tree = buildYogaTree(mod, yoga, blueprint, null, 'root');

  if (blueprint.width) tree.yogaNode.setWidth(blueprint.width);
  else tree.yogaNode.setWidth(393);

  tree.yogaNode.calculateLayout(undefined, undefined, mod.Direction.LTR);

  const nodes = collectResults(tree);
  const issues = detectIssues(tree);
  const layout = computeLayoutInfo(tree);

  const fixedBlueprint = issues.some(i => i.fix) ? applyFixes(blueprint, issues) : null;

  // Yoga 메모리 해제 — freeRecursive로 안전하게 전체 트리 해제
  tree.yogaNode.freeRecursive();

  return { nodes, issues, layout, fixedBlueprint, elapsed_ms: Math.round(performance.now() - start) };
}
```

- [ ] **Step 3: Commit**

```bash
git add src/main/yoga-simulator.ts
git commit -m "feat: simulateLayout — layout computation, issue detection, auto-fix"
```

---

### Task 5: 단위 테스트

**Files:**
- Create: `src/main/yoga-simulator.test.ts`

- [ ] **Step 1: 테스트 작성**

```typescript
// src/main/yoga-simulator.test.ts
import { describe, it, expect } from 'vitest';
import { simulateLayout, type BlueprintNode } from './yoga-simulator';

describe('simulateLayout', () => {
  it('VERTICAL 레이아웃: FILL 자식의 width = 부모width - padding*2', async () => {
    const bp: BlueprintNode = {
      name: 'Root', type: 'frame', width: 393,
      autoLayout: { layoutMode: 'VERTICAL', paddingTop: 20, paddingBottom: 20, paddingLeft: 16, paddingRight: 16, itemSpacing: 12 },
      children: [
        { name: 'Section1', type: 'frame', height: 100, layoutSizingHorizontal: 'FILL' },
        { name: 'Section2', type: 'frame', height: 200, layoutSizingHorizontal: 'FILL' },
      ],
    };
    const result = await simulateLayout(bp);
    expect(result.layout.rootWidth).toBe(393);
    const s1 = result.nodes.find(n => n.name === 'Section1')!;
    expect(s1.width).toBe(361);  // 393 - 16*2
    expect(s1.height).toBe(100);
    const s2 = result.nodes.find(n => n.name === 'Section2')!;
    expect(s2.y).toBe(20 + 100 + 12);  // paddingTop + s1 + gap
    expect(result.issues).toHaveLength(0);
  });

  it('FILL 누락 FRAME → FILL_REQUIRED 이슈 탐지', async () => {
    const bp: BlueprintNode = {
      name: 'Root', type: 'frame', width: 393,
      autoLayout: { layoutMode: 'VERTICAL' },
      children: [{ name: 'BadSection', type: 'frame', height: 100 }],
    };
    const result = await simulateLayout(bp);
    const fillIssues = result.issues.filter(i => i.type === 'FILL_REQUIRED');
    expect(fillIssues.length).toBeGreaterThan(0);
    expect(fillIssues[0].fix?.to).toBe('FILL');
  });

  it('자동 수정된 fixedBlueprint 반환', async () => {
    const bp: BlueprintNode = {
      name: 'Root', type: 'frame', width: 393,
      autoLayout: { layoutMode: 'VERTICAL' },
      children: [{ name: 'Section', type: 'frame', height: 100 }],
    };
    const result = await simulateLayout(bp);
    expect(result.fixedBlueprint).not.toBeNull();
    expect(result.fixedBlueprint!.children![0].layoutSizingHorizontal).toBe('FILL');
  });

  it('이슈 없으면 fixedBlueprint는 null', async () => {
    const bp: BlueprintNode = {
      name: 'Root', type: 'frame', width: 393,
      autoLayout: { layoutMode: 'VERTICAL' },
      children: [{ name: 'Section', type: 'frame', height: 100, layoutSizingHorizontal: 'FILL' }],
    };
    const result = await simulateLayout(bp);
    expect(result.fixedBlueprint).toBeNull();
  });

  it('Tab Bar/FAB 위치 사전 계산', async () => {
    const bp: BlueprintNode = {
      name: 'Root', type: 'frame', width: 393,
      autoLayout: { layoutMode: 'VERTICAL', itemSpacing: 0 },
      children: [
        { name: 'Content', type: 'frame', height: 800, layoutSizingHorizontal: 'FILL' },
        { name: 'FAB', type: 'frame', width: 120, height: 44, layoutPositioning: 'ABSOLUTE' },
        { name: 'Tab Bar', type: 'frame', width: 393, height: 73, layoutPositioning: 'ABSOLUTE' },
      ],
    };
    const result = await simulateLayout(bp);
    expect(result.layout.contentBottom).toBe(800);
    expect(result.layout.suggestedFabY).toBe(824);
    expect(result.layout.suggestedTabBarY).toBe(884);
    expect(result.layout.suggestedRootHeight).toBe(957);
  });

  it('HORIZONTAL 캐로셀 레이아웃', async () => {
    const bp: BlueprintNode = {
      name: 'Carousel', type: 'frame', width: 393, height: 162,
      autoLayout: { layoutMode: 'HORIZONTAL', itemSpacing: 12, paddingLeft: 20, clipsContent: true },
      children: [
        { name: 'Banner1', type: 'frame', width: 353, height: 162 },
        { name: 'Banner2', type: 'frame', width: 353, height: 162 },
      ],
    };
    const result = await simulateLayout(bp);
    const b1 = result.nodes.find(n => n.name === 'Banner1')!;
    const b2 = result.nodes.find(n => n.name === 'Banner2')!;
    expect(b1.x).toBe(20);
    expect(b2.x).toBe(20 + 353 + 12);
  });

  it('SPACE_BETWEEN 마지막 HUG 자식은 FILL_REQUIRED 미탐지', async () => {
    const bp: BlueprintNode = {
      name: 'Root', type: 'frame', width: 393,
      autoLayout: { layoutMode: 'VERTICAL', primaryAxisAlignItems: 'SPACE_BETWEEN' },
      children: [
        { name: 'Main', type: 'frame', height: 100 },
        { name: 'Trailing', type: 'frame', height: 40 },  // 마지막 HUG → 보존
      ],
    };
    const result = await simulateLayout(bp);
    const trailingIssue = result.issues.find(i => i.name === 'Trailing');
    expect(trailingIssue).toBeUndefined();
  });

  it('50 노드 레이아웃: 50ms 이내', async () => {
    const children = Array.from({ length: 50 }, (_, i) => ({
      name: `Item${i}`, type: 'frame' as const, height: 56, layoutSizingHorizontal: 'FILL' as const,
    }));
    const bp: BlueprintNode = {
      name: 'Root', type: 'frame', width: 393,
      autoLayout: { layoutMode: 'VERTICAL', itemSpacing: 0 },
      children,
    };
    const result = await simulateLayout(bp);
    expect(result.elapsed_ms).toBeLessThan(50);
  });
});
```

- [ ] **Step 2: 테스트 실행**

```bash
npm test
```

Expected: 모든 테스트 PASS

- [ ] **Step 3: Commit**

```bash
git add src/main/yoga-simulator.test.ts
git commit -m "test: yoga-simulator unit tests — layout, issues, Tab Bar/FAB, carousel"
```

---

## Chunk 2: MCP 도구 등록 + Python 클라이언트 통합

### Task 6: `simulate_layout` MCP 도구 등록

**Files:**
- Modify: `src/main/figma-mcp-embedded.ts` (line 619 근처에 추가)

- [ ] **Step 1: figma-mcp-embedded.ts에 도구 추가**

`batch_build_screen` 바로 앞에 추가. `fixedBlueprint`는 이슈가 있을 때만 반환 (응답 크기 최적화).

```typescript
// src/main/figma-mcp-embedded.ts — batch_build_screen 전에 추가

import { simulateLayout } from './yoga-simulator';

reg('simulate_layout',
  'Simulate Blueprint layout using Yoga WASM. Returns detected issues, pre-computed Tab Bar/FAB positions, and auto-fixed Blueprint. Call BEFORE batch_build_screen.',
  {
    type: 'object',
    properties: {
      blueprint: { type: 'object', description: 'Blueprint JSON (same format as batch_build_screen)' },
    },
    required: ['blueprint'],
  },
  async (params) => {
    const result = await simulateLayout(params.blueprint as any);
    return {
      issues_count: result.issues.length,
      issues: result.issues,
      layout: result.layout,
      fixedBlueprint: result.fixedBlueprint,  // null if no issues
      elapsed_ms: result.elapsed_ms,
      node_count: result.nodes.length,
    };
  }
);
```

- [ ] **Step 2: 빌드 확인**

```bash
npm run build:main
```

- [ ] **Step 3: Commit**

```bash
git add src/main/figma-mcp-embedded.ts
git commit -m "feat: register simulate_layout MCP tool"
```

---

### Task 7: Python 클라이언트 `cmd_build`에 시뮬레이션 통합

**Files:**
- Modify: `scripts/figma_mcp_client.py` (line 494-677)

- [ ] **Step 1: `cmd_build`에 simulate_layout 호출 추가**

`resolve_tokens_in_blueprint()` 직후, 이미지 사전 생성 직전에 추가.

```python
# scripts/figma_mcp_client.py — cmd_build 함수 내
# resolve_tokens_in_blueprint 이후에 추가

# ── Step 3.5: Yoga 레이아웃 시뮬레이션 ──
sim_result = None
print("\n[SIM] Yoga 레이아웃 시뮬레이션 중...")
sim_start = time.time()
try:
    sim_content = call_tool("simulate_layout", {"blueprint": blueprint})
    # MCP 응답 파싱
    if isinstance(sim_content, list):
        for item in sim_content:
            if isinstance(item, dict) and item.get("type") == "text":
                import json as _json
                try:
                    sim_result = _json.loads(item["text"])
                except Exception:
                    pass
    elif isinstance(sim_content, dict):
        sim_result = sim_content

    if sim_result:
        issues_count = sim_result.get("issues_count", 0)
        elapsed = sim_result.get("elapsed_ms", 0)
        layout_info = sim_result.get("layout", {})

        if issues_count > 0:
            print(f"[SIM] {issues_count}개 이슈 탐지 ({elapsed}ms)")
            for issue in sim_result.get("issues", [])[:10]:
                print(f"  - [{issue.get('type')}] {issue.get('message')}")
            fixed = sim_result.get("fixedBlueprint")
            if fixed:
                blueprint = fixed
                print(f"[SIM] Blueprint 자동 수정 적용 완료")
        else:
            print(f"[SIM] 이슈 없음 ({elapsed}ms)")

        if layout_info.get("suggestedRootHeight"):
            print(f"[SIM] 사전 계산: contentBottom={layout_info.get('contentBottom')}, "
                  f"fabY={layout_info.get('suggestedFabY')}, "
                  f"tabY={layout_info.get('suggestedTabBarY')}, "
                  f"rootH={layout_info.get('suggestedRootHeight')}")

    print(f"[SIM] 완료 ({time.time() - sim_start:.1f}s)")
except Exception as e:
    print(f"[SIM] 시뮬레이션 실패 (무시하고 계속): {e}")
```

- [ ] **Step 2: `cmd_post_fix`에 사전 계산값 전달**

`cmd_post_fix` 시그니처 수정 (기본값 None이므로 기존 CLI 호출과 호환):

```python
def cmd_post_fix(root_node_id: str, pre_computed_layout: dict = None):
```

`cmd_build` 내 호출 수정:

```python
sim_layout = sim_result.get("layout") if sim_result else None
cmd_post_fix(root_id, pre_computed_layout=sim_layout)
```

`_fix_layout_and_positions` 내 위치 갱신(get_nodes_info 재조회) 부분에서 사전 계산값 우선 사용:

```python
# _fix_layout_and_positions 함수 시작 부분에 추가
if pre_computed_layout and pre_computed_layout.get("suggestedFabY"):
    print(f"  [PRECOMP] 사전 계산값 사용")
    # content_bottom, fab_y, tab_y, root_height를 사전 계산값으로 설정
    # get_nodes_info 재조회 건너뜀
```

주의: `_collect_tree`는 여전히 필요 (FILL 수정 등 다른 단계에서 tree를 사용). 위치 계산의 `get_nodes_info` 재조회만 건너뛴다.

- [ ] **Step 3: Commit**

```bash
git add scripts/figma_mcp_client.py
git commit -m "feat: integrate Yoga simulation into cmd_build pipeline"
```

---

### Task 8: 빌드 + 통합 테스트

- [ ] **Step 1: 전체 빌드 + 단위 테스트**

```bash
npm run build && npm test
```

Expected: 빌드 성공, 테스트 PASS

- [ ] **Step 2: MCP 서버 통합 테스트**

Electron 앱 실행 후:

```bash
python3 scripts/figma_mcp_client.py call simulate_layout '{"blueprint": {"name": "Test", "type": "frame", "width": 393, "autoLayout": {"layoutMode": "VERTICAL"}, "children": [{"name": "Section", "type": "frame", "height": 100}]}}'
```

Expected: `FILL_REQUIRED` 이슈 탐지, `fixedBlueprint`에 `layoutSizingHorizontal: "FILL"` 적용

- [ ] **Step 3: 실제 Blueprint 빌드 테스트**

```bash
python3 scripts/figma_mcp_client.py build scripts/blueprint_assembled_*.json
```

Expected: `[SIM]` 로그 출력, post-fix 시간 단축

- [ ] **Step 4: Commit**

```bash
git add src/main/yoga-simulator.ts src/main/yoga-simulator.test.ts src/main/figma-mcp-embedded.ts scripts/figma_mcp_client.py package.json tsup.config.ts
git commit -m "feat: Yoga layout simulator — complete integration"
```

---

## 예상 효과

| 지표 | 현재 | 시뮬레이터 적용 후 |
|------|------|-------------------|
| FILL 이슈 → Figma 수정 | 10-40초 (네트워크) | ~0ms (Blueprint 사전 수정) |
| Tab Bar/FAB 위치 계산 | 5-10초 (get_nodes_info) | ~0ms (사전 계산) |
| post-fix 총 시간 | 20-80초 | **10-30초 예상** (50%+ 단축) |
| Blueprint 검증 정확도 | 5가지 규칙 | 5가지 + Yoga 레이아웃 검증 |

## 리뷰 반영 사항

- **C1-C4**: Yoga API 접근 패턴 수정 — `{ yoga, mod }` 분리, `mod.Direction.LTR` 사용
- **C5**: FILL 교차축 + 명시적 크기 충돌 해결 — FILL이면 해당 축 크기 미설정
- **I1**: `freeRecursive()` 사용 (수동 재귀 해제 제거)
- **I3**: R1/R3 중복 탐지 → `reported` Set으로 통합, R3 제거
- **I6**: `fixedBlueprint` — 이슈 없으면 `null` 반환 (응답 크기 최적화)
- **S1**: 한글 텍스트 추정 (`charWidth = fontSize * 0.95`)
- **S3**: SPACE_BETWEEN 마지막 HUG 자식 보존

## 향후 확장 (이번 범위 아님)

- **전략 B**: post-fix 전체를 Yoga 시뮬레이션으로 대체
- **전략 A**: FIXED 좌표 모드 (프로토타입용 빠른 빌드)
- **batch_set_layout_sizing**: post-fix의 개별 FILL 수정을 배치 도구로 통합
