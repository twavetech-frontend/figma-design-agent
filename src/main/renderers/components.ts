/**
 * Component renderers — one per SectionSpec type.
 *
 * Each renderer takes a section spec and returns JS code that, when run
 * inside a context where setup helpers (cAL, txt, sp, solid, tintIcon, v, ic,
 * HUE, FONT, NS_FALLBACK, fmtKRW, initialOf) are in scope and `wrapper` is
 * the parent frame, builds that section.
 *
 * The orchestrator concatenates the renderer outputs in spec order.
 */
import type {
  SectionSpec, OverlaySpec,
  AppHeaderSection, ModalHeaderSection, BackHeaderSection,
  FilterChipRowSection, SegmentedTabSection, UnderlineTabSection,
  SectionHeaderRow, StepperCardSection, AvatarRowSection,
  SummaryCardLinkRowsSection, MonthScrollerCalendarSection,
  StatsStrip3ColSection, TransactionTimelineSection, StageCardListSection,
  FooterLegalSection, TabBarSection, FabSection, SpacerSection,
} from './types';

const j = (x: unknown) => JSON.stringify(x);

// Each section is wrapped in an IIFE to isolate its locals.
const wrap = (body: string) => `await (async () => {\n${body}\n})();`;

// ─── App Header ────────────────────────────────────────────────────────
function renderAppHeader(s: AppHeaderSection): string {
  return wrap(`
const s = ${j(s)};
const nav = cAL("HORIZONTAL", { name: "App Header" });
nav.fills = [];
nav.paddingLeft = 20; nav.paddingRight = 20;
nav.paddingTop = 12; nav.paddingBottom = 8;
nav.primaryAxisAlignItems = "SPACE_BETWEEN";
nav.counterAxisAlignItems = "CENTER";
wrapper.appendChild(nav);
nav.layoutSizingHorizontal = "FILL"; nav.layoutSizingVertical = "HUG";

const logoComp = await figma.getNodeByIdAsync(LOGO_NODE_ID);
let logoNode;
if (logoComp && logoComp.type === "COMPONENT") {
  logoNode = logoComp.createInstance();
  const targetH = 22;
  const aspectW = Math.round((logoComp.width / logoComp.height) * targetH);
  logoNode.resize(aspectW, targetH);
} else {
  logoNode = txt(s.logoText || "imin", { weight: "Bold", size: 22, colorVar: v.textPrimary });
}
nav.appendChild(logoNode);

const navRight = cAL("HORIZONTAL", { itemSpacing: 4 });
navRight.fills = []; navRight.counterAxisAlignItems = "CENTER";
nav.appendChild(navRight);
navRight.layoutSizingHorizontal = "HUG"; navRight.layoutSizingVertical = "HUG";
const rightIcons = (s.rightIcons && s.rightIcons.length) ? s.rightIcons : ["bell", "message"];
for (const ck of rightIcons) {
  if (!ic[ck]) continue;
  const btn = cAL("HORIZONTAL");
  btn.fills = [];
  btn.paddingLeft = 4; btn.paddingRight = 4; btn.paddingTop = 4; btn.paddingBottom = 4;
  btn.primaryAxisAlignItems = "CENTER"; btn.counterAxisAlignItems = "CENTER";
  navRight.appendChild(btn);
  btn.layoutSizingHorizontal = "HUG"; btn.layoutSizingVertical = "HUG";
  const inst = ic[ck].createInstance();
  inst.resize(22, 22);
  tintIcon(inst, v.textSecondary);
  btn.appendChild(inst);
}
`);
}

// ─── Modal Header — registered component
function renderModalHeader(s: ModalHeaderSection): string {
  return wrap(`
const s = ${j(s)};
const { component: mhComp } = await ensureComponent("modalHeader", async (parent) => {
  parent.layoutMode = "HORIZONTAL";
  parent.primaryAxisSizingMode = "FIXED";
  parent.counterAxisSizingMode = "AUTO";
  parent.resize(393, 56);
  parent.paddingLeft = 20; parent.paddingRight = 20;
  parent.paddingTop = 16; parent.paddingBottom = 16;
  parent.counterAxisAlignItems = "CENTER";
  parent.primaryAxisAlignItems = "SPACE_BETWEEN";
  parent.fills = [];
  const titleNode = txt("Title", { weight: "Bold", size: 17, colorVar: v.textPrimary });
  parent.appendChild(titleNode);
  const closeBtn = cAL("HORIZONTAL");
  closeBtn.fills = [];
  closeBtn.paddingLeft = 4; closeBtn.paddingRight = 4; closeBtn.paddingTop = 4; closeBtn.paddingBottom = 4;
  closeBtn.primaryAxisAlignItems = "CENTER"; closeBtn.counterAxisAlignItems = "CENTER";
  parent.appendChild(closeBtn);
  closeBtn.layoutSizingHorizontal = "HUG"; closeBtn.layoutSizingVertical = "HUG";
  if (ic.xClose) {
    const xi = ic.xClose.createInstance(); xi.resize(24, 24);
    tintIcon(xi, v.textPrimary);
    closeBtn.appendChild(xi);
  }
  return {
    properties: [
      { name: "title", type: "TEXT", default: "Title", bindNodeToCharacters: titleNode },
      { name: "showTitle", type: "BOOLEAN", default: true, bindNodeToVisible: titleNode },
      { name: "showClose", type: "BOOLEAN", default: true, bindNodeToVisible: closeBtn },
    ],
  };
});
const inst = mhComp.createInstance();
wrapper.appendChild(inst);
inst.layoutSizingHorizontal = "FILL"; inst.layoutSizingVertical = "HUG";
await setComponentProperties(inst, {
  title: s.title || "",
  showTitle: !!s.title,
  showClose: s.showClose !== false,
});
`);
}

// ─── Back Header (chevron-left on left) ───────────────────────────────
function renderBackHeader(s: BackHeaderSection): string {
  return wrap(`
const s = ${j(s)};
const { component: bhComp } = await ensureComponent("backHeader", async (parent) => {
  parent.layoutMode = "HORIZONTAL";
  parent.primaryAxisSizingMode = "FIXED";
  parent.counterAxisSizingMode = "AUTO";
  parent.resize(393, 48);
  parent.paddingLeft = 16; parent.paddingRight = 20;
  parent.paddingTop = 12; parent.paddingBottom = 12;
  parent.itemSpacing = 8;
  parent.counterAxisAlignItems = "CENTER";
  parent.fills = [];
  const backBtn = cAL("HORIZONTAL");
  backBtn.fills = [];
  backBtn.paddingLeft = 4; backBtn.paddingRight = 4; backBtn.paddingTop = 4; backBtn.paddingBottom = 4;
  backBtn.primaryAxisAlignItems = "CENTER"; backBtn.counterAxisAlignItems = "CENTER";
  parent.appendChild(backBtn);
  backBtn.layoutSizingHorizontal = "HUG"; backBtn.layoutSizingVertical = "HUG";
  if (ic.chevronLeft) {
    const ci = ic.chevronLeft.createInstance(); ci.resize(24, 24);
    tintIcon(ci, v.textPrimary);
    backBtn.appendChild(ci);
  }
  const titleNode = txt("Title", { weight: "Bold", size: 17, colorVar: v.textPrimary });
  parent.appendChild(titleNode);
  return {
    properties: [
      { name: "title", type: "TEXT", default: "Title", bindNodeToCharacters: titleNode },
      { name: "showTitle", type: "BOOLEAN", default: true, bindNodeToVisible: titleNode },
    ],
  };
});
const inst = bhComp.createInstance();
wrapper.appendChild(inst);
inst.layoutSizingHorizontal = "FILL"; inst.layoutSizingVertical = "HUG";
await setComponentProperties(inst, {
  title: s.title || "",
  showTitle: !!s.title,
});
`);
}

