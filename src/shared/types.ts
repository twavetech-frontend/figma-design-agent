// ============================================================
// Shared types for the Figma bridge (WebSocket server + embedded MCP)
// ============================================================

// --- Figma Connection ---

export type FigmaConnectionStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

export type InputMode = 'terminal' | 'app';

export interface FigmaConnectionState {
  status: FigmaConnectionStatus;
  channel: string | null;
  pluginVersion?: string;
  documentName?: string;
  inputMode?: InputMode;
}

// --- Figma WebSocket Types ---

export type FigmaCommand = string;

export interface PendingRequest {
  resolve: (value: unknown) => void;
  reject: (reason: Error) => void;
  timeout: ReturnType<typeof setTimeout>;
  lastActivity: number;
}

// --- Tool Definition for Embedded MCP ---

export interface ToolDefinition {
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
  handler: (params: Record<string, unknown>) => Promise<unknown>;
  /** Per-tool timeout hint (ms). Used by the MCP HTTP server. */
  timeoutMs?: number;
}
