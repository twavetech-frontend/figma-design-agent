/**
 * Embedded MCP Tools — Direct function calls, no stdio transport
 *
 * Converts existing 58+ MCP tools into a tool registry that the
 * AgentOrchestrator can call directly. Each tool calls FigmaWSServer.sendCommand()
 * instead of going through MCP protocol.
 */

import { z, ZodObject, ZodRawShape } from 'zod';
import { FigmaWSServer } from './figma-ws-server';
import type { ToolDefinition } from '../shared/types';
import { getIcons, getVariants, getTokenMap, syncTokensIfNeeded, type VariantEntry } from '../shared/ds-data';

import { getIconSvg, getIconSvgAsync, resolveIconFile } from './untitled-icons';
import { simulateLayout } from './yoga-simulator';
import { buildScreenJS } from './renderers/orchestrate';
import type { ScreenSpec } from './renderers/types';

// Re-export for convenience
export type { ToolDefinition };

/**
 * Build the complete tool registry from FigmaWSServer
 */
// Track the last agent-built root frame for cleanup on next build
let lastBuiltRootId: string | null = null;

export function buildToolRegistry(figmaWS: FigmaWSServer): Map<string, ToolDefinition> {
  const tools = new Map<string, ToolDefinition>();

  // Helper to register a tool
  function reg(name: string, description: string, schema: Record<string, unknown>, handler: (params: Record<string, unknown>) => Promise<unknown>, options?: { timeoutMs?: number }) {
    tools.set(name, { name, description, inputSchema: schema, handler, timeoutMs: options?.timeoutMs });
  }

  // Helper: send command to Figma plugin
  async function cmd(command: string, params: Record<string, unknown> = {}, timeoutMs?: number) {
    return figmaWS.sendCommand(command, params, timeoutMs);
  }

  // ============================================================
  // Shared critique body — used by `critique_design` (explicit) AND
  // by `build_from_spec` (auto-trigger after every build). Must be a
  // self-contained `(async (root) => {...})` JS expression so the same
  // body can be invoked from either call site without a separate plugin
  // round-trip.
  //
  // Mental model: every screen the agent ships to a non-designer user is
  // automatically self-graded across 5 dimensions. Result is attached to
  // the build response so the agent reports a score + actionable issues
  // instead of asking the user to evaluate.
  // ============================================================
  const critiqueScreenJsBody = `(async (root) => {
const texts = []; const frames = []; let depth = 0;
const PLACEHOLDER_RE = /^(Title|Trailing|Label|Mon|Heading|Lorem ipsum|placeholder|Sample text|0)$/i;
// inInst flag: nodes inside a component instance are the master's responsibility.
// Skip them for spacing/grid checks (otherwise Status Bar 1.5px paddings, DS atom
// strokes, etc. flood the report). TEXT nodes are still collected (placeholder
// leaks must be caught regardless of master/instance origin).
const walk = (n, d, inInst) => {
  if (d > depth) depth = d;
  if (n.type === "TEXT") {
    let fontSize = 0, fontWeight = "Regular";
    try { fontSize = typeof n.fontSize === "number" ? n.fontSize : 0; } catch (e) {}
    try { fontWeight = (n.fontName && n.fontName.style) || "Regular"; } catch (e) {}
    texts.push({ id: n.id, name: n.name, characters: n.characters || "", fontSize, fontWeight, inInst });
  } else if (n.type === "FRAME" || n.type === "COMPONENT" || n.type === "INSTANCE") {
    // An INSTANCE node itself is master-owned — mark its frame as inInst so spacing
    // check skips it. Children are also inInst via childInInst below.
    const ownInInst = inInst || (n.type === "INSTANCE");
    frames.push({
      id: n.id, name: n.name, depth: d, inInst: ownInInst,
      pl: n.paddingLeft || 0, pr: n.paddingRight || 0,
      pt: n.paddingTop || 0, pb: n.paddingBottom || 0,
      gap: n.itemSpacing || 0,
    });
  }
  const childInInst = inInst || (n.type === "INSTANCE");
  if ("children" in n && Array.isArray(n.children)) for (const c of n.children) walk(c, d + 1, childInInst);
};
walk(root, 0, false);

// Dim 1: Anti-slop — placeholder + slop emoji + invented metrics + filler + Tailwind AI accent
// Patterns lifted from open-design's lint-artifact.ts (Apache 2.0).
const SLOP_EMOJI_RE = /[\\u2728\\u26A1\\u2705\\u2B50\\uD83D\\uDE80\\uD83C\\uDFAF\\uD83D\\uDD25\\uD83D\\uDCA1\\uD83D\\uDCC8\\uD83C\\uDFA8\\uD83D\\uDEE1\\uD83C\\uDF1F\\uD83D\\uDCAA\\uD83C\\uDF89\\uD83D\\uDC4B\\uD83D\\uDE4C\\uD83C\\uDFC6]/;
const INVENTED_METRIC_RE = /(10[xX×]\\s+(faster|better|easier)|100[xX×]\\s+(faster|better)|99\\.\\d+%\\s+uptime|zero[- ]downtime|3[xX×]\\s+more\\s+(productive|efficient))/i;
const FILLER_RE = /(feature\\s+(one|two|three|1|2|3)|lorem\\s+ipsum|dolor\\s+sit\\s+amet|placeholder\\s+text|sample\\s+content|Sample text)/i;
// Tailwind violet/indigo raw RGB ranges — common AI default accent
const isAiSlopPurple = (c) => {
  if (!c) return false;
  // Tailwind violet 500-900: rgb(168,85,247)..rgb(88,28,135) → r 0.34-0.66, g 0.10-0.34, b 0.53-0.97
  if (c.r > 0.30 && c.r < 0.70 && c.g > 0.05 && c.g < 0.35 && c.b > 0.55) return true;
  // Tailwind indigo 500-900: rgb(99,102,241)..rgb(49,46,129) → r 0.19-0.39, g 0.18-0.40, b 0.51-0.95
  if (c.r > 0.18 && c.r < 0.42 && c.g > 0.18 && c.g < 0.42 && c.b > 0.50) return true;
  return false;
};
const slopIssues = [];
for (const t of texts) {
  const txt = t.characters.trim();
  if (PLACEHOLDER_RE.test(txt)) {
    slopIssues.push({ severity: "P0", nodeId: t.id, nodeName: t.name, msg: "Placeholder text visible: " + JSON.stringify(t.characters) });
  } else if (SLOP_EMOJI_RE.test(t.characters)) {
    slopIssues.push({ severity: "P1", nodeId: t.id, nodeName: t.name, msg: "AI-slop emoji in copy: " + JSON.stringify(t.characters.slice(0, 40)) });
  } else if (INVENTED_METRIC_RE.test(txt)) {
    slopIssues.push({ severity: "P0", nodeId: t.id, nodeName: t.name, msg: "Invented marketing metric (must come from PRD): " + JSON.stringify(txt.slice(0, 60)) });
  } else if (FILLER_RE.test(txt)) {
    slopIssues.push({ severity: "P0", nodeId: t.id, nodeName: t.name, msg: "Filler/Lorem text: " + JSON.stringify(txt.slice(0, 60)) });
  } else if (txt.length === 0) {
    slopIssues.push({ severity: "P3", nodeId: t.id, nodeName: t.name, msg: "Empty TEXT node (likely hidden master leftover)" });
  }
}
// Detect Tailwind violet/indigo raw RGB on any frame fill (DS-bound paints are skipped)
for (const f of frames) {
  // Skip frames inside instances (master responsibility)
  if (f.inInst) continue;
}
// Note: raw-RGB scan happens in checkText below where fills are read with bound-variable awareness.
const slopScore = Math.max(0, 100 - slopIssues.filter(i => i.severity === "P0").length * 25 - slopIssues.filter(i => i.severity === "P1").length * 8);

// Dim 2: Typography scale
const sizeSet = new Set(); const weightSet = new Set();
for (const t of texts) { if (t.fontSize > 0) sizeSet.add(t.fontSize); if (t.fontWeight) weightSet.add(t.fontWeight); }
const uniqueSizes = [...sizeSet].sort((a, b) => a - b);
const uniqueWeights = [...weightSet];
const typoIssues = [];
if (uniqueSizes.length > 12) typoIssues.push({ severity: "P1", msg: "Type scale chaos: " + uniqueSizes.length + " unique font sizes (>12). Sizes: " + uniqueSizes.join(", ") });
else if (uniqueSizes.length > 10) typoIssues.push({ severity: "P2", msg: "Type scale dense: " + uniqueSizes.length + " unique font sizes (10-tier scale recommended)." });
if (uniqueWeights.length > 5) typoIssues.push({ severity: "P2", msg: "Weight chaos: " + uniqueWeights.length + " font weights" });
const typoScore = Math.max(0, 100 - typoIssues.filter(i => i.severity === "P1").length * 20 - typoIssues.filter(i => i.severity === "P2").length * 8);

// Dim 3: Spacing 2-grid (even numbers; 4-grid was too strict for design intent
// like 14px-padding cards). Only for screen-level frames — INSTANCE descendants
// are the master's responsibility and get skipped.
// P2 = odd value (1, 3, 5, 7…). P3 = sub-pixel (e.g. 1.5px from cloned DS).
const gridViolations = [];
const subPixel = [];
const screenFrames = frames.filter(f => !f.inInst);
for (const f of screenFrames) {
  for (const [k, val] of [["pl", f.pl], ["pr", f.pr], ["pt", f.pt], ["pb", f.pb], ["gap", f.gap]]) {
    if (val <= 0) continue;
    if (val !== Math.floor(val)) subPixel.push({ nodeName: f.name, prop: k, value: val });
    else if (val % 2 !== 0) gridViolations.push({ nodeName: f.name, prop: k, value: val });
  }
}
const oddCount = gridViolations.length;
const spacingIssues = [];
if (oddCount > 0) spacingIssues.push({ severity: "P2", msg: "Off-grid spacing: " + oddCount + " paddings/gaps with odd pixel values (use even numbers)", samples: gridViolations.slice(0, 5) });
if (subPixel.length > 0) spacingIssues.push({ severity: "P3", msg: "Sub-pixel spacing: " + subPixel.length + " paddings/gaps below 1px (often from cloned DS atoms)", samples: subPixel.slice(0, 3) });
const spacingScore = Math.max(0, 100 - oddCount * 8);

// Dim 4: Contrast — alpha-aware composition + DS semantic awareness
const lum = (c) => {
  const f = (x) => x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4);
  return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
};
const ratio = (fg, bg) => { const L1 = lum(fg), L2 = lum(bg); return (Math.max(L1, L2) + 0.05) / (Math.min(L1, L2) + 0.05); };
const blend = (base, paint) => {
  if (!paint || paint.type !== "SOLID") return base;
  const a = (typeof paint.opacity === "number" ? paint.opacity : 1) * (paint.visible === false ? 0 : 1);
  if (a <= 0) return base; if (a >= 1) return paint.color;
  return { r: paint.color.r * a + base.r * (1 - a), g: paint.color.g * a + base.g * (1 - a), b: paint.color.b * a + base.b * (1 - a) };
};
const composeFills = (fills, base) => {
  if (!Array.isArray(fills)) return base;
  let out = base; for (const f of fills) if (f && f.visible !== false) out = blend(out, f);
  return out;
};
const intentLowContrast = async (n) => {
  try {
    const bv = n.boundVariables;
    if (!bv || !bv.fills) return false;
    const arr = Array.isArray(bv.fills) ? bv.fills : [bv.fills];
    for (const ref of arr) {
      const ids = Array.isArray(ref) ? ref : [ref];
      for (const r of ids) {
        const id = r && r.id;
        if (!id) continue;
        const v = await figma.variables.getVariableByIdAsync(id);
        if (!v) continue;
        const name = (v.name || "").toLowerCase();
        if (/(text|fg|color)[\\\\/-]?(secondary|tertiary|quaternary|disabled|placeholder|caption|hint|muted|inverse-disabled|brand-tertiary|on-disabled)/.test(name)) return true;
        if (/(secondary|tertiary|quaternary|disabled|placeholder|caption|hint|muted)$/.test(name)) return true;
      }
    }
  } catch (e) {}
  return false;
};
const contrastIssues = []; const contrastInfos = [];
const checkText = async (n, parentBg) => {
  if (n.type === "TEXT") {
    let fgPaint = null;
    try { if (Array.isArray(n.fills) && n.fills[0]?.type === "SOLID") fgPaint = n.fills[0]; } catch (e) {}
    if (fgPaint && parentBg) {
      const fg = blend(parentBg, fgPaint);
      const r = ratio(fg, parentBg);
      if (r > 0 && r < 4.5) {
        const intent = await intentLowContrast(n);
        if (intent) contrastInfos.push({ severity: "P3", nodeId: n.id, nodeName: n.name, ratio: Math.round(r * 100) / 100, intent: "DS semantic low-contrast (intentional)" });
        else if (r < 3.0) contrastIssues.push({ severity: "P1", nodeId: n.id, nodeName: n.name, ratio: Math.round(r * 100) / 100 });
        else contrastIssues.push({ severity: "P2", nodeId: n.id, nodeName: n.name, ratio: Math.round(r * 100) / 100 });
      }
    }
  }
  let bgHere = parentBg;
  try {
    if ((n.type === "FRAME" || n.type === "INSTANCE" || n.type === "COMPONENT") && Array.isArray(n.fills)) {
      bgHere = composeFills(n.fills, parentBg);
    }
  } catch (e) {}
  if ("children" in n && Array.isArray(n.children)) for (const c of n.children) await checkText(c, bgHere);
};
await checkText(root, { r: 1, g: 1, b: 1 });
const contrastScore = Math.max(0, 100 - contrastIssues.filter(i => i.severity === "P1").length * 10 - contrastIssues.filter(i => i.severity === "P2").length * 2);

// Dim 5: Hierarchy
const heads = texts.filter(t => /Bold|Semi/.test(t.fontWeight) && t.fontSize >= 14);
const headSizes = [...new Set(heads.map(h => h.fontSize))].sort((a, b) => b - a);
const hierIssues = [];
if (heads.length >= 4 && headSizes.length === 1) {
  hierIssues.push({ severity: "P1", msg: "Flat hierarchy: " + heads.length + " bold headings all same size (" + headSizes[0] + "px). Use 2-3 size tiers." });
}
const hierScore = Math.max(0, 100 - hierIssues.filter(i => i.severity === "P1").length * 25);

// Aggregate (anti-slop weighted 2x, hierarchy 1.5x)
const overall = Math.round((slopScore * 2 + typoScore + spacingScore + contrastScore + hierScore * 1.5) / 6.5);
return {
  score: overall,
  dimensions: {
    antiSlop:   { score: slopScore,    issues: slopIssues.slice(0, 30) },
    typography: { score: typoScore,    issues: typoIssues, uniqueSizes, uniqueWeights },
    spacing:    { score: spacingScore, issues: spacingIssues, oddCount },
    contrast:   { score: contrastScore, issues: contrastIssues.slice(0, 20), infos: contrastInfos.slice(0, 20) },
    hierarchy:  { score: hierScore,    issues: hierIssues, headingSizes: headSizes, headingCount: heads.length },
  },
  stats: { textCount: texts.length, frameCount: frames.length, depth },
};
})`;


  // ============================================================
  // Document Tools
  // ============================================================

  reg('join_channel', 'Join a Figma document channel for communication', {
    type: 'object',
    properties: {
      channel: { type: 'string', description: 'Channel name to join' }
    },
    required: ['channel']
  }, async (params) => {
    await figmaWS.joinChannel(params.channel as string);
    return { success: true, channel: params.channel };
  });

  reg('get_document_info', 'Get information about the current Figma document', {
    type: 'object', properties: {}
  }, async () => cmd('get_document_info'));

  reg('get_selection', 'Get the current selection in Figma', {
    type: 'object', properties: {}
  }, async () => cmd('get_selection'));

  reg('get_node_info', 'Get detailed information about a specific node', {
    type: 'object',
    properties: {
      nodeId: { type: 'string', description: 'Node ID to inspect' }
    },
    required: ['nodeId']
  }, async (params) => cmd('get_node_info', params));

  reg('get_nodes_info', 'Get information about multiple nodes', {
    type: 'object',
    properties: {
      nodeIds: { type: 'array', items: { type: 'string' }, description: 'Array of node IDs' }
    },
    required: ['nodeIds']
  }, async (params) => cmd('get_nodes_info', params));

  reg('get_styles', 'Get all styles in the document', {
    type: 'object', properties: {}
  }, async () => cmd('get_styles'));

  reg('get_local_components', 'Get all local components', {
    type: 'object', properties: {}
  }, async () => cmd('get_local_components'));

  reg('get_local_component_sets', 'Get all local component sets (variants)', {
    type: 'object',
    properties: {},
  }, async () => cmd('get_local_component_sets'));

  reg('get_remote_components', 'Get remote/library components', {
    type: 'object', properties: {}
  }, async () => cmd('get_remote_components'));

  reg('get_pages', 'Get all pages in the document', {
    type: 'object', properties: {}
  }, async () => cmd('get_pages'));

  reg('manage_pages', 'Create, rename, or delete pages', {
    type: 'object',
    properties: {
      action: { type: 'string', enum: ['create', 'rename', 'delete'] },
      name: { type: 'string' },
      newName: { type: 'string' },
      pageId: { type: 'string' }
    },
    required: ['action']
  }, async (params) => cmd('manage_pages', params));

  reg('scan_text_nodes', 'Scan text nodes in a subtree', {
    type: 'object',
    properties: {
      nodeId: { type: 'string', description: 'Root node to scan' }
    },
    required: ['nodeId']
  }, async (params) => cmd('scan_text_nodes', params));

  reg('export_node_as_image', 'Export a node as an image', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' },
      format: { type: 'string', enum: ['PNG', 'JPG', 'SVG', 'PDF'] },
      scale: { type: 'number' }
    },
    required: ['nodeId']
  }, async (params) => cmd('export_node_as_image', params));

  // ============================================================
  // Creation Tools
  // ============================================================

  reg('create_rectangle', 'Create a rectangle', {
    type: 'object',
    properties: {
      x: { type: 'number' }, y: { type: 'number' },
      width: { type: 'number' }, height: { type: 'number' },
      name: { type: 'string' }, parentId: { type: 'string' }
    },
    required: ['x', 'y', 'width', 'height']
  }, async (params) => cmd('create_rectangle', params));

  reg('create_frame', 'Create a frame', {
    type: 'object',
    properties: {
      x: { type: 'number' }, y: { type: 'number' },
      width: { type: 'number' }, height: { type: 'number' },
      name: { type: 'string' }, parentId: { type: 'string' }
    },
    required: ['x', 'y', 'width', 'height']
  }, async (params) => cmd('create_frame', params));

  reg('create_text', 'Create a text node', {
    type: 'object',
    properties: {
      x: { type: 'number' }, y: { type: 'number' },
      text: { type: 'string' }, fontSize: { type: 'number' },
      fontWeight: { type: 'number' }, fontColor: { type: 'object' },
      fontName: { type: 'string' }, name: { type: 'string' },
      parentId: { type: 'string' }, width: { type: 'number' },
      textAlignHorizontal: { type: 'string' },
      textAlignVertical: { type: 'string' },
      letterSpacing: { type: 'number' },
      lineHeight: { type: 'number' },
      textAutoResize: { type: 'string' },
      maxLines: { type: 'number' }
    },
    required: ['x', 'y', 'text']
  }, async (params) => {
    // Replace <br> with Unicode Line Separator
    if (typeof params.text === 'string') {
      params = { ...params, text: (params.text as string).replace(/<br>/g, '\u2028') };
    }
    return cmd('create_text', params);
  });

  reg('create_shape', 'Create a polygon or star shape', {
    type: 'object',
    properties: {
      type: { type: 'string', enum: ['POLYGON', 'STAR'] },
      x: { type: 'number' }, y: { type: 'number' },
      width: { type: 'number' }, height: { type: 'number' },
      pointCount: { type: 'number' }, name: { type: 'string' },
      parentId: { type: 'string' }
    },
    required: ['type', 'x', 'y', 'width', 'height']
  }, async (params) => cmd('create_shape', params));

  // ============================================================
  // Modification Tools
  // ============================================================

  reg('move_node', 'Move a node to new coordinates', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' }, x: { type: 'number' }, y: { type: 'number' }
    },
    required: ['nodeId', 'x', 'y']
  }, async (params) => cmd('move_node', params));

  reg('resize_node', 'Resize a node', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' }, width: { type: 'number' }, height: { type: 'number' }
    },
    required: ['nodeId', 'width', 'height']
  }, async (params) => cmd('resize_node', params));

  reg('delete_node', 'Delete a node', {
    type: 'object',
    properties: { nodeId: { type: 'string' } },
    required: ['nodeId']
  }, async (params) => cmd('delete_node', params));

  reg('set_fill_color', 'Set fill color of a node', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' },
      r: { type: 'number' }, g: { type: 'number' },
      b: { type: 'number' }, a: { type: 'number' }
    },
    required: ['nodeId', 'r', 'g', 'b']
  }, async (params) => {
    const { nodeId, r, g, b, a, ...rest } = params as Record<string, number | string>;
    return cmd('set_fill_color', { nodeId, color: { r, g, b, a: a ?? 1 }, ...rest });
  });

  reg('set_stroke_color', 'Set stroke color of a node', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' },
      r: { type: 'number' }, g: { type: 'number' },
      b: { type: 'number' }, a: { type: 'number' },
      strokeWeight: { type: 'number' },
      strokeTopWeight: { type: 'number', description: 'Individual top stroke weight' },
      strokeBottomWeight: { type: 'number', description: 'Individual bottom stroke weight' },
      strokeLeftWeight: { type: 'number', description: 'Individual left stroke weight' },
      strokeRightWeight: { type: 'number', description: 'Individual right stroke weight' }
    },
    required: ['nodeId', 'r', 'g', 'b']
  }, async (params) => {
    const { nodeId, r, g, b, a, strokeWeight, ...rest } = params as Record<string, number | string>;
    return cmd('set_stroke_color', { nodeId, color: { r, g, b, a: a ?? 1 }, strokeWeight: strokeWeight ?? 1, ...rest });
  });

  reg('set_corner_radius', 'Set corner radius', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' },
      radius: { type: 'number' },
      topLeftRadius: { type: 'number' },
      topRightRadius: { type: 'number' },
      bottomLeftRadius: { type: 'number' },
      bottomRightRadius: { type: 'number' }
    },
    required: ['nodeId']
  }, async (params) => cmd('set_corner_radius', params));

  reg('set_auto_layout', 'Set auto layout on a frame', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' },
      layoutMode: { type: 'string', enum: ['HORIZONTAL', 'VERTICAL', 'NONE'] },
      itemSpacing: { type: 'number' },
      paddingTop: { type: 'number' }, paddingBottom: { type: 'number' },
      paddingLeft: { type: 'number' }, paddingRight: { type: 'number' },
      primaryAxisAlignItems: { type: 'string' },
      counterAxisAlignItems: { type: 'string' },
      layoutWrap: { type: 'string' },
      clipsContent: { type: 'boolean', description: 'Clip content that overflows the frame' }
    },
    required: ['nodeId', 'layoutMode']
  }, async (params) => cmd('set_auto_layout', params));

  reg('set_effects', 'Set effects (shadow, blur) on a node', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' },
      effects: { type: 'array' }
    },
    required: ['nodeId', 'effects']
  }, async (params) => cmd('set_effects', params));

  reg('set_effect_style_id', 'Set effect style ID on a node', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' },
      styleId: { type: 'string' }
    },
    required: ['nodeId', 'styleId']
  }, async (params) => cmd('set_effect_style_id', params));

  reg('set_layout_sizing', 'Set layout sizing mode', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' },
      horizontal: { type: 'string', enum: ['FIXED', 'HUG', 'FILL'] },
      vertical: { type: 'string', enum: ['FIXED', 'HUG', 'FILL'] }
    },
    required: ['nodeId']
  }, async (params) => {
    const normalized = { ...params } as Record<string, unknown>;
    if (params.horizontal) normalized.layoutSizingHorizontal = params.horizontal;
    if (params.vertical) normalized.layoutSizingVertical = params.vertical;
    return cmd('set_layout_sizing', normalized);
  });

  reg('set_layout_positioning', 'Set layout positioning (AUTO or ABSOLUTE) on a node within an auto-layout parent', {
    type: 'object',
    properties: {
      nodeId: { type: 'string', description: 'Node ID' },
      layoutPositioning: { type: 'string', enum: ['AUTO', 'ABSOLUTE'], description: 'Positioning mode' },
      constraints: {
        type: 'object',
        properties: {
          horizontal: { type: 'string', enum: ['MIN', 'CENTER', 'MAX', 'STRETCH', 'SCALE'] },
          vertical: { type: 'string', enum: ['MIN', 'CENTER', 'MAX', 'STRETCH', 'SCALE'] }
        },
        description: 'Constraints for absolute positioning'
      }
    },
    required: ['nodeId']
  }, async (params) => cmd('set_layout_positioning', params));

  reg('rename_node', 'Rename a node', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' }, name: { type: 'string' }
    },
    required: ['nodeId', 'name']
  }, async (params) => cmd('rename_node', params));

  reg('set_selection_colors', 'Set colors on selection or node', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' },
      fillColor: { type: 'object' },
      strokeColor: { type: 'object' }
    },
    required: ['nodeId']
  }, async (params) => cmd('set_selection_colors', params));

  // ============================================================
  // Text Tools
  // ============================================================

  reg('set_text_content', 'Set text content of a text node', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' }, text: { type: 'string' }
    },
    required: ['nodeId', 'text']
  }, async (params) => {
    if (typeof params.text === 'string') {
      params = { ...params, text: (params.text as string).replace(/<br>/g, '\u2028') };
    }
    return cmd('set_text_content', params);
  });

  reg('set_text_properties', 'Set text properties', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' },
      fontSize: { type: 'number' },
      fontWeight: { type: 'number' },
      fontName: { type: 'string' },
      letterSpacing: { type: 'number' },
      lineHeight: { type: 'number' },
      textAlignHorizontal: { type: 'string' },
      textAlignVertical: { type: 'string' },
      textAutoResize: { type: 'string' },
      maxLines: { type: 'number' },
      fontColor: { type: 'object' }
    },
    required: ['nodeId']
  }, async (params) => cmd('set_text_properties', params));

  reg('set_font_size', 'Set font size', {
    type: 'object',
    properties: { nodeId: { type: 'string' }, fontSize: { type: 'number' } },
    required: ['nodeId', 'fontSize']
  }, async (params) => cmd('set_font_size', params));

  reg('set_font_weight', 'Set font weight', {
    type: 'object',
    properties: { nodeId: { type: 'string' }, fontWeight: { type: 'number' } },
    required: ['nodeId', 'fontWeight']
  }, async (params) => cmd('set_font_weight', params));

  reg('set_font_name', 'Set font family', {
    type: 'object',
    properties: { nodeId: { type: 'string' }, fontName: { type: 'string' } },
    required: ['nodeId', 'fontName']
  }, async (params) => cmd('set_font_name', params));

  reg('set_letter_spacing', 'Set letter spacing', {
    type: 'object',
    properties: { nodeId: { type: 'string' }, letterSpacing: { type: 'number' } },
    required: ['nodeId', 'letterSpacing']
  }, async (params) => cmd('set_letter_spacing', params));

  reg('set_line_height', 'Set line height', {
    type: 'object',
    properties: { nodeId: { type: 'string' }, lineHeight: { type: 'number' } },
    required: ['nodeId', 'lineHeight']
  }, async (params) => cmd('set_line_height', params));

  reg('set_paragraph_spacing', 'Set paragraph spacing', {
    type: 'object',
    properties: { nodeId: { type: 'string' }, paragraphSpacing: { type: 'number' } },
    required: ['nodeId', 'paragraphSpacing']
  }, async (params) => cmd('set_paragraph_spacing', params));

  reg('set_text_case', 'Set text case', {
    type: 'object',
    properties: { nodeId: { type: 'string' }, textCase: { type: 'string' } },
    required: ['nodeId', 'textCase']
  }, async (params) => cmd('set_text_case', params));

  reg('set_text_decoration', 'Set text decoration', {
    type: 'object',
    properties: { nodeId: { type: 'string' }, textDecoration: { type: 'string' } },
    required: ['nodeId', 'textDecoration']
  }, async (params) => cmd('set_text_decoration', params));

  reg('set_text_align', 'Set text alignment', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' },
      textAlignHorizontal: { type: 'string' },
      textAlignVertical: { type: 'string' }
    },
    required: ['nodeId']
  }, async (params) => cmd('set_text_align', params));

  reg('set_text_style_id', 'Apply a text style by ID', {
    type: 'object',
    properties: { nodeId: { type: 'string' }, styleId: { type: 'string' } },
    required: ['nodeId', 'styleId']
  }, async (params) => cmd('set_text_style_id', params));

  reg('get_styled_text_segments', 'Get styled text segments', {
    type: 'object',
    properties: { nodeId: { type: 'string' } },
    required: ['nodeId']
  }, async (params) => cmd('get_styled_text_segments', params));

  reg('load_font_async', 'Preload a font for use', {
    type: 'object',
    properties: { family: { type: 'string' }, style: { type: 'string' } },
    required: ['family']
  }, async (params) => cmd('load_font_async', params));

  reg('set_multiple_text_contents', 'Set text content on multiple nodes', {
    type: 'object',
    properties: {
      entries: { type: 'array', items: { type: 'object' } }
    },
    required: ['entries']
  }, async (params) => cmd('set_multiple_text_contents', params));

  // ============================================================
  // Component Tools
  // ============================================================

  reg('clone_node', 'Clone a node', {
    type: 'object',
    properties: { nodeId: { type: 'string' } },
    required: ['nodeId']
  }, async (params) => cmd('clone_node', params));

  reg('group_nodes', 'Group nodes together', {
    type: 'object',
    properties: {
      nodeIds: { type: 'array', items: { type: 'string' } },
      name: { type: 'string' }
    },
    required: ['nodeIds']
  }, async (params) => cmd('group_nodes', params));

  reg('ungroup_nodes', 'Ungroup a group node', {
    type: 'object',
    properties: { nodeId: { type: 'string' } },
    required: ['nodeId']
  }, async (params) => cmd('ungroup_nodes', params));

  reg('flatten_node', 'Flatten a node', {
    type: 'object',
    properties: { nodeId: { type: 'string' } },
    required: ['nodeId']
  }, async (params) => cmd('flatten_node', params));

  reg('insert_child', 'Insert a node as child of another', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' }, parentId: { type: 'string' },
      index: { type: 'number' }
    },
    required: ['nodeId', 'parentId']
  }, async (params) => cmd('insert_child', params));

  reg('create_component_instance', 'Create an instance of a component', {
    type: 'object',
    properties: {
      componentKey: { type: 'string' }, x: { type: 'number' }, y: { type: 'number' },
      parentId: { type: 'string' }
    },
    required: ['componentKey', 'x', 'y']
  }, async (params) => cmd('create_component_instance', params));

  reg('get_instance_properties', 'Get properties of a component instance', {
    type: 'object',
    properties: { nodeId: { type: 'string' } },
    required: ['nodeId']
  }, async (params) => cmd('get_instance_properties', params));

  reg('set_instance_properties', 'Set properties on a component instance', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' },
      properties: { type: 'object' }
    },
    required: ['nodeId', 'properties']
  }, async (params) => cmd('set_instance_properties', params));

  reg('create_component_from_node', 'Convert a node to a component', {
    type: 'object',
    properties: { nodeId: { type: 'string' } },
    required: ['nodeId']
  }, async (params) => cmd('create_component_from_node', params));

  reg('scan_instances_for_swap', 'Scan component instances for swap targets', {
    type: 'object',
    properties: { nodeId: { type: 'string' } },
    required: ['nodeId']
  }, async (params) => cmd('scan_instances_for_swap', params));

  // ============================================================
  // Variable & Binding Tools
  // ============================================================

  reg('get_local_variables', 'Get local variables from document', {
    type: 'object',
    properties: { includeLibrary: { type: 'boolean' } },
  }, async (params) => cmd('get_local_variables', params));

  reg('get_bound_variables', 'Get bound variables on a node', {
    type: 'object',
    properties: { nodeId: { type: 'string' } },
    required: ['nodeId']
  }, async (params) => cmd('get_bound_variables', params));

  reg('set_bound_variables', 'Bind variables to a node', {
    type: 'object',
    properties: {
      nodeId: { type: 'string' },
      bindings: { type: 'object' }
    },
    required: ['nodeId', 'bindings']
  }, async (params) => cmd('set_bound_variables', params));

  reg('set_image_fill', 'Set image fill on a node. imageData must be base64-encoded PNG/JPEG. URL is NOT supported.', {
    type: 'object',
    properties: {
      nodeId: { type: 'string', description: 'Target node ID' },
      imageData: { type: 'string', description: 'Base64-encoded image data (PNG or JPEG). Required.' },
      scaleMode: { type: 'string', description: 'FILL, FIT, CROP, or TILE' }
    },
    required: ['nodeId', 'imageData']
  }, async (params) => cmd('set_image_fill', params));

  // ============================================================
  // Batch Tools
  // ============================================================

  reg('batch_execute', 'Execute multiple Figma commands in one call', {
    type: 'object',
    properties: {
      operations: { type: 'array', items: { type: 'object' } }
    },
    required: ['operations']
  }, async (params) => {
    // Same logic as existing batch_execute
    const operations = params.operations as Array<{
      op: string; id?: string; parentRef?: string; params: Record<string, unknown>;
    }>;
    const refMap: Record<string, string> = {};
    const results: unknown[] = [];

    for (const operation of operations) {
      try {
        const resolvedParams = { ...operation.params };

        if (operation.parentRef) {
          const resolved = refMap[operation.parentRef];
          if (!resolved) throw new Error(`Unresolved parentRef: ${operation.parentRef}`);
          resolvedParams.parentId = resolved;
        }

        for (const [key, value] of Object.entries(resolvedParams)) {
          if (typeof value === 'string' && value.startsWith('$') && refMap[value]) {
            resolvedParams[key] = refMap[value];
          }
        }

        const normalized = normalizeParams(operation.op, resolvedParams as Record<string, unknown>);
        const result = await cmd(operation.op, normalized);
        const figmaId = extractId(result);

        if (operation.id && figmaId) {
          refMap[operation.id] = figmaId;
        }

        results.push({ op: operation.op, success: true, id: operation.id, figmaId });
      } catch (error) {
        results.push({
          op: operation.op, success: false,
          error: error instanceof Error ? error.message : String(error)
        });
      }
    }
    return { results, refMap };
  }, { timeoutMs: 310_000 }); // 5min: 여러 operation 순차 실행

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
        fixedBlueprint: result.fixedBlueprint,
        elapsed_ms: result.elapsed_ms,
        node_count: result.nodes.length,
      };
    }
  );

  reg('batch_build_screen', `Build a complete Figma screen from a single JSON tree. Creates all nodes recursively in one call AND auto-binds DS variables when *Var fields are present.

🚨 WIREFRAME FIDELITY — DO NOT EMBELLISH

When the user gives you a wireframe (low-fi sketch with grey blocks/text/no real colors), your job is to translate the **information structure** into a polished DS-tokenized screen — NOT to invent visual hierarchy that wasn't there.

- If the wireframe shows N identical cards in grey → render N identical cards using the SAME fillVar (typically "bg-secondary"). DO NOT pick one to highlight with bg-brand-* "for visual interest". The wireframe author already decided they should be peers. Forced hierarchy is the #1 cause of "your design looks worse than the wireframe".
- If the wireframe shows a grey filter chip with bold text → that is a "currently-selected" indicator using TEXT WEIGHT, not a brand fill. Render with fillVar "bg-secondary" + textColorVar "text-primary" + fontWeight 700. NOT bg-brand-section + text-brand-primary (that produces purple-on-purple invisible text).
- If the wireframe shows an outline pill (border + thin text, no fill color) → keep it outlined: fillVar "bg-primary" + strokeVar "border-secondary" + textColorVar "text-tertiary". Do NOT convert to filled brand chip.
- Brand color budget per screen: usually 1-2 accents max (e.g. FAB + active tab indicator + maybe the active step in a progress bar). If you find yourself adding a 3rd brand-colored element, stop and reconsider — you are over-decorating.

🎨 TOKEN COMBO RULES — contrast safety

The following combos produce unreadable text and are auto-corrected by the enhancer; do not rely on the auto-correct, write the right combo from the start:

- bg-brand-* (solid/section) + textColorVar "text-brand-*"  →  WRONG (purple on purple). Use textColorVar "text-white" or "text-primary_on-brand"
- bg-secondary / bg-tertiary + textColorVar "text-secondary"  →  too low contrast for body text. Use "text-primary"
- bg-primary (white) + textColorVar "text-white"  →  invisible. Use "text-primary"

Reference table for active/selected indicators:
- Selected chip (light grey wireframe)        → fillVar bg-secondary,    textColorVar text-primary, fontWeight 700
- Selected tab (bottom nav active)            → no fill change,           textColorVar text-brand-primary, fontWeight 700, icon iconColor brand
- Featured card (only when wireframe shows it via fill change) → fillVar bg-brand-primary or bg-brand-section, textColorVar text-white
- Selected day in calendar                    → fillVar bg-brand-solid,   textColorVar text-white

⭐ USE *Var FIELDS, NOT RAW HEX, FOR ANY VALUE THAT MAPS TO A DS TOKEN

Every fill/stroke/text-color/cornerRadius/spacing/padding that should be tied to the design system MUST be expressed via a *Var field with the semantic-token name. The build pipeline looks the token up in TOKEN_MAP.json, fills the raw value automatically, AND calls batch_bind_variables right after the build so the resulting Figma node is variable-linked (light/dark mode safe). Raw RGB you write by hand will NOT auto-bind because raw _Primitives are excluded from binding candidates.

Token *Var fields (preferred over raw fill/stroke/fontColor/cornerRadius/itemSpacing/padding):
- fillVar:         frame/rectangle/ellipse fill          → use bg-* token (e.g. "bg-primary", "bg-secondary", "bg-tertiary", "bg-quaternary", "bg-brand-primary")
- strokeVar:       frame/rectangle stroke                → use border-* token (e.g. "border-primary", "border-secondary")
- textColorVar:    text node fontColor                   → use text-* token (e.g. "text-primary", "text-secondary", "text-tertiary", "text-brand-primary", "text-white")
- cornerRadiusVar: frame/rectangle cornerRadius          → use radius-* token (e.g. "radius-md", "radius-lg")
- itemSpacingVar:  autoLayout itemSpacing                → use spacing-* token
- paddingVar:      autoLayout padding (all four sides)   → use spacing-* token

Category rules (CRITICAL — sweep matches strictly by category):
- frame fill         → bg-*       (Colors/Background/*)
- icon / button fill → use type:"instance" with the DS Button component (raw fg-* fills should be rare)
- stroke             → border-*   (Colors/Border/*)
- text fill          → text-*     (Colors/Text/*)
- A bg-* token on a text fill (or vice-versa) will not bind. Match category and field.

Token-name resolution accepts (in order): full figmaPath ("Colors/Background/bg-primary"), CSS-var key ("--colors-background-bg-primary"), or leaf name ("bg-primary"). Leaf name is preferred — shortest and unambiguous.

Reference-first workflow (use Read first, do NOT compose from scratch):
- Before authoring a Blueprint, Read docs/references/imin-home/blueprint.json (or the closest reference under docs/references/) and clone the matching section subtree, replacing only text content. Do NOT invent your own card hierarchy / icon treatment / list-item structure — the references encode hundreds of validated micro-decisions you cannot reproduce from scratch.

Node types and their properties:
- frame: x, y, width, height, name, fill({r,g,b,a}), fillVar, stroke({r,g,b,a}), strokeVar, strokeWeight, cornerRadius, cornerRadiusVar, autoLayout({layoutMode,paddingTop,paddingBottom,paddingLeft,paddingRight,paddingHorizontal,paddingVertical,padding,itemSpacing,primaryAxisAlignItems,counterAxisAlignItems,layoutWrap}), itemSpacingVar, paddingVar, layoutSizingHorizontal(FILL|HUG|FIXED), layoutSizingVertical(FILL|HUG|FIXED), effects([{type,color,offset,radius,spread}]), imageFill({url,scaleMode}), clipsContent, statusBar (root only — true→DS Status Bar instance auto-injected as first child), children[]
- text: x, y, name, text, fontSize, fontWeight(100-900), fontFamily("Pretendard"), fontColor({r,g,b,a}), textColorVar, textAlignHorizontal(LEFT|CENTER|RIGHT), textAutoResize(WIDTH_AND_HEIGHT|HEIGHT|TRUNCATE), lineHeight, letterSpacing, layoutSizingHorizontal, layoutSizingVertical
- rectangle: x, y, width, height, name, fill, fillVar, stroke, strokeVar, strokeWeight, cornerRadius, cornerRadiusVar, layoutSizingHorizontal, layoutSizingVertical, imageFill
- ellipse: x, y, width, height, name, fill, fillVar, stroke, strokeVar, layoutSizingHorizontal, layoutSizingVertical
- instance: x, y, name, component (semantic, e.g. "Button") + variant (e.g. "Size=lg, Hierarchy=Primary"), or componentKey (direct), width, height, layoutSizingHorizontal, layoutSizingVertical, text (auto-set on main text), textOverrides({suffix: text})
- clone: name, sourceNodeId (REQUIRED), width, height, layoutSizingHorizontal, layoutSizingVertical
- icon: name (icon name — DS v1 or Lucide names accepted), size (default 24), iconColor({r,g,b,a})

Status Bar auto-injection: root frame with statusBar:true → DS Status Bar instance auto-prepended. Do NOT draw status bar manually.
textOverrides (instance only): { "suffix": "new text" } — Sets text on instance children using Suffix Map.
imageFill: { url: "https://..." | base64, scaleMode?: "FILL"|"FIT" } — Downloads and applies image as fill.
layoutSizingHorizontal/Vertical: FILL to stretch to parent, HUG to fit content, FIXED for explicit size.
Colors (raw fallback): { r: 0-1, g: 0-1, b: 0-1, a?: 0-1 } — only when there is genuinely no DS token for the value.

Result: returns rootId, screenshot, and (when *Var fields were used) tokenBindCount + tokenBindResult. Inspect tokenBindCount to confirm DS bindings landed.`, {
    type: 'object',
    properties: {
      blueprint: {
        type: 'object',
        description: 'Root node blueprint with children tree. Use *Var fields (fillVar/strokeVar/textColorVar/cornerRadiusVar/itemSpacingVar/paddingVar) for any value that maps to a DS token — they auto-fill the raw value AND auto-bind the variable post-build. Use raw fill/stroke/etc. only when no DS token applies.'
      },
      parentId: {
        type: 'string',
        description: 'Optional parent node ID. When set, builds inside the existing parent (section build) and skips auto-deletion of previous root frame.'
      }
    },
    required: ['blueprint']
  }, async (params) => {
    // Pre-flight: ensure Figma plugin is connected before long operation
    if (!figmaWS.isConnected) {
      throw new Error('Figma plugin is not connected. Please check the plugin is running.');
    }

    const hasParentId = !!(params as Record<string, unknown>).parentId;

    // ═══════════════════════════════════════════════════════════════════
    // RULE 1 enforcement (mirror of build_from_spec gate). Without this,
    // the agent bypasses RULE 1 by routing through batch_build_screen
    // — exactly what happened in the 2026-05-03 fresh-session re-test.
    // Section builds (parentId set) are exempt; otherwise discoverySource
    // must be present in the blueprint root.
    // ═══════════════════════════════════════════════════════════════════
    const blueprintRaw = params.blueprint as Record<string, unknown> | undefined;
    if (!hasParentId) {
      const ds = blueprintRaw && typeof blueprintRaw === 'object'
        ? (blueprintRaw as Record<string, unknown>).discoverySource
        : undefined;
      if (typeof ds !== 'string' || ds.length === 0 || !/^(wireframe|skill|form|skip):/.test(ds)) {
        throw new Error([
          'batch_build_screen REJECTED: blueprint.discoverySource is required for full-screen builds.',
          '',
          'Use build_from_spec instead — it is the preferred path. If you must use',
          'batch_build_screen, declare how you decided what to build:',
          '  - "wireframe:<nodeId>"    (wireframe attached → RULE 0)',
          '  - "skill:<skillId>"       (matched docs/skills/<id>/spec.json)',
          '  - "form:<key=val,...>"    (RULE 1 mode B — user answered form)',
          '  - "skip:<reason>"         (user said "just build, skip questions")',
          '',
          'If wireframe is NOT attached and PRD is text-only, FIRST emit AskUserQuestion',
          'with the 7-item discovery form (output / mode / activeTab / data / scale /',
          'emphasis / constraints) and WAIT for the user response. Then build with',
          'discoverySource: "form:<key=val,...>".',
          '',
          'Section builds (parentId set) are exempt from this gate.',
        ].join('\n'));
      }
    }

    // Auto-check for DS token updates before building
    await syncTokensIfNeeded();

    // Auto-cleanup DISABLED: multiple screens need to coexist on the same page.
    // Previously this deleted the last built root frame on each new build.
    // if (lastBuiltRootId && !hasParentId) { ... }
    lastBuiltRootId = null;

    // ★ Step 1: Enhance blueprint (code-level auto-correction)
    // skipEnhance=true: Clone & Bind 모델에서 검증된 레퍼런스 blueprint를
    // raw 그대로 빌드하는 경로 (S2.5 star-01 fallback 우회용)
    const blueprint = params.blueprint as Record<string, unknown>;
    const skipEnhance = params.skipEnhance === true;
    const enhanced = skipEnhance ? blueprint : enhanceBlueprint(blueprint);
    if (skipEnhance) {
      console.log('[batch_build_screen] skipEnhance=true — raw blueprint mode');
    }
    // Detach _pendingBindings marker from the tree so it does NOT travel to plugin
    type PendingBinding = { bpid: string; origName: string; bindings: Record<string, string> };
    const pendingBindings: PendingBinding[] =
      ((enhanced as Record<string, unknown>)._pendingBindings as PendingBinding[]) || [];
    delete (enhanced as Record<string, unknown>)._pendingBindings;

    // ★ Step 2: Smart Resolution: resolve semantic names → actual keys
    const resolved = await resolveBlueprint(enhanced);
    const resolvedParams = { ...params, blueprint: resolved };

    // Pre-fetch images in the blueprint tree
    const nodes = resolved.children ? [resolved] : [resolved];
    await prefetchImages(nodes as unknown[]);

    const result = await cmd('batch_build_screen', resolvedParams, 300000) as Record<string, unknown>; // 5 min timeout
    // Track the root frame ID for cleanup on next build (only for full screen builds)
    if (result?.rootId && !hasParentId) {
      lastBuiltRootId = result.rootId as string;
      console.log(`[batch_build_screen] Tracking rootId: ${lastBuiltRootId}`);
    }
    console.log(`[batch_build_screen] Build complete:`, JSON.stringify(result).slice(0, 200));

    // ★ Step 2.5: Auto-bind variables for nodes that carried fillVar/strokeVar/etc.
    //    This is the real "build-time variable binding" — replaces guessing in
    //    the post-fix sweep when the Blueprint already declared the token by name.
    if (pendingBindings.length > 0 && result?.rootId) {
      try {
        const rootInfo = await cmd('get_node_info', { nodeId: result.rootId }, 30000) as Record<string, unknown>;
        const idByBpid = new Map<string, string>();
        const walk = (n: Record<string, unknown> | null | undefined) => {
          if (!n || typeof n !== 'object') return;
          const name = typeof n.name === 'string' ? n.name : '';
          for (const pb of pendingBindings) {
            if (idByBpid.has(pb.bpid)) continue;
            // Match by suffix — the bpid is appended to the original name
            if (name.endsWith(pb.bpid)) {
              const id = (n.id as string) || '';
              if (id) idByBpid.set(pb.bpid, id);
            }
          }
          const cs = n.children as Array<Record<string, unknown>> | undefined;
          if (Array.isArray(cs)) cs.forEach(walk);
        };
        walk(rootInfo);

        const bindItems = pendingBindings
          .map(pb => {
            const nodeId = idByBpid.get(pb.bpid);
            return nodeId ? { nodeId, bindings: pb.bindings } : null;
          })
          .filter((x): x is { nodeId: string; bindings: Record<string, string> } => x !== null);

        if (bindItems.length > 0) {
          const bindRes = await cmd('batch_bind_variables', { items: bindItems }, 60000) as Record<string, unknown>;
          console.log(`[batch_build_screen] Auto-bound ${bindItems.length}/${pendingBindings.length} token vars:`, JSON.stringify(bindRes).slice(0, 200));
          (result as Record<string, unknown>).tokenBindCount = bindItems.length;
          (result as Record<string, unknown>).tokenBindResult = bindRes;
        } else {
          console.warn(`[batch_build_screen] Could not match any of ${pendingBindings.length} pending bindings to built nodes`);
          (result as Record<string, unknown>).tokenBindCount = 0;
        }

        // Restore original names (best-effort — failures don't block the build)
        await Promise.allSettled(
          pendingBindings.map(async pb => {
            const nodeId = idByBpid.get(pb.bpid);
            if (!nodeId) return;
            try {
              await cmd('rename_node', { nodeId, name: pb.origName || 'Node' }, 5000);
            } catch (e) {
              console.warn(`[batch_build_screen] rename_node failed for ${pb.bpid}:`, e);
            }
          })
        );
      } catch (e) {
        console.warn('[batch_build_screen] Auto-token-binding step failed:', e);
      }
    }

    // ★ Auto-screenshot: capture immediately after build
    if (result?.rootId) {
      try {
        const screenshot = await cmd('export_node_as_image', {
          nodeId: result.rootId, format: 'PNG', scale: 1
        }, 30000) as Record<string, unknown>;
        if (screenshot?.imageData) {
          result.screenshot = screenshot;
          console.log(`[batch_build_screen] Auto-screenshot captured for ${result.rootId}`);
        }
      } catch (e) {
        console.warn('[batch_build_screen] Auto-screenshot failed:', e);
      }

      // ★ Post-build QA: programmatic dimension check
      try {
        const rootInfo = await cmd('get_node_info', { nodeId: result.rootId }, 10000) as Record<string, unknown>;
        const rootW = rootInfo?.width as number;
        const issues: string[] = [];
        const children = rootInfo?.children as Array<Record<string, unknown>> || [];
        for (const child of children) {
          const cw = child.width as number;
          const ch = child.height as number;
          const cName = child.name as string;
          const cLayout = child.layoutPositioning as string;
          // Skip absolute-positioned children (Tab Bar, FAB)
          if (cLayout === 'ABSOLUTE') continue;
          // Check: full-width sections should match root width
          if (cw < rootW * 0.9 && cw > 0) {
            issues.push(`[QA] "${cName}" width=${cw} (expected ~${rootW}) — may need FILL or explicit width`);
          }
          // Check: zero-dimension nodes
          if (cw === 0 || ch === 0) {
            issues.push(`[QA] "${cName}" has zero dimension: ${cw}x${ch}`);
          }
        }
        if (issues.length > 0) {
          console.warn(`[batch_build_screen] Post-build QA found ${issues.length} issues:`);
          issues.forEach(i => console.warn(i));
          (result as Record<string, unknown>).qaIssues = issues;
        } else {
          console.log('[batch_build_screen] Post-build QA: all checks passed');
        }
      } catch (e) {
        console.warn('[batch_build_screen] Post-build QA failed:', e);
      }
    }

    return result;
  }, { timeoutMs: 310_000 }); // 5min WS + 10s margin

  // ============================================================
  // build_from_spec — generic component-based screen builder
  // ============================================================
  reg('build_from_spec', `Build a polished screen from a high-level component spec — the PREFERRED path for all wireframe-to-figma work.

🚨 INPUT REQUIREMENTS — ALWAYS READ BOTH

1. **The selected wireframe** (use get_selection + scan_text_nodes + export_node_as_image to extract structure + actual data verbatim).
2. **PRD.md (or any *.md product spec) attached or in the project repo** — Read the file and pull product context, exact copy, numbers, labels, and intended states from it. The wireframe shows structure, the PRD shows the source-of-truth content.

If the user mentions a PRD or attaches a markdown file, you MUST Read it before authoring the spec.

📐 SPEC SHAPE — generic, sections-based

{
  width: 393,                                  // mobile root width
  discoverySource: "<kind>:<detail>",          // ★ REQUIRED — see below
  positionRelativeTo?: "<figma node ID>",     // optional — placed to the right of the wireframe
  // bgVar: IGNORED — wrapper bg is always bg-primary by absolute project rule.
  //   Card hierarchy (bg-secondary/bg-tertiary/bg-quaternary) is handled inside sections.
  statusBar?: boolean,                         // default true — clones the in-file Status bar
  sections: SectionSpec[],                     // normal-flow children, top-to-bottom
  overlays?: OverlaySpec[]                     // ABSOLUTE bottom overlays (TabBar + FAB)
}

🚨 spec.discoverySource is REQUIRED (HARD GATE — call rejected if missing/invalid)
  - "wireframe:<nodeId>"      Wireframe attached → RULE 0 (wireframe is ground truth)
  - "skill:<skillId>"         Matched a verified skill in docs/skills/<id>/spec.json
  - "form:<key=val,...>"      User answered the RULE 1 mode-B 7-item question form
  - "skip:<reason>"           User explicitly said "just build, skip questions"

If wireframe is NOT attached and PRD is text-only, FIRST emit AskUserQuestion with
the 7-item discovery form (output / mode / activeTab / data / scale / emphasis /
constraints) and WAIT for the answer. Then call build_from_spec with
discoverySource: "form:output=<...>,mode=<...>,activeTab=<...>".

This validation is enforced in code; build_from_spec throws if the field is missing.

🚨 ABSOLUTE COLOR RULE
- Screen wrapper background = bg-primary (always, no exceptions)
- Inside cards/sections: bg-secondary > bg-tertiary > bg-quaternary hierarchy
- Never use _Primitives raw scale colors. Only "1. Color modes" semantic tokens.

🧩 AVAILABLE SECTION TYPES (sections[])

Headers:
  { type: "appHeader", rightIcons?: IconKey[], logoText?: string }
  { type: "modalHeader", title?: string, showClose?: boolean }
  { type: "backHeader", title?: string }

Tabs / chips:
  { type: "filterChipRow", chips: [{ text, selected? }, ...] }
  { type: "segmentedTab", tabs: [{ id, label }, ...], activeId }
  { type: "underlineTab", tabs: [{ id, label }, ...], activeId }

Layout:
  { type: "sectionHeader", title, trailing? }
  { type: "spacer", height: number }

Cards / forms:
  { type: "stepperCard", rows: [{ label, value, unit }, ...] }
  { type: "avatarRow", add?: { label }, makers: [{ name, level, colorHue, crown? }, ...] }
  { type: "summaryCardLinkRows", title, titleIcons?, rows: [{ label, value, valueTone?: "positive"|"negative"|"neutral", asLink? }, ...] }
  { type: "stageCardList", layout: "timeline", items: [{ monthly, months, payoutAt, payout, interest, points, fee }, ...] }
  { type: "stageCardScroll", cards: [{ status: "inProgress"|"scheduled"|"overdue"|"completed", statusLabel, rate, amount, description?, favorited? }, ...] }
  { type: "creditUsageCard", usageLabel, usageAmount, usageUnit, rightInfo, progressPercent?, cta?: { iconKey?, text, tone?: "info"|"warning" } }
  { type: "recommendHero", topLabel, amount, unit, subText?, slider?: { label, valueText, current, max }, steppers?: [{ label, value, unit? }, ...], ctaText, toggleText? }

Alerts:
  { type: "alertBanner", tone: "error"|"warning"|"info"|"success", iconKey?, title, description?, trailingChevron? }

Engagement / commerce:
  { type: "attendanceWeek", streakText, rewardText, ctaText, days: [{ label, state: "completed"|"today"|"future" }, ...] }
  { type: "eventBannerCarousel", banners: [{ badge?, title, description?, iconKey?, tone?: "brand"|"neutral" }, ...], activeIndex? }
  { type: "productHotDeal", title, pointBalance, trailing?, products: [{ badge?: "hotdeal"|"best"|"new", name, discount?, price, imageHue? }, ...] }

Strips / calendars:
  { type: "monthScrollerCalendar", title?, months: [{ short, day, active?, activeLabel?, badge? }, ...], filterLabel? }
  { type: "statsStrip3Col", cols: [{ label, value, valueTone? }, ...] }

Lists:
  { type: "transactionTimeline", items: [{ dayLabel, dayState, rowState: "overdue"|"today"|"soon"|"scheduled"|"completed", title, amount, rightAction }, ...] }

Footer:
  { type: "footerLegal", legalLinks: string[], companyName, bizNumber, ceo, teleSalesNumber, disclaimer, copyright }

🎯 OVERLAYS (overlays[])
  { type: "tabBar", tabs: [{ id, label, iconKey }, ...], activeId }
  { type: "fab", iconKey: "wallet"|"plus"|"message"|"gift" }

🎨 IconKey values (typed enums)
  bell, message, home, shoppingBag, award, users, menu, wallet, plus, gift, star, check, sparkle, info, chevronLeft, chevronRight, eye, search, x

🚦 RULES THE AGENT MUST FOLLOW

- Copy data VERBATIM from the wireframe + PRD. Do NOT substitute reference sample data ("비비빔밥파괴자", 이모지 등).
- If a section type doesn't exist for a wireframe element, request a new section type (file an issue / ask the user) — do NOT fall back to batch_build_screen.
- Never include figma fields (frame, autoLayout, fillVar, cornerRadius). The spec is data-only.
- For colorHue values, choose by the wireframe's intent: brand items → "purple", warning → "amber", error → "red", success → "green", info → "blue", accent → "pink". No raw hex.
- For TabBar/FAB: place under "overlays", not "sections".
- For stage screens, use stageCardList. For modal-like 거래 내역 lists, use modalHeader + summaryCardLinkRows + monthScrollerCalendar + statsStrip3Col + sectionHeader + transactionTimeline.

The renderer encodes all polished visual details (padding, dividers, shadows, gradient avatars, brand token mapping, font hierarchy) — agents never decide visual details.`, {
    type: 'object',
    properties: {
      spec: { type: 'object', description: 'A ScreenSpec — see description for the schema.' },
    },
    required: ['spec'],
  }, async (params) => {
    if (!figmaWS.isConnected) throw new Error('Figma plugin is not connected.');
    await syncTokensIfNeeded();
    const spec = params.spec as Record<string, unknown>;
    if (!spec || typeof spec !== 'object') {
      throw new Error('build_from_spec: spec is required.');
    }

    // ═══════════════════════════════════════════════════════════════════
    // RULE 1 enforcement — discoverySource validation (HARD GATE)
    //
    // Without this gate, the agent skips the question form on text-only
    // PRDs and goes straight to build_from_spec — exactly the regression
    // the user reported (2026-05-03). Validation here forces the agent
    // to declare HOW it decided what to build:
    //   - wireframe:<nodeId>    (RULE 0 — wireframe is ground truth)
    //   - skill:<skillId>       (verified skill match from docs/skills/)
    //   - form:<key=val,…>      (RULE 1 mode B — user answered form)
    //   - skip:<reason>         (user explicit "just build")
    //
    // Reject is a thrown Error with an actionable message so the agent
    // self-corrects on the next turn.
    // ═══════════════════════════════════════════════════════════════════
    const discoverySource = spec.discoverySource;
    if (typeof discoverySource !== 'string' || discoverySource.length === 0) {
      throw new Error([
        'build_from_spec REJECTED: spec.discoverySource is required.',
        '',
        'You must declare how you decided what to build. One of:',
        '  - "wireframe:<nodeId>"    (wireframe attached → RULE 0)',
        '  - "skill:<skillId>"       (matched docs/skills/<id>/spec.json)',
        '  - "form:<key=val,...>"    (RULE 1 mode B — user answered form)',
        '  - "skip:<reason>"         (user said "just build, skip questions")',
        '',
        'If a wireframe is NOT attached and the PRD is text-only, you MUST',
        'first emit AskUserQuestion with the 7-item discovery form (RULE 1',
        'mode B) and wait for the user response. Only THEN call build_from_spec',
        'with discoverySource: "form:<key=val,...>".',
      ].join('\n'));
    }
    const validPrefix = /^(wireframe|skill|form|skip):/.test(discoverySource);
    if (!validPrefix) {
      throw new Error([
        'build_from_spec REJECTED: spec.discoverySource has invalid format.',
        `  Got: ${JSON.stringify(discoverySource).slice(0, 100)}`,
        '  Expected prefix: "wireframe:", "skill:", "form:", or "skip:"',
      ].join('\n'));
    }

    const code = buildScreenJS(spec as unknown as ScreenSpec);
    const result = await cmd('execute_js', { code }, 300000) as Record<string, unknown>;
    if (result && typeof result === 'object' && result.wrapperId) {
      try {
        const screenshot = await cmd('export_node_as_image', {
          nodeId: result.wrapperId, format: 'PNG', scale: 1,
        }, 30000) as Record<string, unknown>;
        if (screenshot?.imageData) (result as Record<string, unknown>).screenshot = screenshot;
      } catch (e) { console.warn('[build_from_spec] screenshot failed:', e); }
      // Auto-critique: every build runs the 5-dim self-critique. Result is
      // attached as `critique` so the agent can report it to the (non-designer)
      // user without an extra tool call.
      try {
        const wrapperId = result.wrapperId as string;
        const critiqueCode = `
const root = await figma.getNodeByIdAsync(${JSON.stringify(wrapperId)});
if (!root) return null;
return await (async () => {
  const __crit = ${critiqueScreenJsBody};
  return await __crit(root);
})();
`;
        const critique = await cmd('execute_js', { code: critiqueCode }, 60000);
        if (critique && typeof critique === 'object') {
          (result as Record<string, unknown>).critique = critique;
        }
      } catch (e) { console.warn('[build_from_spec] auto-critique failed:', e); }
    }
    return result;
  }, { timeoutMs: 310_000 });

  // ============================================================
  // critique_design — deterministic 5-dim self-critique
  // ============================================================
  reg('critique_design', `Run a deterministic 5-dimensional critique on a built screen frame.

Input: { rootId: "<wrapper node id>" }
Output: {
  score: 0..100,
  dimensions: {
    antiSlop:     { score, issues: [...] },   // placeholder text (Title/Trailing/Label/Mon/Lorem/0/Heading) detection
    typography:   { score, issues, uniqueSizes, uniqueWeights },
    spacing:      { score, issues, gridViolations: [{nodeName, prop, value}] },
    contrast:     { score, issues: [{nodeName, ratio, fg, bg}] },
    hierarchy:    { score, issues, sectionTitles: [{name, size, weight}] },
  },
  stats: { textCount, frameCount, depth }
}

Run AFTER build_from_spec to catch:
- Unbound TEXT properties leaving placeholder text ("Trailing", "Label", "0")
- Type-scale chaos (>8 unique font sizes)
- Off-grid spacing (paddings/gaps not multiples of 4)
- Low-contrast text (ratio < 4.5)
- Flat hierarchy (sections all same heading size)

Score: 100 = clean. Issues classified as P0 (placeholder visible), P1 (token scale violation), P2 (style hint).`, {
    type: 'object',
    properties: {
      rootId: { type: 'string', description: 'Wrapper node id (e.g. from build_from_spec result.wrapperId)' },
    },
    required: ['rootId'],
  }, async (params) => {
    if (!figmaWS.isConnected) throw new Error('Figma plugin is not connected.');
    const rootId = params.rootId as string;
    const code = `
const root = await figma.getNodeByIdAsync(${JSON.stringify(rootId)});
if (!root) return { error: "node not found", rootId: ${JSON.stringify(rootId)} };
const __crit = ${critiqueScreenJsBody};
return await __crit(root);
`;
    return await cmd('execute_js', { code }, 60000);
  }, { timeoutMs: 70_000 });


  // ============================================================
  // scan_unstamped_screens — detect screens built by bypassing our gate
  // ============================================================
  reg('scan_unstamped_screens', `Scan the figma file for ROOT-level screens (≥360px wide frames on the GUI page) that LACK our build provenance stamp. Any frame here was created by an agent bypassing build_from_spec / batch_build_screen — typically via the figma-official use_figma plugin, route around our hard gate.

Returns:
  - unstamped: [{ nodeId, name, x, y, width, height }]   // suspicious frames
  - stamped:   [{ nodeId, name, builtAt, discoverySource, builder }]
  - totalRoots: number

Action options (caller's responsibility):
  - mark_unstamped_screens(nodeIds)  — rename frames with "⚠️ RULE 1 우회" prefix
  - delete_unstamped_screens(nodeIds) — destructive cleanup (require user confirm)

Run this proactively at the start of any design session — if scan finds
unstamped frames, the agent must explain to the user before doing anything
else.`, {
    type: 'object',
    properties: {
      minWidth: { type: 'number', description: 'Minimum width to count as a screen (default 360)' },
    },
  }, async (params) => {
    if (!figmaWS.isConnected) throw new Error('Figma plugin is not connected.');
    const minWidth = (typeof params.minWidth === 'number' ? params.minWidth : 360);
    const code = `
const guiPage = figma.root.children.find(p => p.name === "GUI") || figma.currentPage;
await figma.setCurrentPageAsync(guiPage);
const unstamped = []; const stamped = [];
for (const n of guiPage.children) {
  if (n.type !== "FRAME" || n.width < ${minWidth}) continue;
  // Skip the wireframe description templates and known infrastructure
  if (/디스크립션|description|AGENT_LIBRARY|Cover/i.test(n.name || "")) continue;
  let stamp = null;
  try { stamp = n.getSharedPluginData("fda_renderer", "screenMeta"); } catch (e) {}
  if (stamp && stamp.length > 0) {
    try {
      const meta = JSON.parse(stamp);
      stamped.push({ nodeId: n.id, name: n.name, builtAt: meta.builtAt, discoverySource: meta.discoverySource, builder: meta.builder });
    } catch (e) {
      stamped.push({ nodeId: n.id, name: n.name, raw: stamp.slice(0, 100) });
    }
  } else {
    unstamped.push({ nodeId: n.id, name: n.name, x: n.x, y: n.y, width: n.width, height: n.height });
  }
}
return { unstamped, stamped, totalRoots: unstamped.length + stamped.length };
`;
    return await cmd('execute_js', { code }, 30000);
  }, { timeoutMs: 40_000 });

  // ============================================================
  // mark_unstamped_screens — rename bypass frames so user/agent see them
  // ============================================================
  reg('mark_unstamped_screens', `Rename one or more frames with the "⚠️ RULE 1 우회" prefix so the user and the next agent turn can see they were built by bypassing the gate. Non-destructive.`, {
    type: 'object',
    properties: {
      nodeIds: { type: 'array', items: { type: 'string' }, description: 'Node IDs from scan_unstamped_screens.unstamped' },
    },
    required: ['nodeIds'],
  }, async (params) => {
    if (!figmaWS.isConnected) throw new Error('Figma plugin is not connected.');
    const ids = (params.nodeIds as string[]) || [];
    const code = `
const ids = ${JSON.stringify(ids)};
const renamed = [];
for (const id of ids) {
  try {
    const n = await figma.getNodeByIdAsync(id);
    if (n && "name" in n) {
      const original = n.name;
      if (!/^⚠️ RULE 1 우회/.test(original)) {
        n.name = "⚠️ RULE 1 우회 — " + original;
      }
      renamed.push({ nodeId: id, oldName: original, newName: n.name });
    }
  } catch (e) {}
}
return { renamed };
`;
    return await cmd('execute_js', { code }, 30000);
  }, { timeoutMs: 40_000 });

  // ============================================================
  // delete_unstamped_screens — destructive cleanup of bypass frames
  // ============================================================
  reg('delete_unstamped_screens', `DELETE one or more frames identified by scan_unstamped_screens.unstamped. Destructive — require user confirmation in the chat before calling.`, {
    type: 'object',
    properties: {
      nodeIds: { type: 'array', items: { type: 'string' } },
      confirmed: { type: 'boolean', description: 'User explicitly confirmed deletion' },
    },
    required: ['nodeIds', 'confirmed'],
  }, async (params) => {
    if (!figmaWS.isConnected) throw new Error('Figma plugin is not connected.');
    if (!params.confirmed) {
      throw new Error('delete_unstamped_screens REJECTED: confirmed=true required (destructive).');
    }
    const ids = (params.nodeIds as string[]) || [];
    const code = `
const ids = ${JSON.stringify(ids)};
const deleted = [];
for (const id of ids) {
  try {
    const n = await figma.getNodeByIdAsync(id);
    if (n && "remove" in n) {
      const name = ("name" in n) ? n.name : "(no-name)";
      n.remove();
      deleted.push({ nodeId: id, name });
    }
  } catch (e) {}
}
return { deleted };
`;
    return await cmd('execute_js', { code }, 30000);
  }, { timeoutMs: 40_000 });

  reg('batch_bind_variables', 'Bind variables to multiple nodes at once', {
    type: 'object',
    properties: {
      bindings: { type: 'array', items: { type: 'object' } }
    },
    required: ['bindings']
  }, async (params) => cmd('batch_bind_variables', params, 300000),
  { timeoutMs: 310_000 });

  reg('batch_set_text_style_id', 'Apply text styles to multiple nodes', {
    type: 'object',
    properties: {
      entries: { type: 'array', items: { type: 'object' } }
    },
    required: ['entries']
  }, async (params) => cmd('batch_set_text_style_id', params, 300000),
  { timeoutMs: 310_000 });

  reg('set_layout_sizing_batch', 'Set layout sizing on multiple nodes', {
    type: 'object',
    properties: {
      entries: { type: 'array', items: { type: 'object' } }
    },
    required: ['entries']
  }, async (params) => cmd('set_layout_sizing_batch', params));

  // ★ Pre-cache ALL DS components on connect (internal tool, not exposed to LLM)
  reg('pre_cache_components', 'Pre-cache DS component keys in Figma plugin for instant lookups', {
    type: 'object',
    properties: {
      keys: {
        type: 'array',
        items: { type: 'string' },
        description: 'Array of componentKey strings to pre-import'
      }
    },
    required: ['keys']
  }, async (params) => cmd('pre_cache_components', params, 600000),
  { timeoutMs: 620_000 }); // 10min WS + 20s margin

  return tools;
}