// ─── Filter Chip Row ───────────────────────────────────────────────────
function renderFilterChipRow(s: FilterChipRowSection): string {
  return wrap(`
const s = ${j(s)};
const row = cAL("HORIZONTAL", { name: "Filter Row" });
row.fills = [];
row.paddingLeft = 20; row.paddingRight = 20;
row.paddingTop = 8; row.paddingBottom = 12;
row.itemSpacing = 8;
wrapper.appendChild(row);
row.layoutSizingHorizontal = "FILL"; row.layoutSizingVertical = "HUG";
const { component: chipComp } = await ensureComponent("filterChip", async (parent) => {
  parent.layoutMode = "HORIZONTAL";
  parent.primaryAxisSizingMode = "AUTO";
  parent.counterAxisSizingMode = "AUTO";
  parent.fills = [solid(v.bgSecondary)];
  parent.cornerRadius = 9999;
  parent.paddingLeft = 14; parent.paddingRight = 14;
  parent.paddingTop = 7; parent.paddingBottom = 7;
  parent.primaryAxisAlignItems = "CENTER"; parent.counterAxisAlignItems = "CENTER";
  const labelNode = txt("Chip", { weight: "Bold", size: 14, colorVar: v.textPrimary });
  parent.appendChild(labelNode);
  return {
    properties: [
      { name: "label", type: "TEXT", default: "Chip", bindNodeToCharacters: labelNode },
    ],
  };
});

for (const c of s.chips) {
  const inst = chipComp.createInstance();
  row.appendChild(inst);
  inst.layoutSizingHorizontal = "HUG"; inst.layoutSizingVertical = "HUG";
  await setComponentProperties(inst, { label: c.text });
  if (c.selected) {
    try { inst.fills = [solid(v.bgBrandSection)]; } catch (e) {}
    try {
      const labelNode = inst.children[0];
      if (labelNode) labelNode.fills = [solid(v.textWhite)];
    } catch (e) {}
  }
}
`);
}

// ─── Segmented Tab (pill) ─────────────────────────────────────────────
function renderSegmentedTab(s: SegmentedTabSection): string {
  return wrap(`
const s = ${j(s)};
const wrap2 = cAL("HORIZONTAL", { name: "Segmented Tab Wrap" });
wrap2.fills = [];
wrap2.paddingLeft = 20; wrap2.paddingRight = 20;
wrap2.paddingTop = 8; wrap2.paddingBottom = 12;
wrapper.appendChild(wrap2);
wrap2.layoutSizingHorizontal = "FILL"; wrap2.layoutSizingVertical = "HUG";

const track = cAL("HORIZONTAL", { name: "Segmented Track" });
track.fills = [solid(v.bgSecondary)];
track.cornerRadius = 9999;
track.paddingLeft = 4; track.paddingRight = 4; track.paddingTop = 4; track.paddingBottom = 4;
track.itemSpacing = 0;
wrap2.appendChild(track);
track.layoutSizingHorizontal = "FILL"; track.layoutSizingVertical = "HUG";

const { component: segComp } = await ensureComponent("segmentedTabItem", async (parent) => {
  parent.layoutMode = "HORIZONTAL";
  parent.primaryAxisSizingMode = "FIXED";
  parent.counterAxisSizingMode = "AUTO";
  parent.resize(120, 32);
  parent.fills = [];
  parent.cornerRadius = 9999;
  parent.paddingTop = 8; parent.paddingBottom = 8;
  parent.primaryAxisAlignItems = "CENTER";
  parent.counterAxisAlignItems = "CENTER";
  const labelNode = txt("Tab", { weight: "Medium", size: 14, colorVar: v.textTertiary });
  parent.appendChild(labelNode);
  return {
    properties: [
      { name: "label", type: "TEXT", default: "Tab", bindNodeToCharacters: labelNode },
    ],
  };
});
for (const t of s.tabs) {
  const isActive = t.id === s.activeId;
  const inst = segComp.createInstance();
  track.appendChild(inst);
  inst.layoutSizingHorizontal = "FILL"; inst.layoutSizingVertical = "HUG";
  await setComponentProperties(inst, { label: t.label });
  if (isActive) {
    try { inst.fills = [solid(v.bgPrimary)]; } catch (e) {}
    try {
      inst.effects = [{
        type: "DROP_SHADOW", color: { r: 0, g: 0, b: 0, a: 0.06 },
        offset: { x: 0, y: 1 }, radius: 2, spread: 0, visible: true, blendMode: "NORMAL",
      }];
    } catch (e) {}
    try {
      const labelNode = inst.children[0];
      if (labelNode) {
        labelNode.fills = [solid(v.textPrimary)];
        labelNode.fontName = { family: labelNode.fontName.family, style: "Bold" };
      }
    } catch (e) {}
  }
}
`);
}

// ─── Underline Tab ─────────────────────────────────────────────────────
function renderUnderlineTab(s: UnderlineTabSection): string {
  return wrap(`
const s = ${j(s)};
const tabRow = cAL("HORIZONTAL", { name: "Underline Tabs" });
tabRow.fills = [];
tabRow.paddingLeft = 20; tabRow.paddingRight = 20;
tabRow.itemSpacing = 16;
tabRow.strokes = [solid(v.borderSecondary)];
tabRow.strokeWeight = 1; tabRow.strokeAlign = "INSIDE";
tabRow.strokeBottomWeight = 1; tabRow.strokeTopWeight = 0;
tabRow.strokeLeftWeight = 0; tabRow.strokeRightWeight = 0;
wrapper.appendChild(tabRow);
tabRow.layoutSizingHorizontal = "FILL"; tabRow.layoutSizingVertical = "HUG";

const { component: utComp } = await ensureComponent("underlineTabItem", async (parent) => {
  parent.layoutMode = "VERTICAL";
  parent.primaryAxisSizingMode = "AUTO";
  parent.counterAxisSizingMode = "AUTO";
  parent.itemSpacing = 8;
  parent.paddingTop = 12; parent.paddingBottom = 12;
  parent.primaryAxisAlignItems = "CENTER";
  parent.counterAxisAlignItems = "CENTER";
  parent.fills = [];
  const labelNode = txt("Tab", { weight: "Medium", size: 16, colorVar: v.textTertiary });
  parent.appendChild(labelNode);
  return {
    properties: [
      { name: "label", type: "TEXT", default: "Tab", bindNodeToCharacters: labelNode },
    ],
  };
});
for (const t of s.tabs) {
  const isActive = t.id === s.activeId;
  const inst = utComp.createInstance();
  tabRow.appendChild(inst);
  inst.layoutSizingHorizontal = "HUG"; inst.layoutSizingVertical = "HUG";
  await setComponentProperties(inst, { label: t.label });
  if (isActive) {
    try {
      inst.strokes = [solid(v.textPrimary)];
      inst.strokeWeight = 2; inst.strokeAlign = "INSIDE";
      inst.strokeBottomWeight = 2; inst.strokeTopWeight = 0;
      inst.strokeLeftWeight = 0; inst.strokeRightWeight = 0;
    } catch (e) {}
    try {
      const labelNode = inst.children[0];
      if (labelNode) {
        labelNode.fills = [solid(v.textPrimary)];
        labelNode.fontName = { family: labelNode.fontName.family, style: "Bold" };
      }
    } catch (e) {}
  }
}
`);
}

// ─── Section Header — registered component, instance + setProperties
function renderSectionHeader(s: SectionHeaderRow): string {
  return wrap(`
const s = ${j(s)};
const { component } = await ensureComponent("sectionHeader", async (parent) => {
  parent.layoutMode = "HORIZONTAL";
  parent.primaryAxisSizingMode = "FIXED";
  parent.counterAxisSizingMode = "AUTO";
  parent.resize(393, 40);
  parent.primaryAxisAlignItems = "SPACE_BETWEEN";
  parent.counterAxisAlignItems = "CENTER";
  parent.paddingLeft = 20; parent.paddingRight = 20;
  parent.paddingTop = 16; parent.paddingBottom = 8;
  parent.fills = [];
  const titleNode = txt("Title", { weight: "Bold", size: 15, colorVar: v.textPrimary });
  parent.appendChild(titleNode);
  const trailingNode = txt("Trailing", { weight: "Medium", size: 13, colorVar: v.textTertiary });
  parent.appendChild(trailingNode);
  return {
    properties: [
      { name: "title", type: "TEXT", default: "Title", bindNodeToCharacters: titleNode },
      { name: "trailing", type: "TEXT", default: "Trailing", bindNodeToCharacters: trailingNode },
      { name: "showTrailing", type: "BOOLEAN", default: true, bindNodeToVisible: trailingNode },
    ],
  };
});
const inst = component.createInstance();
wrapper.appendChild(inst);
inst.layoutSizingHorizontal = "FILL"; inst.layoutSizingVertical = "HUG";
await setComponentProperties(inst, {
  title: s.title,
  trailing: s.trailing || "",
  showTrailing: !!s.trailing,
});
`);
}

