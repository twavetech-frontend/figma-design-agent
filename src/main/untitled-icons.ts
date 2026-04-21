/**
 * Untitled UI Icons — SVG fetching from Design System Docs (GitHub Pages).
 *
 * Fetches icons-data.json index once, then retrieves individual SVG files
 * from the published docs site. Much faster than parsing npm package JS files.
 *
 * Source: https://twavetech-frontend.github.io/design-system-docs/icons/
 */

import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs';
import { join } from 'path';
import https from 'https';

const BASE_URL = 'https://twavetech-frontend.github.io/design-system-docs';
const ICONS_DATA_URL = `${BASE_URL}/icons-data.json`;

let projectRoot: string = join(__dirname, '..', '..');
let iconNames: Set<string> | null = null;
let iconCategories: Map<string, string> | null = null; // name → category

// In-memory SVG cache: name → svg string
const svgCache = new Map<string, string>();

export function setIconProjectRoot(root: string) {
  projectRoot = root;
}

function getCacheDir(): string {
  const dir = join(projectRoot, 'ds', '.icon-cache');
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
  return dir;
}

/** Fetch a URL and return the response body as string */
function fetchUrl(url: string): Promise<string> {
  return new Promise((resolve, reject) => {
    https.get(url, (res) => {
      if (res.statusCode === 301 || res.statusCode === 302) {
        const loc = res.headers.location;
        if (loc) return fetchUrl(loc).then(resolve, reject);
      }
      if (res.statusCode !== 200) {
        res.resume();
        return reject(new Error(`HTTP ${res.statusCode} for ${url}`));
      }
      let data = '';
      res.on('data', (chunk: string) => { data += chunk; });
      res.on('end', () => resolve(data));
    }).on('error', reject);
  });
}

/** Load icons-data.json index (fetches once, caches to disk) */
async function loadIndex(): Promise<void> {
  if (iconNames) return;

  const cacheFile = join(getCacheDir(), 'icons-data.json');

  let data: Record<string, Array<{ name: string; file: string }>>;

  // Try disk cache first (less than 24h old)
  if (existsSync(cacheFile)) {
    try {
      const stat = require('fs').statSync(cacheFile);
      const ageMs = Date.now() - stat.mtimeMs;
      if (ageMs < 24 * 60 * 60 * 1000) {
        data = JSON.parse(readFileSync(cacheFile, 'utf8'));
        buildFromData(data);
        return;
      }
    } catch { /* fall through to fetch */ }
  }

  // Fetch from GitHub Pages
  try {
    const raw = await fetchUrl(ICONS_DATA_URL);
    data = JSON.parse(raw);
    writeFileSync(cacheFile, raw, 'utf8');
    buildFromData(data);
    console.log(`[untitled-icons] Loaded ${iconNames!.size} icons from GitHub Pages`);
  } catch (err) {
    console.warn('[untitled-icons] Failed to fetch icons-data.json:', (err as Error).message);
    // Fallback: try disk cache regardless of age
    if (existsSync(cacheFile)) {
      data = JSON.parse(readFileSync(cacheFile, 'utf8'));
      buildFromData(data);
    } else {
      iconNames = new Set();
      iconCategories = new Map();
    }
  }
}

function buildFromData(data: Record<string, Array<{ name: string; file: string }>>) {
  iconNames = new Set();
  iconCategories = new Map();
  for (const [category, icons] of Object.entries(data)) {
    for (const icon of icons) {
      iconNames.add(icon.name);
      iconCategories.set(icon.name, category);
    }
  }
}

/** Synchronous index load from disk cache only (for startup) */
function loadIndexSync(): void {
  if (iconNames) return;
  const cacheFile = join(getCacheDir(), 'icons-data.json');
  if (existsSync(cacheFile)) {
    try {
      const data = JSON.parse(readFileSync(cacheFile, 'utf8'));
      buildFromData(data);
      return;
    } catch { /* ignore */ }
  }
  iconNames = new Set();
  iconCategories = new Map();
}

