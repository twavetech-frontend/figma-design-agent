/**
 * WebSocket Server for Figma Plugin Communication
 *
 * Unlike the MCP server (which is a WS client connecting to an external relay),
 * this is a WS server running inside Electron. The Figma plugin connects directly.
 * No relay server needed.
 */

import { WebSocketServer, WebSocket } from 'ws';
import { v4 as uuidv4 } from 'uuid';
import { EventEmitter } from 'events';
import type { PendingRequest, FigmaCommand, FigmaConnectionState, InputMode } from '../shared/types';

export interface FigmaWSServerEvents {
  'connection-change': (state: FigmaConnectionState) => void;
  'plugin-message': (data: unknown) => void;
}

export class FigmaWSServer extends EventEmitter {
  private wss: WebSocketServer | null = null;
  private pluginSocket: WebSocket | null = null;
  private pendingRequests = new Map<string, PendingRequest>();
  private currentChannel: string | null = null;
  private port: number;
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private lastPongTime: number = 0;
  private currentInputMode: InputMode = 'app';
  // 🔴 DS 문서 로딩 상태 (2026-06-05 사용자: "learn-planning 을 디자인 시스템 로딩
  //    완료 후에 시작하도록 코드에 박아"). 플러그인 연결 시 'loading', syncComponentDocs
  //    완료/실패 시 'done', 미연결/해제 시 'idle'. learn-planning(Python)이 get_ds_loading_status
  //    로 이 값을 폴링해 'done' 이후에만 통독 progress 를 시작한다.
  private dsLoadingStatus: 'idle' | 'loading' | 'done' = 'idle';

  constructor(port: number = 8767) {
    super();
    this.port = port;
  }

  /** DS 문서 로딩 상태 설정 (bridge 가 connection-change 핸들러에서 갱신) */
  setDsLoadingStatus(status: 'idle' | 'loading' | 'done'): void {
    this.dsLoadingStatus = status;
  }

  /** 현재 DS 문서 로딩 상태 (learn-planning 대기용 get_ds_loading_status 도구가 노출) */
  get dsLoading(): 'idle' | 'loading' | 'done' {
    return this.dsLoadingStatus;
  }

  /** Start the WebSocket server */
  start(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.wss) {
        resolve();
        return;
      }

      this.wss = new WebSocketServer({ port: this.port });

      this.wss.on('listening', () => {
        console.log(`[FigmaWS] Server listening on port ${this.port}`);
        resolve();
      });

      this.wss.on('error', (error) => {
        console.error('[FigmaWS] Server error:', error);
        reject(error);
      });

