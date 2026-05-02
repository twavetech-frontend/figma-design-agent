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
import { ImageGenerator } from '../main/image-generator';
import { getGeminiApiKey } from '../main/settings-store';
import { setProjectRoot, syncTokensFull, syncComponentDocs } from '../shared/ds-data';

// ============================================================
// Configuration
// ============================================================

const WS_PORT = 8767;
// Project root: out/bridge/ → ../../ → project root
const PROJECT_ROOT = join(__dirname, '..', '..');
const ASSETS_DIR = join(PROJECT_ROOT, 'assets', 'generated');

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

  // 3. Initialize image generator
  const imageGenerator = new ImageGenerator(ASSETS_DIR, getGeminiApiKey());

  // Register generate_image tool
  tools.set('generate_image', {
    name: 'generate_image',
    description: 'Generate an image using Gemini AI and apply it as fill to a Figma node. For hero/banner: set isHero=true and pass the HERO SECTION FRAME nodeId (NOT a child rectangle). The image fills the entire frame as background. For icons: isHero=false (default), removes background.',
    inputSchema: {
      type: 'object',
      properties: {
        prompt: { type: 'string', description: 'Image description' },
        nodeId: { type: 'string', description: 'Figma node ID to apply the image fill to' },
        isHero: { type: 'boolean', description: 'Set true for hero/banner images. Default: false.' },
        width: { type: 'number', description: 'Target width in px. Default: 120.' },
        height: { type: 'number', description: 'Target height in px. Default: 120.' },
        style: { type: 'string', description: 'Optional style override' },
      },
      required: ['prompt', 'nodeId'],
    },
    handler: async (params) => {
      const prompt = params.prompt as string;
      let targetNodeId = params.nodeId as string;
      const isHero = (params.isHero as boolean) || false;
      const style = params.style as string | undefined;
      let width = (params.width as number) || 120;
      let height = (params.height as number) || 120;

      if (isHero) {
        const MIN_HERO_SIZE = 200;
        try {
          const nodeInfo = await figmaWS.sendCommand('get_node_info', { nodeId: targetNodeId }) as Record<string, unknown>;
          let nodeWidth = nodeInfo.width as number;
          let nodeHeight = nodeInfo.height as number;

          if (nodeWidth && nodeHeight && (nodeWidth < MIN_HERO_SIZE || nodeHeight < MIN_HERO_SIZE)) {
            const parentId = nodeInfo.parentId as string;
            if (parentId) {
              const parentInfo = await figmaWS.sendCommand('get_node_info', { nodeId: parentId }) as Record<string, unknown>;
              const parentWidth = parentInfo.width as number;
              const parentHeight = parentInfo.height as number;
              if (parentWidth && parentHeight && parentWidth >= MIN_HERO_SIZE) {
                targetNodeId = parentId;
                nodeWidth = parentWidth;
                nodeHeight = parentHeight;
              }
            }
          }

          if (nodeWidth && nodeHeight) {
            width = Math.round(nodeWidth);
            height = Math.round(nodeHeight);
          }
        } catch (e) {
          console.warn('[Bridge] Failed to get node size for hero:', e);
        }
      }

      const result = await imageGenerator.generate({
        prompt,
        figmaWidth: width,
        figmaHeight: height,
        style,
        isHero,
        outputName: `gen_${Date.now()}`,
      });

      await figmaWS.sendCommand('set_image_fill', {
        nodeId: targetNodeId,
        imageData: result.base64,
        scaleMode: isHero ? 'FILL' : 'FIT',
      });

      return { success: true, nodeId: targetNodeId, width: result.width, height: result.height, mode: isHero ? 'hero' : 'icon' };
    },
  });

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

  // 6. Bypass-detection watchdog with whitelist. Every 15s, scan the GUI page
  // for root frames added AFTER the watchdog initialized. Original wireframes
  // / pre-existing screens are whitelisted on first plugin connect so we
  // never falsely flag user-authored content. Only frames born during this
  // bridge session need a build stamp; absence of stamp on a delta frame
  // proves use_figma bypass.
  //
  // Also UNDO any false-positive markings from earlier (no-whitelist) runs:
  // any frame whose stamp exists OR whose nodeId is in the whitelist gets
  // its "⚠️ RULE 1 우회 — " prefix stripped.
  const POLL_INTERVAL_MS = 15_000;
  const knownAtBoot = new Set<string>();
  let bootScanDone = false;
  let watchdogBusy = false;
  setInterval(async () => {
    if (watchdogBusy) return;
    if (!figmaWS.isConnected) return;
    watchdogBusy = true;
    try {
      const code = `
const guiPage = figma.root.children.find(p => p.name === "GUI") || figma.currentPage;
await figma.setCurrentPageAsync(guiPage);
const known = new Set(${JSON.stringify(Array.from(knownAtBoot))});
const bootDone = ${bootScanDone};
const allRoots = []; const toMark = []; const toUnmark = [];
for (const n of guiPage.children) {
  if (n.type !== "FRAME" || n.width < 360) continue;
  if (/디스크립션|description|AGENT_LIBRARY|Cover/.test(n.name || "")) continue;
  allRoots.push(n.id);
  let stamp = "";
  try { stamp = n.getSharedPluginData("fda_renderer", "screenMeta"); } catch (e) {}
  const isStamped = !!(stamp && stamp.length > 0);
  const isWhitelisted = known.has(n.id);
  const hasMark = /^⚠️ RULE 1 우회 — /.test(n.name || "");
  if (!bootDone) continue;
  // Repair: if a frame is whitelisted or stamped but still has the bypass mark,
  // strip the prefix (false-positive from a no-whitelist run).
  if ((isWhitelisted || isStamped) && hasMark) {
    n.name = n.name.replace(/^⚠️ RULE 1 우회 — /, "");
    toUnmark.push({ nodeId: n.id, newName: n.name });
    continue;
  }
  // Mark: only frames added AFTER bridge boot AND lacking a stamp
  if (!isWhitelisted && !isStamped && !hasMark) {
    n.name = "⚠️ RULE 1 우회 — " + n.name;
    toMark.push({ nodeId: n.id, newName: n.name });
  }
}
return { allRoots, marked: toMark, unmarked: toUnmark };
`;
      const result = await figmaWS.sendCommand('execute_js', { code }, 20000) as Record<string, unknown>;
      const allRoots = (result?.allRoots as string[]) || [];
      if (!bootScanDone) {
        // First successful pass after the plugin connects — capture the
        // whitelist and unmark anything that previously got falsely flagged.
        for (const id of allRoots) knownAtBoot.add(id);
        bootScanDone = true;
        console.log(`[Watchdog] Whitelist captured: ${knownAtBoot.size} pre-existing root frame(s).`);
      }
      const marked = (result?.marked as Array<{ nodeId: string; newName: string }>) || [];
      const unmarked = (result?.unmarked as Array<{ nodeId: string; newName: string }>) || [];
      if (unmarked.length > 0) {
        console.log(`[Watchdog] Repaired ${unmarked.length} false-positive mark(s):`);
        for (const u of unmarked) console.log(`  ✓ ${u.nodeId}  ${u.newName}`);
      }
      if (marked.length > 0) {
        console.log(`[Watchdog] Auto-marked ${marked.length} new bypass screen(s):`);
        for (const m of marked) console.log(`  ⚠ ${m.nodeId}  ${m.newName}`);
      }
    } catch (e) {
      // Quiet — connection drops are normal during plugin reloads
    } finally {
      watchdogBusy = false;
    }
  }, POLL_INTERVAL_MS);
  console.log(`[Bridge] Bypass watchdog armed (every ${POLL_INTERVAL_MS / 1000}s, whitelist mode).`);

  // 7. Graceful shutdown
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
