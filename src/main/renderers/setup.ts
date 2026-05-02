/**
 * Shared JS prelude that every generated build script starts with.
 *
 * Imports DS variables, icon components, fonts, and defines helper functions
 * (cAL, solid, txt, tintIcon, sp, fmtKRW, HUE, initialOf) that all component
 * renderers rely on. Emitted as a string and prepended by the orchestrator.
 */

// Variable keys discovered from imin DS file.
const VK = {
  bgPrimary: '6c9ef5bd6455bf4f056171ab65ae0dd2fadd45b4',
  bgSecondary: '97b2252f4f73f5fb26b1a7c8ff265c24ed464419',
  bgTertiary: 'a3dff86445e2076997c1bacd9136345ca0389acf',
  bgBrandPrimary: '83aa30a930aeb09c304465a7ec88849d9314d1a7',
  bgBrandSection: 'bb13767b7ff7e425d29bb917562b2b2d2a507ebf',
  textPrimary: '9306199145f76d6e79a403c51e7681b305d7ba0e',
  textSecondary: 'eaeea10790deb9cdf3641bac32338769d4bc912e',
  textTertiary: '25c91bd529559c0b8c9a1176092fa93fd98a754b',
  textWhite: '671ebf59024cf6039e7970c06143b9bd2bad6e87',
  textBrandPrimary: 'f7baf5dbdac9bf89b937e4132518e5de9a3b0f25',
  textBrandTertiary: '32a8253a5460bfd89757ac18fcc316754659c778',
  textErrorPrimary: '73f96c409c0a2aa4c09c385ae99bc1e96b168cc7',
  textWarningPrimary: 'cdd48986a9b57e92566ca3eadfa3ac9c9838dc0f',
  textSuccessPrimary: '4ab4c13e22da24fb7c8c200781fabc878a253386',
  bgErrorSecondary: 'd229063601ae192b66aa218da95a1095f6f4f175',
  bgErrorSolid: '19609f402e4f0384c8eb63733e9f0f2e262ce890',
  bgWarningPrimary: '7206ac4878279434ab441d91b0ce094a65e939d9',
  bgWarningSecondary: 'fd2439aaad0bb44ae1e30b6e7ccca1371865a56d',
  bgWarningSolid: '8dd0235fe239dfed692f44742163ce092f86e3cf',
  bgSuccessSecondary: 'f6e49c9bb0252de75d149e84b67c9dbcb60f2abf',
  bgSuccessSolid: '36323b552f28b9711e91dfd3f294bd7d007d9a30',
  fgWarningPrimary: '2ed2128976bc567313c051914e5a037d7ea26eeb',
  fgSuccessPrimary: '32bd287a0f58570ceb338469ee27f36d11a4d13e',
  borderPrimary: '879d09834d327a7a5b103b731ce39d6c1abba6f4',
  borderSecondary: '414a1701c43313f6fdcffa0c8c4cd21630086749',
};

// Icon component keys (extend as more icons are needed).
const IK = {
  bell: 'f80e23373a1afc1b460be44da32915f390b5af2a',
  message: '3071d1cea18e103f7187986d83ecc64972cccb21',
  home: '3b9e167503a7a91c597375d8c11c4f1a39fe5705',
  shoppingBag: '152430df50a07e03ae0c23e66095ca1e01cad66a',
  award: '693fa51a04e663ebcdd170889af004f5e53b0d67',
  users: '79e81ec517b9231b88e83c3b2320152ae38fd683',
  menu: '773e8ac3572b64c2031233074661490b45c43584',
  wallet: 'aa266194d742496709395561be5836b1445ee6ab',
  plus: '79245e6d92ced8a66acb73da034aa9f0b9f2dea2',
  minus: '8f765fd2b344e601d5fdc941f1ad6ba0bd71b1f1',
  star: '87c944c74bf3872495e2b8ce9b321479845e6958',
  starFilled: 'a6b00e07852059ae18ce4e3c8718b88bc721f696',
  currencyDollarCircle: '206d894ba988bcfdcb7af2c7272b30f465fa563a',
  creditCard: '3ae7504722eda4055dce0caaf35d48cc6b290fca',
  xClose: '4ba052703931aeecf495c7698e5002b6c89d1ad4',
  xCircle: 'f61c6bd7f114fee93cf4ba95dbe305dfdc6a7e39',
  chevronLeft: 'e129d4561a8d895e1767ed0667d2dde57de75835',
  chevronRight: 'e651fa113a7da73d33c1c755c8e4ed252bd6a9f5',
  check: 'fc7072f34589313dbb4bff965da31c0ab3c4e18a',
  checkCircle: 'd14346a2f1b8cf60680bf795cebf4bd32626a496',
  infoCircle: 'fbaa3423c6c4dbdf2558d9e590508df6b2128b91',
  diamond: 'bf815bf0397124249be6802be340f882ad7c450f',
  sparkle: '781d56540e849275dbc6f0cbf93b0bdb1a1392f4',
};

