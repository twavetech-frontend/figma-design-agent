#!/usr/bin/env node
/**
 * Patch a freshly-fetched sync-to-agent.js to exclude the DS "Dark" color mode.
 *
 * sync-to-agent.js intends Light as the agent default (its own comment:
 * "Exclude Dark mode — agent uses Light mode as default"), but its filter only
 * drops keys containing the substring 'dark mode'. The DS token set key is
 * `1. Color modes/Dark` — which contains 'modes/dark', NOT 'dark mode' — so the
 * Dark mode set survives the filter and, being merged last, overrides Light.
 * Result: TOKEN_MAP.json comes out with Dark values (bg-primary #000000 …).
 *
 * This patch adds an explicit exclusion for the Dark color-mode set so syncs
 * produce Light-mode TOKEN_MAP.json. Idempotent.
 *
 * Usage: node scripts/patch-sync-agent.js <path-to-sync-to-agent.js>
 */
const fs = require('fs');

const file = process.argv[2];
if (!file || !fs.existsSync(file)) {
  console.log('[patch-sync] file not found, skipping:', file);
  process.exit(0);
}

let c = fs.readFileSync(file, 'utf8');
const find = "!k.toLowerCase().includes('dark mode')";

if (c.includes('color modes\\/dark') || c.includes('color modes/dark')) {
  console.log('[patch-sync] already patched');
} else if (c.includes(find)) {
  c = c.replace(find, find + " && !/color modes\\/dark/i.test(k)");
  fs.writeFileSync(file, c);
  console.log('[patch-sync] Dark color mode excluded — TOKEN_MAP will use Light mode');
} else {
  console.log('[patch-sync] WARNING: filter pattern not found — sync-to-agent.js changed; update scripts/patch-sync-agent.js');
}
