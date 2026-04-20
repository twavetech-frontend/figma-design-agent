/**
 * Agent Orchestrator — Claude Agent SDK Edition
 *
 * Uses @anthropic-ai/claude-agent-sdk query() for agent execution.
 * Claude Code subprocess handles tool calls via MCP server.
 * Supports dual mode: Agent SDK (Claude Code auth) or direct API key fallback.
 *
 * Performance optimizations:
 * - Uses Claude Code preset prompt + short design append (not full system prompt)
 * - Keeps Claude Code process alive via AsyncIterable prompt for multi-turn
 * - Deduplicates assistant messages (stream vs result)
 */

import { EventEmitter } from 'events';
import { v4 as uuidv4 } from 'uuid';
import { buildSystemPrompt, buildDesignContext, type PromptContext } from './system-prompt-builder';
import { getMcpServersConfig } from './mcp-server-config';
import { PipelineOrchestrator } from './pipeline/pipeline-orchestrator';
import type { PipelineStepState } from './pipeline/types';
import type { AgentState, AgentEvent, ChatMessage, ToolDefinition, AttachmentData } from '../shared/types';
import { processAttachmentText } from './rtf-stripper';

const MAX_TURNS = 40;
const TURN_WARNING_THRESHOLD = 30; // Inject "wrap up" warning at this turn

// Tool call timeout/retry configuration
// Outermost layer: must be > MCP HTTP timeout (tool.timeoutMs) to receive errors properly
const DEFAULT_TOOL_TIMEOUT_MS = 65_000; // 65초 (MCP default 60s + 5s margin)
const MAX_TOOL_RETRIES = 2; // 최대 2회 재시도 (총 3회 시도)
// Per-tool timeout overrides (outermost layer, > MCP HTTP tool.timeoutMs)
const TOOL_TIMEOUT_MAP: Record<string, number> = {
  batch_build_screen: 330_000,       // MCP 310s + 20s margin
  batch_bind_variables: 330_000,
  batch_set_text_style_id: 330_000,
  pre_cache_components: 650_000,     // MCP 620s + 30s margin
};

export interface OrchestratorConfig {
  tools: Map<string, ToolDefinition>;
  projectRoot: string;
  /** If true, use Agent SDK (Claude Code auth). If false, use direct API key. */
  useAgentSdk: boolean;
  /** API key for direct mode fallback */
  apiKey?: string;
  /** Figma WebSocket 서버 인스턴스 (파이프라인용) */
  figmaWS?: { sendCommand: (command: string, params?: Record<string, unknown>, timeout?: number) => Promise<unknown> };
  /** 이미지 생성기 (파이프라인용) */
  imageGenerator?: {
    generate: (request: {
      prompt: string;
      figmaWidth: number;
      figmaHeight: number;
      style?: string;
      isHero?: boolean;
      outputName: string;
    }) => Promise<{ base64: string; width: number; height: number }>;
  };
}

export class AgentOrchestrator extends EventEmitter {
  private tools: Map<string, ToolDefinition>;
  private projectRoot: string;
  private useAgentSdk: boolean;
  private apiKey?: string;
  private systemPrompt: string = '';
  private designContext: string = '';
  private abortController: AbortController | null = null;
  private agents = new Map<string, AgentState>();

  // Agent SDK session
  private sdkSessionId: string | null = null;

  // Direct API mode client (lazy loaded)
  private directClient: import('@anthropic-ai/sdk').default | null = null;
  private conversationHistory: import('@anthropic-ai/sdk').MessageParam[] = [];

  // Busy lock to prevent concurrent sendMessage calls
  private busy = false;

  // Pipeline mode
  private pipeline: PipelineOrchestrator | null = null;

  constructor(config: OrchestratorConfig) {
    super();
    this.tools = config.tools;
    this.projectRoot = config.projectRoot;
    this.useAgentSdk = config.useAgentSdk;
    this.apiKey = config.apiKey;

    // 파이프라인 초기화 (Direct API 모드 + figmaWS 제공 시)
    if (!config.useAgentSdk && config.apiKey && config.figmaWS && config.imageGenerator) {
      this.pipeline = new PipelineOrchestrator({
        tools: config.tools,
        projectRoot: config.projectRoot,
        apiKey: config.apiKey,
        figmaWS: config.figmaWS,
        imageGenerator: config.imageGenerator,
      });

      // 파이프라인 이벤트 전달
      this.pipeline.on('pipeline:step', (step: PipelineStepState) => {
        this.emit('pipeline:step', step);
      });

      this.pipeline.on('streaming', (data: { step: string; text: string }) => {
        this.emitEvent('orchestrator', 'streaming', { text: data.text });
      });
    }
  }