// ============================================================
// Helper functions (ported from existing batch-tools.ts)
// ============================================================

function extractId(result: unknown): string | undefined {
  const r = result as Record<string, unknown>;
  return (r?.id || r?.nodeId) as string | undefined;
}

function normalizeParams(op: string, params: Record<string, unknown>): Record<string, unknown> {
  switch (op) {
    case 'set_fill_color': {
      if (params.r !== undefined && !params.color) {
        const { nodeId, r, g, b, a, ...rest } = params;
        return { nodeId, color: { r, g, b, a: a ?? 1 }, ...rest };
      }
      return params;
    }
    case 'set_stroke_color': {
      if (params.r !== undefined && !params.color) {
        const { nodeId, r, g, b, a, strokeWeight, ...rest } = params;
        return { nodeId, color: { r, g, b, a: a ?? 1 }, strokeWeight: strokeWeight ?? 1, ...rest };
      }
      return params;
    }
    case 'set_layout_sizing': {
      const n = { ...params };
      if (params.horizontal && !params.layoutSizingHorizontal) n.layoutSizingHorizontal = params.horizontal;
      if (params.vertical && !params.layoutSizingVertical) n.layoutSizingVertical = params.vertical;
      return n;
    }
    case 'set_text_content': {
      if (typeof params.text === 'string') {
        return { ...params, text: (params.text as string).replace(/<br>/g, '\u2028') };
      }
      return params;
    }
    default:
      return params;
  }
}

