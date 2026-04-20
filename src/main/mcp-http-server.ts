/**
 * MCP HTTP Server — Hono + Streamable HTTP Transport
 *
 * Single server replacing both tool-bridge-server.ts and figma-mcp-server.ts.
 * Paper.app pattern: direct HTTP MCP with security middleware + multi-session.
 *
 * Flow:
 *   Claude Code / Cursor → (HTTP POST) → this server → tools.handler() → FigmaWSServer → Figma Plugin
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import { StreamableHTTPTransport } from '@hono/mcp';
import { Hono } from 'hono';
import { serve } from '@hono/node-server';
import type { ToolDefinition } from '../shared/types';

const MCP_PORT = 8769;
const MCP_ENDPOINT = '/mcp';

const ALLOWED_HOSTS = [
  '127.0.0.1',
  `127.0.0.1:${MCP_PORT}`,
  'localhost',
  `localhost:${MCP_PORT}`,
];

interface Session {
  server: Server;
  transport: StreamableHTTPTransport;
}

export class McpHttpServer {
  private httpServer: ReturnType<typeof serve> | null = null;
  private sessions = new Map<string, Session>();
  private tools: Map<string, ToolDefinition>;
  private getInputMode: () => 'terminal' | 'app';

  constructor(tools: Map<string, ToolDefinition>, getInputMode: () => 'terminal' | 'app') {
    this.tools = tools;
    this.getInputMode = getInputMode;
  }

  async start(): Promise<void> {
    const app = new Hono();

    // ── Security middleware (Paper.app pattern) ──

    app.use('*', async (c, next) => {
      const method = c.req.method;
      const origin = c.req.header('origin');
      const host = c.req.header('host');

      // 1. Block CORS preflight (browser requests)
      if (method === 'OPTIONS') {
        return c.text('Forbidden', 403);
      }

      // 2. Block Origin header (browser cross-origin requests)
      if (origin) {
        return c.text('Forbidden', 403);
      }

      // 3. Validate Host header (DNS rebinding prevention)
      if (host && !ALLOWED_HOSTS.includes(host)) {
        return c.text('Forbidden', 403);
      }

      // 4. App/Terminal mode check removed — MCP connections always allowed

      await next();
    });

    // Accept header check removed from @hono/mcp dist for Claude Code compatibility

    // ── MCP endpoint ──

    app.all(MCP_ENDPOINT, async (c) => {
      const sessionId = c.req.header('mcp-session-id');

      // Route to existing session
      if (sessionId && this.sessions.has(sessionId)) {
        const session = this.sessions.get(sessionId)!;

        // DELETE = close session
        if (c.req.method === 'DELETE') {
          this.sessions.delete(sessionId);
          await session.transport.close();
          console.log(`[MCP] Session closed: ${sessionId}`);
          return c.text('Session closed', 200);
        }

        const response = await session.transport.handleRequest(c);
        if (response) return response;
        return c.body(null, 200);
      }

      // New session (POST without session ID = initialization)
      if (c.req.method === 'POST') {
        const { server, transport } = this.createSession();
        const response = await transport.handleRequest(c);
        if (response) return response;
        return c.body(null, 200);
      }

      // Unknown session
      if (sessionId) {
        return c.text('Session not found', 404);
      }

      return c.text('Bad request', 400);
    });

    // ── Start HTTP server ──

    return new Promise<void>((resolve) => {
      this.httpServer = serve(
        { fetch: app.fetch, port: MCP_PORT, hostname: '127.0.0.1' },
        () => {
          // Extend HTTP server timeout to accommodate long-running tools (11 min)
          const server = this.httpServer as unknown as { requestTimeout?: number; headersTimeout?: number };
          if (server) {
            server.requestTimeout = 660_000;  // 11 min
            server.headersTimeout = 665_000;  // slightly above requestTimeout
          }
          console.log(`[MCP] HTTP server listening on http://127.0.0.1:${MCP_PORT}${MCP_ENDPOINT} (requestTimeout=660s)`);
          resolve();
        },
      );
    });
  }

  stop(): void {
    // Close all sessions
    for (const [id, session] of this.sessions) {
      session.transport.close();
      this.sessions.delete(id);
    }

    // Close HTTP server
    if (this.httpServer) {
      this.httpServer.close();
      this.httpServer = null;
    }

    console.log('[MCP] HTTP server stopped');
  }

  get url(): string {
    return `http://127.0.0.1:${MCP_PORT}${MCP_ENDPOINT}`;
  }

  // ── Session factory ──

  private createSession(): Session {
    const transport = new StreamableHTTPTransport({
      enableJsonResponse: true,
      sessionIdGenerator: () => crypto.randomUUID(),
      onsessioninitialized: (sessionId: string) => {
        this.sessions.set(sessionId, session);
        console.log(`[MCP] Session created: ${sessionId} (total: ${this.sessions.size})`);
      },
      onsessionclosed: (sessionId: string) => {
        this.sessions.delete(sessionId);
        console.log(`[MCP] Session ended: ${sessionId} (total: ${this.sessions.size})`);
      },
    });

    const server = this.createServerInstance();
    server.connect(transport);

    const session: Session = { server, transport };
    return session;
  }

  private createServerInstance(): Server {
    const server = new Server(
      { name: 'figma-tools', version: '1.0.0' },
      { capabilities: { tools: {} } },
    );

    // ── ListTools ──

    server.setRequestHandler(ListToolsRequestSchema, async () => ({
      tools: Array.from(this.tools.values()).map((t) => ({
        name: t.name,
        description: t.description,
        inputSchema: t.inputSchema as { type: 'object'; properties?: Record<string, unknown> },
      })),
    }));

    // ── CallTool ──

    server.setRequestHandler(CallToolRequestSchema, async (request) => {
      const { name, arguments: args } = request.params;
      console.log(`[MCP] Tool call: ${name}`);

      const tool = this.tools.get(name);
      if (!tool) {
        return {
          content: [{ type: 'text' as const, text: `Error: Unknown tool: ${name}` }],
          isError: true,
        };
      }

      try {
        // Per-tool timeout: use tool.timeoutMs if set, otherwise default 60s
        const toolTimeout = tool.timeoutMs || 60_000;
        const result = await Promise.race([
          tool.handler((args || {}) as Record<string, unknown>),
          new Promise<never>((_, reject) =>
            setTimeout(() => reject(new Error(`Tool '${name}' timed out after ${toolTimeout / 1000}s`)), toolTimeout),
          ),
        ]);

        return this.formatToolResult(name, result);
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error);
        console.error(`[MCP] Tool error (${name}):`, errorMsg);
        return {
          content: [{ type: 'text' as const, text: `Error: ${errorMsg}` }],
          isError: true,
        };
      }
    });

    return server;
  }

  // ── Image content block conversion (ported from figma-mcp-server.ts) ──

  private formatToolResult(name: string, result: unknown) {
    if (result && typeof result === 'object') {
      const obj = result as Record<string, unknown>;

      // export_node_as_image → MCP image content block
      if (name === 'export_node_as_image' && obj.imageData && typeof obj.imageData === 'string') {
        const { imageData, ...rest } = obj;
        return {
          content: [
            {
              type: 'image' as const,
              data: imageData as string,
              mimeType: (obj.mimeType as string) || 'image/png',
            },
            {
              type: 'text' as const,
              text: `Screenshot captured. Node: ${obj.nodeId || 'unknown'}, format: ${obj.format || 'PNG'}, scale: ${obj.scale || 1}. Analyze this image carefully for QA.\n${JSON.stringify(rest)}`,
            },
          ],
        };
      }

      // batch_build_screen → screenshot.imageData nested
      if (name === 'batch_build_screen' && obj.screenshot && typeof obj.screenshot === 'object') {
        const screenshot = obj.screenshot as Record<string, unknown>;
        if (screenshot.imageData && typeof screenshot.imageData === 'string') {
          const { screenshot: _s, ...rest } = obj;
          return {
            content: [
              {
                type: 'image' as const,
                data: screenshot.imageData as string,
                mimeType: 'image/png',
              },
              {
                type: 'text' as const,
                text: JSON.stringify(rest),
              },
              {
                type: 'text' as const,
                text: `빌드 완료: ${obj.totalNodes || '?'}개 노드 생성. rootId=${obj.rootId}. 자동 스크린샷입니다.`,
              },
            ],
          };
        }
      }
    }

    // Default: text content
    const text = typeof result === 'string' ? result : JSON.stringify(result);
    return { content: [{ type: 'text' as const, text }] };
  }
}