  /** Initialize system prompt with current context */
  async initialize(context: Partial<PromptContext> = {}): Promise<void> {
    // Full system prompt for direct API mode
    this.systemPrompt = await buildSystemPrompt(
      { tools: this.tools, ...context },
      this.projectRoot
    );
    // Short design context for Agent SDK mode (appended to Claude Code preset)
    this.designContext = await buildDesignContext(this.projectRoot, context);
    this.conversationHistory = [];

    // ★ Critical: Pipeline도 반드시 초기화 (시스템 프롬프트 전달)
    if (this.pipeline) {
      await this.pipeline.initialize({ tools: this.tools, ...context });
      console.log('[Agent] Pipeline initialized with system prompt');
    }
  }

  /** Send a user message and run the agent loop */
  async sendMessage(userMessage: string, attachments?: AttachmentData[]): Promise<void> {
    // Prevent concurrent calls — if already busy, reject
    if (this.busy) {
      console.warn('[Agent] sendMessage called while busy — ignoring');
      this.emitEvent('orchestrator', 'error', { error: '이전 요청이 아직 처리 중입니다.' });
      return;
    }

    this.busy = true;
    this.abortController = new AbortController();

    // Emit user message (with attachments for display)
    this.emitChatMessage({
      id: uuidv4(),
      role: 'user',
      content: userMessage,
      timestamp: Date.now(),
      attachments,
    });

    try {
      if (this.useAgentSdk) {
        await this.sendAgentSdkMessage(userMessage, attachments);
      } else if (this.pipeline) {
        await this.runPipelineMode(userMessage, attachments);
      } else {
        await this.runDirectApiLoop(userMessage, attachments);
      }
    } finally {
      this.busy = false;
    }
  }

  /** Convert attachments to Claude API content blocks */
  private buildAttachmentContentBlocks(attachments: AttachmentData[]): Array<Record<string, unknown>> {
    const blocks: Array<Record<string, unknown>> = [];
    for (const att of attachments) {
      if (att.type === 'image') {
        blocks.push({
          type: 'image',
          source: {
            type: 'base64',
            media_type: att.mediaType,
            data: att.base64,
          },
        });
      } else if (att.textContent) {
        const cleanText = processAttachmentText(att.textContent, att.name);
        blocks.push({
          type: 'text',
          text: `--- 첨부 문서: ${att.name} ---\n\n아래는 첨부 문서의 전체 내용입니다. 이 문서의 요구사항을 빠짐없이 분석하여 디자인에 반영하세요.\n\n${cleanText}`,
        });
      }
    }
    return blocks;
  }

  // ============================================================
  // Agent SDK Mode — Persistent Session
  // ============================================================