// ─── Stepper Card ──────────────────────────────────────────────────────
function renderStepperCard(s: StepperCardSection): string {
  return wrap(`
const s = ${j(s)};
const w = cAL("VERTICAL", { name: "Stepper Wrap" });
w.fills = [];
w.paddingLeft = 20; w.paddingRight = 20; w.paddingBottom = 18;
wrapper.appendChild(w);
w.layoutSizingHorizontal = "FILL"; w.layoutSizingVertical = "HUG";

const card = cAL("VERTICAL", { name: "Stepper Card" });
card.fills = [solid(v.bgSecondary)];
card.cornerRadius = 14;
card.paddingLeft = 16; card.paddingRight = 16; card.paddingTop = 4; card.paddingBottom = 4;
card.itemSpacing = 0;
w.appendChild(card);
card.layoutSizingHorizontal = "FILL"; card.layoutSizingVertical = "HUG";

const { component: scComp } = await ensureComponent("stepperCardRow", async (parent) => {
  parent.layoutMode = "HORIZONTAL";
  parent.primaryAxisSizingMode = "FIXED";
  parent.counterAxisSizingMode = "AUTO";
  parent.resize(321, 46);
  parent.fills = [];
  parent.primaryAxisAlignItems = "SPACE_BETWEEN";
  parent.counterAxisAlignItems = "CENTER";
  parent.paddingTop = 10; parent.paddingBottom = 10;
  parent.strokes = [solid(v.borderSecondary)];
  parent.strokeBottomWeight = 1; parent.strokeTopWeight = 0;
  parent.strokeLeftWeight = 0; parent.strokeRightWeight = 0;
  parent.strokeAlign = "INSIDE";
  const labelNode = txt("Label", { weight: "Medium", size: 14, colorVar: v.textSecondary });
  parent.appendChild(labelNode);

  const grp = cAL("HORIZONTAL", { itemSpacing: 14 });
  grp.fills = []; grp.counterAxisAlignItems = "CENTER";
  parent.appendChild(grp);
  grp.layoutSizingHorizontal = "HUG"; grp.layoutSizingVertical = "HUG";

  const minusBtn = cAL("HORIZONTAL");
  minusBtn.fills = [solid(v.bgPrimary)]; minusBtn.strokes = [solid(v.borderPrimary)];
  minusBtn.strokeWeight = 1; minusBtn.cornerRadius = 9999;
  minusBtn.primaryAxisAlignItems = "CENTER"; minusBtn.counterAxisAlignItems = "CENTER";
  grp.appendChild(minusBtn);
  minusBtn.resize(26, 26);
  minusBtn.layoutSizingHorizontal = "FIXED"; minusBtn.layoutSizingVertical = "FIXED";
  if (ic.minus) {
    const mi = ic.minus.createInstance(); mi.resize(14, 14);
    tintIcon(mi, v.textSecondary);
    minusBtn.appendChild(mi);
  }

  const valWrap = cAL("HORIZONTAL", { itemSpacing: 2 });
  valWrap.fills = []; valWrap.counterAxisAlignItems = "BASELINE"; valWrap.primaryAxisAlignItems = "CENTER";
  grp.appendChild(valWrap);
  valWrap.resize(90, 20);
  valWrap.layoutSizingHorizontal = "FIXED"; valWrap.layoutSizingVertical = "HUG";
  const valueNode = txt("0", { weight: "Bold", size: 14, colorVar: v.textPrimary });
  const unitNode = txt("", { weight: "Medium", size: 12, colorVar: v.textTertiary });
  valWrap.appendChild(valueNode);
  valWrap.appendChild(unitNode);

  const plusBtn = cAL("HORIZONTAL");
  plusBtn.fills = [solid(v.bgPrimary)]; plusBtn.strokes = [solid(v.borderPrimary)];
  plusBtn.strokeWeight = 1; plusBtn.cornerRadius = 9999;
  plusBtn.primaryAxisAlignItems = "CENTER"; plusBtn.counterAxisAlignItems = "CENTER";
  grp.appendChild(plusBtn);
  plusBtn.resize(26, 26);
  plusBtn.layoutSizingHorizontal = "FIXED"; plusBtn.layoutSizingVertical = "FIXED";
  if (ic.plus) {
    const pi = ic.plus.createInstance(); pi.resize(14, 14);
    tintIcon(pi, v.textSecondary);
    plusBtn.appendChild(pi);
  }

  return {
    properties: [
      { name: "label", type: "TEXT", default: "Label", bindNodeToCharacters: labelNode },
      { name: "value", type: "TEXT", default: "0", bindNodeToCharacters: valueNode },
      { name: "unit", type: "TEXT", default: "", bindNodeToCharacters: unitNode },
    ],
  };
});

s.rows.forEach((row, idx) => {
  const isLast = idx === s.rows.length - 1;
  const inst = scComp.createInstance();
  card.appendChild(inst);
  inst.layoutSizingHorizontal = "FILL"; inst.layoutSizingVertical = "HUG";
  // Last row: hide bottom border
  if (isLast) {
    try { inst.strokeBottomWeight = 0; } catch (e) {}
  }
  // setComponentProperties is sync-friendly; but await for safety
  inst.setProperties && inst.setProperties; // no-op to avoid lint
});
// Apply props after all instances created
for (let i = 0; i < s.rows.length; i++) {
  const inst = card.children[i];
  if (!inst) continue;
  await setComponentProperties(inst, {
    label: s.rows[i].label,
    value: s.rows[i].value,
    unit: s.rows[i].unit,
  });
}
`);
}

// ─── Avatar Row ────────────────────────────────────────────────────────
function renderAvatarRow(s: AvatarRowSection): string {
  return wrap(`
const s = ${j(s)};
const row = cAL("HORIZONTAL", { name: "Avatars" });
row.fills = [];
row.paddingLeft = 20; row.paddingRight = 20;
row.paddingBottom = 18;
row.itemSpacing = 18; row.counterAxisAlignItems = "MIN";
row.clipsContent = false;
wrapper.appendChild(row);
row.layoutSizingHorizontal = "FILL"; row.layoutSizingVertical = "HUG";

if (s.add) {
  const add = cAL("VERTICAL", { itemSpacing: 6 });
  add.fills = []; add.primaryAxisAlignItems = "CENTER"; add.counterAxisAlignItems = "CENTER";
  row.appendChild(add);
  add.layoutSizingHorizontal = "HUG"; add.layoutSizingVertical = "HUG";
  const ac = cAL("HORIZONTAL");
  ac.fills = [solid(v.bgPrimary)]; ac.strokes = [solid(v.borderPrimary)];
  ac.strokeWeight = 1.5; ac.dashPattern = [4, 4]; ac.cornerRadius = 9999;
  ac.primaryAxisAlignItems = "CENTER"; ac.counterAxisAlignItems = "CENTER";
  add.appendChild(ac);
  ac.resize(52, 52); ac.layoutSizingHorizontal = "FIXED"; ac.layoutSizingVertical = "FIXED";
  if (ic.plus) {
    const pi = ic.plus.createInstance(); pi.resize(22, 22);
    tintIcon(pi, v.textTertiary);
    ac.appendChild(pi);
  }
  add.appendChild(txt(s.add.label, { weight: "Medium", size: 11, colorVar: v.textTertiary, align: "CENTER" }));
}

// Master: avatar circle + initial + optional crown overlay + name + level
const { component: avComp } = await ensureComponent("avatarMaker", async (parent) => {
  parent.layoutMode = "VERTICAL";
  parent.primaryAxisSizingMode = "AUTO";
  parent.counterAxisSizingMode = "AUTO";
  parent.itemSpacing = 6;
  parent.fills = [];
  parent.primaryAxisAlignItems = "CENTER";
  parent.counterAxisAlignItems = "CENTER";
  parent.clipsContent = false;

  const box = figma.createFrame();
  box.name = "Avatar Box"; box.fills = []; box.resize(52, 52); box.clipsContent = false;
  parent.appendChild(box);

  const circle = figma.createEllipse();
  circle.resize(52, 52); circle.x = 0; circle.y = 0;
  circle.fills = [{
    type: "GRADIENT_LINEAR",
    gradientStops: [
      { position: 0, color: { r: HUE.purple.c1.r, g: HUE.purple.c1.g, b: HUE.purple.c1.b, a: 1 } },
      { position: 1, color: { r: HUE.purple.c2.r, g: HUE.purple.c2.g, b: HUE.purple.c2.b, a: 1 } },
    ],
    gradientTransform: [[0.707, 0.707, 0], [-0.707, 0.707, 0.5]],
  }];
  circle.effects = [{
    type: "DROP_SHADOW", color: { r: 0, g: 0, b: 0, a: 0.12 },
    offset: { x: 0, y: 2 }, radius: 6, spread: 0, visible: true, blendMode: "NORMAL",
  }];
  box.appendChild(circle);

  const initialNode = figma.createText();
  try { initialNode.fontName = { family: FONT.family, style: "Bold" }; }
  catch (e) { initialNode.fontName = { family: NS_FALLBACK, style: "Bold" }; }
  initialNode.characters = "?";
  initialNode.fontSize = 22;
  initialNode.fills = [{ type: "SOLID", color: { r: 1, g: 1, b: 1 } }];
  initialNode.textAutoResize = "WIDTH_AND_HEIGHT";
  box.appendChild(initialNode);
  initialNode.x = (52 - initialNode.width) / 2;
  initialNode.y = (52 - initialNode.height) / 2;

  // Crown overlay (3 layers) — toggle as a unit via showCrown BOOLEAN
  const crownGroup = figma.createFrame();
  crownGroup.name = "Crown"; crownGroup.fills = []; crownGroup.resize(16, 16);
  crownGroup.x = 36; crownGroup.y = 36; crownGroup.clipsContent = false;
  box.appendChild(crownGroup);
  const ring = figma.createEllipse();
  ring.resize(20, 20); ring.x = -2; ring.y = -2;
  ring.fills = [{ type: "SOLID", color: { r: 1, g: 1, b: 1 } }];
  crownGroup.appendChild(ring);
  const dot = figma.createEllipse();
  dot.resize(16, 16); dot.x = 0; dot.y = 0;
  dot.fills = [solid(v.bgBrandSection)];
  crownGroup.appendChild(dot);
  if (ic.star) {
    const si = ic.star.createInstance(); si.resize(10, 10);
    si.x = 3; si.y = 3;
    const setFill = (n) => {
      if (n.fills && Array.isArray(n.fills) && n.fills.length > 0) {
        try { n.fills = [{ type: "SOLID", color: { r: 1, g: 1, b: 1 } }]; } catch (e) {}
      }
      if ("children" in n && Array.isArray(n.children)) for (const c of n.children) setFill(c);
    };
    setFill(si);
    crownGroup.appendChild(si);
  }

  const nameNode = txt("Name", { weight: "Medium", size: 10, colorVar: v.textSecondary, align: "CENTER" });
  parent.appendChild(nameNode);
  const levelNode = txt("(0)", { weight: "Regular", size: 9, colorVar: v.textTertiary, align: "CENTER" });
  parent.appendChild(levelNode);

  return {
    properties: [
      { name: "initial", type: "TEXT", default: "?", bindNodeToCharacters: initialNode },
      { name: "name", type: "TEXT", default: "Name", bindNodeToCharacters: nameNode },
      { name: "level", type: "TEXT", default: "(0)", bindNodeToCharacters: levelNode },
      { name: "showCrown", type: "BOOLEAN", default: false, bindNodeToVisible: crownGroup },
    ],
  };
});

for (const m of s.makers) {
  const inst = avComp.createInstance();
  row.appendChild(inst);
  inst.layoutSizingHorizontal = "HUG"; inst.layoutSizingVertical = "HUG";
  await setComponentProperties(inst, {
    initial: initialOf(m.name),
    name: m.name,
    level: "(" + m.level + ")",
    showCrown: !!m.crown,
  });
  // Per-instance overrides: gradient hue + name color/weight
  try {
    const hue = HUE[m.colorHue] || HUE.purple;
    // children: [box, name, level]; box.children: [circle, initial, crown]
    const box = inst.children[0];
    const circle = box && box.children && box.children[0];
    if (circle) {
      circle.fills = [{
        type: "GRADIENT_LINEAR",
        gradientStops: [
          { position: 0, color: { r: hue.c1.r, g: hue.c1.g, b: hue.c1.b, a: 1 } },
          { position: 1, color: { r: hue.c2.r, g: hue.c2.g, b: hue.c2.b, a: 1 } },
        ],
        gradientTransform: [[0.707, 0.707, 0], [-0.707, 0.707, 0.5]],
      }];
    }
    if (m.crown) {
      const nameNode = inst.children[1];
      if (nameNode) {
        nameNode.fills = [solid(v.textPrimary)];
        try { nameNode.fontName = { family: nameNode.fontName.family, style: "Bold" }; } catch (e) {}
      }
    }
  } catch (e) {}
}
`);
}