async function fetchImageAsBase64(url: string): Promise<string | null> {
  try {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const buffer = await response.arrayBuffer();
    return Buffer.from(buffer).toString('base64');
  } catch (error) {
    console.error(`Image fetch failed for ${url}:`, error);
    return null;
  }
}

// ============================================================
// Smart Resolution — semantic names → actual Figma keys
// ============================================================

export async function resolveBlueprint(node: Record<string, unknown>): Promise<Record<string, unknown>> {
  // Deep copy to prevent shared references — shallow copy caused SVG icons
  // to be moved to wrong parents when the same object was mutated in multiple places
  const resolved = JSON.parse(JSON.stringify(node)) as Record<string, unknown>;

  // 1. statusBar: true → pass through to code.js for name-based search across all pages
  //    code.js will find "Status Bar" component/instance and createInstance/clone it.
  //    Previously this injected a clone node with a hardcoded sourceNodeId that could be stale.

  // 2. type: "instance" + component/variant → componentKey resolution
  if (resolved.type === 'instance' && resolved.component && !resolved.componentKey) {
    const key = resolveVariantKey(resolved.component as string, resolved.variant as string | undefined);
    if (key) {
      resolved.componentKey = key;
      console.log(`[resolve] ${resolved.component}${resolved.variant ? ` (${resolved.variant})` : ''} → ${key.slice(0, 12)}...`);
    } else {
      console.warn(`[resolve] Component not found: ${resolved.component} (${resolved.variant || 'default'})`);
    }
    delete resolved.component;
    delete resolved.variant;
  }

  // 3. type: "icon" → type: "svg_icon" (local @untitledui/icons SVG)
  if (resolved.type === 'icon' && (resolved.iconName || resolved.name)) {
    const iconName = (resolved.iconName || resolved.name) as string;
    const iconSize = (resolved.size as number) || 24;
    const iconColor = resolved.iconColor as { r: number; g: number; b: number; a?: number } | undefined;
    // Convert {r,g,b} 0-1 to hex for SVG stroke attribute
    const hexColor = iconColor
      ? '#' + [iconColor.r, iconColor.g, iconColor.b].map(c => Math.round(c * 255).toString(16).padStart(2, '0')).join('')
      : '#000000';
    const svgData = await getIconSvgAsync(iconName, iconSize, hexColor) || getIconSvg(iconName, iconSize, hexColor);
    if (svgData) {
      resolved.type = 'svg_icon';
      resolved.svgData = svgData;
      resolved.ds1Name = resolveIconFile(iconName) || iconName;
      resolved.width = iconSize;
      resolved.height = iconSize;
      if (!resolved.iconColor) resolved.iconColor = { r: 0, g: 0, b: 0, a: 1 };
      delete resolved.size;
      console.log(`[resolve] icon "${iconName}" → svg_icon (local, ${iconSize}px)`);
    } else {
      // Fallback: 회색 원형 placeholder
      console.warn(`[resolve] Icon not found: ${iconName}, creating placeholder`);
      resolved.type = 'frame';
      resolved.width = iconSize;
      resolved.height = iconSize;
      resolved.cornerRadius = iconSize / 2;
      resolved.fill = { r: 0.85, g: 0.85, b: 0.88, a: 1 };
      delete resolved.size;
    }
  }

  // 4. Flat layout properties → autoLayout object (code.js expects spec.autoLayout)
  if (resolved.layoutMode && !resolved.autoLayout) {
    const autoLayoutKeys = ['layoutMode', 'itemSpacing', 'paddingTop', 'paddingBottom', 'paddingLeft', 'paddingRight',
      'paddingHorizontal', 'paddingVertical', 'padding', 'primaryAxisAlignItems', 'counterAxisAlignItems', 'layoutWrap'];
    const al: Record<string, unknown> = {};
    for (const key of autoLayoutKeys) {
      if (resolved[key] !== undefined) {
        al[key] = resolved[key];
        delete resolved[key];
      }
    }
    resolved.autoLayout = al;
  }

  // 5. fills array → fill single object (code.js expects spec.fill, not spec.fills)
  if (Array.isArray(resolved.fills) && !resolved.fill) {
    const fills = resolved.fills as Array<Record<string, unknown>>;
    const solidFill = fills.find(f => f.type === 'SOLID' && f.visible !== false);
    if (solidFill) {
      const color = solidFill.color as Record<string, number>;
      if (color) {
        resolved.fill = { r: color.r, g: color.g, b: color.b, a: (solidFill.opacity as number) ?? 1 };
      }
    }
    delete resolved.fills;
  }

  // 6. TEXT type normalization (code.js expects lowercase "text")
  if (typeof resolved.type === 'string' && resolved.type.toUpperCase() === 'TEXT') {
    resolved.type = 'text';
    // Map fontFamily/fontWeight/fontSize to code.js expected format
    if (resolved.fontFamily && !resolved.fontName) {
      resolved.fontName = resolved.fontFamily;
      delete resolved.fontFamily;
    }
  }

  // 7. effects array: ensure blendMode and visible for DROP_SHADOW
  if (Array.isArray(resolved.effects)) {
    resolved.effects = (resolved.effects as Array<Record<string, unknown>>).map(e => {
      if (e.type === 'DROP_SHADOW') {
        return { blendMode: 'NORMAL', visible: true, ...e };
      }
      return e;
    });
  }

  // Recurse: process children
  if (Array.isArray(resolved.children)) {
    resolved.children = await Promise.all(
      (resolved.children as Record<string, unknown>[]).map(child =>
        resolveBlueprint(child as Record<string, unknown>)
      )
    );
  }

  return resolved;
}

