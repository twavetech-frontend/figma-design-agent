import { useState, useEffect, useCallback, useRef } from 'react';
import type { ChatMessage, AgentState, FigmaConnectionState, AgentEvent, ClaudeCodeStatus, DSCacheStatus, PipelineStepEvent, AttachmentData } from '../../shared/types';

// Access the preload-exposed API
declare global {
  interface Window {
    electronAPI: {
      sendMessage: (message: string, attachments?: AttachmentData[]) => void;
      cancelAgent: () => void;
      onAgentEvent: (callback: (event: AgentEvent) => void) => () => void;
      onChatUpdate: (callback: (message: ChatMessage) => void) => () => void;
      joinChannel: (channel: string) => Promise<{ success: boolean; error?: string }>;
      getFigmaStatus: () => Promise<FigmaConnectionState>;
      onFigmaStatus: (callback: (status: FigmaConnectionState) => void) => () => void;
      getDesignTokens: () => Promise<unknown>;
      // Claude Code (primary)
      getClaudeCodeStatus: () => Promise<ClaudeCodeStatus>;
      claudeCodeLogin: () => Promise<{ success: boolean; error?: string }>;
      // Claude API (legacy fallback)
      getClaudeApiStatus: () => Promise<{ hasKey: boolean; maskedKey: string }>;
      setClaudeApiKey: (key: string) => Promise<{ success: boolean; error?: string }>;
      validateClaudeApiKey: (key: string) => Promise<{ valid: boolean; error?: string }>;
      openExternal: (url: string) => void;
      onDSCacheStatus: (callback: (status: DSCacheStatus) => void) => () => void;
      onPipelineStep: (callback: (event: PipelineStepEvent) => void) => () => void;
      onError: (callback: (error: string) => void) => () => void;
    };
  }
}

export function useAgent() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [agentState, setAgentState] = useState<AgentState | null>(null);
  const [figmaStatus, setFigmaStatus] = useState<FigmaConnectionState>({
    status: 'disconnected',
    channel: null,
  });
  const [error, setError] = useState<string | null>(null);
  const [taskTiming, setTaskTiming] = useState<{ startedAt: number | null; endedAt: number | null }>({ startedAt: null, endedAt: null });
  const [dsCacheStatus, setDSCacheStatus] = useState<DSCacheStatus>({
    status: 'idle', total: 0, cached: 0, failed: 0,
  });
  const [pipelineSteps, setPipelineSteps] = useState<PipelineStepEvent[]>([]);

  // Set up event listeners
  useEffect(() => {
    const api = window.electronAPI;
    if (!api) return;

    const cleanups: Array<() => void> = [];

    // Chat messages
    cleanups.push(api.onChatUpdate((message) => {
      setMessages((prev) => [...prev, message as ChatMessage]);
    }));

    // Agent events
    cleanups.push(api.onAgentEvent((event) => {
      const e = event as AgentEvent;
      if (e.type === 'status') {
        setAgentState((prev) => prev ? { ...prev, ...(e.data as Partial<AgentState>) } : null);
      } else if (e.type === 'streaming') {
        const data = e.data as { text?: string };
        if (data.text) {
          setAgentState((prev) => prev ? { ...prev, status: 'streaming', streamingText: data.text } : {
            id: e.agentId,
            role: 'orchestrator',
            status: 'streaming',
            progress: 50,
            streamingText: data.text,
          });
        }
      } else if (e.type === 'tool-call') {
        const data = e.data as { name: string };
        setAgentState((prev) => prev ? { ...prev, status: 'running', currentAction: `Calling ${data.name}...` } : null);
      } else if (e.type === 'done') {
        setAgentState((prev) => prev ? { ...prev, status: 'done', progress: 100 } : null);
        setTaskTiming((prev) => ({ ...prev, endedAt: Date.now() }));
      } else if (e.type === 'error') {
        const data = e.data as { error?: string };
        setAgentState((prev) => prev ? { ...prev, status: 'error' } : null);
        setTaskTiming((prev) => ({ ...prev, endedAt: Date.now() }));
        if (data.error) setError(data.error);
      }
    }));

    // Figma status
    cleanups.push(api.onFigmaStatus((status) => {
      setFigmaStatus(status as FigmaConnectionState);
    }));

    // DS cache status
    cleanups.push(api.onDSCacheStatus((status) => {
      setDSCacheStatus(status);
    }));

    // Pipeline step events
    cleanups.push(api.onPipelineStep((event) => {
      setPipelineSteps((prev) => {
        const existing = prev.findIndex((s) => s.name === event.name);
        if (existing >= 0) {
          const updated = [...prev];
          updated[existing] = event;
          return updated;
        }
        return [...prev, event];
      });
    }));

    // Errors
    cleanups.push(api.onError((err) => {
      setError(err);
    }));

    // Get initial Figma status
    api.getFigmaStatus().then((status) => {
      setFigmaStatus(status as FigmaConnectionState);
    });

    return () => {
      for (const cleanup of cleanups) cleanup();
    };
  }, []);

  const sendMessage = useCallback((message: string, attachments?: AttachmentData[]) => {
    window.electronAPI?.sendMessage(message, attachments);

    // Record start time and reset end time
    setTaskTiming({ startedAt: Date.now(), endedAt: null });
    // Reset pipeline steps
    setPipelineSteps([]);

    // Optimistically set agent state
    setAgentState({
      id: 'orchestrator',
      role: 'orchestrator',
      status: 'running',
      progress: 0,
      currentAction: 'Processing...',
    });
  }, []);

  const cancelAgent = useCallback(() => {
    window.electronAPI?.cancelAgent();
    setAgentState((prev) => prev ? { ...prev, status: 'done' } : null);
  }, []);

  const joinChannel = useCallback(async (channel: string) => {
    const result = await window.electronAPI?.joinChannel(channel);
    if (result?.success) {
      setFigmaStatus((prev) => ({ ...prev, status: 'connected', channel }));
    }
    return result;
  }, []);

  return {
    messages,
    agentState,
    figmaStatus,
    dsCacheStatus,
    pipelineSteps,
    error,
    taskTiming,
    sendMessage,
    cancelAgent,
    joinChannel,
  };
}
