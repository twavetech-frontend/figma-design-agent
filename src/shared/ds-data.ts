/**
 * DS Data Loader — Reused from existing MCP server
 *
 * Loads and caches design system data from local files.
 * No Figma connection needed.
 */

import * as fs from 'fs';
import * as path from 'path';
import { execSync } from 'child_process';
import * as https from 'https';

// ─── Types ───────────────────────────────────────────────────────────

export interface VariantEntry {
  name: string;
  setKey: string;
  variants: Record<string, string>;
}

export interface DesignToken {
  token: string;
  value: string;
  type?: string;
  cssVar?: string;
}

export interface TokenMapEntry {
  figmaPath: string;
  value: string;
  type: string;
}

export interface TextStyleEntry {
  name: string;
  fontFamily: string;
  fontWeight: string;
  fontSize: string;
  lineHeight: string;
}

export interface EffectEntry {
  name: string;
  type: string;
  value: string;
}

export interface DesignTokens {
  colors: DesignToken[];
  spacing: DesignToken[];
  radius: DesignToken[];
  typography: DesignToken[];
  textStyles: TextStyleEntry[];
  effects: EffectEntry[];
  layout: DesignToken[];
  width: DesignToken[];
}

export interface ComponentDoc {
  name: string;
  category: string;
  path: string;
  description: string;
  figmaComponentName: string | null;
  variants: Array<{ name: string; description: string; subVariants: string[] }>;
  props: Array<{ name: string; type: string; values: string[]; default: string | null }>;
  figmaVariants: string[];
  usageGuidelines: string | null;
}

export interface ComponentDocsData {
  source: string;
  lastFetched: string;
  foundation: ComponentDoc[];
  components: ComponentDoc[];
}

// ─── Caches ──────────────────────────────────────────────────────────

let iconsCache: Record<string, string> | null = null;
let variantsCache: VariantEntry[] | null = null;
let tokensCache: DesignTokens | null = null;
let tokenMapCache: Record<string, TokenMapEntry> | null = null;
let componentDocsCache: ComponentDocsData | null = null;
let projectRoot: string | null = null;

/** Set the project root for file resolution */
export function setProjectRoot(root: string): void {
  projectRoot = root;
}

/** Invalidate all caches — call after sync-tokens-from-github.sh */
export function invalidateDSCaches(): void {
  iconsCache = null;
  variantsCache = null;
  tokensCache = null;
  tokenMapCache = null;
  componentDocsCache = null;
}

function getRoot(): string {
  if (!projectRoot) {
    // Default: project root is two levels up from out/main/ or src/shared/
    projectRoot = path.resolve(__dirname, '..', '..');
  }
  return projectRoot;
}

/** Resolve the ds/ directory within the project root */
function getDsDir(): string {
  return path.join(getRoot(), 'ds');
}

// ─── Icons ───────────────────────────────────────────────────────────

export function getIcons(): Record<string, string> {
  if (iconsCache) return iconsCache;

  const filePath = path.join(getDsDir(), 'ds-1-icons.json');
  if (!fs.existsSync(filePath)) {
    throw new Error(`Icons file not found: ${filePath}`);
  }

  const raw = fs.readFileSync(filePath, 'utf-8');
  iconsCache = JSON.parse(raw) as Record<string, string>;
  return iconsCache;
}

// ─── Variants ────────────────────────────────────────────────────────

export function getVariants(): VariantEntry[] {
  if (variantsCache) return variantsCache;

  const filePath = path.join(getDsDir(), 'ds-1-variants.jsonl');
  if (!fs.existsSync(filePath)) {
    throw new Error(`Variants file not found: ${filePath}`);
  }

  const raw = fs.readFileSync(filePath, 'utf-8');
  variantsCache = raw
    .split('\n')
    .filter((line) => line.trim().length > 0)
    .map((line) => JSON.parse(line) as VariantEntry);
  return variantsCache;
}

// ─── Design Tokens ───────────────────────────────────────────────────