export function resolveVariantKey(componentName: string, variantStr?: string): string | null {
  try {
    const variants = getVariants();
    const nameLower = componentName.toLowerCase();

    // Smart component name matching (priority order):
    // 1. Exact match (case-insensitive)
    // 2. Suffix match: "Button" → "Buttons/Button"
    // 3. Starts-with match: "Input" → "Input field"
    // 4. Contains match: "Social" → "Social button"
    let entry = variants.find(v => v.name.toLowerCase() === nameLower);
    if (!entry) {
      entry = variants.find(v => {
        const vLower = v.name.toLowerCase();
        // Suffix: "Buttons/Button" ends with "/button"
        return vLower.endsWith('/' + nameLower);
      });
    }
    if (!entry) {
      entry = variants.find(v => v.name.toLowerCase().startsWith(nameLower));
    }
    if (!entry) {
      entry = variants.find(v => v.name.toLowerCase().includes(nameLower));
    }
    if (!entry) {
      console.warn(`[resolve] Component "${componentName}" not found in ${variants.length} components`);
      return null;
    }

    console.log(`[resolve] "${componentName}" → matched "${entry.name}" (${Object.keys(entry.variants).length} variants)`);

    if (!variantStr) {
      return Object.values(entry.variants)[0] || null;
    }

    // Try exact variant match first
    if (entry.variants[variantStr]) {
      return entry.variants[variantStr];
    }

    // Partial matching: all parts of variantStr must be present in the key
    // Collect ALL matches, then pick the best one
    const parts = variantStr.split(',').map(p => p.trim().toLowerCase());
    const userSpecifiedProps = new Set(parts.map(p => p.split('=')[0].trim()));
    const matches: Array<{ key: string; value: string; score: number }> = [];

    for (const [key, value] of Object.entries(entry.variants)) {
      const keyLower = key.toLowerCase();
      if (parts.every(part => keyLower.includes(part))) {
        // Score: prefer default-like values for unspecified properties
        let score = 0;
        if (!userSpecifiedProps.has('state') && keyLower.includes('state=default')) score += 10;
        if (!userSpecifiedProps.has('icon only') && keyLower.includes('icon only=false')) score += 5;
        if (!userSpecifiedProps.has('supporting text') && keyLower.includes('supporting text=false')) score += 5;
        if (!userSpecifiedProps.has('destructive') && keyLower.includes('destructive=false')) score += 3;
        matches.push({ key, value, score });
      }
    }

    if (matches.length > 0) {
      // Sort by score descending, pick best
      matches.sort((a, b) => b.score - a.score);
      console.log(`[resolve] "${variantStr}" → ${matches.length} matches, best: "${matches[0].key}" (score=${matches[0].score})`);
      return matches[0].value;
    }

    // Fallback: return first variant
    console.warn(`[resolve] Variant "${variantStr}" not found for ${entry.name}, using first variant`);
    return Object.values(entry.variants)[0] || null;
  } catch (e) {
    console.error('[resolve] resolveVariantKey error:', e);
    return null;
  }
}

