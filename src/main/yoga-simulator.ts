/**
 * Yoga WASM 기반 Blueprint 레이아웃 시뮬레이터.
 * OpenPencil layout.ts의 Figma↔Yoga 매핑 로직을 참고하여 구현.
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

type YogaMod = typeof import('yoga-layout/load');
type YogaInstance = Awaited<ReturnType<YogaMod['loadYoga']>>;

let _yoga: YogaInstance | null = null;
let _yogaMod: YogaMod | null = null;

async function getYoga(): Promise<{ yoga: YogaInstance; mod: YogaMod }> {
  if (_yoga && _yogaMod) return { yoga: _yoga, mod: _yogaMod };
  _yogaMod = await import('yoga-layout/load') as YogaMod;
  _yoga = await _yogaMod.loadYoga();
  return { yoga: _yoga, mod: _yogaMod };
}

// --- Mapping helpers ---

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
  if (al.paddingTop != null) yogaNode.setPadding(mod.Edge.Top, al.paddingTop);
  if (al.paddingBottom != null) yogaNode.setPadding(mod.Edge.Bottom, al.paddingBottom);
  if (al.paddingLeft != null) yogaNode.setPadding(mod.Edge.Left, al.paddingLeft);
  if (al.paddingRight != null) yogaNode.setPadding(mod.Edge.Right, al.paddingRight);
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
}

function setCrossAxisSizing(mod: YogaMod, yogaNode: any, axis: 'width' | 'height', sizing: string | undefined, fixedValue: number | undefined) {
  if (sizing === 'FILL') {
    yogaNode.setAlignSelf(mod.Align.Stretch);
  } else if (sizing === 'FIXED' && fixedValue != null) {
    if (axis === 'width') yogaNode.setWidth(fixedValue);
    else yogaNode.setHeight(fixedValue);
  }
}

// --- Build Yoga Tree ---

interface YogaTreeNode {
  yogaNode: any;
  blueprint: BlueprintNode;
  path: string;
  children: YogaTreeNode[];
}

function buildYogaTree(mod: YogaMod, yoga: YogaInstance, bp: BlueprintNode, parentLayoutMode: string | null, path: string): YogaTreeNode {
  const yogaNode = yoga.Node.create();
  const children: YogaTreeNode[] = [];
  const al = bp.autoLayout;
  const isContainer = al && al.layoutMode;
  const nodeType = (bp.type || 'frame').toLowerCase();

  if (bp.layoutPositioning === 'ABSOLUTE') {
    yogaNode.setPositionType(mod.PositionType.Absolute);
    if (bp.x != null) yogaNode.setPosition(mod.Edge.Left, bp.x);
    if (bp.y != null) yogaNode.setPosition(mod.Edge.Top, bp.y);
    if (bp.width != null) yogaNode.setWidth(bp.width);
    if (bp.height != null) yogaNode.setHeight(bp.height);
  }

  if (parentLayoutMode && bp.layoutPositioning !== 'ABSOLUTE') {
    const isParentRow = parentLayoutMode === 'HORIZONTAL';
    const hSizing = bp.layoutSizingHorizontal || inferHSizing(bp, parentLayoutMode);
    const vSizing = bp.layoutSizingVertical || inferVSizing(bp);

    if (isParentRow) {
      setMainAxisSizing(mod, yogaNode, 'width', hSizing, bp.width);
      setCrossAxisSizing(mod, yogaNode, 'height', vSizing, bp.height);
      if (hSizing !== 'FILL' && bp.width != null) yogaNode.setWidth(bp.width);
    } else {
      setCrossAxisSizing(mod, yogaNode, 'width', hSizing, bp.width);
      setMainAxisSizing(mod, yogaNode, 'height', vSizing, bp.height);
      if (vSizing !== 'FILL' && bp.height != null) yogaNode.setHeight(bp.height);
    }
  } else if (!parentLayoutMode) {
    if (bp.width != null) yogaNode.setWidth(bp.width);
    if (bp.height != null) yogaNode.setHeight(bp.height);
  }

  if (isContainer) configureContainer(mod, yogaNode, al!);

  if (nodeType === 'text' && bp.text) {
    const est = estimateTextSize(bp);
    if (!bp.width) yogaNode.setWidth(est.width);
    yogaNode.setHeight(est.height);
  }

  const childLayoutMode = isContainer ? (al!.layoutMode || 'VERTICAL') : null;
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
  if (parentLayoutMode === 'VERTICAL' && (nodeType === 'frame' || nodeType === 'instance')) return 'FILL';
  return undefined;
}

function inferVSizing(bp: BlueprintNode): string | undefined {
  if (bp.autoLayout && !bp.height) return 'HUG';
  return undefined;
}

function estimateTextSize(bp: BlueprintNode): { width: number; height: number } {
  const text = bp.text || '';
  const fontSize = typeof bp.fontSize === 'string' ? parseInt(bp.fontSize) || 16 : (bp.fontSize || 16);
  const lineHeight = bp.lineHeight || Math.ceil(fontSize * 1.4);
  const hasKorean = /[\uAC00-\uD7AF]/.test(text);
  const charWidth = fontSize * (hasKorean ? 0.95 : 0.6);
  const singleLineWidth = Math.ceil(text.length * charWidth);
  const maxWidth = bp.width || 361;
  if (singleLineWidth > maxWidth) {
    const lines = Math.ceil(singleLineWidth / maxWidth);
    return { width: maxWidth, height: Math.ceil(lines * lineHeight) };
  }
  return { width: singleLineWidth, height: lineHeight };
}

// --- Simulation ---

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
  const HUG_PRESERVE = /tag|badge|chip|pill|label|indicator|underline|divider/i;
  const reported = new Set<string>();

  function walk(node: YogaTreeNode, parentLayoutMode: string | null, parentAlign?: string, isLastChild?: boolean) {
    const bp = node.blueprint;
    const name = bp.name || '';
    const nodeType = (bp.type || 'frame').toLowerCase();
    const hSizing = bp.layoutSizingHorizontal;
    const al = bp.autoLayout;
    const childLayoutMode = al?.layoutMode || null;
    const isAbsolute = bp.layoutPositioning === 'ABSOLUTE';

    const isSpaceBetweenLastHug = parentAlign === 'SPACE_BETWEEN' && isLastChild && (!hSizing || hSizing === 'HUG');
    if (parentLayoutMode === 'VERTICAL'
        && (nodeType === 'frame' || nodeType === 'component')
        && !isAbsolute
        && hSizing !== 'FILL'
        && !ICON_KEYWORDS.test(name)
        && !SKIP_NAMES.test(name)
        && !HUG_PRESERVE.test(name)
        && hSizing !== 'HUG'  // 명시적 HUG는 의도적이므로 보존
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

    if (nodeType === 'text' && node.yogaNode.getComputedWidth() < 1) {
      issues.push({
        path: node.path,
        name,
        type: 'ZERO_WIDTH_TEXT',
        message: `TEXT '${name}' computed width is ${node.yogaNode.getComputedWidth()}px`,
      });
    }

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

// --- Public API ---

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

  tree.yogaNode.freeRecursive();

  return { nodes, issues, layout, fixedBlueprint, elapsed_ms: Math.round(performance.now() - start) };
}