// ─── Summary Card with Link Rows ──────────────────────────────────────
function renderSummaryCardLinkRows(s: SummaryCardLinkRowsSection): string {
  return wrap(`
const s = ${j(s)};
const w = cAL("VERTICAL", { name: "Summary Card Wrap" });
w.fills = []; w.paddingLeft = 20; w.paddingRight = 20; w.paddingTop = 8; w.paddingBottom = 12;
wrapper.appendChild(w);
w.layoutSizingHorizontal = "FILL"; w.layoutSizingVertical = "HUG";

const card = cAL("VERTICAL", { name: "Summary Card" });
card.fills = [solid(v.bgSecondary)];
card.cornerRadius = 16;
card.paddingLeft = 18; card.paddingRight = 18; card.paddingTop = 18; card.paddingBottom = 18;
card.itemSpacing = 12;
w.appendChild(card);
card.layoutSizingHorizontal = "FILL"; card.layoutSizingVertical = "HUG";

const titleRow = cAL("HORIZONTAL");
titleRow.fills = []; titleRow.itemSpacing = 6;
titleRow.primaryAxisAlignItems = "SPACE_BETWEEN"; titleRow.counterAxisAlignItems = "CENTER";
card.appendChild(titleRow);
titleRow.layoutSizingHorizontal = "FILL"; titleRow.layoutSizingVertical = "HUG";
titleRow.appendChild(txt(s.title, { weight: "Bold", size: 16, colorVar: v.textPrimary }));
if (s.titleIcons && s.titleIcons.length) {
  const icons = cAL("HORIZONTAL", { itemSpacing: 4 });
  icons.fills = []; icons.counterAxisAlignItems = "CENTER";
  titleRow.appendChild(icons);
  icons.layoutSizingHorizontal = "HUG"; icons.layoutSizingVertical = "HUG";
  for (const ck of s.titleIcons) {
    // Map common spec aliases to actual icon component keys
    const aliasMap = { info: "infoCircle", x: "xClose" };
    const realKey = aliasMap[ck] || ck;
    if (ic[realKey]) {
      const inst = ic[realKey].createInstance();
      inst.resize(18, 18);
      tintIcon(inst, v.textBrandPrimary);
      icons.appendChild(inst);
    }
  }
}

// Row component — registered, label/value as TEXT props
const { component: rowComp } = await ensureComponent("summaryCardLinkRow", async (parent) => {
  parent.layoutMode = "HORIZONTAL";
  parent.primaryAxisSizingMode = "FIXED";
  parent.counterAxisSizingMode = "AUTO";
  parent.resize(357, 30);
  parent.primaryAxisAlignItems = "SPACE_BETWEEN";
  parent.counterAxisAlignItems = "CENTER";
  parent.paddingTop = 4; parent.paddingBottom = 4;
  parent.fills = [];
  const labelNode = txt("Label", { weight: "Medium", size: 14, colorVar: v.textSecondary });
  const valueNode = txt("Value", { weight: "Bold", size: 15, colorVar: v.textPrimary });
  parent.appendChild(labelNode);
  parent.appendChild(valueNode);
  return {
    properties: [
      { name: "label", type: "TEXT", default: "Label", bindNodeToCharacters: labelNode },
      { name: "value", type: "TEXT", default: "Value", bindNodeToCharacters: valueNode },
    ],
  };
});

for (const r of s.rows) {
  const inst = rowComp.createInstance();
  card.appendChild(inst);
  inst.layoutSizingHorizontal = "FILL"; inst.layoutSizingVertical = "HUG";
  await setComponentProperties(inst, { label: r.label, value: r.value });
  // valueTone + asLink — per-instance overrides on the value text node
  let valColor = v.textPrimary;
  if (r.valueTone === "positive") valColor = v.textBrandPrimary;
  else if (r.valueTone === "negative") valColor = v.textErrorPrimary;
  try {
    const valueNode = inst.children[1];
    if (valueNode) {
      valueNode.fills = [solid(valColor)];
      if (r.asLink) valueNode.textDecoration = "UNDERLINE";
    }
  } catch (e) {}
}
`);
}

