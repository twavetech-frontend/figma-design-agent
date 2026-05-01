/**
 * LLM Caller — tool_choice 강제 단일 턴 LLM 호출 유틸리티
 *
 * 각 파이프라인 단계에서 LLM을 호출할 때 사용.
 * tool_choice: { type: 'tool', name: toolName }으로 반드시 지정된 도구로 JSON 반환.
 */

import type Anthropic from '@anthropic-ai/sdk';
import type { MessageParam, Tool } from '@anthropic-ai/sdk/resources/messages';

export interface CallLLMOptions<T> {
  /** Anthropic SDK 클라이언트 */
  client: Anthropic;
  /** 시스템 프롬프트 */
  systemPrompt: string;
  /** 대화 메시지 */
  messages: MessageParam[];
  /** 강제 호출할 도구 이름 */
  toolName: string;
  /** 도구 스키마 (JSON Schema) */
  toolSchema: Record<string, unknown>;
  /** 도구 설명 */
  toolDescription: string;
  /** 모델 (기본: claude-opus-4-7) */
  model?: string;
  /** 최대 토큰 (기본: 16384) */
  maxTokens?: number;
  /** 스트리밍 텍스트 콜백 (선택) */
  onStreamText?: (text: string) => void;
  /** AbortController 시그널 (선택) */
  signal?: AbortSignal;
}

/**
 * tool_choice 강제로 단일 턴 LLM 호출.
 * LLM이 반드시 지정된 도구를 호출하고 그 input을 T로 파싱하여 반환.
 */
export async function callLLMWithTool<T>(options: CallLLMOptions<T>): Promise<T> {
  const {
    client,
    systemPrompt,
    messages,
    toolName,
    toolSchema,
    toolDescription,
    model = 'claude-opus-4-7',
    maxTokens = 16384,
    onStreamText,
    signal,
  } = options;

  const tool: Tool = {
    name: toolName,
    description: toolDescription,
    input_schema: toolSchema as Tool['input_schema'],
  };

  if (onStreamText) {
    // 스트리밍 모드
    const stream = client.messages.stream(
      {
        model,
        max_tokens: maxTokens,
        system: systemPrompt,
        messages,
        tools: [tool],
        tool_choice: { type: 'tool', name: toolName },
      },
      signal ? { signal } : undefined,
    );

    let streamedText = '';
    stream.on('text', (text: string) => {
      streamedText += text;
      onStreamText(streamedText);
    });

    const response = await stream.finalMessage();
    return extractToolInput<T>(response.content, toolName);
  } else {
    // 논스트리밍 모드
    const response = await client.messages.create(
      {
        model,
        max_tokens: maxTokens,
        system: systemPrompt,
        messages,
        tools: [tool],
        tool_choice: { type: 'tool', name: toolName },
      },
      signal ? { signal } : undefined,
    );

    return extractToolInput<T>(response.content, toolName);
  }
}

/**
 * 응답 content에서 tool_use 블록의 input을 추출
 */
function extractToolInput<T>(
  content: Array<{ type: string; name?: string; input?: unknown }>,
  toolName: string,
): T {
  const toolUse = content.find(
    (block) => block.type === 'tool_use' && block.name === toolName,
  );

  if (!toolUse || toolUse.input === undefined) {
    throw new Error(
      `LLM did not return expected tool_use for "${toolName}". Content: ${JSON.stringify(content).slice(0, 500)}`,
    );
  }

  return toolUse.input as T;
}
