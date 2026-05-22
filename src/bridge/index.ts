/**
 * Figma Bridge Server — Standalone Node.js Entry Point
 *
 * Lightweight bridge between Figma plugin and Claude Code.
 * No Electron dependency. Runs two servers:
 *   - WebSocket server (port 8767) ← Figma plugin connects here
 *   - HTTP MCP server (port 8769) ← Claude Code connects here
 *
 * Usage:
 *   npm run build && node out/bridge/index.js
 */

import { join } from 'path';
import { FigmaWSServer } from '../main/figma-ws-server';
import { buildToolRegistry } from '../main/figma-mcp-embedded';
import { registerDSLookupTools } from '../main/ds-lookup-tools';
import { McpHttpServer } from '../main/mcp-http-server';
import { setProjectRoot, syncTokensFull, syncComponentDocs } from '../shared/ds-data';

// ============================================================
// Configuration
// ============================================================

const WS_PORT = 8767;
// Project root: out/bridge/ → ../../ → project root
const PROJECT_ROOT = join(__dirname, '..', '..');

// ============================================================
// Error handlers
// ============================================================

process.on('uncaughtException', (err) => {
  if ((err as NodeJS.ErrnoException).code === 'EPIPE') {
    console.error('[Bridge] EPIPE error:', err.message);
    return;
  }
  console.error('[Bridge] Uncaught exception:', err);
  process.exit(1);
});

process.on('unhandledRejection', (reason) => {
  console.error('[Bridge] Unhandled rejection:', reason);
});

// ============================================================
// Main
// ============================================================

async function main() {
  console.log('[Bridge] Starting Figma Bridge Server...');

  // Set DS data project root
  setProjectRoot(PROJECT_ROOT);

  // Auto-sync DS tokens from GitHub on startup
  syncTokensFull();

  // 1. Start WebSocket server for Figma plugin
  const figmaWS = new FigmaWSServer(WS_PORT);
  await figmaWS.start();

  // 2. Build tool registry (58+ Figma tools)
  const tools = buildToolRegistry(figmaWS);
  registerDSLookupTools(tools);

  console.log(`[Bridge] Registered ${tools.size} tools`);

  // 4. Start MCP HTTP server
  const mcpServer = new McpHttpServer(tools);
  await mcpServer.start();

  // 5. Log connection events + sync component docs from GitHub Pages
  figmaWS.on('connection-change', (state) => {
    console.log(`[Bridge] Figma: ${state.status}${state.channel ? ` (channel: ${state.channel})` : ''}`);

    if (state.status === 'connected') {
      // Notify plugin: DS loading started
      figmaWS.sendNotification('ds-loading', { status: 'loading' });

      // Async: fetch docs from GitHub Pages with progress
      syncComponentDocs((current, total, name) => {
        figmaWS.sendNotification('ds-loading', { status: 'syncing', current, total, name });
      })
        .then((count) => {
          figmaWS.sendNotification('ds-loading', { status: 'done', count });
        })
        .catch((e) => {
          console.warn('[Bridge] DS docs sync failed:', e);
          figmaWS.sendNotification('ds-loading', { status: 'done', count: 0 });
        });
    }
  });

  console.log('[Bridge] Ready. Waiting for Figma plugin connection...');

  // 6. Graceful shutdown
  const shutdown = async () => {
    console.log('\n[Bridge] Shutting down...');
    mcpServer.stop();
    await figmaWS.stop();
    process.exit(0);
  };

  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);
}

main().catch((err) => {
  console.error('[Bridge] Fatal error:', err);
  process.exit(1);
});