// ─── Month Scroller Calendar ──────────────────────────────────────────
function renderMonthScrollerCalendar(s: MonthScrollerCalendarSection): string {
  return wrap(`
const s = ${j(s)};
const w = cAL("VERTICAL", { name: "Month Calendar Wrap" });
w.fills = []; w.paddingLeft = 20; w.paddingRight = 20; w.paddingTop = 8; w.paddingBottom = 12;
w.itemSpacing = 8;
wrapper.appendChild(w);
w.layoutSizingHorizontal = "FILL"; w.layoutSizingVertical = "HUG";

if (s.title) {
  w.appendChild(txt(s.title, { weight: "Bold", size: 14, colorVar: v.textPrimary, align: "CENTER" }));
}

// Strip with left/right chevron arrows for month navigation
const stripRow = cAL("HORIZONTAL", { itemSpacing: 4 });
stripRow.fills = []; stripRow.counterAxisAlignItems = "CENTER";
w.appendChild(stripRow);
stripRow.layoutSizingHorizontal = "FILL"; stripRow.layoutSizingVertical = "HUG";

const leftBtn = cAL("HORIZONTAL");
leftBtn.fills = [];
leftBtn.paddingLeft = 4; leftBtn.paddingRight = 4; leftBtn.paddingTop = 8; leftBtn.paddingBottom = 8;
leftBtn.primaryAxisAlignItems = "CENTER"; leftBtn.counterAxisAlignItems = "CENTER";
stripRow.appendChild(leftBtn);
leftBtn.layoutSizingHorizontal = "HUG"; leftBtn.layoutSizingVertical = "HUG";
if (ic.chevronLeft) {
  const cli = ic.chevronLeft.createInstance(); cli.resize(20, 20);
  tintIcon(cli, v.textTertiary);
  leftBtn.appendChild(cli);
}

const strip = cAL("HORIZONTAL");
strip.fills = []; strip.itemSpacing = 0;
strip.primaryAxisAlignItems = "SPACE_BETWEEN"; strip.counterAxisAlignItems = "CENTER";
stripRow.appendChild(strip);
strip.layoutSizingHorizontal = "FILL"; strip.layoutSizingVertical = "HUG";

// Month cell master — short + day (with active variant) + badge + activeLabel
const { component: mcComp } = await ensureComponent("monthCell", async (parent) => {
  parent.layoutMode = "VERTICAL";
  parent.primaryAxisSizingMode = "AUTO";
  parent.counterAxisSizingMode = "AUTO";
  parent.itemSpacing = 4;
  parent.fills = [];
  parent.primaryAxisAlignItems = "CENTER";
  parent.counterAxisAlignItems = "CENTER";

  const shortNode = txt("Mon", { weight: "Medium", size: 10, colorVar: v.textTertiary, align: "CENTER" });
  parent.appendChild(shortNode);

  // active dot wrapper (visible when active)
  const dot = cAL("HORIZONTAL");
  dot.fills = [solid(v.bgBrandSection)];
  dot.cornerRadius = 9999;
  dot.primaryAxisAlignItems = "CENTER"; dot.counterAxisAlignItems = "CENTER";
  parent.appendChild(dot);
  dot.resize(28, 28);
  dot.layoutSizingHorizontal = "FIXED"; dot.layoutSizingVertical = "FIXED";
  const dayActiveNode = txt("0", { weight: "Bold", size: 14, colorVar: v.textWhite, align: "CENTER" });
  dot.appendChild(dayActiveNode);

  // inactive day text (visible when not active)
  const dayNode = txt("0", { weight: "Medium", size: 14, colorVar: v.textPrimary, align: "CENTER" });
  parent.appendChild(dayNode);

  // badge (small dot under inactive day)
  const badge = figma.createEllipse();
  badge.resize(4, 4);
  badge.fills = [solid(v.bgBrandSection)];
  parent.appendChild(badge);

  // active label ("이번달")
  const activeLabel = txt("Label", { weight: "Medium", size: 11, colorVar: v.textBrandPrimary, align: "CENTER" });
  parent.appendChild(activeLabel);

  return {
    properties: [
      { name: "short", type: "TEXT", default: "Mon", bindNodeToCharacters: shortNode },
      { name: "day", type: "TEXT", default: "0", bindNodeToCharacters: dayNode },
      { name: "dayActive", type: "TEXT", default: "0", bindNodeToCharacters: dayActiveNode },
      { name: "activeLabel", type: "TEXT", default: "Label", bindNodeToCharacters: activeLabel },
      { name: "isActive", type: "BOOLEAN", default: false, bindNodeToVisible: dot },
      { name: "isInactive", type: "BOOLEAN", default: true, bindNodeToVisible: dayNode },
      { name: "showBadge", type: "BOOLEAN", default: false, bindNodeToVisible: badge },
      { name: "showActiveLabel", type: "BOOLEAN", default: false, bindNodeToVisible: activeLabel },
    ],
  };
});

for (const m of s.months) {
  const inst = mcComp.createInstance();
  strip.appendChild(inst);
  inst.layoutSizingHorizontal = "FILL"; inst.layoutSizingVertical = "HUG";
  await setComponentProperties(inst, {
    short: m.short,
    day: m.day,
    dayActive: m.day,
    activeLabel: m.activeLabel || "",
    isActive: !!m.active,
    isInactive: !m.active,
    showBadge: !m.active && !!m.badge,
    showActiveLabel: !!m.activeLabel,
  });
}

// Right chevron, sibling to strip inside stripRow
const rightBtn = cAL("HORIZONTAL");
rightBtn.fills = [];
rightBtn.paddingLeft = 4; rightBtn.paddingRight = 4; rightBtn.paddingTop = 8; rightBtn.paddingBottom = 8;
rightBtn.primaryAxisAlignItems = "CENTER"; rightBtn.counterAxisAlignItems = "CENTER";
stripRow.appendChild(rightBtn);
rightBtn.layoutSizingHorizontal = "HUG"; rightBtn.layoutSizingVertical = "HUG";
if (ic.chevronRight) {
  const cri = ic.chevronRight.createInstance(); cri.resize(20, 20);
  tintIcon(cri, v.textTertiary);
  rightBtn.appendChild(cri);
}

if (s.filterLabel) {
  const filterRow = cAL("HORIZONTAL");
  filterRow.fills = []; filterRow.primaryAxisAlignItems = "MAX";
  w.appendChild(filterRow);
  filterRow.layoutSizingHorizontal = "FILL"; filterRow.layoutSizingVertical = "HUG";
  filterRow.appendChild(txt(s.filterLabel, { weight: "Medium", size: 13, colorVar: v.textSecondary }));
}
`);
}

// ─── Stats Strip 3-col — registered component (3 fixed cols, 6 TEXT props)
function renderStatsStrip3Col(s: StatsStrip3ColSection): string {
  return wrap(`
const s = ${j(s)};
const { component } = await ensureComponent("statsStrip3Col", async (parent) => {
  parent.layoutMode = "HORIZONTAL";
  parent.primaryAxisSizingMode = "FIXED";
  parent.counterAxisSizingMode = "AUTO";
  parent.resize(393, 60);
  parent.primaryAxisAlignItems = "SPACE_BETWEEN";
  parent.counterAxisAlignItems = "MIN";
  parent.paddingLeft = 20; parent.paddingRight = 20;
  parent.paddingTop = 14; parent.paddingBottom = 14;
  parent.fills = [solid(v.bgSecondary)];
  const labels = [];
  const values = [];
  for (let i = 0; i < 3; i++) {
    const col = cAL("VERTICAL", { itemSpacing: 4 });
    col.fills = []; col.counterAxisAlignItems = "MIN";
    parent.appendChild(col);
    col.layoutSizingHorizontal = "FILL"; col.layoutSizingVertical = "HUG";
    const labelNode = txt("Label " + (i + 1), { weight: "Medium", size: 12, colorVar: v.textTertiary });
    const valueNode = txt("Value " + (i + 1), { weight: "Bold", size: 15, colorVar: v.textPrimary });
    col.appendChild(labelNode);
    col.appendChild(valueNode);
    labels.push(labelNode); values.push(valueNode);
  }
  const props = [];
  for (let i = 0; i < 3; i++) {
    props.push({ name: "label" + (i + 1), type: "TEXT", default: "Label " + (i + 1), bindNodeToCharacters: labels[i] });
    props.push({ name: "value" + (i + 1), type: "TEXT", default: "Value " + (i + 1), bindNodeToCharacters: values[i] });
  }
  return { properties: props };
});
const inst = component.createInstance();
wrapper.appendChild(inst);
inst.layoutSizingHorizontal = "FILL"; inst.layoutSizingVertical = "HUG";
const propMap = {};
for (let i = 0; i < Math.min(3, s.cols.length); i++) {
  propMap["label" + (i + 1)] = s.cols[i].label || "";
  propMap["value" + (i + 1)] = s.cols[i].value || "";
}
await setComponentProperties(inst, propMap);
for (let i = 0; i < Math.min(3, s.cols.length); i++) {
  const tone = s.cols[i].valueTone;
  if (!tone || tone === "neutral") continue;
  const colorVar = tone === "positive" ? v.textBrandPrimary : (tone === "negative" ? v.textErrorPrimary : v.textPrimary);
  const cols = inst.children;
  if (cols && cols[i] && cols[i].children && cols[i].children[1]) {
    try { cols[i].children[1].fills = [solid(colorVar)]; } catch (e) {}
  }
}
`);
}