function parseTokenTable(lines: string[], startIdx: number): { tokens: DesignToken[]; endIdx: number } {
  const tokens: DesignToken[] = [];
  let i = startIdx;

  while (i < lines.length && !lines[i].startsWith('|')) i++;
  if (i >= lines.length) return { tokens, endIdx: i };

  i += 2; // Skip header + separator

  while (i < lines.length && lines[i].startsWith('|')) {
    const cols = lines[i].split('|').map((c) => c.trim()).filter(Boolean);
    if (cols.length >= 2) {
      const third = cols[2]?.replace(/`/g, '') || undefined;
      const cssVar = third?.startsWith('--') ? third : undefined;
      tokens.push({ token: cols[0], value: cols[1], type: cssVar ? undefined : third, cssVar });
    }
    i++;
  }

  return { tokens, endIdx: i };
}

function parseTextStyleTable(lines: string[], startIdx: number): { styles: TextStyleEntry[]; endIdx: number } {
  const styles: TextStyleEntry[] = [];
  let i = startIdx;

  while (i < lines.length && !lines[i].startsWith('|')) i++;
  if (i >= lines.length) return { styles, endIdx: i };

  i += 2; // Skip header + separator

  while (i < lines.length && lines[i].startsWith('|')) {
    const cols = lines[i].split('|').map((c) => c.trim()).filter(Boolean);
    if (cols.length >= 5) {
      styles.push({
        name: cols[0],
        fontFamily: cols[1],
        fontWeight: cols[2],
        fontSize: cols[3],
        lineHeight: cols[4],
      });
    }
    i++;
  }

  return { styles, endIdx: i };
}

function parseEffectTable(lines: string[], startIdx: number): { effects: EffectEntry[]; endIdx: number } {
  const effects: EffectEntry[] = [];
  let i = startIdx;

  while (i < lines.length && !lines[i].startsWith('|')) i++;
  if (i >= lines.length) return { effects, endIdx: i };

  i += 2;

  while (i < lines.length && lines[i].startsWith('|')) {
    const cols = lines[i].split('|').map((c) => c.trim()).filter(Boolean);
    if (cols.length >= 3) {
      effects.push({
        name: cols[0],
        type: cols[1],
        value: cols[2],
      });
    }
    i++;
  }

  return { effects, endIdx: i };
}

export function getDesignTokens(): DesignTokens {
  if (tokensCache) return tokensCache;

  const filePath = path.join(getDsDir(), 'DESIGN_TOKENS.md');
  if (!fs.existsSync(filePath)) {
    throw new Error(`Design tokens file not found: ${filePath}`);
  }

  const raw = fs.readFileSync(filePath, 'utf-8');
  const lines = raw.split('\n');

  const result: DesignTokens = {
    colors: [], spacing: [], radius: [], typography: [],
    textStyles: [], effects: [], layout: [], width: [],
  };

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];

    if (line.startsWith('## Colors')) {
      i++;
      while (i < lines.length && !lines[i].startsWith('## ')) {
        if (lines[i].startsWith('|') && !lines[i].startsWith('|--') && !lines[i].startsWith('| Token')) {
          const cols = lines[i].split('|').map((c) => c.trim()).filter(Boolean);
          if (cols.length >= 2) {
            const third = cols[2]?.replace(/`/g, '') || undefined;
            const cssVar = third?.startsWith('--') ? third : undefined;
            result.colors.push({ token: cols[0], value: cols[1], type: cssVar ? undefined : third, cssVar });
          }
        }
        i++;
      }
    } else if (line.startsWith('## Spacing')) {
      const p = parseTokenTable(lines, i + 1);
      result.spacing = p.tokens; i = p.endIdx;
    } else if (line.startsWith('## Radius')) {
      const p = parseTokenTable(lines, i + 1);
      result.radius = p.tokens; i = p.endIdx;
    } else if (line.startsWith('## Typography')) {
      const p = parseTokenTable(lines, i + 1);
      result.typography = p.tokens; i = p.endIdx;
    } else if (line.startsWith('## Text Styles')) {
      const p = parseTextStyleTable(lines, i + 1);
      result.textStyles = p.styles; i = p.endIdx;
    } else if (line.startsWith('## Effects')) {
      const p = parseEffectTable(lines, i + 1);
      result.effects = p.effects; i = p.endIdx;
    } else if (line.startsWith('## Layout')) {
      const p = parseTokenTable(lines, i + 1);
      result.layout = p.tokens; i = p.endIdx;
    } else if (line.startsWith('## Width')) {
      const p = parseTokenTable(lines, i + 1);
      result.width = p.tokens; i = p.endIdx;
    } else {
      i++;
    }
  }

  tokensCache = result;
  return tokensCache;
}

// ─── Token Map (CSS var ↔ Figma path) ───────────────────────────────