export function resolveIconNodeId(iconName: string): string | null {
  try {
    const icons = getIcons();
    const nameLower = iconName.toLowerCase().trim();

    // 1. Exact match
    if (icons[iconName]) return icons[iconName];
    if (icons[nameLower]) return icons[nameLower];

    const allNames = Object.keys(icons);

    // 2. Case-insensitive exact match
    const exact = allNames.find(n => n.toLowerCase() === nameLower);
    if (exact) return icons[exact];

    // 2.5 Lucide → DS v1 name mapping (before fuzzy matching)
    const lucideMapped = LUCIDE_TO_DS1_MAP[nameLower];
    if (lucideMapped) {
      const mappedId = icons[lucideMapped] || icons[lucideMapped.toLowerCase()];
      if (mappedId) {
        console.log(`[resolve] icon lucide: "${iconName}" → "${lucideMapped}"`);
        return mappedId;
      }
      const mappedExact = allNames.find(n => n.toLowerCase() === lucideMapped.toLowerCase());
      if (mappedExact) {
        console.log(`[resolve] icon lucide: "${iconName}" → "${mappedExact}"`);
        return icons[mappedExact];
      }
    }

    // 3. Suffix match: "bell" → "bell-01" (most common pattern — icons have -01/-02 suffixes)
    const suffixed = allNames.find(n => n.toLowerCase() === nameLower + '-01');
    if (suffixed) {
      console.log(`[resolve] icon fuzzy: "${iconName}" → "${suffixed}" (added -01 suffix)`);
      return icons[suffixed];
    }

    // 4. Prefix match: "shopping-bag" → "shopping-bag-01"
    const prefixed = allNames.filter(n => n.toLowerCase().startsWith(nameLower));
    if (prefixed.length > 0) {
      // Prefer shortest match (most specific)
      prefixed.sort((a, b) => a.length - b.length);
      console.log(`[resolve] icon fuzzy: "${iconName}" → "${prefixed[0]}" (prefix match, ${prefixed.length} candidates)`);
      return icons[prefixed[0]];
    }

    // 5. Contains match: "cart" → "shopping-cart-01"
    const contains = allNames.filter(n => n.toLowerCase().includes(nameLower));
    if (contains.length > 0) {
      contains.sort((a, b) => a.length - b.length);
      console.log(`[resolve] icon fuzzy: "${iconName}" → "${contains[0]}" (contains match, ${contains.length} candidates)`);
      return icons[contains[0]];
    }

    // 6. Word match: "close" → "x-close", "search" → "search-lg"
    const words = nameLower.split('-');
    const wordMatch = allNames.filter(n => {
      const nLower = n.toLowerCase();
      return words.every(w => nLower.includes(w));
    });
    if (wordMatch.length > 0) {
      wordMatch.sort((a, b) => a.length - b.length);
      console.log(`[resolve] icon fuzzy: "${iconName}" → "${wordMatch[0]}" (word match)`);
      return icons[wordMatch[0]];
    }

    // 7. Fallback: use a visually appealing icon instead of nothing
    const FALLBACK_ICON = 'star-01';
    const fallback = allNames.find(n => n.toLowerCase() === FALLBACK_ICON);
    if (fallback) {
      console.warn(`[resolve] icon "${iconName}" not found in DS — using fallback "${fallback}" (requested: "${iconName}")`);
      return icons[fallback];
    }

    console.warn(`[resolve] Icon not found (no fallback available): "${iconName}"`);
    return null;
  } catch (e) {
    console.error('[resolve] resolveIconNodeId error:', e);
    return null;
  }
}

/**
 * Resolve icon name to DS v1 icon name (not node ID).
 * Reuses the same 7-step fuzzy matching + Lucide mapping from resolveIconNodeId.
 */
export function resolveIconDs1Name(iconName: string): string | null {
  try {
    const icons = getIcons();
    const nameLower = iconName.toLowerCase().trim();
    const allNames = Object.keys(icons);

    // 1. Exact match
    if (icons[iconName]) return iconName;
    if (icons[nameLower]) return nameLower;
    const exact = allNames.find(n => n.toLowerCase() === nameLower);
    if (exact) return exact;

    // 2. Lucide mapping
    const lucideMapped = LUCIDE_TO_DS1_MAP[nameLower];
    if (lucideMapped) {
      const mapped = allNames.find(n => n.toLowerCase() === lucideMapped.toLowerCase());
      if (mapped) return mapped;
    }

    // 3. Suffix match: "bell" → "bell-01"
    const suffixed = allNames.find(n => n.toLowerCase() === nameLower + '-01');
    if (suffixed) return suffixed;

    // 4. Prefix match
    const prefixed = allNames.filter(n => n.toLowerCase().startsWith(nameLower));
    if (prefixed.length > 0) {
      prefixed.sort((a, b) => a.length - b.length);
      return prefixed[0];
    }

    // 5. Contains match
    const contains = allNames.filter(n => n.toLowerCase().includes(nameLower));
    if (contains.length > 0) {
      contains.sort((a, b) => a.length - b.length);
      return contains[0];
    }

    // 6. Word match
    const words = nameLower.split('-');
    const wordMatch = allNames.filter(n => words.every(w => n.toLowerCase().includes(w)));
    if (wordMatch.length > 0) {
      wordMatch.sort((a, b) => a.length - b.length);
      return wordMatch[0];
    }

    // 7. Fallback
    return 'star-01';
  } catch {
    return null;
  }
}

/** Lucide 아이콘명 → DS v1 아이콘명 매핑 (이름이 다른 것만, 퍼지 매칭이 처리하는 이름은 제외) */
const LUCIDE_TO_DS1_MAP: Record<string, string> = {
  // 완전 MISS되는 이름 (DS v1에 다른 이름으로 존재)
  'house': 'home-01',
  'more-horizontal': 'dots-horizontal',
  'more-vertical': 'dots-vertical',
  'map-pin': 'marker-pin-01',
  'coins': 'currency-dollar-circle',
  'flag': 'announcement-01',
  'file-text': 'file-06',
  'trending-up': 'trend-up-01',
  'trending-down': 'trend-down-01',
  'rotate-cw': 'refresh-cw-01',
  'volume-2': 'volume-max',
  'scan-line': 'scan',
  'footprints': 'route',
  'ellipsis': 'dots-horizontal',
  'dollar-sign': 'currency-dollar',
  'undo': 'reverse-left',
  'redo': 'reverse-right',
  'smartphone': 'phone-01',
  'loader': 'loading-01',
  'timer': 'clock-stopwatch',
  'calendar-days': 'calendar-date',
  'megaphone': 'announcement-01',
  'sparkle': 'star-06',
  'sparkles': 'stars-01',
  'crown': 'award-01',
  'shield-check': 'shield-tick',
  'bell-ring': 'bell-ringing-01',
  'bell-off': 'bell-off-01',
  'panel-left': 'layout-left',
  'panel-right': 'layout-right',
  'calendar-check': 'calendar-check-01',
  'history': 'clock-refresh',
  'signal': 'signal-01',
  'battery-full': 'battery-full',
  // 퍼지 매칭이 틀린 결과를 주는 이름
  'share': 'share-05',
  'share-2': 'share-05',
  'filter': 'filter-funnel-01',
  'download': 'download-04',
  'upload': 'upload-04',
  'credit-card': 'credit-card-plus',
  'phone': 'phone-call-01',
  // 안전한 명시적 매핑 (빠른 해결 + 정확도 보장)
  'x': 'x-close',
  'trash-2': 'trash-01',
  'edit-2': 'edit-01',
  'edit-3': 'edit-01',
  'log-out': 'log-out-01',
  'log-in': 'log-in-01',
  'layers': 'layers-two-01',
  'smile': 'face-smile',
  'moon': 'moon-01',
  'cloud': 'cloud-01',
  'qr-code': 'qr-code-01',
  'unlock': 'lock-unlocked-01',
  'circle-check': 'check-circle',
  'circle-x': 'x-circle',
  'circle-alert': 'alert-circle',
  'triangle-alert': 'alert-triangle',
  'external-link': 'link-external-01',
};

// ============================================================
// Blueprint Enhancer — 코드 레벨 자동 변환 (LLM 의존 없음)
// ============================================================

/** 텍스트 키워드 → DS 아이콘 이름 매핑 */
const ICON_KEYWORD_MAP: Record<string, string> = {
  '출석': 'calendar',
  '체크인': 'check-circle',
  '초대': 'user-plus-01',
  '친구': 'users-01',
  '구매': 'shopping-bag-01',
  '쇼핑': 'shopping-cart-01',
  '포인트': 'currency-dollar-circle',
  '적립': 'star-01',
  '보상': 'gift-01',
  '리워드': 'gift-01',
  '이벤트': 'announcement-01',
  '알림': 'bell-01',
  '설정': 'settings-01',
  '홈': 'home-01',
  '검색': 'search-lg',
  '마이': 'user-01',
  '프로필': 'user-circle',
  '결제': 'credit-card-plus',
  '지갑': 'wallet-01',
  '공유': 'share-05',
  '메시지': 'message-circle-01',
  '채팅': 'message-circle-01',
  '전화': 'phone-call-01',
  '메일': 'mail-01',
  '카메라': 'camera-01',
  '사진': 'image-01',
  '좋아요': 'heart',
  '북마크': 'bookmark',
  '잠금': 'lock-01',
  '보안': 'lock-01',
  '시간': 'clock',
  '위치': 'globe-01',
  '링크': 'link-01',
  '태그': 'tag-01',
  '다운로드': 'download-04',
  '삭제': 'trash-01',
  '수정': 'edit-01',
  '복사': 'copy-01',
  '필터': 'filter-funnel-01',
  'qr': 'qr-code-01',
  '주문': 'receipt',
  '영수증': 'receipt',
  '쿠폰': 'tag-01',
  '할인': 'tag-01',
  '배송': 'shopping-bag-01',
  '정보': 'info-circle',
  '도움': 'help-circle',
  '안내': 'info-circle',
  '공지': 'bell-01',
  // 챌린지/스테이지 관련
  '운동': 'activity',
  '챌린지': 'flag-01',
  '독서': 'book-open-01',
  '마라톤': 'activity',
  '미술': 'palette',
  '작품': 'palette',
  '스테이지': 'layers-three-01',
  '참가': 'users-01',
  '모집': 'users-01',
  '완성': 'check-circle',
  '달성': 'target-01',
  '목표': 'target-01',
  '건강': 'heart-hand',
  '피트니스': 'activity',
  '요리': 'coffee',
  '학습': 'graduation-hat-01',
  '영어': 'book-open-01',
  '코딩': 'code-01',
  '음악': 'music-note-01',
};