  /**
   * Send a message via Agent SDK.
   * Each call creates a new query() but uses `resume` to continue the session.
   */
  private async sendAgentSdkMessage(userMessage: string, attachments?: AttachmentData[]): Promise<void> {
    const agentId = 'orchestrator';
    this.updateAgentState(agentId, { status: 'streaming', currentAction: 'Thinking...' });

    try {
      const { query } = await import('@anthropic-ai/claude-agent-sdk');
      const mcpServers = getMcpServersConfig();

      // Clean env: remove CLAUDECODE to avoid nested session detection
      const cleanEnv: Record<string, string | undefined> = { ...process.env };
      delete cleanEnv.CLAUDECODE;

      const options: Record<string, unknown> = {
        model: 'claude-sonnet-4-20250514',
        systemPrompt: {
          type: 'preset',
          preset: 'claude_code',
          append: this.designContext,
        },
        mcpServers,
        maxTurns: MAX_TURNS,
        permissionMode: 'bypassPermissions',
        allowDangerouslySkipPermissions: true,
        allowedTools: ['mcp__figma-tools__*'],
        disallowedTools: [
          // Block ALL Claude Code built-in tools (this is a design-only agent)
          // These tools don't work in the Electron app context and cause hangs
          'Edit', 'Write', 'Bash', 'Read', 'Glob', 'Grep', 'Agent',
          'Skill', 'EnterPlanMode', 'ExitPlanMode', 'AskUserQuestion',
          'WebSearch', 'WebFetch', 'NotebookEdit', 'EnterWorktree',
          'TaskCreate', 'TaskUpdate', 'TaskList', 'TaskGet',
          // Block individual creation tools — MUST use batch_build_screen instead
          'mcp__figma-tools__create_frame',
          'mcp__figma-tools__create_text',
          'mcp__figma-tools__create_rectangle',
          'mcp__figma-tools__create_shape',
          'mcp__figma-tools__create_component_from_node',
          'mcp__figma-tools__create_component_set',

        ],
        includePartialMessages: true,
        abortController: this.abortController,
        cwd: this.projectRoot,
        env: cleanEnv,
        stderr: (data: string) => {
          if (!data.includes('Compiling') && !data.includes('Watching')) {
            console.log('[Claude Code]', data.trim());
          }
        },
      };

      // Resume previous session if available
      if (this.sdkSessionId) {
        options.resume = this.sdkSessionId;
        console.log('[Agent SDK] Resuming session:', this.sdkSessionId);
      } else {
        console.log('[Agent SDK] Starting new session');
      }

      // Agent SDK only accepts text prompts; embed document attachments inline
      let effectivePrompt = userMessage;
      if (attachments && attachments.length > 0) {
        const docParts = attachments
          .filter((a) => a.type === 'document' && a.textContent)
          .map((a) => {
            const cleanText = processAttachmentText(a.textContent!, a.name);
            return `--- 첨부 문서: ${a.name} ---\n\n아래는 첨부 문서의 전체 내용입니다. 이 문서의 요구사항을 빠짐없이 분석하여 디자인에 반영하세요.\n\n${cleanText}`;
          });
        if (docParts.length > 0) {
          effectivePrompt = `${userMessage}\n\n${docParts.join('\n\n')}`;
        }
        // Note: Agent SDK doesn't support image content blocks directly
        // Images will be described in the prompt text if needed
        const imageNames = attachments.filter((a) => a.type === 'image').map((a) => a.name);
        if (imageNames.length > 0) {
          effectivePrompt += `\n\n[첨부 이미지: ${imageNames.join(', ')}] (Agent SDK 모드에서는 이미지를 직접 볼 수 없습니다. Direct API 모드에서 이미지 첨부를 사용해주세요.)`;
        }
      }

      const q = query({ prompt: effectivePrompt, options: options as never });
      await this.processSdkMessages(q, agentId);

    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error);
      console.error('[Agent SDK] Error:', errorMsg);
      this.updateAgentState(agentId, { status: 'error' });
      this.emitEvent(agentId, 'error', { error: errorMsg });
    }
  }

  private async processSdkMessages(q: AsyncIterable<unknown>, agentId: string): Promise<void> {
    let assistantText = '';
    let lastEmittedText = '';

    try {
      for await (const message of q as AsyncIterable<{ type: string; [key: string]: unknown }>) {
        if (this.abortController?.signal.aborted) break;

        switch (message.type) {
          case 'system': {
            const sysMsg = message as { session_id?: string };
            if (sysMsg.session_id) {
              this.sdkSessionId = sysMsg.session_id;
              console.log('[Agent SDK] Session:', this.sdkSessionId);
            }
            break;
          }

          case 'stream_event': {
            const streamMsg = message as { event?: { type: string; delta?: { type: string; text?: string }; content_block?: { type: string; name?: string } } };
            const event = streamMsg.event;
            if (!event) break;

            if (event.type === 'content_block_start' && event.content_block?.type === 'tool_use') {
              const toolName = event.content_block.name || '';
              if (toolName) {
                // Strip MCP prefix for display
                const displayName = toolName.replace('mcp__figma-tools__', '');
                this.updateAgentState(agentId, {
                  status: 'running',
                  currentAction: `Calling ${displayName}...`,
                });
                this.emitEvent(agentId, 'tool-call', { name: displayName });
              }
            } else if (event.type === 'content_block_delta' && event.delta?.type === 'text_delta' && event.delta.text) {
              assistantText += event.delta.text;
              this.emitEvent(agentId, 'streaming', { text: assistantText });
            } else if (event.type === 'content_block_stop') {
              // Nothing needed
            }
            break;
          }

          case 'assistant': {
            const assistMsg = message as { message?: { content?: Array<{ type: string; text?: string; name?: string; input?: unknown }> } };
            const content = assistMsg.message?.content;
            if (!content) break;

            const textParts: string[] = [];
            for (const block of content) {
              if (block.type === 'text' && block.text) {
                textParts.push(block.text);
              } else if (block.type === 'tool_use') {
                const displayName = (block.name || '').replace('mcp__figma-tools__', '');
                this.emitEvent(agentId, 'tool-call', { name: displayName, input: block.input });
              }
            }

            const fullText = textParts.join('');
            if (fullText && fullText !== lastEmittedText) {
              lastEmittedText = fullText;
              assistantText = ''; // Reset streaming buffer
              this.emitChatMessage({
                id: uuidv4(),
                role: 'assistant',
                content: fullText,
                timestamp: Date.now(),
                agentId,
              });
            }
            break;
          }

          case 'result': {
            const resultMsg = message as { subtype?: string; result?: string; errors?: string[] };
            if (resultMsg.subtype === 'success') {
              // Only emit if different from what we already sent
              if (resultMsg.result && resultMsg.result !== lastEmittedText) {
                this.emitChatMessage({
                  id: uuidv4(),
                  role: 'assistant',
                  content: resultMsg.result,
                  timestamp: Date.now(),
                  agentId,
                });
                lastEmittedText = resultMsg.result;
              }
              this.updateAgentState(agentId, { status: 'done', progress: 100 });
              this.emitEvent(agentId, 'done', { text: resultMsg.result });
              // Reset for next turn
              assistantText = '';
              lastEmittedText = '';
            } else {
              const errorText = resultMsg.errors?.join(', ') || 'Unknown error';
              this.updateAgentState(agentId, { status: 'error' });
              this.emitEvent(agentId, 'error', { error: errorText });
              assistantText = '';
              lastEmittedText = '';
            }
            break;
          }
        }
      }
    } catch (error) {
      const errorMsg = error instanceof Error ? error.message : String(error);
      if (!errorMsg.includes('aborted')) {
        console.error('[Agent SDK] Processing loop error:', errorMsg);
        this.updateAgentState(agentId, { status: 'error' });
        this.emitEvent(agentId, 'error', { error: errorMsg });
      }
    }
  }

  // ============================================================
  // Pipeline Mode (결정론적 7단계)
  // ============================================================

  private async runPipelineMode(userMessage: string, attachments?: AttachmentData[]): Promise<void> {
    const agentId = 'orchestrator';

    if (!this.pipeline) {
      throw new Error('Pipeline not initialized');
    }

    // 수정 모드: 이전 빌드가 있으면 패치만 적용
    if (this.pipeline.hasPreviousBuild) {
      this.updateAgentState(agentId, { status: 'running', currentAction: '수정 패치 생성 중...' });
      try {
        const modResult = await this.pipeline.sendModification(
          userMessage,
          this.abortController?.signal,
        );
        this.emitChatMessage({
          id: uuidv4(),
          role: 'assistant',
          content: `수정 완료: ${modResult.summary}\n(${modResult.appliedCount}개 적용, ${modResult.failedCount}개 실패)`,
          timestamp: Date.now(),
          agentId,
        });
        this.updateAgentState(agentId, { status: 'done', progress: 100 });
        this.emitEvent(agentId, 'done', { text: modResult.summary });
        return;
      } catch (error) {
        // 수정 실패 시 전체 파이프라인 재실행
        console.warn('[Pipeline] Modification failed, falling back to full pipeline:', error);
        this.pipeline.clearBuildState();
      }
    }

    // 전체 파이프라인 실행
    this.updateAgentState(agentId, { status: 'running', currentAction: '파이프라인 시작...' });

    const result = await this.pipeline.runPipeline(
      userMessage,
      this.abortController?.signal,
      attachments,
    );

    if (result.success) {
      const durationSec = (result.totalDuration / 1000).toFixed(1);
      const stepSummary = Object.entries(result.stepDurations)
        .filter(([, dur]) => dur > 0)
        .map(([name, dur]) => `${name}: ${(dur / 1000).toFixed(1)}s`)
        .join(', ');

      this.emitChatMessage({
        id: uuidv4(),
        role: 'assistant',
        content: `디자인 완료! (${durationSec}초)\n\n단계별 소요 시간: ${stepSummary}\n\nQA: ${result.qaResult?.summary || 'N/A'}\n\n수정이 필요하면 말씀해주세요.`,
        timestamp: Date.now(),
        agentId,
      });
      this.updateAgentState(agentId, { status: 'done', progress: 100 });
      this.emitEvent(agentId, 'done', { text: 'Pipeline complete' });
    } else {
      this.emitChatMessage({
        id: uuidv4(),
        role: 'assistant',
        content: `파이프라인 오류: ${result.error}`,
        timestamp: Date.now(),
        agentId,
      });
      this.updateAgentState(agentId, { status: 'error' });
      this.emitEvent(agentId, 'error', { error: result.error });
    }
  }

  // ============================================================
  // Direct API Mode (API key fallback — legacy agent loop)
  // ============================================================

  /**
   * Sanitize conversation history to ensure valid API message structure.
   * Fixes orphaned assistant messages with tool_use blocks that lack matching tool_results.
   */
  private sanitizeHistory(): void {
    if (this.conversationHistory.length === 0) return;

    const last = this.conversationHistory[this.conversationHistory.length - 1];

    // If the last message is an assistant message with tool_use blocks,
    // there are no matching tool_results — remove it to prevent API errors.
    if (last.role === 'assistant' && Array.isArray(last.content)) {
      const content = last.content as Array<{ type: string }>;
      const hasToolUse = content.some((b) => b.type === 'tool_use');
      if (hasToolUse) {
        console.warn('[Agent] Removing orphaned assistant message with pending tool_use blocks');
        this.conversationHistory.pop();
      }
    }

    // Ensure messages alternate between user and assistant.
    // Remove consecutive same-role messages (keep the last one of each run).
    const cleaned: typeof this.conversationHistory = [];
    for (const msg of this.conversationHistory) {
      if (cleaned.length > 0 && cleaned[cleaned.length - 1].role === msg.role) {
        // Merge consecutive user messages by combining content
        if (msg.role === 'user') {
          const prev = cleaned[cleaned.length - 1];
          const prevContent = Array.isArray(prev.content) ? prev.content : [{ type: 'text', text: prev.content }];
          const currContent = Array.isArray(msg.content) ? msg.content : [{ type: 'text', text: msg.content }];
          cleaned[cleaned.length - 1] = { role: 'user', content: [...prevContent, ...currContent] } as typeof msg;
        } else {
          // For consecutive assistant messages, keep the latest
          cleaned[cleaned.length - 1] = msg;
        }
      } else {
        cleaned.push(msg);
      }
    }
    this.conversationHistory = cleaned;
  }

  private async runDirectApiLoop(userMessage: string, attachments?: AttachmentData[]): Promise<void> {
    const agentId = 'orchestrator';

    // Lazy-init client
    if (!this.directClient) {
      const Anthropic = (await import('@anthropic-ai/sdk')).default;
      const key = this.apiKey || '';
      // OAuth Access Token (sk-ant-oat...)은 authToken으로, 일반 API 키는 apiKey로 전달
      if (key.includes('-oat')) {
        this.directClient = new Anthropic({ authToken: key });
      } else {
        this.directClient = new Anthropic({ apiKey: key });
      }
    }

    // Sanitize history from any previous corrupted state before adding new message
    this.sanitizeHistory();

    // Add user message to history (with attachment content blocks if present)
    if (attachments && attachments.length > 0) {
      const contentBlocks: Array<Record<string, unknown>> = [
        { type: 'text', text: userMessage },
        ...this.buildAttachmentContentBlocks(attachments),
      ];
      this.conversationHistory.push({ role: 'user', content: contentBlocks as never });
    } else {
      this.conversationHistory.push({ role: 'user', content: userMessage });
    }

    let turns = 0;
    let screenshotTaken = false; // Track if export_node_as_image was called
    let batchBuildDone = false; // Track if batch_build_screen was called
    while (turns < MAX_TURNS) {
      turns++;

      if (this.abortController?.signal.aborted) {
        this.emitEvent(agentId, 'done', { reason: 'cancelled' });
        return;
      }

      // Strip base64 image blocks from PREVIOUS turns to prevent context overflow.
      // Only the most recent user message (last in history) may keep image blocks
      // so Claude can see the latest screenshot. Older images are replaced with text.
      for (let i = 0; i < this.conversationHistory.length - 1; i++) {
        const msg = this.conversationHistory[i];
        if (msg.role === 'user' && Array.isArray(msg.content)) {
          const content = msg.content as Array<Record<string, unknown>>;
          let changed = false;
          const cleaned = content.map((block) => {
            if (block.type === 'tool_result' && Array.isArray(block.content)) {
              const inner = block.content as Array<Record<string, unknown>>;
              const hasImage = inner.some((c) => c.type === 'image');
              if (hasImage) {
                changed = true;
                const textParts = inner
                  .filter((c) => c.type === 'text')
                  .map((c) => c.text as string);
                return {
                  ...block,
                  content: textParts.join('\n') + '\n[Screenshot was analyzed in a previous turn.]',
                };
              }
            }
            return block;
          });
          if (changed) {
            this.conversationHistory[i] = { ...msg, content: cleaned } as typeof msg;
          }
        }
      }

      // Inject turn budget warning when approaching limit.
      // Only inject if the last message is NOT already a user message (prevent consecutive user messages).
      if (turns === TURN_WARNING_THRESHOLD) {
        const lastMsg = this.conversationHistory[this.conversationHistory.length - 1];
        if (lastMsg?.role !== 'user') {
          console.log(`[Agent] Turn ${turns}/${MAX_TURNS} — injecting wrap-up warning`);
          this.conversationHistory.push({
            role: 'user',
            content: `⚠️ SYSTEM: Turn budget ${turns}/${MAX_TURNS}. You are running low on turns. IMMEDIATELY stop any icon replacement or non-essential operations. Do the following RIGHT NOW:\n1. export_node_as_image for screenshot QA\n2. Fix only critical issues (text overlap, clipping)\n3. Declare completion.\nDo NOT start new icon searches or clone operations.`,
          });
        } else {
          console.log(`[Agent] Turn ${turns}/${MAX_TURNS} — skipping warning injection (last msg is user)`);
        }
      }

      this.updateAgentState(agentId, { status: 'streaming', currentAction: 'Thinking...' });

      try {
        type Tool = import('@anthropic-ai/sdk').Tool;
        type ToolUseBlock = import('@anthropic-ai/sdk').ToolUseBlock;
        type ToolResultBlockParam = import('@anthropic-ai/sdk').ToolResultBlockParam;

        // Block individual creation tools — MUST use batch_build_screen instead
        // Also block internal-only tools not meant for the LLM
        const blockedTools = new Set([
          'create_frame', 'create_text', 'create_rectangle', 'create_shape',
          'create_component_from_node', 'create_component_set',
          'pre_cache_components',
        ]);
        const anthropicTools: Tool[] = Array.from(this.tools.values())
          .filter((t) => !blockedTools.has(t.name))
          .map((t) => ({
            name: t.name,
            description: t.description,
            input_schema: t.inputSchema as Tool['input_schema'],
          }));

        const stream = this.directClient.messages.stream({
          model: 'claude-sonnet-4-20250514',
          max_tokens: 16384,
          system: this.systemPrompt,
          messages: this.conversationHistory,
          tools: anthropicTools,
        });

        let assistantText = '';

        stream.on('text', (text: string) => {
          assistantText += text;
          this.emitEvent(agentId, 'streaming', { text: assistantText });
        });

        const response = await stream.finalMessage();
        const toolUseBlocks: ToolUseBlock[] = [];
        const textParts: string[] = [];

        for (const block of response.content) {
          if (block.type === 'text') textParts.push(block.text);
          else if (block.type === 'tool_use') toolUseBlocks.push(block);
        }

        const fullText = textParts.join('');
        if (fullText) {
          this.emitChatMessage({
            id: uuidv4(),
            role: 'assistant',
            content: fullText,
            timestamp: Date.now(),
            agentId,
          });
        }

        this.conversationHistory.push({ role: 'assistant', content: response.content });

        if (toolUseBlocks.length === 0) {
          // Force screenshot QA if batch_build_screen was called but no screenshot taken
          if (batchBuildDone && !screenshotTaken) {
            console.log('[Agent] Agent tried to finish without screenshot QA — forcing it');
            this.conversationHistory.push({
              role: 'user',
              content: '⚠️ SYSTEM: You MUST call export_node_as_image on the root frame before completing. You have not taken a screenshot yet. Take one NOW and analyze the result for QA issues.',
            });
            continue; // Force another turn
          }
          this.updateAgentState(agentId, { status: 'done', progress: 100 });
          this.emitEvent(agentId, 'done', { text: fullText });
          return;
        }

        // Execute tool calls
        const toolResults: ToolResultBlockParam[] = [];
        for (const toolUse of toolUseBlocks) {
          // Track key tool calls
          if (toolUse.name === 'export_node_as_image') screenshotTaken = true;
          if (toolUse.name === 'batch_build_screen') batchBuildDone = true;

          this.updateAgentState(agentId, { status: 'running', currentAction: `Calling ${toolUse.name}...` });
          this.emitEvent(agentId, 'tool-call', { name: toolUse.name, input: toolUse.input });

          try {
            const tool = this.tools.get(toolUse.name);
            if (!tool) throw new Error(`Unknown tool: ${toolUse.name}`);
            const result = await this.callToolWithRetry(tool, toolUse.input as Record<string, unknown>);
            this.emitEvent(agentId, 'tool-result', { name: toolUse.name, result });

            // Special handling: batch_build_screen with auto-screenshot
            if (toolUse.name === 'batch_build_screen' && result && typeof result === 'object') {
              const buildResult = result as Record<string, unknown>;
              const screenshot = buildResult.screenshot as Record<string, unknown> | undefined;
              if (screenshot?.imageData) {
                batchBuildDone = true;
                screenshotTaken = true; // Auto-screenshot counts

                type ImageBlockParam = import('@anthropic-ai/sdk').ImageBlockParam;
                type TextBlockParam = import('@anthropic-ai/sdk').TextBlockParam;
                const imageBlock: ImageBlockParam = {
                  type: 'image',
                  source: {
                    type: 'base64',
                    media_type: 'image/png',
                    data: screenshot.imageData as string,
                  },
                };
                // Strip screenshot from JSON to avoid bloating context
                const { screenshot: _s, ...resultWithoutScreenshot } = buildResult;
                const textBlock: TextBlockParam = {
                  type: 'text',
                  text: `빌드 완료: ${buildResult.totalNodes || '?'}개 노드 생성. rootId=${buildResult.rootId}. 자동 스크린샷입니다. QA 체크리스트를 확인하세요.\n\n${JSON.stringify(resultWithoutScreenshot)}`,
                };
                toolResults.push({
                  type: 'tool_result',
                  tool_use_id: toolUse.id,
                  content: [imageBlock, textBlock],
                });
              } else {
                toolResults.push({
                  type: 'tool_result',
                  tool_use_id: toolUse.id,
                  content: typeof result === 'string' ? result : JSON.stringify(result),
                });
              }
            }
            // Special handling: pass image data as vision input so Claude can SEE screenshots
            else if (toolUse.name === 'export_node_as_image' && result && typeof result === 'object') {
              const imgResult = result as Record<string, unknown>;
              if (imgResult.imageData && typeof imgResult.imageData === 'string') {
                type ImageBlockParam = import('@anthropic-ai/sdk').ImageBlockParam;
                type TextBlockParam = import('@anthropic-ai/sdk').TextBlockParam;
                const imageBlock: ImageBlockParam = {
                  type: 'image',
                  source: {
                    type: 'base64',
                    media_type: (imgResult.mimeType as 'image/png' | 'image/jpeg') || 'image/png',
                    data: imgResult.imageData as string,
                  },
                };
                const textBlock: TextBlockParam = {
                  type: 'text',
                  text: `Screenshot of node ${imgResult.nodeId || 'unknown'} (${imgResult.format || 'PNG'}, scale=${imgResult.scale || 1}). Analyze this image carefully for QA.`,
                };
                toolResults.push({
                  type: 'tool_result',
                  tool_use_id: toolUse.id,
                  content: [imageBlock, textBlock],
                });
              } else {
                toolResults.push({
                  type: 'tool_result',
                  tool_use_id: toolUse.id,
                  content: typeof result === 'string' ? result : JSON.stringify(result),
                });
              }
            } else {
              toolResults.push({
                type: 'tool_result',
                tool_use_id: toolUse.id,
                content: typeof result === 'string' ? result : JSON.stringify(result),
              });
            }
          } catch (error) {
            const errorMsg = error instanceof Error ? error.message : String(error);
            this.emitEvent(agentId, 'error', { tool: toolUse.name, error: errorMsg });
            toolResults.push({
              type: 'tool_result',
              tool_use_id: toolUse.id,
              content: `Error: ${errorMsg}`,
              is_error: true,
            });
          }
        }

        this.conversationHistory.push({ role: 'user', content: toolResults });
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error);
        const errorStack = error instanceof Error ? error.stack : '';
        console.error('[Agent] Direct API error:', errorMsg);
        if (errorStack) console.error('[Agent] Stack:', errorStack);
        console.error('[Agent] Turn:', turns, '/ History length:', this.conversationHistory.length);

        // Clean up orphaned assistant message with pending tool_use blocks
        // so the next sendMessage() doesn't encounter a corrupted history
        this.sanitizeHistory();

        this.updateAgentState(agentId, { status: 'error' });
        this.emitEvent(agentId, 'error', { error: errorMsg });
        // Show error in chat so user can see it
        this.emitChatMessage({
          id: uuidv4(),
          role: 'assistant',
          content: `⚠️ Error: ${errorMsg}`,
          timestamp: Date.now(),
          agentId,
        });
        return;
      }
    }

    this.updateAgentState(agentId, { status: 'done' });
    this.emitEvent(agentId, 'done', { reason: 'max_turns_reached' });
  }

  // ============================================================
  // Public API
  // ============================================================

  cancel(): void {
    this.abortController?.abort();
    // Clean up any orphaned messages after cancellation
    // (abort may leave assistant messages without tool_results)
    setTimeout(() => this.sanitizeHistory(), 100);
  }

  clearHistory(): void {
    this.conversationHistory = [];
    this.sdkSessionId = null;
  }

  // ============================================================
  // Tool call retry wrapper
  // ============================================================

  /**
   * 도구 호출을 타임아웃 + 재시도로 감싸는 래퍼.
   * - 기본 타임아웃: 30초, 대용량 도구: 300초
   * - 최대 2회 재시도 (총 3회 시도)
   * - Promise.race()로 타임아웃 감지
   */
  private async callToolWithRetry(
    tool: ToolDefinition,
    input: Record<string, unknown>,
  ): Promise<unknown> {
    const timeoutMs = TOOL_TIMEOUT_MAP[tool.name] || DEFAULT_TOOL_TIMEOUT_MS;

    for (let attempt = 0; attempt <= MAX_TOOL_RETRIES; attempt++) {
      try {
        const result = await Promise.race([
          tool.handler(input),
          new Promise<never>((_, reject) =>
            setTimeout(() => reject(new Error(`Tool "${tool.name}" timed out after ${timeoutMs / 1000}s`)), timeoutMs),
          ),
        ]);
        return result;
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error);
        const isTimeout = errorMsg.includes('timed out');

        if (isTimeout && attempt < MAX_TOOL_RETRIES) {
          console.warn(`[Agent] Tool "${tool.name}" timeout (attempt ${attempt + 1}/${MAX_TOOL_RETRIES + 1}), retrying...`);
          this.emitEvent('orchestrator', 'tool-retry', {
            name: tool.name,
            attempt: attempt + 1,
            maxRetries: MAX_TOOL_RETRIES,
            reason: 'timeout',
          });
          continue;
        }

        // Non-timeout error or final retry exhausted
        throw error;
      }
    }

    // Should not reach here, but TypeScript needs it
    throw new Error(`Tool "${tool.name}" failed after ${MAX_TOOL_RETRIES + 1} attempts`);
  }

  // ============================================================
  // Event helpers
  // ============================================================

  private updateAgentState(agentId: string, partial: Partial<AgentState>): void {
    const current = this.agents.get(agentId) || {
      id: agentId,
      role: 'orchestrator' as const,
      status: 'idle' as const,
      progress: 0,
    };
    const updated = { ...current, ...partial };
    this.agents.set(agentId, updated);
    this.emit('agent-state', updated);
  }

  private emitEvent(agentId: string, type: AgentEvent['type'], data: unknown): void {
    this.emit('agent-event', { type, agentId, data } satisfies AgentEvent);
  }

  private emitChatMessage(message: ChatMessage): void {
    this.emit('chat-message', message);
  }
}