// ─── Transaction Timeline ─────────────────────────────────────────────
function renderTransactionTimeline(s: TransactionTimelineSection): string {
  return wrap(`
const s = ${j(s)};
const list = cAL("VERTICAL", { name: "Transaction Timeline" });
list.fills = []; list.itemSpacing = 0;
list.paddingLeft = 20; list.paddingRight = 20;
wrapper.appendChild(list);
list.layoutSizingHorizontal = "FILL"; list.layoutSizingVertical = "HUG";

// Row component — single master; rowState drives BOOLEAN visibility + per-instance color overrides
const { component: txnRowComp } = await ensureComponent("transactionTimelineRow", async (parent) => {
  parent.layoutMode = "HORIZONTAL";
  parent.primaryAxisSizingMode = "FIXED";
  parent.counterAxisSizingMode = "AUTO";
  parent.resize(353, 70);
  parent.paddingTop = 10; parent.paddingBottom = 10;
  parent.itemSpacing = 12;
  parent.counterAxisAlignItems = "CENTER";
  parent.fills = [];
  parent.strokes = [solid(v.borderSecondary)];
  parent.strokeBottomWeight = 1; parent.strokeTopWeight = 0;
  parent.strokeLeftWeight = 0; parent.strokeRightWeight = 0;
  parent.strokeAlign = "INSIDE";

  // [0] dayBadge
  const dayBadge = cAL("VERTICAL");
  dayBadge.fills = [solid(v.bgTertiary)];
  dayBadge.cornerRadius = 8;
  dayBadge.paddingLeft = 8; dayBadge.paddingRight = 8;
  dayBadge.paddingTop = 8; dayBadge.paddingBottom = 8;
  dayBadge.itemSpacing = 2;
  dayBadge.primaryAxisAlignItems = "CENTER"; dayBadge.counterAxisAlignItems = "CENTER";
  parent.appendChild(dayBadge);
  dayBadge.resize(48, 48);
  dayBadge.layoutSizingHorizontal = "FIXED"; dayBadge.layoutSizingVertical = "FIXED";
  const dayLabelNode = txt("Day", { weight: "Bold", size: 13, colorVar: v.textTertiary, align: "CENTER" });
  const dayStateNode = txt("D-0", { weight: "Medium", size: 11, colorVar: v.textTertiary, align: "CENTER" });
  dayBadge.appendChild(dayLabelNode);
  dayBadge.appendChild(dayStateNode);

  // [1] body
  const body = cAL("VERTICAL", { itemSpacing: 6 });
  body.fills = [];
  parent.appendChild(body);
  body.layoutSizingHorizontal = "FILL"; body.layoutSizingVertical = "HUG";
  const titleNode = txt("Title", { weight: "Bold", size: 14, colorVar: v.textPrimary });
  const amountNode = txt("0원", { weight: "Bold", size: 15, colorVar: v.textPrimary });
  body.appendChild(titleNode);
  body.appendChild(amountNode);
  const trackWrap = cAL("HORIZONTAL");
  trackWrap.fills = [solid(v.bgTertiary)];
  trackWrap.cornerRadius = 9999;
  trackWrap.itemSpacing = 0;
  body.appendChild(trackWrap);
  trackWrap.layoutSizingHorizontal = "FILL";
  trackWrap.resize(100, 4);
  trackWrap.layoutSizingVertical = "FIXED";
  const fillBar = figma.createRectangle();
  fillBar.fills = [solid(v.bgBrandSection)];
  fillBar.cornerRadius = 9999;
  trackWrap.appendChild(fillBar);
  fillBar.resize(2, 4);

  // [2] outline pill (right action — outline style)
  const pill = cAL("HORIZONTAL");
  pill.fills = [solid(v.bgPrimary)]; pill.strokes = [solid(v.borderPrimary)];
  pill.strokeWeight = 1; pill.cornerRadius = 9999;
  pill.paddingLeft = 12; pill.paddingRight = 12; pill.paddingTop = 6; pill.paddingBottom = 6;
  pill.primaryAxisAlignItems = "CENTER"; pill.counterAxisAlignItems = "CENTER";
  parent.appendChild(pill);
  pill.layoutSizingHorizontal = "HUG"; pill.layoutSizingVertical = "HUG";
  const pillLabel = txt("Action", { weight: "Bold", size: 11, colorVar: v.textPrimary });
  pill.appendChild(pillLabel);

  // [3] right action text (brand/tertiary)
  const actionText = txt("Action", { weight: "Medium", size: 12, colorVar: v.textBrandPrimary });
  parent.appendChild(actionText);

  return {
    properties: [
      { name: "dayLabel", type: "TEXT", default: "Day", bindNodeToCharacters: dayLabelNode },
      { name: "dayState", type: "TEXT", default: "D-0", bindNodeToCharacters: dayStateNode },
      { name: "title", type: "TEXT", default: "Title", bindNodeToCharacters: titleNode },
      { name: "amount", type: "TEXT", default: "0원", bindNodeToCharacters: amountNode },
      { name: "showProgress", type: "BOOLEAN", default: true, bindNodeToVisible: trackWrap },
      { name: "showOutlinePill", type: "BOOLEAN", default: false, bindNodeToVisible: pill },
      { name: "showActionText", type: "BOOLEAN", default: true, bindNodeToVisible: actionText },
    ],
  };
});

for (const it of s.items) {
  const inst = txnRowComp.createInstance();
  list.appendChild(inst);
  inst.layoutSizingHorizontal = "FILL"; inst.layoutSizingVertical = "HUG";

  const isOutlinePill = it.rowState === "overdue" || it.rowState === "scheduled";
  const isCompleted = it.rowState === "completed";

  // Progress %
  let pct = (typeof it.progressPercent === "number") ? it.progressPercent : null;
  if (pct === null) {
    const m = /(\\d+)\\s*\\/\\s*(\\d+)\\s*회차/.exec(it.title || "");
    if (m) pct = Math.max(0, Math.min(100, (Number(m[1]) / Number(m[2])) * 100));
  }
  if (pct === null) pct = 0;

  await setComponentProperties(inst, {
    dayLabel: it.dayLabel,
    dayState: it.dayState,
    title: it.title,
    amount: it.amount,
    showProgress: pct > 0,
    showOutlinePill: !!it.rightAction && isOutlinePill,
    showActionText: !!it.rightAction && !isOutlinePill,
  });

  // Per-instance color + structural overrides
  try {
    const kids = inst.children;
    const dayBadge = kids[0];
    const body = kids[1];
    const pill = kids[2];
    const actionText = kids[3];

    const badgeBgVar = it.rowState === "overdue" ? v.bgBrandSection
      : it.rowState === "today" ? v.bgBrandSection
      : it.rowState === "soon" ? v.bgBrandPrimary
      : v.bgTertiary;
    const badgeTextVar = it.rowState === "overdue" ? v.textWhite
      : it.rowState === "today" ? v.textWhite
      : it.rowState === "soon" ? v.textBrandPrimary
      : v.textTertiary;
    if (dayBadge) dayBadge.fills = [solid(badgeBgVar)];
    if (dayBadge && dayBadge.children) {
      try { dayBadge.children[0].fills = [solid(badgeTextVar)]; } catch (e) {}
      try { dayBadge.children[1].fills = [solid(badgeTextVar)]; } catch (e) {}
    }

    // Title color (red for overdue)
    if (body && body.children && body.children[0]) {
      const titleColor = it.rowState === "overdue" ? v.textErrorPrimary : v.textPrimary;
      try { body.children[0].fills = [solid(titleColor)]; } catch (e) {}
    }

    // Progress fill width + color
    if (body && body.children && body.children[2] && pct > 0) {
      const tw = body.children[2];
      const fb = tw.children && tw.children[0];
      const fillVar = it.rowState === "completed" ? v.bgBrandSection
        : it.rowState === "overdue" ? v.textErrorPrimary
        : v.bgBrandSection;
      if (fb) {
        try { fb.fills = [solid(fillVar)]; } catch (e) {}
        try { fb.resize(Math.max(2, Math.round((pct / 100) * 280)), 4); } catch (e) {}
      }
    }

    // Right action text content (set on whichever is visible)
    if (it.rightAction) {
      if (isOutlinePill && pill && pill.children && pill.children[0]) {
        try { pill.children[0].characters = it.rightAction; } catch (e) {}
      } else if (actionText) {
        try { actionText.characters = it.rightAction; } catch (e) {}
        const colVar = isCompleted ? v.textTertiary : v.textBrandPrimary;
        try { actionText.fills = [solid(colVar)]; } catch (e) {}
      }
    }
  } catch (e) {}
}
`);
}