/** 아이콘 배경 tint 색상 (회전 사용) */
const ICON_TINT_COLORS = [
  { r: 1, g: 0.94, b: 0.92 },      // warm peach
  { r: 0.92, g: 0.97, b: 1 },      // soft blue
  { r: 0.93, g: 1, b: 0.95 },      // mint green
  { r: 0.98, g: 0.95, b: 1 },      // lavender
  { r: 1, g: 0.97, b: 0.88 },      // warm yellow
  { r: 0.95, g: 0.93, b: 1 },      // soft purple
];

/** 탭바 기본 아이콘 매핑 */
const TAB_ICON_MAP: Record<string, string> = {
  '홈': 'home-01', 'home': 'home-01',
  '포인트': 'currency-dollar-circle', 'point': 'currency-dollar-circle', 'points': 'currency-dollar-circle',
  '쇼핑': 'shopping-bag-01', 'shop': 'shopping-bag-01', 'store': 'shopping-bag-01',
  '마이': 'user-01', 'my': 'user-01', '마이페이지': 'user-01', 'profile': 'user-01', '나': 'user-01',
  '검색': 'search-lg', 'search': 'search-lg',
  '장바구니': 'shopping-cart-01', 'cart': 'shopping-cart-01',
  '메시지': 'message-circle-01', 'chat': 'message-circle-01',
  '알림': 'bell-01', 'notification': 'bell-01',
  '설정': 'settings-01', 'settings': 'settings-01',
  '즐겨찾기': 'heart', 'favorite': 'heart',
  '카테고리': 'menu-01', 'category': 'menu-01',
  '챌린지뷰': 'flag-01', '챌린지': 'flag-01', 'challenge': 'flag-01',
  '스테이지': 'layers-three-01', 'stage': 'layers-three-01',
  '다이어리': 'book-open-01', 'diary': 'book-open-01',
  '타임뷰': 'clock', 'timeline': 'clock',
  '피드': 'rss-01', 'feed': 'rss-01',
  '커뮤니티': 'users-01', 'community': 'users-01',
  '활동': 'activity', 'activity': 'activity',
  '지도': 'globe-01', 'map': 'globe-01',
  '예약': 'calendar', 'booking': 'calendar',
  '혜택': 'gift-01', 'benefit': 'gift-01',
  '다이얼뷰': 'clock',
};

/**
 * Blueprint 전체 트리를 코드 레벨에서 개선.
 * LLM이 rectangle을 생성해도 텍스트 컨텍스트 기반으로 적절한 아이콘으로 변환.
 */
