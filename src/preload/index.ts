/**
 * Preload Script — Electron context bridge
 *
 * Exposes safe IPC methods to the renderer process.
 */

import { contextBridge, ipcRenderer } from 'electron';
import { IPC_CHANNELS } from '../shared/types';
import type { ClaudeCodeStatus, DSCacheStatus, PipelineStepEvent, AttachmentData } from '../shared/types';

export interface ElectronAPI {
  // Agent
  sendMessage: (message: string, attachments?: AttachmentData[]) => void;
  cancelAgent: () => void;
  onAgentEvent: (callback: (event: unknown) => void) => () => void;
  onChatUpdate: (callback: (message: unknown) => void) => () => void;

  // Figma
  joinChannel: (channel: string) => Promise<unknown>;
  getFigmaStatus: () => Promise<unknown>;
  onFigmaStatus: (callback: (status: unknown) => void) => () => void;

  // DS
  getDesignTokens: () => Promise<unknown>;

  // Claude Code (primary)
  getClaudeCodeStatus: () => Promise<ClaudeCodeStatus>;
  claudeCodeLogin: () => Promise<{ success: boolean; error?: string }>;

  // Claude API (legacy fallback)
  getClaudeApiStatus: () => Promise<{ hasKey: boolean; maskedKey: string }>;
  setClaudeApiKey: (key: string) => Promise<{ success: boolean; error?: string }>;
  validateClaudeApiKey: (key: string) => Promise<{ valid: boolean; error?: string }>;

  openExternal: (url: string) => void;

  // DS Cache
  onDSCacheStatus: (callback: (status: DSCacheStatus) => void) => () => void;

  // Pipeline
  onPipelineStep: (callback: (event: PipelineStepEvent) => void) => () => void;

  // App
  onError: (callback: (error: string) => void) => () => void;
  onInputModeChange: (callback: (mode: string) => void) => () => void;
}

contextBridge.exposeInMainWorld('electronAPI', {
  // Agent
  sendMessage: (message: string, attachments?: AttachmentData[]) => {
    ipcRenderer.send(IPC_CHANNELS.AGENT_SEND_MESSAGE, { message, attachments });
  },
  cancelAgent: () => {
    ipcRenderer.send(IPC_CHANNELS.AGENT_CANCEL);
  },
  onAgentEvent: (callback: (event: unknown) => void) => {
    const handler = (_: unknown, event: unknown) => callback(event);
    ipcRenderer.on(IPC_CHANNELS.AGENT_EVENT, handler);
    return () => ipcRenderer.removeListener(IPC_CHANNELS.AGENT_EVENT, handler);
  },
  onChatUpdate: (callback: (message: unknown) => void) => {
    const handler = (_: unknown, message: unknown) => callback(message);
    ipcRenderer.on(IPC_CHANNELS.AGENT_CHAT_UPDATE, handler);
    return () => ipcRenderer.removeListener(IPC_CHANNELS.AGENT_CHAT_UPDATE, handler);
  },

  // Figma
  joinChannel: (channel: string) => {
    return ipcRenderer.invoke(IPC_CHANNELS.FIGMA_JOIN_CHANNEL, channel);
  },
  getFigmaStatus: () => {
    return ipcRenderer.invoke(IPC_CHANNELS.FIGMA_GET_STATUS);
  },
  onFigmaStatus: (callback: (status: unknown) => void) => {
    const handler = (_: unknown, status: unknown) => callback(status);
    ipcRenderer.on(IPC_CHANNELS.FIGMA_STATUS, handler);
    return () => ipcRenderer.removeListener(IPC_CHANNELS.FIGMA_STATUS, handler);
  },

  // DS
  getDesignTokens: () => {
    return ipcRenderer.invoke(IPC_CHANNELS.DS_GET_TOKENS);
  },

  // Claude Code
  getClaudeCodeStatus: () => {
    return ipcRenderer.invoke(IPC_CHANNELS.CLAUDE_CODE_STATUS);
  },
  claudeCodeLogin: () => {
    return ipcRenderer.invoke(IPC_CHANNELS.CLAUDE_CODE_LOGIN);
  },

  // Claude API (legacy)
  getClaudeApiStatus: () => {
    return ipcRenderer.invoke(IPC_CHANNELS.CLAUDE_API_STATUS);
  },
  setClaudeApiKey: (key: string) => {
    return ipcRenderer.invoke(IPC_CHANNELS.CLAUDE_API_SET_KEY, key);
  },
  validateClaudeApiKey: (key: string) => {
    return ipcRenderer.invoke(IPC_CHANNELS.CLAUDE_API_VALIDATE, key);
  },
  openExternal: (url: string) => {
    ipcRenderer.send('shell:open-external', url);
  },

  // DS Cache
  onDSCacheStatus: (callback: (status: DSCacheStatus) => void) => {
    const handler = (_: unknown, status: DSCacheStatus) => callback(status);
    ipcRenderer.on(IPC_CHANNELS.DS_CACHE_STATUS, handler);
    return () => { ipcRenderer.removeListener(IPC_CHANNELS.DS_CACHE_STATUS, handler); };
  },

  // Pipeline
  onPipelineStep: (callback: (event: PipelineStepEvent) => void) => {
    const handler = (_: unknown, event: PipelineStepEvent) => callback(event);
    ipcRenderer.on(IPC_CHANNELS.PIPELINE_STEP, handler);
    return () => { ipcRenderer.removeListener(IPC_CHANNELS.PIPELINE_STEP, handler); };
  },

  // App
  onError: (callback: (error: string) => void) => {
    const handler = (_: unknown, error: string) => callback(error);
    ipcRenderer.on(IPC_CHANNELS.APP_ERROR, handler);
    return () => ipcRenderer.removeListener(IPC_CHANNELS.APP_ERROR, handler);
  },
  onInputModeChange: (callback: (mode: string) => void) => {
    const handler = (_: unknown, mode: string) => callback(mode);
    ipcRenderer.on(IPC_CHANNELS.FIGMA_INPUT_MODE, handler);
    return () => { ipcRenderer.removeListener(IPC_CHANNELS.FIGMA_INPUT_MODE, handler); };
  },
} satisfies ElectronAPI);
