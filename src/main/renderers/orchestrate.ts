/**
 * Orchestrator — turns a ScreenSpec into a single executable JS payload.
 *
 *   buildScreenJS(spec) === setup + create-wrapper + sections... + overlays...
 *
 * The output is a self-contained async-IIFE-ready JS string that runs inside
 * the plugin's `execute_js` handler.
 */
import type { ScreenSpec } from './types';
import { buildSetupJS } from './setup';
import { renderSection, renderOverlay } from './components';

export function buildScreenJS(spec: ScreenSpec): string {
  const setup = buildSetupJS();

  const wrapperBg = spec.bgVar || 'bg-primary';
  const wrapperJSON = JSON.stringify({
    width: spec.width,
    positionRelativeTo: spec.positionRelativeTo || null,
    bgVar: wrapperBg,
    statusBar: spec.statusBar !== false,
  });

  const wrapperSetup = `
// ─── Wrapper ───────────────────────────────────────────────────────────
const SCREEN = ${wrapperJSON};
const wrapper = cAL("VERTICAL", { name: "Screen" });
wrapper.resize(SCREEN.width, 100);
wrapper.layoutSizingHorizontal = "FIXED";
wrapper.itemSpacing = 0;
wrapper.fills = [solid(v[SCREEN.bgVar.replace(/-([a-z])/g, (m,c)=>c.toUpperCase())] || v.bgPrimary)];
wrapper.clipsContent = false;
guiPage.appendChild(wrapper);

if (SCREEN.positionRelativeTo) {
  const ref = await figma.getNodeByIdAsync(SCREEN.positionRelativeTo);
  if (ref) { wrapper.x = ref.x + ref.width + 100; wrapper.y = ref.y; }
  else {
    const vp = figma.viewport.center;
    wrapper.x = Math.round(vp.x - SCREEN.width / 2);
    wrapper.y = Math.round(vp.y - 200);
  }
} else {
  const vp = figma.viewport.center;
  wrapper.x = Math.round(vp.x - SCREEN.width / 2);
  wrapper.y = Math.round(vp.y - 200);
}

if (SCREEN.statusBar) {
  try {
    const sbRef = await figma.getNodeByIdAsync(STATUS_BAR_INSTANCE_ID);
    if (sbRef) {
      const sb = sbRef.clone();
      sb.name = "Status Bar";
      wrapper.appendChild(sb);
      try { sb.layoutSizingHorizontal = "FILL"; } catch (e) {}
    }
  } catch (e) {}
}
`;

  // Insert spacer before TabBar overlay if present (so content doesn't sit under it)
  const hasTabBarOverlay = !!spec.overlays?.some(o => o.type === 'tabBar');
  const hasFabOverlay = !!spec.overlays?.some(o => o.type === 'fab');
  const sectionsCode = (spec.sections || []).map(renderSection).join('\n');
  const overlayPad = hasTabBarOverlay
    ? `
{
  const sf = figma.createFrame(); sf.fills = []; sf.resize(10, 90); sf.name = "TabBar Spacer";
  wrapper.appendChild(sf);
  sf.layoutSizingHorizontal = "FILL"; sf.resize(sf.width, 90);
}
`
    : '';
  const overlaysCode = (spec.overlays || []).map(renderOverlay).join('\n');

  const tail = `
// Sync in-memory __fdaComponents back to sharedPluginData on every build —
// covers cases where in-memory hit short-circuited the per-call writeRegistry.
try {
  const __mem = (typeof globalThis !== "undefined" ? globalThis.__fdaComponents : null) || {};
  const __reg = readRegistry();
  let __dirty = false;
  for (const __n of Object.keys(__mem)) {
    const __c = __mem[__n];
    if (__c && !__c.removed && __c.type === "COMPONENT") {
      const __cur = __reg[__n];
      if (!__cur || __cur.id !== __c.id) {
        __reg[__n] = { id: __c.id, key: __c.key };
        __dirty = true;
      }
    }
  }
  if (__dirty) writeRegistry(__reg);
} catch (e) {}

return {
  wrapperId: wrapper.id,
  wrapperHeight: wrapper.height,
  pretendardLoaded: pretendardOK,
  fontFamilyApplied: FONT.family,
  hasTabBar: ${hasTabBarOverlay},
  hasFab: ${hasFabOverlay},
};
`;

  return setup + wrapperSetup + sectionsCode + overlayPad + overlaysCode + tail;
}