export function getTokenMap(): Record<string, TokenMapEntry> {
  if (tokenMapCache) return tokenMapCache;

  const filePath = path.join(getDsDir(), 'TOKEN_MAP.json');
  if (!fs.existsSync(filePath)) {
    return {};
  }

  const raw = fs.readFileSync(filePath, 'utf-8');
  tokenMapCache = JSON.parse(raw) as Record<string, TokenMapEntry>;
  return tokenMapCache;
}

// ─── Component Docs (from DS docs site) ─────────────────────────────

export function getComponentDocs(): ComponentDocsData | null {
  if (componentDocsCache) return componentDocsCache;

  const filePath = path.join(getDsDir(), 'DS_COMPONENT_DOCS.json');
  if (!fs.existsSync(filePath)) {
    console.warn(`[DS] Component docs not found: ${filePath}`);
    return null;
  }

  try {
    const raw = fs.readFileSync(filePath, 'utf-8');
    componentDocsCache = JSON.parse(raw) as ComponentDocsData;
    const total = (componentDocsCache.foundation?.length || 0) + (componentDocsCache.components?.length || 0);
    console.log(`[DS] Loaded ${total} component docs from DS_COMPONENT_DOCS.json`);
    return componentDocsCache;
  } catch (e) {
    console.warn('[DS] Failed to parse DS_COMPONENT_DOCS.json:', e);
    return null;
  }
}

/** Build a compact summary of all components for system prompt injection */
export function getComponentDocsSummary(): string | null {
  const docs = getComponentDocs();
  if (!docs) return null;

  const lines: string[] = [];
  lines.push('### DS Component Reference (from design-system-docs)');
  lines.push('');

  // Components section
  if (docs.components?.length) {
    lines.push('**Components:**');
    for (const comp of docs.components) {
      const figma = comp.figmaComponentName ? ` (Figma: \`${comp.figmaComponentName}\`)` : '';
      const variantNames = comp.variants?.map((v) => v.name).join(', ') || '';
      const props = comp.props?.map((p) => p.name).join(', ') || '';
      lines.push(`- **${comp.name}**${figma}: ${comp.description || ''}`);
      if (variantNames) lines.push(`  - Variants: ${variantNames}`);
      if (props) lines.push(`  - Props: ${props}`);
    }
    lines.push('');
  }

  // Foundation section (brief)
  if (docs.foundation?.length) {
    lines.push('**Foundation:**');
    for (const f of docs.foundation) {
      lines.push(`- **${f.name}**: ${f.description || ''}`);
    }
    lines.push('');
  }

  lines.push('> Use `lookup_component_docs` tool for detailed variant/prop info per component.');

  return lines.join('\n');
}

// ─── Component Docs Sync from GitHub Pages ──────────────────────────

const DOCS_BASE = 'https://twavetech-frontend.github.io';
const DOCS_PREFIX = '/design-system-docs';

export type DocsSyncProgress = (current: number, total: number, name: string) => void;

/** HTTPS GET helper — returns response body as string */
function httpsGet(urlStr: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const url = new URL(urlStr);
    const req = https.request({
      hostname: url.hostname,
      path: url.pathname + url.search,
      method: 'GET',
      headers: { 'User-Agent': 'figma-design-agent' },
    }, (res) => {
      if (res.statusCode && res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        httpsGet(res.headers.location).then(resolve).catch(reject);
        return;
      }
      let data = '';
      res.on('data', (chunk: Buffer) => { data += chunk.toString(); });
      res.on('end', () => resolve(data));
    });
    req.on('error', reject);
    req.setTimeout(15000, () => { req.destroy(); reject(new Error('Timeout')); });
    req.end();
  });
}

/** Parse sidebar navigation links from index page HTML */
function parseNavLinks(html: string): Array<{ name: string; path: string; category: 'foundation' | 'components' }> {
  const links: Array<{ name: string; path: string; category: 'foundation' | 'components' }> = [];
  const seen = new Set<string>();
  const regex = /<a[^>]*href="(\/design-system-docs\/(foundation|components)\/[^"]+)"[^>]*>([^<]*)<\/a>/g;
  let match;
  while ((match = regex.exec(html)) !== null) {
    const [, linkPath, cat, name] = match;
    if (!seen.has(linkPath) && name.trim()) {
      seen.add(linkPath);
      links.push({
        name: name.trim().replace(/&amp;/g, '&'),
        path: linkPath,
        category: cat === 'foundation' ? 'foundation' : 'components',
      });
    }
  }
  return links;
}

