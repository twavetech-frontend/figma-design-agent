#!/usr/bin/env node
/**
 * Patch @hono/mcp to remove Accept header validation.
 *
 * The Python MCP client (scripts/figma_mcp_client.py) and Claude Code's HTTP
 * MCP client send `Accept: application/json` only — not `text/event-stream`.
 * @hono/mcp rejects those with 406 "Not Acceptable". The bridge runs the
 * transport with `enableJsonResponse: true`, so it replies with plain JSON
 * regardless — the Accept check is the only thing in the way.
 *
 * This patch neuters both Accept checks (POST handlePostRequest + GET
 * handleGetRequest) by replacing their `if (...)` conditions with `if (false)`.
 * It is idempotent and version-tolerant: it targets the stable condition
 * expressions, not surrounding formatting.
 *
 * Runs automatically via `npm run postinstall`. Re-run manually with:
 *   node scripts/patch-hono-mcp.js
 */
const fs = require('fs');
const path = require('path');

const filePath = path.join(__dirname, '..', 'node_modules', '@hono', 'mcp', 'dist', 'index.cjs');

if (!fs.existsSync(filePath)) {
  console.log('[patch] @hono/mcp not found, skipping');
  process.exit(0);
}

let content = fs.readFileSync(filePath, 'utf-8');
const original = content;

// POST handler (handlePostRequest): requires both application/json AND text/event-stream
const postCheck =
  'if (!acceptHeader?.includes("application/json") || !acceptHeader.includes("text/event-stream")) throw';
// GET handler (handleGetRequest): requires text/event-stream
const getCheck =
  'if (!ctx.req.header("Accept")?.includes("text/event-stream")) throw';

let postPatched = false;
let getPatched = false;

if (content.includes(postCheck)) {
  content = content.split(postCheck).join('if (false) throw');
  postPatched = true;
}
if (content.includes(getCheck)) {
  content = content.split(getCheck).join('if (false) throw');
  getPatched = true;
}

if (content !== original) {
  fs.writeFileSync(filePath, content);
  console.log(
    `[patch] @hono/mcp: Accept header check removed (POST=${postPatched}, GET=${getPatched})`
  );
} else if (content.includes('if (false) throw')) {
  console.log('[patch] @hono/mcp: already patched');
} else {
  console.log(
    '[patch] @hono/mcp: Accept-check pattern not found — @hono/mcp may have changed; ' +
      'update scripts/patch-hono-mcp.js'
  );
}