const LOGO_NODE_ID = '16712:25820';
const STATUS_BAR_INSTANCE_ID = '16941:49618';

export function buildSetupJS(): string {
  return `
const VK = ${JSON.stringify(VK)};
const IK = ${JSON.stringify(IK)};
const LOGO_NODE_ID = ${JSON.stringify(LOGO_NODE_ID)};
const STATUS_BAR_INSTANCE_ID = ${JSON.stringify(STATUS_BAR_INSTANCE_ID)};

const guiPage = figma.root.children.find(p => p.name === "GUI") || figma.currentPage;
await figma.setCurrentPageAsync(guiPage);

// ─── Fonts ─────────────────────────────────────────────────────────────
const NS_FALLBACK = "Noto Sans KR";
const FONT = { family: NS_FALLBACK };
let pretendardOK = false;
try {
  for (const style of ["Regular", "Medium", "Bold"]) {
    await figma.loadFontAsync({ family: "Pretendard", style });
  }
  FONT.family = "Pretendard";
  pretendardOK = true;
} catch (e) {
  for (const style of ["Regular", "Medium", "Bold"]) {
    await figma.loadFontAsync({ family: NS_FALLBACK, style });
  }
}
try { await figma.loadFontAsync({ family: "Inter", style: "Regular" }); } catch (e) {}

// ─── Variables + icons (cached for the rest of the script) ──────────
const v = {};
for (const k of Object.keys(VK)) {
  try { v[k] = await figma.variables.importVariableByKeyAsync(VK[k]); }
  catch (e) { v[k] = null; }
}
const ic = {};
for (const k of Object.keys(IK)) {
  try { ic[k] = await figma.importComponentByKeyAsync(IK[k]); }
  catch (e) { ic[k] = null; }
}

// ─── Helpers ───────────────────────────────────────────────────────────
const cAL = (direction, props) => {
  const f = figma.createFrame();
  f.layoutMode = (direction === "VERTICAL" || direction === "HORIZONTAL") ? direction : "HORIZONTAL";
  f.primaryAxisSizingMode = "AUTO";
  f.counterAxisSizingMode = "AUTO";
  if (props && typeof props === "object") {
    if (typeof props.name === "string") f.name = props.name;
    if (typeof props.itemSpacing === "number") f.itemSpacing = props.itemSpacing;
  }
  return f;
};
const solid = (vRef) => figma.variables.setBoundVariableForPaint(
  { type: "SOLID", color: { r: 0.5, g: 0.5, b: 0.5 } }, "color", vRef
);
const rawSolid = (r, g, b, a) => ({ type: "SOLID", color: { r, g, b }, opacity: a == null ? 1 : a });
const txt = (chars, opts) => {
  const t = figma.createText();
  try { t.fontName = { family: FONT.family, style: opts.weight || "Regular" }; }
  catch (e) { t.fontName = { family: NS_FALLBACK, style: opts.weight || "Regular" }; }
  t.characters = chars;
  t.fontSize = opts.size;
  if (opts.colorVar) t.fills = [solid(opts.colorVar)];
  else if (opts.colorRaw) t.fills = [rawSolid(opts.colorRaw.r, opts.colorRaw.g, opts.colorRaw.b)];
  if (opts.align) t.textAlignHorizontal = opts.align;
  return t;
};
const tintIcon = (inst, colorVar) => {
  const setFill = (n) => {
    if (n.fills && Array.isArray(n.fills) && n.fills.length > 0) {
      try { n.fills = [solid(colorVar)]; } catch (e) {}
    }
    if ("children" in n && Array.isArray(n.children)) {
      for (const c of n.children) setFill(c);
    }
  };
  setFill(inst);
};
const sp = (parent, h) => {
  const s = figma.createFrame(); s.fills = []; s.resize(10, h);
  parent.appendChild(s);
  s.layoutSizingHorizontal = "FILL";
  s.resize(s.width, h);
  return s;
};
const fmtKRW = (n) => (n < 0 ? "-" : "") + Math.abs(n).toLocaleString("en-US") + "원";

// ─── Component registry — read/write component keys from file's sharedPluginData
//     Lazy-registered components live on a hidden "AGENT_LIBRARY" page.
const REGISTRY_NS = "fda_renderer";
const REGISTRY_KEY = "componentKeys";
const LIBRARY_PAGE_NAME = "❖ AGENT_LIBRARY";

const readRegistry = () => {
  try {
    const raw = figma.root.getSharedPluginData(REGISTRY_NS, REGISTRY_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch (e) { return {}; }
};
const writeRegistry = (map) => {
  try { figma.root.setSharedPluginData(REGISTRY_NS, REGISTRY_KEY, JSON.stringify(map)); } catch (e) {}
};
const getOrCreateLibraryPage = async () => {
  let page = figma.root.children.find(p => p.name === LIBRARY_PAGE_NAME);
  if (!page) {
    page = figma.createPage();
    page.name = LIBRARY_PAGE_NAME;
  }
  return page;
};

// ensureComponent(name, buildFn) — name maps to a single registered component.
// Subsequent calls re-import the registered component instead of rebuilding.
//
// buildFn(component) populates the component's children and may return
//   { properties: [{ name, type, default, bindNodeToCharacters?, bindNodeToVisible? }, ...] }
// on first build. The helper adds those component properties and binds child
// nodes' characters/visible to them, so callers can use setComponentProperties
// on instances later.
// Registry stores { id, key } per name. id is the local node id (used by
// getNodeByIdAsync — works for unpublished local components). key is kept
// for parity / future publish-aware lookup but importComponentByKeyAsync
// fails for unpublished local components, so id is the primary lookup.
//
// In-memory cache keyed by component name — survives the same execute_js
// block so two calls in the same screen share one master without round-tripping
// through getSharedPluginData.
const __memCache = (typeof globalThis !== "undefined" ? globalThis : {});
__memCache.__fdaComponents = __memCache.__fdaComponents || {};
__memCache.__fdaDsSets = __memCache.__fdaDsSets || {};

// DS published library set keys — works in any file via importComponentSetByKeyAsync.
// Variants are selected via setProperties on the instance.
const DS_KEYS = {
  tag: "b0e07022957bb0df43abbe3183c6bdc2bc41bf7c",
  segmentedButton: "96f893df8e457a0dbf9be27bd7c2de1c3d6cc654",
  tabButton: "189bffb4112ea1036b51a3d4536ce349f134177d",
  metricItem: "924774d77017f1e51387f88a392391c60ebaab63",
  buttons: "4d53db77d62f7e0cd7495bcbf219127c67ef30d2",
  avatar: "f2faecdad7c29604051ff497f3f543b159ccc3ae",
  calendarCell: "62c138750e64094a9a4f56906ddbc468f0d5ea90",
};

// ensureDsSet(setKey) — imports a published DS component set, caching in-memory
// for the rest of the screen build. Returns the ComponentSet (use .defaultVariant
// or pick a specific variant by traversing children).
const ensureDsSet = async (setKey) => {
  const cached = __memCache.__fdaDsSets[setKey];
  if (cached && !cached.removed) return cached;
  const set = await figma.importComponentSetByKeyAsync(setKey);
  __memCache.__fdaDsSets[setKey] = set;
  return set;
};

// dsInstance(setKey, propsMap?) — creates an instance of the published DS set's
// default variant and applies setProperties. Returns the instance.
const dsInstance = async (setKey, propsMap) => {
  const set = await ensureDsSet(setKey);
  const inst = set.defaultVariant.createInstance();
  if (propsMap) {
    try {
      const defs = set.defaultVariant.componentPropertyDefinitions || {};
      const realProps = {};
      for (const name of Object.keys(propsMap)) {
        const propKey = Object.keys(defs).find(k => k === name || k.startsWith(name + "#"));
        if (propKey) realProps[propKey] = propsMap[name];
      }
      if (Object.keys(realProps).length > 0) {
        inst.setProperties(realProps);
      }
    } catch (e) {}
  }
  return inst;
};

const ensureComponent = async (name, buildFn) => {
  // 1. in-memory hit (same execute_js call)
  const cached = __memCache.__fdaComponents[name];
  if (cached && !cached.removed && cached.type === "COMPONENT") {
    return { component: cached, key: cached.key, reused: true };
  }
  // 2. sharedPluginData hit (across execute_js calls)
  const registry = readRegistry();
  const entry = registry[name];
  if (entry && entry.id) {
    try {
      const node = await figma.getNodeByIdAsync(entry.id);
      if (node && node.type === "COMPONENT" && !node.removed) {
        __memCache.__fdaComponents[name] = node;
        return { component: node, key: node.key, reused: true };
      }
    } catch (e) { /* stale id, fall through and rebuild */ }
  }
  const libPage = await getOrCreateLibraryPage();
  const comp = figma.createComponent();
  comp.name = name;
  comp.layoutMode = "VERTICAL";
  comp.primaryAxisSizingMode = "AUTO";
  comp.counterAxisSizingMode = "AUTO";
  comp.fills = [];
  comp.clipsContent = false;
  libPage.appendChild(comp);
  let maxX = 0;
  for (const c of libPage.children) if (c.id !== comp.id) maxX = Math.max(maxX, c.x + c.width);
  comp.x = maxX + 60; comp.y = 0;

  const meta = await buildFn(comp);

  if (meta && Array.isArray(meta.properties)) {
    for (const p of meta.properties) {
      let propKey;
      try { propKey = comp.addComponentProperty(p.name, p.type, p.default); }
      catch (e) { continue; }
      if (p.bindNodeToCharacters) {
        try {
          const existing = p.bindNodeToCharacters.componentPropertyReferences || {};
          p.bindNodeToCharacters.componentPropertyReferences = Object.assign({}, existing, { characters: propKey });
        } catch (e) {}
      }
      if (p.bindNodeToVisible) {
        try {
          const existing = p.bindNodeToVisible.componentPropertyReferences || {};
          p.bindNodeToVisible.componentPropertyReferences = Object.assign({}, existing, { visible: propKey });
        } catch (e) {}
      }
    }
  }

  registry[name] = { id: comp.id, key: comp.key };
  writeRegistry(registry);
  __memCache.__fdaComponents[name] = comp;
  return { component: comp, key: comp.key, reused: false };
};

// setComponentProperties(instance, { propName: value, ... }) — resolves the
// "name#randomId" propKeys and calls instance.setProperties safely.
// Uses getMainComponentAsync (dynamic-page mode safe).
const setComponentProperties = async (instance, propsMap) => {
  if (!instance) return;
  let mainComp;
  try { mainComp = await instance.getMainComponentAsync(); } catch (e) { return; }
  if (!mainComp) return;
  const defs = mainComp.componentPropertyDefinitions || {};
  const realProps = {};
  for (const name of Object.keys(propsMap)) {
    const propKey = Object.keys(defs).find(k => k === name || k.startsWith(name + "#"));
    if (propKey) realProps[propKey] = propsMap[name];
  }
  if (Object.keys(realProps).length > 0) {
    try { instance.setProperties(realProps); } catch (e) {}
  }
};
const HUE = {
  purple: { c1: { r: 0.737, g: 0.502, b: 0.984 }, c2: { r: 0.412, g: 0.220, b: 0.937 } },
  pink:   { c1: { r: 0.961, g: 0.443, b: 0.706 }, c2: { r: 0.925, g: 0.282, b: 0.600 } },
  amber:  { c1: { r: 0.992, g: 0.749, b: 0.286 }, c2: { r: 0.961, g: 0.620, b: 0.043 } },
  green:  { c1: { r: 0.204, g: 0.831, b: 0.600 }, c2: { r: 0.063, g: 0.725, b: 0.506 } },
  blue:   { c1: { r: 0.380, g: 0.647, b: 0.980 }, c2: { r: 0.149, g: 0.388, b: 0.922 } },
  red:    { c1: { r: 0.973, g: 0.443, b: 0.443 }, c2: { r: 0.890, g: 0.196, b: 0.196 } },
};
const initialOf = (name) => name && name.length > 0 ? name[0] : "?";
`;
}