/** Extract article text from HTML, stripping tags */
function extractArticleText(html: string): string {
  const m = html.match(/<article[^>]*>([\s\S]*?)<\/article>/);
  if (!m) return '';
  let text = m[1];
  text = text.replace(/<script[\s\S]*?<\/script>/gi, '');
  text = text.replace(/<style[\s\S]*?<\/style>/gi, '');
  text = text.replace(/<br\s*\/?>/gi, '\n');
  text = text.replace(/<\/(p|div|h[1-6]|tr|li)>/gi, '\n');
  text = text.replace(/<[^>]+>/g, ' ');
  text = text.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'");
  text = text.replace(/[ \t]+/g, ' ').replace(/\n\s*\n/g, '\n').trim();
  return text;
}

/** Parse HTML tables from article content */
function parseHtmlTables(html: string): Array<string[][]> {
  const articleMatch = html.match(/<article[^>]*>([\s\S]*?)<\/article>/);
  if (!articleMatch) return [];
  const content = articleMatch[1];
  const tables: Array<string[][]> = [];
  const tableRegex = /<table[^>]*>([\s\S]*?)<\/table>/gi;
  let tm;
  while ((tm = tableRegex.exec(content)) !== null) {
    const rows: string[][] = [];
    const rowRegex = /<tr[^>]*>([\s\S]*?)<\/tr>/gi;
    let rm;
    while ((rm = rowRegex.exec(tm[1])) !== null) {
      const cells: string[] = [];
      const cellRegex = /<t[dh][^>]*>([\s\S]*?)<\/t[dh]>/gi;
      let cm;
      while ((cm = cellRegex.exec(rm[1])) !== null) {
        cells.push(cm[1].replace(/<[^>]+>/g, '').trim());
      }
      rows.push(cells);
    }
    tables.push(rows);
  }
  return tables;
}