// ─── Stage Card List (timeline layout) ────────────────────────────────
function renderStageCardList(s: StageCardListSection): string {
  return wrap(`
const s = ${j(s)};
for (const item of s.items) {
  const sw = cAL("VERTICAL");
  sw.fills = []; sw.paddingLeft = 20; sw.paddingRight = 20; sw.paddingBottom = 10;
  wrapper.appendChild(sw);
  sw.layoutSizingHorizontal = "FILL"; sw.layoutSizingVertical = "HUG";

  const card = cAL("VERTICAL");
  card.fills = [solid(v.bgPrimary)];
  card.strokes = [solid(v.borderSecondary)]; card.strokeWeight = 1;
  card.cornerRadius = 14;
  card.paddingLeft = 16; card.paddingRight = 16; card.paddingTop = 16; card.paddingBottom = 14;
  card.itemSpacing = 0;
  card.effects = [{
    type: "DROP_SHADOW", color: { r: 0.039, g: 0.051, b: 0.094, a: 0.04 },
    offset: { x: 0, y: 1 }, radius: 2, spread: 0, visible: true, blendMode: "NORMAL",
  }];
  sw.appendChild(card);
  card.layoutSizingHorizontal = "FILL"; card.layoutSizingVertical = "HUG";

  const title = txt("→ 월 " + fmtKRW(item.monthly) + " 씩 " + item.months + "개월 모으기", { weight: "Bold", size: 13, colorVar: v.textSecondary, align: "CENTER" });
  card.appendChild(title); title.layoutSizingHorizontal = "FILL";
  sp(card, 10);

  const tl = cAL("HORIZONTAL", { itemSpacing: 2 });
  tl.fills = [];
  card.appendChild(tl);
  tl.layoutSizingHorizontal = "FILL"; tl.layoutSizingVertical = "HUG";
  for (let i = 1; i <= item.months; i++) {
    const isActive = i === item.payoutAt;
    const cell = cAL("VERTICAL");
    cell.fills = [solid(isActive ? v.bgBrandSection : v.bgBrandPrimary)];
    cell.cornerRadius = 4;
    cell.primaryAxisAlignItems = "CENTER"; cell.counterAxisAlignItems = "CENTER";
    tl.appendChild(cell);
    cell.resize(20, 22);
    cell.layoutSizingHorizontal = "FILL"; cell.layoutSizingVertical = "FIXED";
    cell.appendChild(txt(String(i), { weight: "Bold", size: 9, colorVar: isActive ? v.textWhite : v.textBrandTertiary, align: "CENTER" }));
  }
  sp(card, 6);

  const sub = figma.createText();
  try { sub.fontName = { family: FONT.family, style: "Bold" }; }
  catch (e) { sub.fontName = { family: NS_FALLBACK, style: "Bold" }; }
  sub.characters = item.payoutAt + "차 납입 후 목돈 수령";
  sub.fontSize = 12;
  sub.fills = [solid(v.textSecondary)];
  try { sub.setRangeFills(0, String(item.payoutAt).length + 1, [solid(v.textBrandPrimary)]); } catch (e) {}
  sub.textAlignHorizontal = "CENTER";
  card.appendChild(sub); sub.layoutSizingHorizontal = "FILL";
  sp(card, 14);

  const dv = figma.createRectangle();
  dv.resize(100, 1); dv.fills = [solid(v.borderSecondary)];
  card.appendChild(dv); dv.layoutSizingHorizontal = "FILL";
  sp(card, 12);

  const r1 = cAL("HORIZONTAL");
  r1.fills = []; r1.primaryAxisAlignItems = "SPACE_BETWEEN"; r1.counterAxisAlignItems = "CENTER";
  r1.paddingTop = 3; r1.paddingBottom = 3;
  card.appendChild(r1);
  r1.layoutSizingHorizontal = "FILL"; r1.layoutSizingVertical = "HUG";
  const lbl = cAL("HORIZONTAL", { itemSpacing: 4 });
  lbl.fills = []; lbl.counterAxisAlignItems = "BASELINE";
  r1.appendChild(lbl);
  lbl.layoutSizingHorizontal = "HUG"; lbl.layoutSizingVertical = "HUG";
  lbl.appendChild(txt("목돈", { weight: "Medium", size: 13, colorVar: v.textTertiary }));
  lbl.appendChild(txt("(" + item.payoutAt + "회차 납입 후 수령)", { weight: "Regular", size: 11, colorVar: v.textTertiary }));
  r1.appendChild(txt(fmtKRW(item.payout), { weight: "Bold", size: 14, colorVar: v.textPrimary }));

  const r2 = cAL("HORIZONTAL");
  r2.fills = []; r2.primaryAxisAlignItems = "SPACE_BETWEEN"; r2.counterAxisAlignItems = "CENTER";
  r2.paddingTop = 3; r2.paddingBottom = 3;
  card.appendChild(r2);
  r2.layoutSizingHorizontal = "FILL"; r2.layoutSizingVertical = "HUG";
  r2.appendChild(txt("총 이자", { weight: "Medium", size: 13, colorVar: v.textTertiary }));
  r2.appendChild(txt(fmtKRW(item.interest), { weight: "Bold", size: 14, colorVar: v.textErrorPrimary }));
  sp(card, 10);

  const bene = cAL("HORIZONTAL");
  bene.fills = [solid(v.bgSecondary)];
  bene.cornerRadius = 8;
  bene.paddingLeft = 10; bene.paddingRight = 10; bene.paddingTop = 8; bene.paddingBottom = 8;
  bene.primaryAxisAlignItems = "SPACE_BETWEEN"; bene.counterAxisAlignItems = "CENTER";
  card.appendChild(bene);
  bene.layoutSizingHorizontal = "FILL"; bene.layoutSizingVertical = "HUG";
  bene.appendChild(txt("추가 혜택 (스테이지 시작자 지급)", { weight: "Medium", size: 11, colorVar: v.textTertiary }));

  const bg = cAL("HORIZONTAL", { itemSpacing: 6 });
  bg.fills = []; bg.counterAxisAlignItems = "CENTER";
  bene.appendChild(bg);
  bg.layoutSizingHorizontal = "HUG"; bg.layoutSizingVertical = "HUG";
  const b1 = cAL("HORIZONTAL", { itemSpacing: 3 });
  b1.fills = [solid(v.bgBrandPrimary)]; b1.cornerRadius = 9999;
  b1.paddingLeft = 8; b1.paddingRight = 8; b1.paddingTop = 3; b1.paddingBottom = 3;
  b1.counterAxisAlignItems = "CENTER";
  bg.appendChild(b1);
  b1.layoutSizingHorizontal = "HUG"; b1.layoutSizingVertical = "HUG";
  if (ic.diamond) {
    const di = ic.diamond.createInstance(); di.resize(10, 10);
    tintIcon(di, v.textBrandTertiary);
    b1.appendChild(di);
  }
  b1.appendChild(txt(item.points + "P", { weight: "Bold", size: 11, colorVar: v.textBrandPrimary }));
  const b2 = cAL("HORIZONTAL", { itemSpacing: 3 });
  b2.fills = [solid(v.bgPrimary)]; b2.strokes = [solid(v.borderPrimary)]; b2.strokeWeight = 1;
  b2.cornerRadius = 9999;
  b2.paddingLeft = 8; b2.paddingRight = 8; b2.paddingTop = 3; b2.paddingBottom = 3;
  b2.counterAxisAlignItems = "CENTER";
  bg.appendChild(b2);
  b2.layoutSizingHorizontal = "HUG"; b2.layoutSizingVertical = "HUG";
  b2.appendChild(txt(item.fee + "원", { weight: "Bold", size: 11, colorVar: v.textTertiary }));
}
`);
}