export function enhanceBlueprint(root: Record<string, unknown>): Record<string, unknown> {
  let tintColorIdx = 0;
  // 통계 카운터
  const stats = { font: 0, color: 0, sizing: 0, icon: 0, structure: 0, fontSize: 0, alignment: 0, tokenBind: 0 };

  // ── Token-field resolution (build-time variable binding) ─────────────
  // Recognizes optional fillVar/strokeVar/textColorVar/cornerRadiusVar/itemSpacingVar/paddingVar/effectVar
  // fields, looks them up in TOKEN_MAP.json, fills the corresponding raw value
  // (hex or number) into the node, and accumulates _pendingBindings so the
  // batch_build_screen handler can call batch_bind_variables right after the build.
  const tokenMap = getTokenMap();
  const tokenByPath: Record<string, { value: string; type: string; cssKey: string }> = {};
  const tokenByLeaf: Record<string, { value: string; type: string; cssKey: string; figmaPath: string }> = {};
  for (const [cssKey, entry] of Object.entries(tokenMap)) {
    if (!entry || !entry.figmaPath) continue;
    const fp = entry.figmaPath;
    tokenByPath[fp] = { value: entry.value, type: entry.type, cssKey };
    const leaf = fp.split('/').pop() || fp;
    if (!tokenByLeaf[leaf]) {
      tokenByLeaf[leaf] = { value: entry.value, type: entry.type, cssKey, figmaPath: fp };
    }
  }

  function resolveTokenName(name: string): { value: string; type: string; figmaPath: string } | null {
    if (!name || typeof name !== 'string') return null;
    const trimmed = name.trim();
    // Direct figmaPath match (e.g. "Colors/Background/bg-primary")
    if (tokenByPath[trimmed]) {
      const t = tokenByPath[trimmed];
      return { value: t.value, type: t.type, figmaPath: trimmed };
    }
    // CSS-var-like key (e.g. "--colors-background-bg-primary")
    if (tokenMap[trimmed]) {
      const t = tokenMap[trimmed];
      return { value: t.value, type: t.type, figmaPath: t.figmaPath };
    }
    // Leaf name (e.g. "bg-primary", "text-secondary", "border-primary")
    if (tokenByLeaf[trimmed]) {
      const t = tokenByLeaf[trimmed];
      return { value: t.value, type: t.type, figmaPath: t.figmaPath };
    }
    // Substring path match (last resort, e.g. "Background/bg-primary")
    for (const fp of Object.keys(tokenByPath)) {
      if (fp.endsWith('/' + trimmed) || fp.endsWith('.' + trimmed)) {
        const t = tokenByPath[fp];
        return { value: t.value, type: t.type, figmaPath: fp };
      }
    }
    return null;
  }

  function hexToRgba01(hex: string): { r: number; g: number; b: number; a: number } | null {
    return normalizeColor(hex) as { r: number; g: number; b: number; a: number } | null;
  }

  // Variable name to use in batch_bind_variables = leaf segment of figmaPath.
  // Plugin code (setBoundVariables / batchBindVariables) supports partial-match
  // (endsWith "/" + name), so the leaf is enough.
  function variableNameFromFigmaPath(figmaPath: string): string {
    return figmaPath.split('/').pop() || figmaPath;
  }

  type PendingBinding = { bpid: string; origName: string; bindings: Record<string, string> };
  const pendingBindings: PendingBinding[] = [];
  let bpidCounter = 0;

  // Returns the leaf bg-token name (e.g. "bg-brand-solid") if the node has a
  // brand-tier fillVar. Used to detect contrast-failing combinations on child text.
  function brandBgLeaf(node: Record<string, unknown>): string | null {
    const v = node.fillVar;
    if (typeof v !== 'string') return null;
    const trimmed = v.trim();
    if (/^bg-brand/i.test(trimmed) || /Background\/bg-brand/i.test(trimmed)) return trimmed;
    return null;
  }

  // CONTRAST AUTO-FIX:
  // If a text node carries text-brand-* but its ancestor has a bg-brand-* fill,
  // the result is purple-on-purple (invisible). Force textColorVar to "text-white".
  // Also catches the same-node case (frame with both fillVar bg-brand and
  // textColorVar text-brand — rare but possible).
  function fixContrastOnNode(n: Record<string, unknown>, ancestorBrandBg: string | null): void {
    const myFillIsBrand = brandBgLeaf(n);
    const effectiveBrandBg = myFillIsBrand || ancestorBrandBg;
    if (effectiveBrandBg && typeof n.textColorVar === 'string') {
      const tc = (n.textColorVar as string).trim();
      if (/^text-brand/i.test(tc) || /Text\/text-brand/i.test(tc)) {
        console.warn(`[enforce] contrast fix: textColorVar "${tc}" on bg "${effectiveBrandBg}" → text-white`);
        n.textColorVar = 'text-white';
        stats.color++;
      }
    }
  }

  function processTokenFields(n: Record<string, unknown>): void {
    const bindings: Record<string, string> = {};

    // fillVar → fill (frame/rectangle/ellipse) OR fills/0 binding
    if (typeof n.fillVar === 'string') {
      const tok = resolveTokenName(n.fillVar as string);
      if (tok && tok.type === 'COLOR') {
        const rgba = hexToRgba01(tok.value);
        if (rgba) {
          n.fill = rgba;
          bindings['fills/0'] = variableNameFromFigmaPath(tok.figmaPath);
          stats.tokenBind++;
        }
      } else {
        console.warn(`[enforce] fillVar "${n.fillVar}" not resolvable in TOKEN_MAP — keep raw fill if any`);
      }
      delete n.fillVar;
    }

    // strokeVar → stroke
    if (typeof n.strokeVar === 'string') {
      const tok = resolveTokenName(n.strokeVar as string);
      if (tok && tok.type === 'COLOR') {
        const rgba = hexToRgba01(tok.value);
        if (rgba) {
          n.stroke = rgba;
          bindings['strokes/0'] = variableNameFromFigmaPath(tok.figmaPath);
          stats.tokenBind++;
        }
      } else {
        console.warn(`[enforce] strokeVar "${n.strokeVar}" not resolvable in TOKEN_MAP`);
      }
      delete n.strokeVar;
    }

    // textColorVar → fontColor (text nodes — internally stored as fills/0)
    if (typeof n.textColorVar === 'string') {
      const tok = resolveTokenName(n.textColorVar as string);
      if (tok && tok.type === 'COLOR') {
        const rgba = hexToRgba01(tok.value);
        if (rgba) {
          n.fontColor = rgba;
          bindings['fills/0'] = variableNameFromFigmaPath(tok.figmaPath);
          stats.tokenBind++;
        }
      } else {
        console.warn(`[enforce] textColorVar "${n.textColorVar}" not resolvable in TOKEN_MAP`);
      }
      delete n.textColorVar;
    }

    // cornerRadiusVar → cornerRadius
    if (typeof n.cornerRadiusVar === 'string') {
      const tok = resolveTokenName(n.cornerRadiusVar as string);
      if (tok && tok.type === 'NUMBER') {
        const num = parseFloat(tok.value);
        if (Number.isFinite(num)) {
          n.cornerRadius = num;
          bindings['cornerRadius'] = variableNameFromFigmaPath(tok.figmaPath);
          stats.tokenBind++;
        }
      } else {
        console.warn(`[enforce] cornerRadiusVar "${n.cornerRadiusVar}" not resolvable in TOKEN_MAP`);
      }
      delete n.cornerRadiusVar;
    }

    // itemSpacingVar → autoLayout.itemSpacing
    if (typeof n.itemSpacingVar === 'string') {
      const tok = resolveTokenName(n.itemSpacingVar as string);
      if (tok && tok.type === 'NUMBER') {
        const num = parseFloat(tok.value);
        if (Number.isFinite(num)) {
          const al = (n.autoLayout as Record<string, unknown> | undefined) || {};
          al.itemSpacing = num;
          n.autoLayout = al;
          bindings['itemSpacing'] = variableNameFromFigmaPath(tok.figmaPath);
          stats.tokenBind++;
        }
      } else {
        console.warn(`[enforce] itemSpacingVar "${n.itemSpacingVar}" not resolvable in TOKEN_MAP`);
      }
      delete n.itemSpacingVar;
    }

    // paddingVar → all four paddings (paddingTop/Bottom/Left/Right) bound to the same variable
    if (typeof n.paddingVar === 'string') {
      const tok = resolveTokenName(n.paddingVar as string);
      if (tok && tok.type === 'NUMBER') {
        const num = parseFloat(tok.value);
        if (Number.isFinite(num)) {
          const al = (n.autoLayout as Record<string, unknown> | undefined) || {};
          al.paddingTop = num;
          al.paddingBottom = num;
          al.paddingLeft = num;
          al.paddingRight = num;
          n.autoLayout = al;
          const varName = variableNameFromFigmaPath(tok.figmaPath);
          bindings['paddingTop'] = varName;
          bindings['paddingBottom'] = varName;
          bindings['paddingLeft'] = varName;
          bindings['paddingRight'] = varName;
          stats.tokenBind += 4;
        }
      } else {
        console.warn(`[enforce] paddingVar "${n.paddingVar}" not resolvable in TOKEN_MAP`);
      }
      delete n.paddingVar;
    }

    if (Object.keys(bindings).length > 0) {
      const bpid = `__bp${bpidCounter++}`;
      const rawName = typeof n.name === 'string' ? n.name.trim() : '';
      // Synthesize a natural fallback when the node has no name (e.g. text nodes).
      // text → use the text content; otherwise use a capitalized type.
      const fallbackName = (() => {
        if (n.type === 'text' && typeof n.text === 'string' && (n.text as string).trim()) {
          return (n.text as string).trim().slice(0, 40);
        }
        const t = typeof n.type === 'string' ? n.type : 'node';
        return t[0].toUpperCase() + t.slice(1);
      })();
      const origName = rawName || fallbackName;
      n.name = `${origName} ${bpid}`;
      pendingBindings.push({ bpid, origName, bindings });
    }
  }

  // ── Step 0: 루트 프레임에 statusBar: true 자동 주입 ──
  if (isMobileRootFrame(root) && !root.statusBar) {
    const children = root.children as Record<string, unknown>[] | undefined;
    const hasStatusBarChild = children?.some(c => {
      const name = ((c.name as string) || '').toLowerCase();
      return name.includes('status bar') || name.includes('statusbar') ||
        (c.type === 'clone' && (c.name as string || '').toLowerCase().includes('status'));
    });
    if (!hasStatusBarChild) {
      root.statusBar = true;
      console.log('[enforce] Auto-injected statusBar: true on root frame');
      stats.structure++;
    }
  }

  // ── Step 0a: 규칙 A — 루트 프레임 구조 강제 ──
  if (root.type === 'frame') {
    const w = root.width as number | undefined;
    const h = root.height as number | undefined;
    const isMobileWidth = typeof w === 'number' && w >= 360 && w <= 430;
    const noWidth = typeof w !== 'number';
    // 모바일 루트 프레임 감지 (너비 미지정이거나 360-430 범위)
    if (isMobileWidth || noWidth) {
      if (!w) {
        root.width = 393;
        console.log('[enforce] Root frame width forced: 393');
        stats.structure++;
      }
      if (!h) {
        root.height = 852;
        console.log('[enforce] Root frame height forced: 852');
        stats.structure++;
      }
      if (!root.autoLayout) {
        root.autoLayout = { layoutMode: 'VERTICAL' };
        console.log('[enforce] Root frame autoLayout forced: VERTICAL');
        stats.structure++;
      }
      if (!root.fill) {
        root.fill = { r: 1, g: 1, b: 1, a: 1 };
        console.log('[enforce] Root frame fill forced: white');
        stats.structure++;
      }
      if (root.clipsContent === undefined) {
        root.clipsContent = true;
        console.log('[enforce] Root frame clipsContent forced: true');
        stats.structure++;
      }
      if (!root.name) {
        root.name = 'Mobile Screen';
        console.log('[enforce] Root frame name forced: Mobile Screen');
        stats.structure++;
      }
    }
  }

  // ── 색상 속성 정규화 헬퍼 (노드 내) ──
  function normalizeNodeColors(n: Record<string, unknown>): void {
    const colorProps = ['fill', 'fontColor', 'stroke', 'iconColor', 'backgroundColor'];
    for (const prop of colorProps) {
      if (n[prop] !== undefined) {
        const normalized = normalizeColor(n[prop]);
        if (normalized && typeof n[prop] !== 'object') {
          console.log(`[enforce] Color normalized: ${prop} ${JSON.stringify(n[prop])} → ${JSON.stringify(normalized)}`);
          n[prop] = normalized;
          stats.color++;
        } else if (normalized && typeof n[prop] === 'object') {
          const orig = n[prop] as Record<string, number>;
          // 0-255 범위 정규화 체크
          if (orig.r > 1 || orig.g > 1 || orig.b > 1) {
            console.log(`[enforce] Color range normalized: ${prop} (values > 1 detected)`);
            n[prop] = normalized;
            stats.color++;
          }
        }
      }
    }
  }

  function enhance(node: Record<string, unknown>, _parent?: Record<string, unknown>, isRootChild?: boolean): Record<string, unknown> {
    const n = { ...node };

    // ── 0a. Contrast auto-fix — detect text-brand-* on ancestor bg-brand-* before
    //        we consume textColorVar and force text-white. Looks at parent's _ancestorBrandBg
    //        which was propagated down from the bg-brand carrier. ──
    const inheritedBrandBg = (_parent as Record<string, unknown> | undefined)?._ancestorBrandBg as string | null | undefined;
    fixContrastOnNode(n, inheritedBrandBg || null);
    // Determine effective ancestor brand bg for this node's children.
    const myBrandBg = brandBgLeaf(n);
    const childBrandBg = myBrandBg || inheritedBrandBg || null;
    if (childBrandBg) (n as Record<string, unknown>)._ancestorBrandBg = childBrandBg;

    // ── 0b. FAB auto-detection — round 48-72sq frame named *FAB* / containing a
    //        single icon child should float ABSOLUTE bottom-right. The blueprint
    //        author can still override layoutPositioning explicitly. ──
    {
      const lname = (typeof n.name === 'string' ? n.name : '').toLowerCase();
      const w = typeof n.width === 'number' ? n.width as number : 0;
      const h = typeof n.height === 'number' ? n.height as number : 0;
      const looksFab = (lname === 'fab' || lname.includes('fab') || lname.includes('floating'));
      const isCircle =
        w >= 40 && w <= 80 && Math.abs(w - h) <= 2 &&
        (n.cornerRadius === 9999 || n.cornerRadiusVar === 'radius-full' || n.cornerRadiusVar === 'full');
      if ((looksFab || isCircle) && !n.layoutPositioning) {
        n.layoutPositioning = 'ABSOLUTE';
        console.log(`[enforce] FAB auto-ABSOLUTE: ${lname || 'circular'}`);
        stats.structure++;
      }
    }

    // ── 0. Token-field resolution (must run BEFORE any other transformation
    //      so that downstream steps see the resolved fill/stroke/etc.) ──
    processTokenFields(n);

    // ── 1. Tab Bar detection & fix (기존 + 규칙 G 확장) ──
    if (isTabBar(n)) {
      console.log('[enforce] Tab bar detected, fixing icons & structure');
      fixTabBar(n);
      // 규칙 G: Tab Bar 구조 강제
      if (!n.fill) {
        n.fill = { r: 1, g: 1, b: 1, a: 1 };
        console.log('[enforce] Tab bar fill forced: white');
        stats.structure++;
      }
      if (!n.stroke) {
        n.stroke = { r: 0.95, g: 0.96, b: 0.96, a: 1 };
        if (!n.strokeWeight) n.strokeWeight = 1;
        if (!n.strokeAlign) n.strokeAlign = 'INSIDE';
        if (n.strokeSide === undefined) n.strokeSide = 'TOP';
        console.log('[enforce] Tab bar stroke forced: top border');
        stats.structure++;
      }
      if (!n.height) {
        n.height = 83;
        console.log('[enforce] Tab bar height forced: 83');
        stats.structure++;
      }
      const al = n.autoLayout as Record<string, unknown> | undefined;
      if (al) {
        if (al.layoutMode !== 'HORIZONTAL') {
          al.layoutMode = 'HORIZONTAL';
          console.log('[enforce] Tab bar layoutMode forced: HORIZONTAL');
          stats.structure++;
        }
        if (!al.primaryAxisAlignItems) {
          al.primaryAxisAlignItems = 'SPACE_BETWEEN';
          console.log('[enforce] Tab bar alignment forced: SPACE_BETWEEN');
          stats.structure++;
        }
      }
      if (!n.layoutPositioning) {
        n.layoutPositioning = 'ABSOLUTE';
        console.log('[enforce] Tab bar layoutPositioning forced: ABSOLUTE');
        stats.structure++;
      }
      // 각 탭 아이템 정렬 강제
      const tabChildren = n.children as Record<string, unknown>[] | undefined;
      if (tabChildren) {
        for (const tab of tabChildren) {
          if (tab.type === 'frame') {
            const tabAl = tab.autoLayout as Record<string, unknown> | undefined;
            if (tabAl) {
              if (tabAl.layoutMode !== 'VERTICAL') tabAl.layoutMode = 'VERTICAL';
              if (!tabAl.counterAxisAlignItems) tabAl.counterAxisAlignItems = 'CENTER';
              if (!tabAl.primaryAxisAlignItems) tabAl.primaryAxisAlignItems = 'CENTER';
            }
          }
        }
      }
      stats.icon++;
    }

    // ── 2. List item icon fix ──
    if (isListItemWithPlaceholderIcon(n)) {
      console.log(`[enforce] List item "${n.name}" — converting placeholder to icon`);
      convertListItemIcon(n, tintColorIdx);
      tintColorIdx++;
      stats.icon++;
    }

    // ── 3. Standalone small rectangles/ellipses ──
    if (isSmallPlaceholder(n) && !isInsideListItem(n, _parent)) {
      const contextText = getContextText(n, _parent);
      const iconName = guessIconFromText(contextText) || 'star-01';
      const tint = ICON_TINT_COLORS[tintColorIdx % ICON_TINT_COLORS.length];
      tintColorIdx++;
      console.log(`[enforce] Converting standalone placeholder "${n.name}" → ${iconName}`);
      convertToIconBg(n, iconName, tint);
      stats.icon++;
    }

    // ── 4. Emoji text → icon conversion ──
    if (isEmojiOnlyText(n)) {
      const emoji = (n.text as string).trim();
      const iconName = EMOJI_TO_ICON_MAP[emoji] || guessIconFromEmoji(emoji) || 'star-01';
      const tint = ICON_TINT_COLORS[tintColorIdx % ICON_TINT_COLORS.length];
      tintColorIdx++;
      console.log(`[enforce] Converting emoji "${emoji}" → icon "${iconName}"`);
      if (_parent) {
        const parentAl = _parent.autoLayout as Record<string, unknown> | undefined;
        if (parentAl?.layoutMode === 'HORIZONTAL') {
          convertToIconBg(n, iconName, tint);
        } else {
          n.type = 'icon';
          n.name = iconName;
          n.size = (n.fontSize as number) || 24;
          delete n.text;
          delete n.fontSize;
          delete n.fontWeight;
          delete n.fontFamily;
          delete n.fontColor;
          delete n.textAlignHorizontal;
          delete n.layoutSizingHorizontal;
        }
      } else {
        n.type = 'icon';
        n.name = iconName;
        n.size = 24;
        delete n.text;
        delete n.fontSize;
        delete n.fontWeight;
        delete n.fontFamily;
        delete n.fontColor;
      }
      stats.icon++;
    }

    // ── 5. 텍스트 layoutSizingHorizontal — 부모 방향에 따라 결정 ──
    // VERTICAL 부모 → FILL (가로 폭 채움, 표준 cross-axis stretch)
    // HORIZONTAL 부모 → HUG (텍스트 내용에 맞춤)
    // ⚠️ HORIZONTAL 부모에서 FILL 시 글자가 세로로 1자씩 줄바꿈되는 치명적 버그
    if (n.type === 'text') {
      // 부모 방향 감지 (autoLayout.layoutMode 또는 직접 layoutMode)
      const parentAl = _parent?.autoLayout as Record<string, unknown> | undefined;
      const parentMode = (parentAl?.layoutMode as string) || (_parent?.layoutMode as string) || undefined;
      const isHorizontalParent = parentMode === 'HORIZONTAL';

      if (!n.layoutSizingHorizontal) {
        n.layoutSizingHorizontal = isHorizontalParent ? 'HUG' : 'FILL';
        stats.sizing++;
      } else if (n.layoutSizingHorizontal === 'FILL' && isHorizontalParent) {
        // LLM이 FILL로 설정했어도 HORIZONTAL 부모면 강제 HUG
        console.log(`[enforce] Text "${((n.text as string) || '').slice(0, 15)}" in HORIZONTAL parent: FILL → HUG`);
        n.layoutSizingHorizontal = 'HUG';
        stats.sizing++;
      }
    }

    // ── 5a. 규칙 B — 폰트 강제 (Pretendard) ──
    if (n.type === 'text') {
      const currentFont = ((n.fontFamily as string) || '').toLowerCase().trim();
      const textContent = (n.text as string) || '';
      const hasKorean = containsKorean(textContent) || containsKorean((n.name as string) || '');
      const isNonKoreanFont = !currentFont || NON_KOREAN_FONTS.some(f => currentFont.includes(f));

      if (hasKorean || isNonKoreanFont) {
        if ((n.fontFamily as string) !== 'Pretendard') {
          const oldFont = n.fontFamily || '(none)';
          n.fontFamily = 'Pretendard';
          console.log(`[enforce] Font forced: "${oldFont}" → "Pretendard" (text: "${textContent.slice(0, 20)}")`);
          stats.font++;
        }
      }
    }

    // ── 5b. 규칙 E — 최소 fontSize 강제 ──
    if (n.type === 'text') {
      const fs = n.fontSize as number | undefined;
      if (typeof fs === 'number' && fs < 10) {
        console.log(`[enforce] fontSize forced: ${fs} → 12`);
        n.fontSize = 12;
        stats.fontSize++;
      } else if (fs === undefined) {
        n.fontSize = 14;
        console.log('[enforce] fontSize default: 14');
        stats.fontSize++;
      }
    }

    // ── 5c. 규칙 C — 색상 정규화 ──
    normalizeNodeColors(n);

    // ── 5d. 규칙 D — VERTICAL 부모의 모든 FRAME 자식 FILL width ──
    // 루트 직계뿐 아니라 모든 depth에서 VERTICAL 부모의 FRAME 자식은 FILL 필수
    // code.js에도 auto-FILL이 있지만 enhanceBlueprint에서 미리 설정하면 더 안정적
    if (_parent && n.type === 'frame' && !n.layoutSizingHorizontal) {
      const parentAl = _parent.autoLayout as Record<string, unknown> | undefined;
      const parentMode = (parentAl?.layoutMode as string) || (_parent.layoutMode as string);
      if (parentMode === 'VERTICAL') {
        const name = ((n.name as string) || '').toLowerCase();
        const isStatusBar = name.includes('status bar') || name.includes('statusbar');
        const isSkip = /icon|chevron|dot|badge|tag|chip|indicator|fab|tab.?bar/i.test(name);
        const w = n.width as number | undefined;
        const isSmallFixed = typeof w === 'number' && w <= 60;
        if (!isStatusBar && !isSkip && !isSmallFixed) {
          n.layoutSizingHorizontal = 'FILL';
          if (isRootChild) {
            console.log(`[enforce] Root child "${n.name}" layoutSizingHorizontal forced: FILL`);
          } else {
            console.log(`[enforce] VERTICAL parent child "${n.name}" layoutSizingHorizontal forced: FILL`);
          }
          stats.sizing++;
        }
      }
    }

    // ── 5e-pre. Badge/Tag/Chip은 반드시 HUG ──
    if (n.type === 'frame') {
      const name = ((n.name as string) || '').toLowerCase();
      const isBadgeOrTag = /badge|tag|chip|label.*badge|뱃지|태그|칩/.test(name);
      if (isBadgeOrTag && n.layoutSizingHorizontal && n.layoutSizingHorizontal !== 'HUG') {
        console.log(`[enforce] Badge/Tag "${n.name}" layoutSizingHorizontal: ${n.layoutSizingHorizontal} → HUG`);
        n.layoutSizingHorizontal = 'HUG';
        stats.sizing++;
      }
    }

    // ── 5e. 규칙 F — Content 영역 FILL height ──
    if (n.type === 'frame') {
      const name = ((n.name as string) || '').toLowerCase();
      const contentNames = ['content', 'body', 'main', 'scroll', '리스트', '목록', '콘텐츠', '본문'];
      const isContentArea = contentNames.some(cn => name.includes(cn));
      if (isContentArea && !n.layoutSizingVertical) {
        n.layoutSizingVertical = 'FILL';
        console.log(`[enforce] Content area "${n.name}" layoutSizingVertical forced: FILL`);
        stats.sizing++;
      }
    }

    // ── 5f. 규칙 H — 단일 text 자식 중앙 정렬 ──
    if (n.type === 'frame' && Array.isArray(n.children)) {
      const children = n.children as Record<string, unknown>[];
      const al = n.autoLayout as Record<string, unknown> | undefined;
      if (al?.layoutMode === 'HORIZONTAL' && children.length === 1 && children[0].type === 'text') {
        // 버튼/배지 패턴: 부모에 CENTER 정렬 추가
        if (!al.counterAxisAlignItems) {
          al.counterAxisAlignItems = 'CENTER';
          console.log(`[enforce] Single-text frame "${n.name}" counterAxis forced: CENTER`);
          stats.alignment++;
        }
        if (!al.primaryAxisAlignItems) {
          al.primaryAxisAlignItems = 'CENTER';
          console.log(`[enforce] Single-text frame "${n.name}" primaryAxis forced: CENTER`);
          stats.alignment++;
        }
      }
    }

    // ── 5g. 규칙 I — 아이콘 래퍼 프레임 정사각형 강제 ──
    // 아이콘 1개만 감싸는 프레임(배경색 있음)은 반드시 정사각형이어야 함
    if (n.type === 'frame' && Array.isArray(n.children) && n.fill) {
      const children = n.children as Record<string, unknown>[];
      const iconChild = children.length === 1 && children[0].type === 'icon' ? children[0] : null;
      if (iconChild) {
        const iconSize = (iconChild.size as number) || 24;
        const w = n.width as number | undefined;
        const h = n.height as number | undefined;
        // Case 1: no explicit size → force square
        // Case 2: non-square → force to max(w, h) or icon + padding
        if (!w || !h || w !== h) {
          const desiredSize = Math.max(w || 0, h || 0, iconSize + 24); // icon + 12px padding each side
          n.width = desiredSize;
          n.height = desiredSize;
          console.log(`[enforce] Icon wrapper "${n.name}" forced square: ${desiredSize}×${desiredSize}`);
          stats.sizing++;
        }
        // Ensure center alignment
        const al = n.autoLayout as Record<string, unknown> | undefined;
        if (al) {
          al.primaryAxisAlignItems = 'CENTER';
          al.counterAxisAlignItems = 'CENTER';
        }
      }
    }

    // ── 5h. 규칙 J — 탭바 내 Pill/아이템 간격 강제 ──
    // Pill 컨테이너(탭바 내부)의 children에 FILL 강제
    if (n.type === 'frame' && Array.isArray(n.children)) {
      const name = ((n.name as string) || '').toLowerCase();
      const isPill = name.includes('pill') || name.includes('nav') || name.includes('탭');
      const al = n.autoLayout as Record<string, unknown> | undefined;
      if (isPill && al?.layoutMode === 'HORIZONTAL') {
        const pillChildren = n.children as Record<string, unknown>[];
        const allFrames = pillChildren.every(c => c.type === 'frame');
        if (allFrames && pillChildren.length >= 3) {
          // Pill 안의 탭 아이템들 → FILL width 강제
          for (const tab of pillChildren) {
            if (!tab.layoutSizingHorizontal || tab.layoutSizingHorizontal !== 'FILL') {
              tab.layoutSizingHorizontal = 'FILL';
              stats.sizing++;
            }
            if (!tab.layoutSizingVertical || tab.layoutSizingVertical !== 'FILL') {
              tab.layoutSizingVertical = 'FILL';
              stats.sizing++;
            }
          }
          console.log(`[enforce] Pill "${n.name}" children forced FILL: ${pillChildren.length} tabs`);
        }
      }
    }

    // ── 6. Hero section: padding + height + imageGenHint ──
    if (isHeroSection(n)) {
      // 6a. 좌우 패딩 강제 (Content 영역과 일관성)
      const al = n.autoLayout as Record<string, unknown> | undefined;
      if (al) {
        if (!al.paddingLeft && !al.paddingRight) {
          al.paddingLeft = 24;
          al.paddingRight = 24;
          console.log(`[enforce] Hero "${n.name}" padding forced: 24px left/right`);
          stats.structure++;
        }
      } else if (!n.padding) {
        // autoLayout 없는 경우 padding 배열로 설정
        n.padding = [20, 24, 20, 24]; // top, right, bottom, left
        console.log(`[enforce] Hero "${n.name}" padding array forced: [20, 24, 20, 24]`);
        stats.structure++;
      }

      // 6b. 높이 200px 강제
      if (!n.height || (n.height as number) < 180 || (n.height as number) > 220) {
        n.height = 200;
        console.log(`[enforce] Hero "${n.name}" height forced: 200`);
        stats.structure++;
      }

      // 6c. imageGenHint 자동 추가 — Banner Card 자식이 있으면 그곳에, 없으면 Hero Section에
      if (!n.imageGenHint) {
        const heroText = collectAllText(n);
        const hint = {
          prompt: `soft gradient background with abstract shapes, modern minimal style, matching the theme: ${heroText.slice(0, 60)}`,
          isHero: true,
        };
        // Banner Card 탐색: 자식 중 'banner' 또는 'card' 이름을 가진 프레임
        const children = (n.children as Record<string, unknown>[] | undefined) || [];
        const bannerCard = children.find(c => {
          const cName = ((c.name as string) || '').toLowerCase();
          return c.type === 'frame' && (cName.includes('banner') || cName.includes('card'));
        });
        if (bannerCard && !bannerCard.imageGenHint) {
          bannerCard.imageGenHint = hint;
          console.log(`[enforce] Added imageGenHint to Banner Card "${bannerCard.name}" (inside hero "${n.name}")`);
        } else if (!bannerCard) {
          n.imageGenHint = hint;
          console.log(`[enforce] Added imageGenHint to hero section "${n.name}" (no Banner Card found)`);
        }
      }
    }

    // ── Recurse children ──
    if (Array.isArray(n.children)) {
      n.children = (n.children as Record<string, unknown>[]).map(child =>
        enhance(child, n, false)
      );
    }

    return n;
  }

  // 루트 자체에도 토큰 필드 처리 (루트 fill을 시멘틱 토큰으로 받기 위해)
  processTokenFields(root);

  // 루트 자식들은 isRootChild=true로 호출
  if (Array.isArray(root.children)) {
    root.children = (root.children as Record<string, unknown>[]).map(child =>
      enhance(child, root, true)
    );
  }
  // 루트 자신에 대해서도 색상 정규화 적용
  normalizeNodeColors(root);

  // pendingBindings 마커를 root에 부착 — batch_build_screen 핸들러가 빌드 후 처리
  if (pendingBindings.length > 0) {
    (root as Record<string, unknown>)._pendingBindings = pendingBindings;
  }

  const totalCorrections = Object.values(stats).reduce((a, b) => a + b, 0);
  console.log(`[enforce] Blueprint enforcement complete: ${JSON.stringify(stats)} (${totalCorrections} total corrections, ${tintColorIdx} icons processed, ${pendingBindings.length} token bindings queued)`);
  return root;
}