/** Parse a single component page into ComponentDoc */
function parsePageToDoc(html: string, name: string, pagePath: string, category: string): ComponentDoc {
  const text = extractArticleText(html);
  const lines = text.split('\n').map(l => l.trim()).filter(Boolean);

  // Description: first meaningful paragraph
  let description = '';
  for (const line of lines) {
    if (line.startsWith('🧩') || line.startsWith('🎨') || line === name) continue;
    if (line.length > 15 && !line.startsWith('Figma') && !line.startsWith('Props') && !line.startsWith('Preview')) {
      description = line;
      break;
    }
  }

  // Figma component name
  let figmaComponentName: string | string[] | null = null;
  const fmSingle = html.match(/Figma\s*컴포넌트\s*:\s*(?:<[^>]+>)*\s*([A-Za-z][^<\n]{2,80})/);
  if (fmSingle) {
    const val = fmSingle[1].trim();
    if (val.includes(',')) {
      figmaComponentName = val.split(',').map(s => s.trim());
    } else {
      figmaComponentName = val;
    }
  }

  // Parse tables for props and figma variants
  const tables = parseHtmlTables(html);
  const props: ComponentDoc['props'] = [];
  const figmaVariants: string[] = [];
  const variants: ComponentDoc['variants'] = [];

  for (const table of tables) {
    if (table.length < 2) continue;
    const header = table[0].map(h => h.toLowerCase());

    // Props table: [Prop, Type, Default, Description]
    if (header.includes('prop') && header.includes('type')) {
      const propIdx = header.indexOf('prop');
      const typeIdx = header.indexOf('type');
      const defIdx = header.indexOf('default');
      const descIdx = header.indexOf('description');
      for (let r = 1; r < table.length; r++) {
        const row = table[r];
        const propName = row[propIdx] || '';
        const propType = row[typeIdx] || '';
        if (!propName) continue;
        props.push({
          name: propName,
          type: propType,
          values: propType.includes('|') ? propType.split('|').map(v => v.trim().replace(/'/g, '')) : [],
          default: (defIdx >= 0 && row[defIdx] && row[defIdx] !== '-' && row[defIdx] !== '—') ? row[defIdx] : null,
        });
      }
    }

    // Figma variants table: [Property, Values]
    if (header.includes('property') && header.includes('values')) {
      const propIdx = header.indexOf('property');
      const valIdx = header.indexOf('values');
      for (let r = 1; r < table.length; r++) {
        const row = table[r];
        const prop = row[propIdx] || '';
        const vals = row[valIdx] || '';
        if (prop && vals) {
          figmaVariants.push(`${prop}: ${vals}`);
        }
      }
    }
  }

  // Extract section headings as variant names
  const headingRegex = /<h2[^>]*>([\s\S]*?)<\/h2>/gi;
  let hm;
  while ((hm = headingRegex.exec(html.match(/<article[^>]*>([\s\S]*?)<\/article>/)?.[1] || '')) !== null) {
    const hText = hm[1].replace(/<[^>]+>/g, '').trim();
    if (hText && !['Props', 'Figma Variants', '조합 예시', 'Preview'].includes(hText)) {
      variants.push({ name: hText, description: '', subVariants: [] });
    }
  }

  return {
    name,
    category,
    path: pagePath,
    description,
    figmaComponentName: figmaComponentName as string | null,
    variants,
    props,
    figmaVariants,
    usageGuidelines: null,
  };
}

/**
 * Sync component docs from GitHub Pages.
 * Fetches the docs site, parses all pages, saves to DS_COMPONENT_DOCS.json.
 * Returns the number of docs synced.
 */
export async function syncComponentDocs(onProgress?: DocsSyncProgress): Promise<number> {
  console.log('[DS Docs] Syncing from GitHub Pages...');

  // 1. Fetch index page to discover all nav links
  const indexHtml = await httpsGet(`${DOCS_BASE}${DOCS_PREFIX}`);
  const links = parseNavLinks(indexHtml);

  if (links.length === 0) {
    console.warn('[DS Docs] No navigation links found on index page');
    return 0;
  }

  console.log(`[DS Docs] Found ${links.length} pages to fetch`);

  // 2. Fetch each page and parse
  const foundation: ComponentDoc[] = [];
  const components: ComponentDoc[] = [];

  // Dedupe by path (some pages like Inputs/Dropdowns appear multiple times)
  const uniqueLinks = links.filter((link, idx, arr) => arr.findIndex(l => l.path === link.path) === idx);

  for (let i = 0; i < uniqueLinks.length; i++) {
    const link = uniqueLinks[i];
    if (onProgress) onProgress(i + 1, uniqueLinks.length, link.name);

    try {
      const pageHtml = await httpsGet(`${DOCS_BASE}${link.path}`);
      const doc = parsePageToDoc(pageHtml, link.name, link.path, link.category);

      if (link.category === 'foundation') {
        foundation.push(doc);
      } else {
        components.push(doc);
      }
    } catch (e) {
      console.warn(`[DS Docs] Failed to fetch ${link.name} (${link.path}):`, e);
    }
  }

  // 3. Save to JSON
  const data: ComponentDocsData = {
    source: `${DOCS_BASE}${DOCS_PREFIX}`,
    lastFetched: new Date().toISOString(),
    foundation,
    components,
  };

  const filePath = path.join(getDsDir(), 'DS_COMPONENT_DOCS.json');
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2), 'utf-8');

  // 4. Invalidate cache so next getComponentDocs() reads fresh data
  componentDocsCache = null;

  const total = foundation.length + components.length;
  console.log(`[DS Docs] Synced ${total} docs (${foundation.length} foundation, ${components.length} components)`);
  return total;
}

// ─── DS Token Sync from GitHub ──────────────────────────────────────

/** Path to the file storing the last synced GitHub commit SHA */
function getShaFilePath(): string {
  return path.join(getDsDir(), '.last_sync_sha');
}

/** Read the stored SHA from disk, or null if not present */
function getStoredSha(): string | null {
  try {
    const shaPath = getShaFilePath();
    if (!fs.existsSync(shaPath)) return null;
    const sha = fs.readFileSync(shaPath, 'utf-8').trim();
    return sha || null;
  } catch {
    return null;
  }
}

/** Write the SHA to disk */
function storeSha(sha: string): void {
  try {
    fs.writeFileSync(getShaFilePath(), sha, 'utf-8');
  } catch (e) {
    console.warn('[DS Sync] Failed to store SHA:', e);
  }
}