/** Semantic alias map: common descriptive names → actual icon names in icons-data.json */
const ICON_ALIASES: Record<string, string> = {
  // Navigation & Actions
  'chat': 'message-chat-circle',
  'chat-icon': 'message-chat-circle',
  'message': 'message-chat-circle',
  'bell': 'bell-01',
  'bell-icon': 'bell-01',
  'notification': 'bell-01',
  'bookmark': 'bookmark',
  'bookmark-icon': 'bookmark',
  'counter': 'hash-02',
  'counter-icon': 'hash-02',
  'chevron': 'chevron-right',
  'chevron-right': 'chevron-right',
  'chevron-left': 'chevron-left',
  'arrow-right': 'arrow-right',
  'arrow-left': 'arrow-left',
  'search': 'search-lg',
  'close': 'x-close',
  'menu': 'menu-01',
  'settings': 'settings-01',
  'filter': 'filter-lines',
  'share': 'share-07',
  'more': 'dots-horizontal',
  'edit': 'edit-03',
  'delete': 'trash-01',
  'add': 'plus',
  'plus': 'plus',
  'minus': 'minus',
  'check': 'check',
  'info': 'info-circle',
  'warning': 'alert-triangle',
  'error': 'alert-circle',
  'help': 'help-circle',

  // Tab Bar common
  'home': 'home-03',
  'home-icon': 'home-03',
  'community': 'users-01',
  'community-icon': 'users-01',
  'stage': 'layers-three-01',
  'stage-icon': 'layers-three-01',
  'lounge': 'compass-03',
  'lounge-icon': 'compass-03',
  'my': 'user-01',
  'my-icon': 'user-01',
  'mypage': 'user-01',
  'profile': 'user-01',
  'wallet': 'wallet-02',
  'wallet-icon': 'wallet-02',

  // Finance & Commerce
  'gift': 'gift-01',
  'gift-icon': 'gift-01',
  'calc': 'calculator',
  'calculator': 'calculator',
  'calculator-icon': 'calculator',
  'coin': 'coins-01',
  'money': 'currency-dollar-circle',
  'card': 'credit-card-01',
  'bank': 'bank',
  'receipt': 'receipt',

  // Social & Communication
  'heart': 'heart',
  'like': 'heart',
  'star': 'star-01',
  'favorite': 'star-01',
  'send': 'send-01',
  'attach': 'paperclip',
  'link': 'link-01',
  'copy': 'copy-01',

  // Media & Content
  'image': 'image-01',
  'camera': 'camera-01',
  'video': 'video-recorder',
  'play': 'play',
  'pause': 'pause-circle',
  'download': 'download-01',
  'upload': 'upload-01',

  // Status & Misc
  'lock': 'lock-01',
  'unlock': 'lock-unlocked-01',
  'eye': 'eye',
  'eye-off': 'eye-off',
  'refresh': 'refresh-cw-01',
  'calendar': 'calendar',
  'clock': 'clock',
  'location': 'marker-pin-01',
  'map': 'map-01',
  'phone': 'phone',
  'mail': 'mail-01',
  'globe': 'globe-01',
  'flag': 'flag-01',
  'tag': 'tag-01',
  'folder': 'folder',
  'file': 'file-01',
  'list': 'list',
  'grid': 'grid-01',
  'rocket': 'rocket-02',
  'target': 'target-04',
  'trophy': 'trophy-01',
  'zap': 'zap',
  'shield': 'shield-01',

  // Daily tasks / gamification
  'attendance': 'calendar-check-01',
  'attendance-icon': 'calendar-check-01',
  'checkin': 'calendar-check-01',
  'invite': 'user-plus-01',
  'invite-icon': 'user-plus-01',
  'friend': 'user-plus-01',
  'friend-invite': 'user-plus-01',
  'charge': 'zap',
  'charge-icon': 'zap',
  'point': 'coins-01',
  'point-icon': 'coins-01',
  'random': 'dice-3',
  'random-icon': 'dice-3',
  'randombox': 'dice-3',
  'box': 'package',
  'mystery': 'dice-3',
};

/**
 * Resolve an icon name to its canonical name in the index.
 * Accepts: "check-circle", "home-03", "arrow-right", etc.
 * Also supports semantic aliases: "Chat Icon" → "message-chat-circle", etc.
 */
