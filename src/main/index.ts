/**
 * Electron Main Process Entry Point
 *
 * Wires up all components:
 * - BrowserWindow with React renderer
 * - WebSocket server for Figma plugin
 * - Tool Bridge Server for MCP ↔ Electron communication
 * - Agent Orchestrator with Claude Agent SDK or API key fallback
 * - IPC handlers for renderer communication
 */

import { app, BrowserWindow, ipcMain, shell } from 'electron';
import { join } from 'path';
import { execFile } from 'child_process';
import { FigmaWSServer } from './figma-ws-server';
import { buildToolRegistry } from './figma-mcp-embedded';
import { registerDSLookupTools } from './ds-lookup-tools';
import { AgentOrchestrator } from './agent-orchestrator';
import { McpHttpServer } from './mcp-http-server';
import { ImageGenerator } from './image-generator';

import { getGeminiApiKey, setGeminiApiKey, getAnthropicApiKey, getDirectApiKey, setAnthropicApiKey } from './settings-store';
import { setProjectRoot, getDesignTokens, getVariants, syncComponentDocs } from '../shared/ds-data';
import { IPC_CHANNELS } from '../shared/types';
import type { FigmaConnectionState, ClaudeCodeStatus } from '../shared/types';

// ============================================================
// Global error handlers — prevent EPIPE crashes from subprocess pipes
// ============================================================

process.on('uncaughtException', (err) => {
  if ((err as NodeJS.ErrnoException).code === 'EPIPE') {
    console.error('[Main] EPIPE error (subprocess pipe closed):', err.message);
    return; // Don't crash the app
  }
  console.error('[Main] Uncaught exception:', err);
});

process.on('unhandledRejection', (reason) => {
  console.error('[Main] Unhandled rejection:', reason);
});

// ============================================================
// Configuration
// ============================================================

const WS_PORT = 8767;
// Project root: out/main/ → ../../ → project root
const PROJECT_ROOT = join(__dirname, '..', '..');
const ASSETS_DIR = join(PROJECT_ROOT, 'assets', 'generated');

// ============================================================
// Global instances
// ============================================================

let mainWindow: BrowserWindow | null = null;
let figmaWS: FigmaWSServer;
let orchestrator: AgentOrchestrator | null = null;
let mcpServer: McpHttpServer;
let imageGenerator: ImageGenerator;

// Cached Claude Code status
let claudeCodeStatusCache: ClaudeCodeStatus | null = null;

// ============================================================
// Claude Code Detection
// ============================================================

/** Check if Claude Code CLI is installed and authenticated */
async function checkClaudeCodeStatus(): Promise<ClaudeCodeStatus> {
  return new Promise((resolve) => {
    execFile('claude', ['--version'], (error) => {
      if (error) {
        resolve({ installed: false, authenticated: false });
        return;
      }

      // Claude Code is installed, check auth
      execFile('claude', ['auth', 'status'], (authError, stdout, stderr) => {
        const output = (stdout || '') + (stderr || '');
        if (authError || output.includes('not logged in') || output.includes('Not authenticated')) {
          resolve({ installed: true, authenticated: false });
          return;
        }

        // Extract plan info if available
        const planMatch = output.match(/plan[:\s]+([\w\s]+)/i);
        resolve({
          installed: true,
          authenticated: true,
          plan: planMatch?.[1]?.trim(),
        });
      });
    });
  });
}

// ============================================================
// App lifecycle
// ============================================================