/** 이모지 → DS v1 아이콘 매핑 */
const EMOJI_TO_ICON_MAP: Record<string, string> = {
  '🏠': 'home-01', '🏡': 'home-01', '🏢': 'home-02',
  '🔍': 'search-lg', '🔎': 'search-lg',
  '🔔': 'bell-01', '🔕': 'bell-01',
  '❤️': 'heart', '💜': 'heart', '💙': 'heart', '🧡': 'heart', '💛': 'heart', '💚': 'heart',
  '⭐': 'star-01', '🌟': 'star-01', '⭐️': 'star-01',
  '📱': 'phone-call-01', '📞': 'phone-call-01', '☎️': 'phone-call-01',
  '✉️': 'mail-01', '📧': 'mail-01', '📨': 'mail-01', '📩': 'mail-01',
  '🛒': 'shopping-cart-01', '🛍️': 'shopping-bag-01', '🛍': 'shopping-bag-01',
  '💰': 'currency-dollar-circle', '💵': 'currency-dollar-circle', '💳': 'credit-card-01', '💲': 'currency-dollar-circle',
  '🎁': 'gift-01', '🎀': 'gift-01',
  '👤': 'user-01', '👥': 'users-01', '🧑': 'user-01', '👨': 'user-01', '👩': 'user-01',
  '⚙️': 'settings-01', '🔧': 'settings-01', '🔨': 'settings-01',
  '🔒': 'lock-01', '🔓': 'lock-unlocked-01',
  '📅': 'calendar', '🗓️': 'calendar', '📆': 'calendar',
  '⏰': 'clock', '🕐': 'clock', '⏱️': 'clock',
  '🌍': 'globe-01', '🌎': 'globe-01', '🌏': 'globe-01',
  '🔗': 'link-01',
  '📸': 'camera-01', '📷': 'camera-01',
  '🖼️': 'image-01', '🖼': 'image-01',
  '✏️': 'edit-01', '📝': 'edit-01',
  '🗑️': 'trash-01', '🗑': 'trash-01',
  '📋': 'copy-01',
  '🔖': 'bookmark', '📌': 'bookmark',
  '🏷️': 'tag-01', '🏷': 'tag-01',
  '🚀': 'rocket-01',
  '📊': 'bar-chart-square-01', '📈': 'trend-up-01', '📉': 'trend-down-01',
  '✅': 'check-circle', '✔️': 'check',
  '❌': 'x-close', '⚠️': 'alert-triangle', 'ℹ️': 'info-circle', '❓': 'help-circle',
  '➕': 'plus', '➖': 'minus',
  '⬆️': 'arrow-up', '⬇️': 'arrow-down', '⬅️': 'arrow-left', '➡️': 'arrow-right',
  '▶️': 'play-circle', '⏸️': 'pause-circle',
  '🎵': 'music-note-01', '🎶': 'music-note-01',
  '📤': 'upload-01', '📥': 'download-04',
  '🔊': 'volume-max', '🎤': 'microphone-01',
  '🏅': 'award-01', '🏆': 'trophy-01', '🎯': 'target-01',
  '📖': 'book-open-01', '📚': 'book-open-01', '📕': 'book-open-01',
  '🎪': 'flag-01', '🎨': 'palette',
  '🏃': 'activity', '🏋️': 'activity', '💪': 'activity',
  '🎮': 'gaming-pad-01', '🕹️': 'gaming-pad-01',
  '✈️': 'plane', '🚗': 'car-01',
  '🍽️': 'coffee', '☕': 'coffee', '🍔': 'coffee',
  '💡': 'lightbulb-02',
  '🎉': 'celebration', '🥳': 'celebration', '🎊': 'celebration',
  '🔥': 'flame',
  '💬': 'message-circle-01', '💭': 'message-circle-01',
  '👍': 'thumbs-up', '👎': 'thumbs-down',
  '🧾': 'receipt',
  '📄': 'file-04', '📁': 'folder',
  '🎬': 'video-recorder', '🎥': 'video-recorder',
  '🩺': 'heart-hand', '💊': 'heart-hand',
  '🌱': 'leaf-01',
};

/** 이모지에서 아이콘 이름을 추측 (매핑에 없는 경우) */
function guessIconFromEmoji(_emoji: string): string | null {
  // EMOJI_TO_ICON_MAP에 없으면 null
  return null;
}

/** 이모지만 있는 텍스트인지 판별 */
function isEmojiOnlyText(n: Record<string, unknown>): boolean {
  if (n.type !== 'text' || !n.text) return false;
  const text = (n.text as string).trim();
  if (text.length === 0 || text.length > 10) return false;
  // 숫자/알파벳/한글 등 일반 문자가 있으면 절대 emoji-only 아님 (S2.5 fix)
  // \p{Emoji} 프로퍼티가 0-9, #, * 등을 keycap 후보로 포함하는 문제 회피
  if (/[a-zA-Z0-9가-힣ㄱ-ㅎㅏ-ㅣ]/.test(text)) return false;
  // Remove emoji, variation selectors, ZWJ, etc. If nothing remains, it's emoji-only
  const stripped = text.replace(/[\p{Emoji_Presentation}\p{Emoji}\uFE0F\u200D\u20E3\u{E0061}-\u{E007A}\u{E007F}]/gu, '').trim();
  return stripped.length === 0;
}

/** hex → {r,g,b,a} 변환. 0-255 범위도 0-1로 정규화 */
function normalizeColor(color: unknown): Record<string, number> | null {
  if (!color) return null;
  // 이미 {r,g,b} 객체
  if (typeof color === 'object' && color !== null && 'r' in color) {
    const c = color as Record<string, number>;
    let r = typeof c.r === 'number' ? c.r : 0;
    let g = typeof c.g === 'number' ? c.g : 0;
    let b = typeof c.b === 'number' ? c.b : 0;
    let a = typeof c.a === 'number' ? c.a : 1;
    // 0-255 범위 → 0-1 정규화
    if (r > 1 || g > 1 || b > 1) {
      r = r / 255;
      g = g / 255;
      b = b / 255;
    }
    return { r: Math.min(1, Math.max(0, r)), g: Math.min(1, Math.max(0, g)), b: Math.min(1, Math.max(0, b)), a: Math.min(1, Math.max(0, a)) };
  }
  // hex string
  if (typeof color === 'string') {
    const hex = color.replace('#', '');
    if (!/^[0-9a-fA-F]{3,8}$/.test(hex)) return null;
    let r: number, g: number, b: number, a = 1;
    if (hex.length === 3) {
      r = parseInt(hex[0] + hex[0], 16) / 255;
      g = parseInt(hex[1] + hex[1], 16) / 255;
      b = parseInt(hex[2] + hex[2], 16) / 255;
    } else if (hex.length === 6) {
      r = parseInt(hex.slice(0, 2), 16) / 255;
      g = parseInt(hex.slice(2, 4), 16) / 255;
      b = parseInt(hex.slice(4, 6), 16) / 255;
    } else if (hex.length === 8) {
      r = parseInt(hex.slice(0, 2), 16) / 255;
      g = parseInt(hex.slice(2, 4), 16) / 255;
      b = parseInt(hex.slice(4, 6), 16) / 255;
      a = parseInt(hex.slice(6, 8), 16) / 255;
    } else {
      return null;
    }
    return { r, g, b, a };
  }
  return null;
}

/** 한글 포함 여부 */
function containsKorean(text: string): boolean {
  return /[\uAC00-\uD7AF\u1100-\u11FF\u3130-\u318F\uA960-\uA97F\uD7B0-\uD7FF]/.test(text);
}

/** 한글 미지원 폰트 목록 */
const NON_KOREAN_FONTS = ['inter', 'roboto', 'arial', 'dm sans', 'bricolage grotesque', 'bricolage', 'helvetica', 'sf pro', 'poppins', 'open sans', 'lato', 'montserrat', 'nunito', 'raleway', 'oswald'];

/** 모바일 루트 프레임 판별 */
function isMobileRootFrame(n: Record<string, unknown>): boolean {
  const w = n.width as number;
  const h = n.height as number;
  return n.type === 'frame' &&
    typeof w === 'number' && w >= 360 && w <= 430 &&
    typeof h === 'number' && h >= 700;
}

// ── Detection helpers ──

function isSmallRectangle(n: Record<string, unknown>): boolean {
  return isSmallPlaceholder(n) && n.type === 'rectangle';
}

/** rectangle 또는 ellipse — 아이콘 placeholder로 의심되는 작은 도형 */
function isSmallPlaceholder(n: Record<string, unknown>): boolean {
  if ((n.type !== 'rectangle' && n.type !== 'ellipse') || n.children) return false;
  const w = n.width as number;
  const h = n.height as number;
  if (typeof w !== 'number' || typeof h !== 'number') return false;
  if (w > 60 || h > 60) return false;
  // Skip small decorative elements: status bar indicators, dots, thin dividers
  // Real icon placeholders are typically ≥16px on both dimensions
  if (w < 16 || h < 16) return false;
  // Skip extreme aspect ratios (dividers, lines) — must be roughly square-ish
  const ratio = Math.max(w, h) / Math.min(w, h);
  if (ratio > 2.5) return false;
  return true;
}

function isInsideListItem(_n: Record<string, unknown>, parent?: Record<string, unknown>): boolean {
  if (!parent) return false;
  const al = parent.autoLayout as Record<string, unknown> | undefined;
  return al?.layoutMode === 'HORIZONTAL' && isListItemWithPlaceholderIcon(parent);
}

function isTabBar(n: Record<string, unknown>): boolean {
  const name = ((n.name as string) || '').toLowerCase();
  const children = n.children as Record<string, unknown>[] | undefined;
  if (!children || children.length < 2) return false;

  // Tab bars: horizontal, 3-5 children, near bottom (height ~50-90)
  const al = n.autoLayout as Record<string, unknown> | undefined;
  const isHorizontal = al?.layoutMode === 'HORIZONTAL';
  const isTabLike = name.includes('tab') || name.includes('탭') ||
    name.includes('nav') || name.includes('bottom') || name.includes('하단');
  const hasTabCount = children.length >= 3 && children.length <= 6;
  const height = n.height as number;
  const isTabHeight = typeof height === 'number' && height >= 48 && height <= 100;

  // Each child should have text content (tab labels)
  const hasTextChildren = children.some(c => {
    const cc = c.children as Record<string, unknown>[] | undefined;
    return cc?.some(gc => gc.type === 'text') || c.type === 'text';
  });

  return (isHorizontal || isTabLike) && hasTabCount && hasTextChildren && (isTabLike || isTabHeight);
}

function isListItemWithPlaceholderIcon(n: Record<string, unknown>): boolean {
  const al = n.autoLayout as Record<string, unknown> | undefined;
  if (al?.layoutMode !== 'HORIZONTAL') return false;

  const children = n.children as Record<string, unknown>[] | undefined;
  if (!children || children.length < 2) return false;

  // Has at least one small placeholder (rectangle or ellipse) and at least one text/frame sibling
  const hasPlaceholder = children.some(c => isSmallPlaceholder(c));
  // Also detect emoji text as icon placeholder
  const hasEmoji = children.some(c => isEmojiOnlyText(c));
  const hasTextContent = children.some(c =>
    (c.type === 'text' && !isEmojiOnlyText(c)) ||
    (c.type === 'frame' && (c.children as Record<string, unknown>[] | undefined)?.some(gc => gc.type === 'text'))
  );

  return (hasPlaceholder || hasEmoji) && hasTextContent;
}

// Keep backward compat alias
function isListItemWithRectIcon(n: Record<string, unknown>): boolean {
  return isListItemWithPlaceholderIcon(n);
}

function isHeroSection(n: Record<string, unknown>): boolean {
  const name = ((n.name as string) || '').toLowerCase();
  const width = n.width as number;
  const height = n.height as number;
  const isLargeFrame = n.type === 'frame' &&
    typeof width === 'number' && width >= 300 &&
    typeof height === 'number' && height >= 120 && height <= 280;
  const isHeroNamed = name.includes('hero') || name.includes('banner') || name.includes('히어로') || name.includes('배너');
  const hasDarkFill = n.fill && typeof n.fill === 'object' &&
    (n.fill as Record<string, number>).r < 0.3;

  return isLargeFrame && (isHeroNamed || hasDarkFill);
}

// ── Context text extraction ──

function getContextText(n: Record<string, unknown>, parent?: Record<string, unknown>): string {
  const parts: string[] = [];
  // Node name
  if (n.name) parts.push(n.name as string);
  // Sibling text in parent
  if (parent && Array.isArray(parent.children)) {
    for (const sibling of parent.children as Record<string, unknown>[]) {
      if (sibling.type === 'text' && sibling.text) {
        parts.push(sibling.text as string);
      }
      // Text inside frame siblings
      if (sibling.type === 'frame' && Array.isArray(sibling.children)) {
        for (const gc of sibling.children as Record<string, unknown>[]) {
          if (gc.type === 'text' && gc.text) {
            parts.push(gc.text as string);
          }
        }
      }
    }
  }
  // Parent name
  if (parent?.name) parts.push(parent.name as string);
  return parts.join(' ');
}

function collectAllText(n: Record<string, unknown>): string {
  const parts: string[] = [];
  if (n.type === 'text' && n.text) parts.push(n.text as string);
  if (n.name) parts.push(n.name as string);
  if (Array.isArray(n.children)) {
    for (const child of n.children as Record<string, unknown>[]) {
      parts.push(collectAllText(child));
    }
  }
  return parts.join(' ');
}

function guessIconFromText(text: string): string | null {
  const lower = text.toLowerCase();
  for (const [keyword, iconName] of Object.entries(ICON_KEYWORD_MAP)) {
    if (lower.includes(keyword)) return iconName;
  }
  return null;
}

// ── Conversion helpers ──

function convertToIconBg(n: Record<string, unknown>, iconName: string, tintColor: Record<string, number>): void {
  const bgSize = 44;
  n.type = 'frame';
  n.width = bgSize;
  n.height = bgSize;
  n.cornerRadius = 12;
  n.fill = tintColor;
  n.autoLayout = {
    layoutMode: 'VERTICAL',
    primaryAxisAlignItems: 'CENTER',
    counterAxisAlignItems: 'CENTER',
  };
  n.children = [{
    type: 'icon',
    name: iconName,
    size: 24,
  }];
  // Clean rectangle properties
  delete n.stroke;
  delete n.strokeWeight;
}

function convertListItemIcon(listItem: Record<string, unknown>, colorIdx: number): void {
  const children = listItem.children as Record<string, unknown>[];
  if (!children) return;

  // Find the placeholder to convert: rectangle, ellipse, or emoji text
  let placeholderIdx = children.findIndex(c => isSmallPlaceholder(c));
  if (placeholderIdx === -1) {
    // Try emoji text
    placeholderIdx = children.findIndex(c => isEmojiOnlyText(c));
  }
  if (placeholderIdx === -1) return;

  const placeholder = children[placeholderIdx];
  const tintColor = ICON_TINT_COLORS[colorIdx % ICON_TINT_COLORS.length];

  // If placeholder is emoji text, use emoji mapping first
  let iconName: string;
  if (isEmojiOnlyText(placeholder)) {
    const emoji = (placeholder.text as string).trim();
    iconName = EMOJI_TO_ICON_MAP[emoji] || guessIconFromText(getContextText(placeholder, listItem)) || 'star-01';
    console.log(`[enhance] List item emoji "${emoji}" → ${iconName}`);
  } else {
    const contextText = getContextText(placeholder, listItem);
    iconName = guessIconFromText(contextText) || 'star-01';
    console.log(`[enhance] List item icon: "${contextText.slice(0, 30)}" → ${iconName}`);
  }

  // Convert in-place to icon bg frame
  convertToIconBg(children[placeholderIdx], iconName, tintColor);
}

function fixTabBar(tabBar: Record<string, unknown>): void {
  const children = tabBar.children as Record<string, unknown>[];
  if (!children) return;

  for (const tab of children) {
    const tabChildren = tab.children as Record<string, unknown>[] | undefined;
    if (!tabChildren) continue;

    // Find text label in this tab (non-emoji text)
    let label = '';
    for (const c of tabChildren) {
      if (c.type === 'text' && c.text && !isEmojiOnlyText(c)) {
        label = (c.text as string).toLowerCase();
        break;
      }
    }

    // Find placeholder in this tab: rectangle, ellipse, or emoji text
    let placeholderIdx = tabChildren.findIndex(c => isSmallPlaceholder(c));
    if (placeholderIdx === -1) {
      placeholderIdx = tabChildren.findIndex(c => isEmojiOnlyText(c));
    }

    // Also check if tab has NO icon at all (only text children, no icon/clone/svg_icon)
    const hasRealIcon = tabChildren.some(c =>
      c.type === 'icon' || c.type === 'clone' || c.type === 'svg_icon'
    );

    if (placeholderIdx !== -1) {
      let iconName: string;
      const placeholder = tabChildren[placeholderIdx];
      if (isEmojiOnlyText(placeholder)) {
        const emoji = (placeholder.text as string).trim();
        iconName = EMOJI_TO_ICON_MAP[emoji] || TAB_ICON_MAP[label] || guessIconFromText(label) || 'star-01';
        console.log(`[enhance] Tab emoji "${emoji}" → ${iconName} (label: "${label}")`);
      } else {
        iconName = TAB_ICON_MAP[label] || guessIconFromText(label) || 'star-01';
        console.log(`[enhance] Tab icon: "${label}" → ${iconName}`);
      }
      tabChildren[placeholderIdx] = {
        type: 'icon',
        name: iconName,
        size: 24,
      };
    } else if (!hasRealIcon && label) {
      // No icon at all — inject one at the beginning
      const iconName = TAB_ICON_MAP[label] || guessIconFromText(label) || 'star-01';
      tabChildren.unshift({
        type: 'icon',
        name: iconName,
        size: 24,
      } as Record<string, unknown>);
      console.log(`[enhance] Tab missing icon, injected: "${label}" → ${iconName}`);
    }
  }
}

export async function prefetchImages(nodes: unknown[]): Promise<void> {
  const promises: Promise<void>[] = [];

  function collect(node: Record<string, unknown>) {
    const imageFill = node.imageFill as Record<string, unknown> | undefined;
    if (imageFill?.url) {
      promises.push(
        fetchImageAsBase64(imageFill.url as string).then((base64) => {
          if (base64) node.imageData = base64;
        })
      );
    }
    // SVG icon prefetch: download SVG text from GitHub
    if (node.type === 'svg_icon' && node.svgUrl) {
      promises.push(
        fetch(node.svgUrl as string)
          .then(r => r.ok ? r.text() : Promise.reject(`HTTP ${r.status}`))
          .then(svg => { node.svgData = svg; })
          .catch(err => {
            console.warn(`[prefetch] SVG fetch failed for ${node.svgUrl}: ${err}`);
          })
      );
    }
    const children = node.children as unknown[] | undefined;
    if (children) {
      for (const child of children) {
        collect(child as Record<string, unknown>);
      }
    }
  }

  for (const node of nodes) {
    collect(node as Record<string, unknown>);
  }
  await Promise.all(promises);
}