/** Fetch the latest commit SHA for tokens.json from GitHub API */
function fetchLatestSha(): Promise<string | null> {
  return new Promise((resolve) => {
    const options: https.RequestOptions = {
      hostname: 'api.github.com',
      path: '/repos/twavetech-frontend/design-system/commits?path=tokens.json&per_page=1',
      method: 'GET',
      headers: {
        'User-Agent': 'figma-design-agent',
        'Accept': 'application/vnd.github.v3+json',
      },
    };

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', (chunk: Buffer) => { data += chunk.toString(); });
      res.on('end', () => {
        try {
          if (res.statusCode !== 200) {
            console.warn(`[DS Sync] GitHub API returned status ${res.statusCode}`);
            resolve(null);
            return;
          }
          const commits = JSON.parse(data) as Array<{ sha: string }>;
          if (Array.isArray(commits) && commits.length > 0 && commits[0].sha) {
            resolve(commits[0].sha);
          } else {
            console.warn('[DS Sync] No commits found in GitHub API response');
            resolve(null);
          }
        } catch (e) {
          console.warn('[DS Sync] Failed to parse GitHub API response:', e);
          resolve(null);
        }
      });
    });

    req.on('error', (e) => {
      console.warn('[DS Sync] GitHub API request failed:', e);
      resolve(null);
    });

    req.setTimeout(10000, () => {
      console.warn('[DS Sync] GitHub API request timed out');
      req.destroy();
      resolve(null);
    });

    req.end();
  });
}

/** Run the sync script, invalidate caches, and store the latest SHA */
function runSyncScript(): void {
  const scriptPath = path.join(getRoot(), 'scripts', 'sync-tokens-from-github.sh');
  if (!fs.existsSync(scriptPath)) {
    console.warn(`[DS Sync] Sync script not found: ${scriptPath}`);
    return;
  }

  try {
    execSync(`bash "${scriptPath}"`, {
      cwd: getRoot(),
      timeout: 30000,
      stdio: 'pipe',
    });
    invalidateDSCaches();
    console.log('[DS Sync] Token sync completed successfully');
  } catch (e) {
    console.warn('[DS Sync] Sync script failed:', e);
  }
}

/**
 * Synchronous full sync — run at bridge startup.
 * Executes sync-tokens-from-github.sh, invalidates caches, stores latest SHA.
 * All errors are non-blocking (log and continue).
 */
export function syncTokensFull(): void {
  try {
    console.log('[DS Sync] Running full token sync...');
    runSyncScript();

    // After sync, try to fetch and store the latest SHA for future comparisons
    // Since this is synchronous, we do a best-effort SHA store via execSync curl
    try {
      const result = execSync(
        'curl -s -H "User-Agent: figma-design-agent" -H "Accept: application/vnd.github.v3+json" "https://api.github.com/repos/twavetech-frontend/design-system/commits?path=tokens.json&per_page=1"',
        { timeout: 10000, encoding: 'utf-8' },
      );
      const commits = JSON.parse(result) as Array<{ sha: string }>;
      if (Array.isArray(commits) && commits.length > 0 && commits[0].sha) {
        storeSha(commits[0].sha);
        console.log(`[DS Sync] Stored SHA: ${commits[0].sha.substring(0, 8)}...`);
      }
    } catch (e) {
      console.warn('[DS Sync] Failed to fetch/store SHA after full sync:', e);
    }
  } catch (e) {
    console.warn('[DS Sync] Full sync failed:', e);
  }
}

/**
 * Async conditional sync — call before design generation.
 * Fetches latest commit SHA for tokens.json from GitHub API.
 * If different from stored SHA, re-runs sync + invalidates caches + stores new SHA.
 * If same, skips. All errors non-blocking.
 */
export async function syncTokensIfNeeded(): Promise<void> {
  try {
    const latestSha = await fetchLatestSha();
    if (!latestSha) {
      console.warn('[DS Sync] Could not fetch latest SHA, skipping sync check');
      return;
    }

    const storedSha = getStoredSha();
    if (storedSha === latestSha) {
      console.log(`[DS Sync] Tokens up-to-date (SHA: ${latestSha.substring(0, 8)}...)`);
      return;
    }

    console.log(`[DS Sync] Token change detected (stored: ${storedSha?.substring(0, 8) ?? 'none'}, latest: ${latestSha.substring(0, 8)}...)`);
    runSyncScript();
    storeSha(latestSha);
    console.log(`[DS Sync] Updated to SHA: ${latestSha.substring(0, 8)}...`);
  } catch (e) {
    console.warn('[DS Sync] syncTokensIfNeeded failed:', e);
  }
}