      this.wss.on('connection', (socket) => {
        console.log('[FigmaWS] Plugin WebSocket connected, waiting for join...');
        this.pluginSocket = socket;
        this.emitConnectionState('connecting');
        this.startHeartbeat();

        socket.on('message', (data) => {
          this.handleMessage(data.toString());
        });

        socket.on('close', (code, reason) => {
          console.log(`[FigmaWS] Plugin disconnected: ${code} ${reason}`);
          this.stopHeartbeat();
          this.pluginSocket = null;
          this.currentChannel = null;
          this.currentInputMode = 'app';
          this.dsLoadingStatus = 'idle'; // 연결 해제 시 DS 로딩 상태 리셋 (재연결 시 다시 loading→done)
          this.emitConnectionState('disconnected');

          // Reject all pending requests
          for (const [id, request] of this.pendingRequests.entries()) {
            clearTimeout(request.timeout);
            request.reject(new Error('Plugin disconnected'));
            this.pendingRequests.delete(id);
          }
        });

        socket.on('error', (error) => {
          console.error('[FigmaWS] Socket error:', error);
        });
      });
    });
  }

  /** Stop the WebSocket server */
  stop(): Promise<void> {
    this.stopHeartbeat();
    return new Promise((resolve) => {
      if (this.pluginSocket) {
        this.pluginSocket.close();
        this.pluginSocket = null;
      }
      if (this.wss) {
        this.wss.close(() => {
          this.wss = null;
          resolve();
        });
      } else {
        resolve();
      }
    });
  }

  /** Check if plugin is connected */
  get isConnected(): boolean {
    return this.pluginSocket !== null && this.pluginSocket.readyState === WebSocket.OPEN;
  }

  /** Get current channel */
  get channel(): string | null {
    return this.currentChannel;
  }

  get inputMode(): InputMode {
    return this.currentInputMode;
  }

  /** Join a Figma document channel */
  async joinChannel(channelName: string): Promise<void> {
    await this.sendCommand('join', { channel: channelName });
    this.currentChannel = channelName;
    console.log(`[FigmaWS] Joined channel: ${channelName}`);
  }

  /** Send a command to the Figma plugin and wait for response */
  sendCommand(
    command: FigmaCommand,
    params: Record<string, unknown> = {},
    timeoutMs: number = 120000
  ): Promise<unknown> {
    return new Promise((resolve, reject) => {
      if (!this.pluginSocket || this.pluginSocket.readyState !== WebSocket.OPEN) {
        reject(new Error('Not connected to Figma plugin'));
        return;
      }

      if (command !== 'join' && !this.currentChannel) {
        reject(new Error('Must join a channel before sending commands'));
        return;
      }

      const id = uuidv4();
      const request = {
        id,
        type: command === 'join' ? 'join' : 'message',
        ...(command === 'join'
          ? { channel: (params as Record<string, unknown>).channel }
          : { channel: this.currentChannel }),
        message: {
          id,
          command,
          params: {
            ...params,
            commandId: id,
          },
        },
      };

      const timeout = setTimeout(() => {
        if (this.pendingRequests.has(id)) {
          this.pendingRequests.delete(id);
          reject(new Error(`Request timed out after ${timeoutMs / 1000}s`));
        }
      }, timeoutMs);

      this.pendingRequests.set(id, {
        resolve,
        reject,
        timeout,
        lastActivity: Date.now(),
      });

      this.pluginSocket.send(JSON.stringify(request));
    });
  }

  /** Handle incoming message from plugin */
  private handleMessage(rawData: string): void {
    try {
      const json = JSON.parse(rawData);

      // Handle ping (heartbeat from plugin) — respond with pong
      if (json.type === 'ping') {
        if (this.pluginSocket && this.pluginSocket.readyState === WebSocket.OPEN) {
          this.pluginSocket.send(JSON.stringify({ type: 'pong' }));
        }
        return;
      }

      // Handle server_pong (response to our server_ping heartbeat)
      if (json.type === 'server_pong') {
        this.lastPongTime = Date.now();
        return;
      }

      // Handle join from plugin (auto-connect flow)
      if (json.type === 'join') {
        const channel = json.channel as string;
        this.currentChannel = channel;
        const documentName = (json.documentName as string) || channel.replace('auto-', '');
        console.log(`[FigmaWS] Plugin joined channel: ${channel} (document: ${documentName})`);

        // Send acknowledgment (format the plugin expects)
        if (this.pluginSocket && this.pluginSocket.readyState === WebSocket.OPEN) {
          this.pluginSocket.send(JSON.stringify({
            type: 'system',
            channel: channel,
            message: { result: true },
          }));
        }

        this.emit('connection-change', {
          status: 'connected',
          channel,
          documentName,
          inputMode: this.currentInputMode,
        } satisfies FigmaConnectionState);

        return;
      }

      // Handle input mode change from plugin
      if (json.type === 'set-input-mode') {
        const mode = json.mode as string;
        if (mode === 'terminal' || mode === 'app') {
          this.currentInputMode = mode;
          console.log(`[FigmaWS] Input mode changed to: ${mode}`);
          this.emit('input-mode-change', mode);
        }
        return;
      }

      // Handle progress updates
      if (json.type === 'progress_update') {
        const requestId = json.id || '';
        if (requestId && this.pendingRequests.has(requestId)) {
          const request = this.pendingRequests.get(requestId)!;
          request.lastActivity = Date.now();

          // Reset timeout
          clearTimeout(request.timeout);
          request.timeout = setTimeout(() => {
            if (this.pendingRequests.has(requestId)) {
              this.pendingRequests.delete(requestId);
              request.reject(new Error('Request timed out after inactivity'));
            }
          }, 120000);
        }
        this.emit('plugin-message', json);
        return;
      }

      // Handle regular responses
      const response = json.message;
      if (
        response?.id &&
        this.pendingRequests.has(response.id) &&
        ('result' in response || 'error' in response)
      ) {
        const request = this.pendingRequests.get(response.id)!;
        clearTimeout(request.timeout);

        if (response.error) {
          request.reject(new Error(response.error));
        } else {
          request.resolve(response.result ?? null);
        }
        this.pendingRequests.delete(response.id);
      } else {
        this.emit('plugin-message', json);
      }
    } catch (error) {
      console.error('[FigmaWS] Parse error:', error);
    }
  }

  // ── Server-side heartbeat (25s interval) ──

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.lastPongTime = Date.now();
    this.heartbeatTimer = setInterval(() => {
      if (this.pluginSocket && this.pluginSocket.readyState === WebSocket.OPEN) {
        this.pluginSocket.send(JSON.stringify({ type: 'server_ping', ts: Date.now() }));
      }
    }, 25_000);
    console.log('[FigmaWS] Heartbeat started (25s interval)');
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  /** Full round-trip health check via Figma plugin (5s timeout) */
  async checkHealth(): Promise<boolean> {
    if (!this.isConnected) return false;
    try {
      const result = await this.sendCommand('ping_check', {}, 5_000) as Record<string, unknown>;
      return result?.ok === true;
    } catch {
      return false;
    }
  }

  /** Send a one-way notification to the plugin UI (no response expected) */
  sendNotification(notificationType: string, data: Record<string, unknown>): void {
    if (!this.pluginSocket || this.pluginSocket.readyState !== WebSocket.OPEN) return;
    this.pluginSocket.send(JSON.stringify({
      type: 'notification',
      channel: this.currentChannel,
      message: { type: notificationType, ...data },
    }));
  }

  private emitConnectionState(status: FigmaConnectionState['status']): void {
    this.emit('connection-change', {
      status,
      channel: this.currentChannel,
    } satisfies FigmaConnectionState);
  }
}