app.whenReady().then(async () => {
  // Set DS data project root
  setProjectRoot(PROJECT_ROOT);

  // Start WebSocket server
  figmaWS = new FigmaWSServer(WS_PORT);
  await figmaWS.start();

  // Build tool registry
  const tools = buildToolRegistry(figmaWS);
  registerDSLookupTools(tools);

  // Initialize image generator with saved API key
  imageGenerator = new ImageGenerator(ASSETS_DIR, getGeminiApiKey());

  // Register generate_image tool (Gemini API → base64 → set_image_fill)
  tools.set('generate_image', {
    name: 'generate_image',
    description: 'Generate an image using Gemini AI and apply it as fill to a Figma node. For hero/banner: set isHero=true. If a Banner Card frame exists inside the Hero Section, pass the BANNER CARD nodeId (not the Hero Section). If no Banner Card exists, pass the Hero Section nodeId. For icons: isHero=false (default), removes background.',
    inputSchema: {
      type: 'object',
      properties: {
        prompt: { type: 'string', description: 'Image description (e.g. "minimal app logo, letter M, purple gradient")' },
        nodeId: { type: 'string', description: 'Figma node ID to apply the image fill to. For hero banners: pass Banner Card nodeId if it exists inside Hero Section, otherwise pass Hero Section nodeId.' },
        isHero: { type: 'boolean', description: 'Set true for hero/banner images. Auto-detects node size from Figma, keeps solid background, forces graphics to right side. Default: false.' },
        width: { type: 'number', description: 'Target width in Figma pixels. Ignored when isHero=true (auto-detected from node). Default: 120.' },
        height: { type: 'number', description: 'Target height in Figma pixels. Ignored when isHero=true (auto-detected from node). Default: 120.' },
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

      // Hero mode: auto-detect node dimensions from the specified nodeId (no auto-escalation)
      if (isHero) {
        try {
          const nodeInfo = await figmaWS.sendCommand('get_node_info', { nodeId: targetNodeId }) as Record<string, unknown>;
          const nodeWidth = nodeInfo.width as number;
          const nodeHeight = nodeInfo.height as number;

          if (nodeWidth && nodeHeight) {
            width = Math.round(nodeWidth);
            height = Math.round(nodeHeight);
            console.log(`[Main] Hero mode: target ${targetNodeId}, size ${width}x${height}`);
          }
        } catch (e) {
          console.warn('[Main] Failed to get node size for hero, using provided dimensions:', e);
        }
      }

      // Generate image via Gemini
      const result = await imageGenerator.generate({
        prompt,
        figmaWidth: width,
        figmaHeight: height,
        style,
        isHero,
        outputName: `gen_${Date.now()}`,
      });

      // Apply as image fill to the target node
      await figmaWS.sendCommand('set_image_fill', {
        nodeId: targetNodeId,
        imageData: result.base64,
        scaleMode: 'FILL',
      });

      return { success: true, nodeId: targetNodeId, width: result.width, height: result.height, mode: isHero ? 'hero' : 'icon' };
    },
  });

  console.log(`[Main] Registered ${tools.size} tools`);

  // Start MCP HTTP Server (Hono + Streamable HTTP Transport)
  mcpServer = new McpHttpServer(tools, () => figmaWS.inputMode);
  await mcpServer.start();

  // Check Claude Code status
  claudeCodeStatusCache = await checkClaudeCodeStatus();
  console.log(`[Main] Claude Code: installed=${claudeCodeStatusCache.installed}, authenticated=${claudeCodeStatusCache.authenticated}`);

  // Create window
  createWindow();

  // Set up IPC handlers
  setupIPC(tools);

  // Forward Figma connection events + pre-cache DS components
  figmaWS.on('connection-change', (state: FigmaConnectionState) => {
    mainWindow?.webContents.send(IPC_CHANNELS.FIGMA_STATUS, state);

    // ★ Pre-cache ALL DS components + sync docs from GitHub Pages when Figma connects
    if (state.status === 'connected') {
      // Notify plugin: DS loading started
      figmaWS.sendNotification('ds-loading', { status: 'loading' });

      // Sync component docs from GitHub Pages (with progress), then pre-cache DS components
      syncComponentDocs((current, total, name) => {
        figmaWS.sendNotification('ds-loading', { status: 'syncing', current, total, name });
      })
        .then(() => preCacheDSComponents(tools))
        .then(() => {
          figmaWS.sendNotification('ds-loading', { status: 'done' });
        })
        .catch((e) => {
          console.warn('[Main] DS sync/pre-cache failed:', e);
          figmaWS.sendNotification('ds-loading', { status: 'done' });
        });
    }
  });

  figmaWS.on('input-mode-change', (mode: string) => {
    console.log(`[Main] Input mode changed: ${mode}`);
    mainWindow?.webContents.send(IPC_CHANNELS.FIGMA_INPUT_MODE, mode);
  });
});

app.on('window-all-closed', () => {
  mcpServer?.stop();
  figmaWS?.stop();
  app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

// ============================================================
// DS Pre-cache — import ALL DS component variants on Figma connect
// ============================================================

async function preCacheDSComponents(tools: Map<string, import('../shared/types').ToolDefinition>): Promise<void> {
  const preCacheTool = tools.get('pre_cache_components');
  if (!preCacheTool) {
    console.warn('[Main] pre_cache_components tool not found');
    return;
  }

  // Extract ONE representative key per component (first variant = default)
  // Caching 154 keys is fast; caching all 4716 variants overwhelms Figma API
  const variants = getVariants();
  const representativeKeys: string[] = [];
  for (const entry of variants) {
    const keys = Object.values(entry.variants);
    if (keys.length > 0) {
      representativeKeys.push(keys[0]); // first variant as representative
    }
  }

  if (representativeKeys.length === 0) {
    console.log('[Main] No DS variant keys found, skipping pre-cache');
    return;
  }

  // Clear previous cache to pick up DS updates
  try {
    await figmaWS.sendCommand('clear_component_cache');
    console.log('[Main] Cleared plugin component cache');
  } catch (e) {
    console.warn('[Main] Failed to clear component cache:', e);
  }

  console.log(`[Main] Pre-caching ${representativeKeys.length} DS components (1 representative per component)...`);
  const startTime = Date.now();

  // Notify renderer: caching started
  mainWindow?.webContents.send(IPC_CHANNELS.DS_CACHE_STATUS, {
    status: 'caching', total: representativeKeys.length, cached: 0, failed: 0,
  });

  try {
    const result = await preCacheTool.handler({ keys: representativeKeys }) as Record<string, unknown>;
    const elapsed = Date.now() - startTime;
    console.log(`[Main] DS pre-cache complete in ${elapsed}ms: ${result.newlyCached} cached, ${result.failed} failed`);

    // Notify renderer: caching done
    mainWindow?.webContents.send(IPC_CHANNELS.DS_CACHE_STATUS, {
      status: 'done',
      total: representativeKeys.length,
      cached: (result.newlyCached as number) || 0,
      failed: (result.failed as number) || 0,
      elapsed,
    });

    // Save failed keys to file for JSONL cleanup
    const failedKeys = result.failedKeys as string[] | undefined;
    if (failedKeys && failedKeys.length > 0) {
      const failedPath = join(PROJECT_ROOT, 'ds', 'failed-keys.json');
      const { writeFile: writeF } = require('fs/promises');
      await writeF(failedPath, JSON.stringify(failedKeys, null, 2));
      console.log(`[Main] Saved ${failedKeys.length} failed keys to ${failedPath}`);
    }
  } catch (e) {
    console.error('[Main] DS pre-cache error:', e);

    // Notify renderer: caching error
    mainWindow?.webContents.send(IPC_CHANNELS.DS_CACHE_STATUS, {
      status: 'error', total: representativeKeys.length, cached: 0, failed: 0,
    });
  }
}

// ============================================================
// Window creation
// ============================================================

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1024,
    height: 768,
    minWidth: 200,
    minHeight: 150,
    titleBarStyle: 'hiddenInset',
    webPreferences: {
      preload: join(__dirname, '..', 'preload', 'index.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  });

  // Load renderer
  if (process.env.ELECTRON_RENDERER_URL) {
    mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL);
  } else {
    mainWindow.loadFile(join(__dirname, '..', 'renderer', 'index.html'));
  }

  // Open DevTools in development
  if (process.env.NODE_ENV === 'development') {
    mainWindow.webContents.openDevTools({ mode: 'bottom' });
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// ============================================================
// IPC Handlers
// ============================================================

function setupIPC(tools: Map<string, import('../shared/types').ToolDefinition>): void {
  // --- Agent ---

  ipcMain.on(IPC_CHANNELS.AGENT_SEND_MESSAGE, async (event, payload: unknown) => {
    // Block messages when in terminal mode
    if (figmaWS.inputMode === 'terminal') {
      event.sender.send(IPC_CHANNELS.AGENT_EVENT, {
        type: 'error',
        message: '현재 터미널 모드입니다. Figma 플러그인에서 앱 모드로 전환하세요.',
      });
      return;
    }

    // Support both legacy string and new { message, attachments } format
    const message = typeof payload === 'string' ? payload : (payload as Record<string, unknown>).message as string;
    const attachments = typeof payload === 'string' ? undefined : (payload as Record<string, unknown>).attachments as import('../shared/types').AttachmentData[] | undefined;
    // Determine mode: Pipeline (Direct API key) or Agent SDK (Claude Code subscription)
    // Pipeline requires a real API key (not OAuth). OAuth only works via Agent SDK.
    const directApiKey = getDirectApiKey(); // Real API key only (no OAuth)
    const fullApiKey = getAnthropicApiKey(); // Includes OAuth fallback
    const claudeCodeAvailable = claudeCodeStatusCache?.installed && claudeCodeStatusCache?.authenticated;
    const usePipeline = !!directApiKey; // Pipeline only with real API key
    const useAgentSdk = !usePipeline && claudeCodeAvailable;

    if (!directApiKey && !claudeCodeAvailable) {
      mainWindow?.webContents.send(IPC_CHANNELS.APP_ERROR,
        'API 키를 설정하거나 Claude Code에 로그인해주세요. Settings에서 설정할 수 있습니다.'
      );
      return;
    }

    console.log(`[Main] Mode: ${usePipeline ? 'Pipeline (Direct API)' : useAgentSdk ? 'Agent SDK (subscription)' : 'Direct API (OAuth)'}`);

    // Create orchestrator if needed, or if mode changed
    if (!orchestrator) {
      orchestrator = new AgentOrchestrator({
        tools,
        projectRoot: PROJECT_ROOT,
        useAgentSdk: !!useAgentSdk,
        apiKey: usePipeline ? directApiKey : (useAgentSdk ? undefined : fullApiKey),
        figmaWS,
        imageGenerator,
      });

      // Forward events to renderer
      orchestrator.on('agent-event', (agentEvent) => {
        mainWindow?.webContents.send(IPC_CHANNELS.AGENT_EVENT, agentEvent);
      });

      orchestrator.on('chat-message', (chatMessage) => {
        mainWindow?.webContents.send(IPC_CHANNELS.AGENT_CHAT_UPDATE, chatMessage);
      });

      // Pipeline events
      orchestrator.on('pipeline:step', (stepEvent) => {
        mainWindow?.webContents.send(IPC_CHANNELS.PIPELINE_STEP, stepEvent);
      });

      // Initialize with Figma context if connected
      const initContext: Record<string, unknown> = {};

      if (figmaWS.isConnected && figmaWS.channel) {
        try {
          const docInfo = await figmaWS.sendCommand('get_document_info');
          initContext.figmaDocInfo = docInfo;
          const selection = await figmaWS.sendCommand('get_selection');
          initContext.figmaSelection = selection;
        } catch {
          // Not critical if this fails
        }
      }

      await orchestrator.initialize(initContext);
    }

    try {
      await orchestrator.sendMessage(message, attachments);
    } catch (error) {
      mainWindow?.webContents.send(IPC_CHANNELS.APP_ERROR,
        error instanceof Error ? error.message : String(error)
      );
    }
  });

  ipcMain.on(IPC_CHANNELS.AGENT_CANCEL, () => {
    orchestrator?.cancel();
  });

  // --- Figma ---

  ipcMain.handle(IPC_CHANNELS.FIGMA_JOIN_CHANNEL, async (_event, channel: string) => {
    try {
      await figmaWS.joinChannel(channel);
      return { success: true, channel };
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : String(error) };
    }
  });

  ipcMain.handle(IPC_CHANNELS.FIGMA_GET_STATUS, async () => {
    return {
      status: figmaWS.isConnected ? 'connected' : 'disconnected',
      channel: figmaWS.channel,
    } satisfies FigmaConnectionState;
  });

  // --- DS ---

  ipcMain.handle(IPC_CHANNELS.DS_GET_TOKENS, async () => {
    try {
      return getDesignTokens();
    } catch (error) {
      return { error: error instanceof Error ? error.message : String(error) };
    }
  });

  // --- Claude Code ---

  ipcMain.handle(IPC_CHANNELS.CLAUDE_CODE_STATUS, async () => {
    // Refresh status
    claudeCodeStatusCache = await checkClaudeCodeStatus();
    return claudeCodeStatusCache;
  });

  ipcMain.handle(IPC_CHANNELS.CLAUDE_CODE_LOGIN, async () => {
    return new Promise<{ success: boolean; error?: string }>((resolve) => {
      execFile('claude', ['login'], (error, stdout, stderr) => {
        if (error) {
          resolve({ success: false, error: error.message });
          return;
        }
        // Refresh status after login
        checkClaudeCodeStatus().then((status) => {
          claudeCodeStatusCache = status;
          // Reset orchestrator to pick up new auth
          orchestrator = null;
          resolve({ success: status.authenticated });
        });
      });
    });
  });

  // --- Claude API (legacy fallback) ---

  ipcMain.handle(IPC_CHANNELS.CLAUDE_API_STATUS, async () => {
    const key = getAnthropicApiKey();
    return {
      hasKey: !!key,
      maskedKey: key ? key.slice(0, 8) + '...' + key.slice(-4) : '',
    };
  });

  ipcMain.handle(IPC_CHANNELS.CLAUDE_API_SET_KEY, async (_event, key: string) => {
    try {
      setAnthropicApiKey(key);
      // Reset orchestrator so it picks up new key
      orchestrator = null;
      return { success: true };
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : String(error) };
    }
  });

  ipcMain.handle(IPC_CHANNELS.CLAUDE_API_VALIDATE, async (_event, key: string) => {
    try {
      const Anthropic = (await import('@anthropic-ai/sdk')).default;
      const client = new Anthropic({ apiKey: key });
      await client.messages.create({
        model: 'claude-sonnet-4-20250514',
        max_tokens: 1,
        messages: [{ role: 'user', content: 'hi' }],
      });
      return { valid: true };
    } catch (error: unknown) {
      const msg = error instanceof Error ? error.message : String(error);
      if (msg.includes('401') || msg.includes('authentication') || msg.includes('invalid')) {
        return { valid: false, error: 'Invalid API key' };
      }
      return { valid: true };
    }
  });

  // Open external URL
  ipcMain.on('shell:open-external', (_event, url: string) => {
    shell.openExternal(url);
  });

  // --- Settings ---

  ipcMain.handle(IPC_CHANNELS.SETTINGS_GET_GEMINI_KEY, async () => {
    const key = getGeminiApiKey();
    if (!key) return { hasKey: false, maskedKey: '' };
    const masked = key.slice(0, 4) + '...' + key.slice(-4);
    return { hasKey: true, maskedKey: masked };
  });

  ipcMain.handle(IPC_CHANNELS.SETTINGS_SET_GEMINI_KEY, async (_event, key: string) => {
    try {
      setGeminiApiKey(key);
      imageGenerator.setApiKey(key);
      return { success: true };
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : String(error) };
    }
  });
}