export function resolveIconFile(name: string): string | null {
  loadIndexSync();
  if (!iconNames || iconNames.size === 0) return null;

  const kebab = name.toLowerCase().replace(/[_ ]/g, '-');

  // 0. Alias lookup (semantic names → actual icon names)
  const aliased = ICON_ALIASES[kebab];
  if (aliased && iconNames.has(aliased)) return aliased;
  // Also try without trailing numbers: "bookmark-1" → "bookmark"
  const withoutTrailingNum = kebab.replace(/-\d+$/, '');
  if (withoutTrailingNum !== kebab) {
    const aliased2 = ICON_ALIASES[withoutTrailingNum];
    if (aliased2 && iconNames.has(aliased2)) return aliased2;
  }

  // 1. Exact match
  if (iconNames.has(kebab)) return kebab;

  // 2. Try common suffixes
  for (const suffix of ['-01', '-02', '-03', '-04']) {
    if (iconNames.has(kebab + suffix)) return kebab + suffix;
  }

  // 3. Prefix/contains match
  for (const n of iconNames) {
    if (n.startsWith(kebab) || n.includes(kebab)) return n;
  }

  return null;
}

/**
 * Fetch SVG for an icon from GitHub Pages.
 * Returns complete SVG string with color/size applied, or null if not found.
 */
export async function getIconSvgAsync(
  iconName: string,
  size: number = 24,
  color: string = 'currentColor',
  strokeWidth: number = 2
): Promise<string | null> {
  await loadIndex();

  const resolved = resolveIconFile(iconName);
  if (!resolved) return null;

  // Check memory cache
  const cacheKey = resolved;
  let rawSvg = svgCache.get(cacheKey);

  if (!rawSvg) {
    // Check disk cache
    const diskPath = join(getCacheDir(), `${resolved}.svg`);
    if (existsSync(diskPath)) {
      rawSvg = readFileSync(diskPath, 'utf8');
    } else {
      // Fetch from GitHub Pages
      try {
        const url = `${BASE_URL}/icons/${resolved}.svg`;
        rawSvg = await fetchUrl(url);
        writeFileSync(diskPath, rawSvg, 'utf8');
      } catch (err) {
        console.warn(`[untitled-icons] Failed to fetch ${resolved}.svg:`, (err as Error).message);
        return null;
      }
    }
    svgCache.set(cacheKey, rawSvg);
  }

  // Apply color, size, strokeWidth
  let svg = rawSvg
    .replace(/stroke="[^"]*"/g, `stroke="${color}"`)
    .replace(/width="[^"]*"/, `width="${size}"`)
    .replace(/height="[^"]*"/, `height="${size}"`)
    .replace(/stroke-width="[^"]*"/g, `stroke-width="${strokeWidth}"`);

  return svg;
}

/**
 * Synchronous version — uses disk cache only.
 * Falls back to null if SVG not cached yet.
 */
export function getIconSvg(
  iconName: string,
  size: number = 24,
  color: string = 'currentColor',
  strokeWidth: number = 2
): string | null {
  loadIndexSync();

  const resolved = resolveIconFile(iconName);
  if (!resolved) return null;

  // Check memory cache
  let rawSvg = svgCache.get(resolved);

  if (!rawSvg) {
    // Check disk cache
    const diskPath = join(getCacheDir(), `${resolved}.svg`);
    if (existsSync(diskPath)) {
      rawSvg = readFileSync(diskPath, 'utf8');
      svgCache.set(resolved, rawSvg);
    } else {
      return null; // Not cached — caller should use getIconSvgAsync
    }
  }

  let svg = rawSvg
    .replace(/stroke="[^"]*"/g, `stroke="${color}"`)
    .replace(/width="[^"]*"/, `width="${size}"`)
    .replace(/height="[^"]*"/, `height="${size}"`)
    .replace(/stroke-width="[^"]*"/g, `stroke-width="${strokeWidth}"`);

  return svg;
}

/**
 * Pre-cache all icons to disk (run once at startup).
 * Fetches icons-data.json, then batch-downloads all SVGs.
 */
export async function preCacheIcons(): Promise<number> {
  await loadIndex();
  if (!iconNames || iconNames.size === 0) return 0;

  const cacheDir = getCacheDir();
  let fetched = 0;

  for (const name of iconNames) {
    const diskPath = join(cacheDir, `${name}.svg`);
    if (existsSync(diskPath)) continue;

    try {
      const url = `${BASE_URL}/icons/${name}.svg`;
      const svg = await fetchUrl(url);
      writeFileSync(diskPath, svg, 'utf8');
      fetched++;
    } catch {
      // Skip failed icons
    }
  }

  console.log(`[untitled-icons] Pre-cached ${fetched} new icons (${iconNames.size} total)`);
  return fetched;
}

/**
 * List all available icon names (kebab-case).
 */
export function listIcons(): string[] {
  loadIndexSync();
  return iconNames ? Array.from(iconNames) : [];
}