// ─── Footer Legal ──────────────────────────────────────────────────────
function renderFooterLegal(s: FooterLegalSection): string {
  return wrap(`
const s = ${j(s)};
const f = cAL("VERTICAL", { name: "Footer Legal", itemSpacing: 6 });
f.fills = [];
f.paddingLeft = 20; f.paddingRight = 20; f.paddingTop = 18; f.paddingBottom = 16;
f.strokes = [solid(v.borderSecondary)];
f.strokeWeight = 1; f.strokeAlign = "INSIDE";
f.strokeTopWeight = 1; f.strokeBottomWeight = 0;
f.strokeLeftWeight = 0; f.strokeRightWeight = 0;
wrapper.appendChild(f);
f.layoutSizingHorizontal = "FILL"; f.layoutSizingVertical = "HUG";

const grid = cAL("VERTICAL", { itemSpacing: 6 });
grid.fills = [];
f.appendChild(grid);
grid.layoutSizingHorizontal = "FILL"; grid.layoutSizingVertical = "HUG";
const links = s.legalLinks.filter(Boolean);
for (let i = 0; i < links.length; i += 3) {
  const row = cAL("HORIZONTAL");
  row.fills = [];
  grid.appendChild(row);
  row.layoutSizingHorizontal = "FILL"; row.layoutSizingVertical = "HUG";
  for (let j2 = 0; j2 < 3; j2++) {
    const text = links[i + j2];
    if (!text) continue;
    const cell = cAL("HORIZONTAL");
    cell.fills = [];
    row.appendChild(cell);
    cell.layoutSizingHorizontal = "FILL"; cell.layoutSizingVertical = "HUG";
    cell.appendChild(txt(text, { weight: "Medium", size: 11, colorVar: v.textTertiary }));
  }
}
sp(f, 8);

const r1 = cAL("HORIZONTAL", { itemSpacing: 12 });
r1.fills = [];
f.appendChild(r1);
r1.layoutSizingHorizontal = "FILL"; r1.layoutSizingVertical = "HUG";
r1.appendChild(txt(s.companyName, { weight: "Regular", size: 10, colorVar: v.textTertiary }));
r1.appendChild(txt("사업자등록번호: " + s.bizNumber, { weight: "Regular", size: 10, colorVar: v.textTertiary }));

const r2 = cAL("HORIZONTAL", { itemSpacing: 12 });
r2.fills = [];
f.appendChild(r2);
r2.layoutSizingHorizontal = "FILL"; r2.layoutSizingVertical = "HUG";
r2.appendChild(txt("대표: " + s.ceo, { weight: "Regular", size: 10, colorVar: v.textTertiary }));
r2.appendChild(txt("통신판매업신고: " + s.teleSalesNumber, { weight: "Regular", size: 10, colorVar: v.textTertiary }));

const disc = txt(s.disclaimer, { weight: "Regular", size: 10, colorVar: v.textTertiary });
disc.lineHeight = { unit: "PERCENT", value: 160 };
f.appendChild(disc); disc.layoutSizingHorizontal = "FILL";
f.appendChild(txt(s.copyright, { weight: "Regular", size: 10, colorVar: v.textTertiary }));
`);
}

// ─── Spacer ───────────────────────────────────────────────────────────
function renderSpacer(s: SpacerSection): string {
  return wrap(`
const s = ${j(s)};
const sf = figma.createFrame(); sf.fills = []; sf.resize(10, s.height); sf.name = "Spacer";
wrapper.appendChild(sf);
sf.layoutSizingHorizontal = "FILL"; sf.resize(sf.width, s.height);
`);
}

// ─── Tab Bar (overlay — ABSOLUTE) ─────────────────────────────────────
function renderTabBar(s: TabBarSection): string {
  return wrap(`
const s = ${j(s)};
const tabBar = cAL("HORIZONTAL", { name: "Tab Bar" });
tabBar.fills = [solid(v.bgPrimary)];
tabBar.strokes = [solid(v.borderSecondary)];
tabBar.strokeWeight = 1; tabBar.strokeAlign = "INSIDE";
tabBar.strokeTopWeight = 1; tabBar.strokeBottomWeight = 0;
tabBar.strokeLeftWeight = 0; tabBar.strokeRightWeight = 0;
tabBar.paddingLeft = 8; tabBar.paddingRight = 8;
tabBar.paddingTop = 8; tabBar.paddingBottom = 24;
tabBar.itemSpacing = 0;
tabBar.primaryAxisAlignItems = "SPACE_BETWEEN";
tabBar.counterAxisAlignItems = "MIN";
wrapper.appendChild(tabBar);
tabBar.resize(wrapper.width, 80);
tabBar.layoutPositioning = "ABSOLUTE";
tabBar.x = 0; tabBar.y = wrapper.height - 80;

// One master per iconKey (icon component varies per tab, can't be swapped via prop)
for (const t of s.tabs) {
  const isActive = t.id === s.activeId;
  const masterName = "tabBarItem-" + t.iconKey;
  const iconKey = t.iconKey;
  const { component: itemComp } = await ensureComponent(masterName, async (parent) => {
    parent.layoutMode = "VERTICAL";
    parent.primaryAxisSizingMode = "AUTO";
    parent.counterAxisSizingMode = "AUTO";
    parent.itemSpacing = 4;
    parent.fills = [];
    parent.primaryAxisAlignItems = "CENTER";
    parent.counterAxisAlignItems = "CENTER";
    if (ic[iconKey]) {
      const ico = ic[iconKey].createInstance();
      ico.resize(22, 22);
      tintIcon(ico, v.textTertiary);
      parent.appendChild(ico);
    }
    const labelNode = txt("Tab", { weight: "Medium", size: 10, colorVar: v.textTertiary, align: "CENTER" });
    parent.appendChild(labelNode);
    return {
      properties: [
        { name: "label", type: "TEXT", default: "Tab", bindNodeToCharacters: labelNode },
      ],
    };
  });
  const inst = itemComp.createInstance();
  tabBar.appendChild(inst);
  inst.layoutSizingHorizontal = "FILL"; inst.layoutSizingVertical = "HUG";
  await setComponentProperties(inst, { label: t.label });
  // active — per-instance overrides on icon tint + label color/weight
  if (isActive) {
    try {
      const kids = inst.children;
      // icon (if present) is first; label is last
      const labelNode = kids[kids.length - 1];
      if (labelNode) {
        labelNode.fills = [solid(v.textBrandPrimary)];
        try { labelNode.fontName = { family: labelNode.fontName.family, style: "Bold" }; } catch (e) {}
      }
      if (kids.length > 1) {
        const iconInst = kids[0];
        if (iconInst) tintIcon(iconInst, v.textBrandPrimary);
      }
    } catch (e) {}
  }
}
`);
}

// ─── FAB (overlay — ABSOLUTE) ─────────────────────────────────────────
function renderFab(s: FabSection): string {
  return wrap(`
const s = ${j(s)};
// Use DS Buttons — Size=lg, Icon only=True, Hierarchy=Primary
const btnSet = await ensureDsSet(DS_KEYS.buttons);
const fab = btnSet.defaultVariant.createInstance();
fab.name = "FAB";
try {
  const defs = fab.componentProperties || {};
  const find = (n) => Object.keys(defs).find(k => k === n || k.startsWith(n + "#"));
  const props = {};
  const sk = find("Size"); if (sk) props[sk] = "lg";
  const hk = find("Hierarchy"); if (hk) props[hk] = "Primary";
  const ik = find("Icon only"); if (ik) props[ik] = "True";
  if (Object.keys(props).length > 0) fab.setProperties(props);
} catch (e) {}
// Swap inner icon to spec.iconKey
try {
  const iconNode = fab.findOne(n => n.type === "INSTANCE");
  if (iconNode && ic[s.iconKey]) {
    iconNode.swapComponent(ic[s.iconKey]);
  }
} catch (e) {}
// Drop shadow + ABSOLUTE positioning
fab.effects = [{
  type: "DROP_SHADOW", color: { r: 0.412, g: 0.220, b: 0.937, a: 0.35 },
  offset: { x: 0, y: 6 }, radius: 16, spread: 0, visible: true, blendMode: "NORMAL",
}];
wrapper.appendChild(fab);
fab.layoutPositioning = "ABSOLUTE";
fab.x = wrapper.width - fab.width - 18;
fab.y = wrapper.height - 80 - fab.height - 12;
`);
}

// ─── Dispatch ──────────────────────────────────────────────────────────
export function renderSection(s: SectionSpec): string {
  switch (s.type) {
    case 'appHeader': return renderAppHeader(s);
    case 'modalHeader': return renderModalHeader(s);
    case 'backHeader': return renderBackHeader(s);
    case 'filterChipRow': return renderFilterChipRow(s);
    case 'segmentedTab': return renderSegmentedTab(s);
    case 'underlineTab': return renderUnderlineTab(s);
    case 'sectionHeader': return renderSectionHeader(s);
    case 'stepperCard': return renderStepperCard(s);
    case 'avatarRow': return renderAvatarRow(s);
    case 'summaryCardLinkRows': return renderSummaryCardLinkRows(s);
    case 'monthScrollerCalendar': return renderMonthScrollerCalendar(s);
    case 'statsStrip3Col': return renderStatsStrip3Col(s);
    case 'transactionTimeline': return renderTransactionTimeline(s);
    case 'stageCardList': return renderStageCardList(s);
    case 'footerLegal': return renderFooterLegal(s);
    case 'spacer': return renderSpacer(s);
    default:
      return `// Unknown section type: ${(s as { type: string }).type}\n`;
  }
}

export function renderOverlay(s: OverlaySpec): string {
  switch (s.type) {
    case 'tabBar': return renderTabBar(s);
    case 'fab': return renderFab(s);
    default:
      return `// Unknown overlay type: ${(s as { type: string }).type}\n`;
  }
}
