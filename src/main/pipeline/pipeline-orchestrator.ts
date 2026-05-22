/**
 * Pipeline Orchestrator — 결정론적 7단계 파이프라인
 *
 * 코드가 워크플로우를 제어. LLM은 생성(blueprint, QA, fix)에만 사용.
 * 3-4회 LLM 호출로 30-90초 완료 목표.
 *
 * Step 1: Blueprint (LLM) — 사용자 메시지 → JSON blueprint
 * Step 2: Name Resolution (코드) — 시맨틱 이름 → 실제 키
 * Step 3: Figma Build (Plugin) — blueprint → Figma 노드
 * Step 4: Variable Binding (코드) — DS 토큰 바인딩
 * Step 5: QA Review (LLM) — 스크린샷 기반 검증
 * Step 6: Fix (LLM, 조건부) — QA 이슈 수정
 */

import { EventEmitter } from 'events';
import { resolveBlueprint, enhanceBlueprint, prefetchImages } from '../figma-mcp-embedded';
import { buildSystemPrompt, type PromptContext } from '../system-prompt-builder';
import { processAttachmentText } from '../rtf-stripper';
import { callLLMWithTool } from './llm-caller';
import type {
  BlueprintResult,
  BuildResult,
  QAResult,
  FixResult,
  FixPatch,
  PipelineResult,
  PipelineStepName,
  PipelineStepState,
  ModificationResult,
} from './types';
import type { ToolDefinition, AttachmentData } from '../../shared/types';

const MAX_FIX_ITERATIONS = 2;

// Tool call timeout/retry configuration
const DEFAULT_TIMEOUT_MS = 30_000; // 30초
const LARGE_TIMEOUT_MS = 300_000; // 300초 (5분)
const MAX_RETRIES = 2; // 최대 2회 재시도 (총 3회 시도)

export interface PipelineConfig {
  tools: Map<string, ToolDefinition>;
  projectRoot: string;
  apiKey: string;
  /** Figma WebSocket 서버 인스턴스 (스크린샷 등 직접 호출용) */
  figmaWS: { sendCommand: (command: string, params?: Record<string, unknown>, timeout?: number) => Promise<unknown> };
}

export class PipelineOrchestrator extends EventEmitter {
  private config: PipelineConfig;
  private client: import('@anthropic-ai/sdk').default | null = null;
  private systemPrompt: string = '';
  /** 마지막 빌드 결과 (수정 모드에서 사용) */
  private lastBuildResult: BuildResult | null = null;
  private lastBlueprint: BlueprintResult | null = null;

  constructor(config: PipelineConfig) {
    super();
    this.config = config;
  }

  /** 시스템 프롬프트 초기화 */
  async initialize(context: Partial<PromptContext> = {}): Promise<void> {
    this.systemPrompt = await buildSystemPrompt(
      { tools: this.config.tools, ...context },
      this.config.projectRoot,
    );
  }

  /** Anthropic 클라이언트 지연 초기화 */
  private async getClient(): Promise<import('@anthropic-ai/sdk').default> {
    if (!this.client) {
      const Anthropic = (await import('@anthropic-ai/sdk')).default;
      const key = this.config.apiKey;
      // OAuth Access Token (sk-ant-oat...)은 authToken으로, 일반 API 키는 apiKey로 전달
      if (key.includes('-oat')) {
        this.client = new Anthropic({ authToken: key });
      } else {
        this.client = new Anthropic({ apiKey: key });
      }
    }
    return this.client;
  }

  // ============================================================
  // Retry wrapper
  // ============================================================

  /**
   * 비동기 함수를 타임아웃 + 재시도로 감싸는 래퍼.
   */
  private async callWithRetry<T>(
    fn: () => Promise<T>,
    options: { timeoutMs?: number; label?: string } = {},
  ): Promise<T> {
    const { timeoutMs = DEFAULT_TIMEOUT_MS, label = 'unknown' } = options;

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const result = await Promise.race([
          fn(),
          new Promise<never>((_, reject) =>
            setTimeout(() => reject(new Error(`"${label}" timed out after ${timeoutMs / 1000}s`)), timeoutMs),
          ),
        ]);
        return result;
      } catch (error) {
        const errorMsg = error instanceof Error ? error.message : String(error);
        const isTimeout = errorMsg.includes('timed out');

        if (isTimeout && attempt < MAX_RETRIES) {
          console.warn(`[Pipeline] "${label}" timeout (attempt ${attempt + 1}/${MAX_RETRIES + 1}), retrying...`);
          this.emitStep(0, 'build', 'running', `${label} 재시도 (${attempt + 1}/${MAX_RETRIES})...`);
          continue;
        }

        throw error;
      }
    }

    throw new Error(`"${label}" failed after ${MAX_RETRIES + 1} attempts`);
  }

  // ============================================================
  // Main Pipeline
  // ============================================================

  async runPipeline(userMessage: string, signal?: AbortSignal, attachments?: AttachmentData[]): Promise<PipelineResult> {
    const startTime = Date.now();
    const stepDurations: Record<PipelineStepName, number> = {
      blueprint: 0, resolve: 0, build: 0, variables: 0, qa: 0, fix: 0,
    };

    try {
      // ── Step 1: Blueprint (LLM) ──
      this.emitStep(1, 'blueprint', 'running', 'LLM으로 디자인 설계도 생성 중...');
      const t1 = Date.now();
      const blueprint = await this.generateBlueprint(userMessage, signal, attachments);
      stepDurations.blueprint = Date.now() - t1;
      this.emitStep(1, 'blueprint', 'done', `${stepDurations.blueprint}ms`);

      // ── Step 2: Enhance + Name Resolution (코드) ──
      this.emitStep(2, 'resolve', 'running', '블루프린트 개선 + 시맨틱 이름 해결 중...');
      const t2 = Date.now();
      const enhanced = enhanceBlueprint(blueprint.blueprint as unknown as Record<string, unknown>);
      const resolvedBlueprint = resolveBlueprint(enhanced);
      stepDurations.resolve = Date.now() - t2;
      this.emitStep(2, 'resolve', 'done', `${stepDurations.resolve}ms`);

      // ── Step 3: Figma Build (Plugin) ──
      this.emitStep(3, 'build', 'running', 'Figma에 노드 생성 중...');
      const t3 = Date.now();
      // Pre-fetch images in the blueprint tree
      await prefetchImages([resolvedBlueprint]);
      const buildResult = await this.buildInFigma(resolvedBlueprint);
      stepDurations.build = Date.now() - t3;
      this.lastBuildResult = buildResult;
      this.lastBlueprint = blueprint;
      this.emitStep(3, 'build', 'done', `${buildResult.totalNodes}개 노드, ${stepDurations.build}ms`);

      // ── Step 4: Variable Binding (코드) ──
      this.emitStep(4, 'variables', 'skipped', '추후 구현');
      // TODO: DS 토큰 바인딩 자동화

      // ── Step 5: QA Review (LLM) ──
      this.emitStep(5, 'qa', 'running', '스크린샷 기반 QA 검증 중...');
      const t6 = Date.now();
      const screenshot = await this.captureScreenshot(buildResult.rootId);
      const qaResult = await this.runQA(screenshot, blueprint, signal);
      stepDurations.qa = Date.now() - t6;
      this.emitStep(5, 'qa', 'done', qaResult.passed ? 'PASS' : `${qaResult.issues.length}개 이슈, ${stepDurations.qa}ms`);

      // ── Step 6: Fix (조건부, 최대 2회) ──
      if (!qaResult.passed && qaResult.issues.length > 0) {
        this.emitStep(6, 'fix', 'running', `${qaResult.issues.length}개 이슈 수정 중...`);
        const t7 = Date.now();
        await this.applyFixes(qaResult, buildResult, signal);
        stepDurations.fix = Date.now() - t7;
        this.emitStep(6, 'fix', 'done', `${stepDurations.fix}ms`);
      } else {
        this.emitStep(6, 'fix', 'skipped', 'QA 통과');
      }

      const totalDuration = Date.now() - startTime;
      return {
        success: true,
        rootId: buildResult.rootId,
        totalDuration,
        stepDurations,
        qaResult,
      };
    } catch (error) {
      const totalDuration = Date.now() - startTime;
      const errorMsg = error instanceof Error ? error.message : String(error);
      return {
        success: false,
        totalDuration,
        stepDurations,
        error: errorMsg,
      };
    }
  }

  // ============================================================
  // Step 1: Blueprint Generation (LLM)
  // ============================================================

  private async generateBlueprint(userMessage: string, signal?: AbortSignal, attachments?: AttachmentData[]): Promise<BlueprintResult> {
    const client = await this.getClient();

    const blueprintPrompt = `You are a Figma design blueprint generator. Given the user's design request, generate a complete JSON blueprint for a mobile app screen.

STEP 0 — DESIGN BRIEF (MANDATORY):
Before generating the blueprint, decide internally:
1. Color palette (5-6 hex values): background, surface, accent, 3-4 icon tint colors
2. Typography scale: display(40-48px/800) → title(24-28px/700) → section(17-18px/600) → body(15-16px/400) → caption(13-14px/400) → label(11-12px/500)
3. Spacing rhythm: section gap (24-32px), group gap (12-16px), element gap (8-12px)
4. Visual direction in one sentence
Include this brief in your designSummary.

IMPORTANT RULES:
- Root frame: 393 x 852 px (iPhone 16), white fill, autoLayout VERTICAL
- Use statusBar: true on root frame
- Use semantic names: component/variant for instances, name for icons
- All text MUST have layoutSizingHorizontal: "FILL"
- Font: always "Pretendard"
- clipsContent: false on root and content frames
- Hero banners: 393 x 160-220px (wide rectangle, never square)

VISUAL QUALITY STANDARDS:
- Color: warm white background {r:0.98,g:0.98,b:0.97}. ONE accent color only. Dark emphasis card {r:0.11,g:0.11,b:0.14} max 1 per screen.
- Icon treatment: ALWAYS wrap icons in 44x44 colored background frames (cornerRadius 12). Each category gets a DIFFERENT tint color (e.g. shopping→{r:1,g:0.94,b:0.92}, points→{r:0.92,g:0.97,b:1}, attendance→{r:0.93,g:1,b:0.95}, event→{r:0.98,g:0.95,b:1}).
- List items: icon bg(44x44) + vertical text group(title 16px/500 + desc 13px/400) + chevron-right(20px). HORIZONTAL layout, itemSpacing 14.
- Cards: dark card (fill {r:0.11,g:0.11,b:0.14}, r16, white text) for key info, surface card (fill {r:0.96,g:0.96,b:0.95}, r16) for content groups.
- Spacing: section gaps 24-32px, group gaps 12-16px, horizontal padding 20-24px.

⛔ ANTI-PATTERNS (절대 금지 — 위반 시 blueprint 거부됨):
- ⛔ type:"rectangle" for icons — 아이콘 자리에 rectangle 절대 금지! 반드시 type:"icon" + colored bg frame 사용
- ⛔ Generic gradients (purple-pink, neon colors — feels dated 2019)
- ⛔ Placeholder rectangles for icons (use actual DS icons in colored bg frames)
- ⛔ 1200px height (always 852px for iPhone 16)
- ⛔ Uniform font sizes (must have clear typography hierarchy with 5+ distinct levels)
- ⛔ Stroke-only cards (always use fill, not just border)
- ⛔ All icon backgrounds same color (use different tint per category)
- ⛔ Tab bar without real icons — 탭바에 rectangle 넣지 마라, 반드시 type:"icon" 사용

GOOD EXAMPLE — List item with icon background:
{"type":"frame","name":"List Item","layoutSizingHorizontal":"FILL","autoLayout":{"layoutMode":"HORIZONTAL","itemSpacing":14,"paddingVertical":14,"counterAxisAlignItems":"CENTER"},"children":[{"type":"frame","name":"Icon BG","width":44,"height":44,"cornerRadius":12,"fill":{"r":1,"g":0.94,"b":0.92},"autoLayout":{"layoutMode":"VERTICAL","primaryAxisAlignItems":"CENTER","counterAxisAlignItems":"CENTER"},"children":[{"type":"icon","name":"gift-01","size":24}]},{"type":"frame","name":"Text Group","layoutSizingHorizontal":"FILL","autoLayout":{"layoutMode":"VERTICAL","itemSpacing":2},"children":[{"type":"text","text":"쇼핑 적립","fontSize":16,"fontWeight":500,"fontFamily":"Pretendard","fontColor":{"r":0.12,"g":0.12,"b":0.14},"layoutSizingHorizontal":"FILL"},{"type":"text","text":"구매 금액의 1% 적립","fontSize":13,"fontWeight":400,"fontFamily":"Pretendard","fontColor":{"r":0.45,"g":0.47,"b":0.5},"layoutSizingHorizontal":"FILL"}]},{"type":"icon","name":"chevron-right","size":20}]}

GOOD EXAMPLE — Tab Bar with real icons (NOT rectangles):
{"type":"frame","name":"Tab Bar","layoutSizingHorizontal":"FILL","height":83,"fill":{"r":1,"g":1,"b":1},"autoLayout":{"layoutMode":"HORIZONTAL","primaryAxisAlignItems":"SPACE_BETWEEN","counterAxisAlignItems":"CENTER","paddingHorizontal":32,"paddingTop":8,"paddingBottom":34},"children":[{"type":"frame","name":"Tab Home","autoLayout":{"layoutMode":"VERTICAL","itemSpacing":4,"counterAxisAlignItems":"CENTER"},"children":[{"type":"icon","name":"home-01","size":24},{"type":"text","text":"홈","fontSize":11,"fontWeight":500,"fontFamily":"Pretendard","fontColor":{"r":0.45,"g":0.47,"b":0.5},"layoutSizingHorizontal":"FILL"}]},{"type":"frame","name":"Tab Points","autoLayout":{"layoutMode":"VERTICAL","itemSpacing":4,"counterAxisAlignItems":"CENTER"},"children":[{"type":"icon","name":"coins-01","size":24},{"type":"text","text":"포인트","fontSize":11,"fontWeight":600,"fontFamily":"Pretendard","fontColor":{"r":0.12,"g":0.12,"b":0.14},"layoutSizingHorizontal":"FILL"}]},{"type":"frame","name":"Tab Shop","autoLayout":{"layoutMode":"VERTICAL","itemSpacing":4,"counterAxisAlignItems":"CENTER"},"children":[{"type":"icon","name":"shopping-bag-01","size":24},{"type":"text","text":"쇼핑","fontSize":11,"fontWeight":500,"fontFamily":"Pretendard","fontColor":{"r":0.45,"g":0.47,"b":0.5},"layoutSizingHorizontal":"FILL"}]},{"type":"frame","name":"Tab My","autoLayout":{"layoutMode":"VERTICAL","itemSpacing":4,"counterAxisAlignItems":"CENTER"},"children":[{"type":"icon","name":"user-01","size":24},{"type":"text","text":"마이","fontSize":11,"fontWeight":500,"fontFamily":"Pretendard","fontColor":{"r":0.45,"g":0.47,"b":0.5},"layoutSizingHorizontal":"FILL"}]}]}

AVAILABLE DS COMPONENTS (use type: "instance"):
- Button: variant "Size=sm|md|lg, Hierarchy=Primary|Secondary|Tertiary"
- Input: variant "Size=md, State=Placeholder|Filled"
- Checkbox, Radio, Toggle, Badge, Avatar, Tooltip
- Social button: variant "Social=Google|Apple, Theme=Gray"
- Tab, Tag, Divider

AVAILABLE ICONS (use type: "icon" with "name" field — fuzzy matching supported):
Navigation: arrow-left, arrow-right, chevron-left, chevron-right, chevron-down, x-close, home-01, menu-01
Action: plus, minus, edit-01, trash-01, copy-01, share-05, search-lg, filter-funnel-01, download-04
Status: check, check-circle, alert-circle, alert-triangle, info-circle, help-circle
Communication: bell-01, mail-01, phone-call-01, message-circle-01, send-01
Commerce: shopping-bag-01, shopping-cart-01, credit-card-01, wallet-01, gift-01, receipt, coins-01
User: user-01, user-circle, users-01, user-plus-01
Content: heart, star-01, bookmark, eye, eye-off, flag-01, tag-01
UI: settings-01, lock-01, calendar, clock, globe-01, link-01, qr-code-01

Return the blueprint through the submit_blueprint tool.`;

    // Build user message content — include attachments if present
    const userContent: Array<Record<string, unknown>> = [
      { type: 'text', text: `${blueprintPrompt}\n\n---\n\nUser request: ${userMessage}` },
    ];

    if (attachments && attachments.length > 0) {
      for (const att of attachments) {
        if (att.type === 'image') {
          userContent.push({
            type: 'image',
            source: {
              type: 'base64',
              media_type: att.mediaType,
              data: att.base64,
            },
          });
        } else if (att.textContent) {
          const cleanText = processAttachmentText(att.textContent, att.name);
          userContent.push({
            type: 'text',
            text: `--- 첨부 문서: ${att.name} ---\n\n아래는 첨부 문서의 전체 내용입니다. 이 문서의 요구사항을 빠짐없이 분석하여 디자인에 반영하세요.\n\n${cleanText}`,
          });
        }
      }
    }

    return callLLMWithTool<BlueprintResult>({
      client,
      systemPrompt: this.systemPrompt,
      messages: [
        {
          role: 'user',
          content: userContent as never,
        },
      ],
      toolName: 'submit_blueprint',
      toolDescription: 'Submit the design blueprint as structured JSON. The blueprint field contains the Figma node tree, and designSummary describes the design intent.',
      toolSchema: {
        type: 'object',
        properties: {
          blueprint: {
            type: 'object',
            description: 'Root node blueprint with full children tree. Must include type, name, width, height, fill, autoLayout, and children array.',
          },
          designSummary: {
            type: 'string',
            description: 'One-line summary of the design intent (in Korean)',
          },
        },
        required: ['blueprint', 'designSummary'],
      },
      onStreamText: (text) => {
        this.emit('streaming', { step: 'blueprint', text });
      },
      signal,
    });
  }

  // ============================================================
  // Step 3: Figma Build
  // ============================================================

  private async buildInFigma(resolvedBlueprint: Record<string, unknown>): Promise<BuildResult> {
    const batchBuildTool = this.config.tools.get('batch_build_screen');
    if (!batchBuildTool) {
      throw new Error('batch_build_screen tool not found');
    }

    const result = await this.callWithRetry(
      () => batchBuildTool.handler({ blueprint: resolvedBlueprint }) as Promise<Record<string, unknown>>,
      { timeoutMs: LARGE_TIMEOUT_MS, label: 'batch_build_screen' },
    );

    if (!result?.rootId) {
      throw new Error('batch_build_screen did not return rootId');
    }

    // Build nodeMap from result
    const nodeMap: Record<string, string> = {};
    if (result.nodeMap && typeof result.nodeMap === 'object') {
      Object.assign(nodeMap, result.nodeMap);
    }

    return {
      rootId: result.rootId as string,
      nodeMap,
      totalNodes: (result.totalNodes as number) || 0,
      raw: result,
    };
  }

  // ============================================================
  // Step 5: QA Review (LLM)
  // ============================================================

  private async captureScreenshot(rootId: string): Promise<string> {
    const result = await this.callWithRetry(
      () => this.config.figmaWS.sendCommand('export_node_as_image', {
        nodeId: rootId,
        format: 'PNG',
        scale: 1,
      }, 30000) as Promise<Record<string, unknown>>,
      { timeoutMs: DEFAULT_TIMEOUT_MS, label: 'captureScreenshot' },
    );

    if (!result?.imageData) {
      throw new Error('Failed to capture screenshot');
    }

    return result.imageData as string;
  }

  private async runQA(
    screenshotBase64: string,
    blueprint: BlueprintResult,
    signal?: AbortSignal,
  ): Promise<QAResult> {
    const client = await this.getClient();

    const qaPrompt = `You are a design QA reviewer. Analyze the screenshot of a Figma design against the intended blueprint and identify any issues.

Blueprint summary: ${blueprint.designSummary}

Check for:
1. Status Bar presence and positioning
2. All text readable (not vertical, not clipped)
3. Component instances rendered correctly
4. Layout alignment (no overlapping, no clipping)
5. Text content matches intent (not lorem ipsum unless intended)
6. Spacing and padding consistency

Return your findings through the submit_qa tool.`;

    return callLLMWithTool<QAResult>({
      client,
      systemPrompt: 'You are a Figma design QA expert. Be strict but fair.',
      messages: [
        {
          role: 'user',
          content: [
            {
              type: 'image',
              source: {
                type: 'base64',
                media_type: 'image/png',
                data: screenshotBase64,
              },
            },
            {
              type: 'text',
              text: qaPrompt,
            },
          ],
        },
      ],
      toolName: 'submit_qa',
      toolDescription: 'Submit QA review results. Set passed=true if the design is acceptable, false if issues need fixing.',
      toolSchema: {
        type: 'object',
        properties: {
          passed: { type: 'boolean', description: 'Overall pass/fail' },
          issues: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                severity: { type: 'string', enum: ['critical', 'warning', 'info'] },
                description: { type: 'string' },
                nodeId: { type: 'string' },
                suggestedFix: { type: 'string' },
              },
              required: ['severity', 'description'],
            },
          },
          summary: { type: 'string', description: 'One-line QA summary' },
        },
        required: ['passed', 'issues', 'summary'],
      },
      signal,
    });
  }

  // ============================================================
  // Step 7: Fix (조건부)
  // ============================================================

  private async applyFixes(
    qaResult: QAResult,
    buildResult: BuildResult,
    signal?: AbortSignal,
  ): Promise<void> {
    const client = await this.getClient();

    for (let iteration = 0; iteration < MAX_FIX_ITERATIONS; iteration++) {
      if (signal?.aborted) return;

      // Critical 이슈만 수정 (warning/info는 무시)
      const criticalIssues = qaResult.issues.filter((i) => i.severity === 'critical');
      if (criticalIssues.length === 0) return;

      const fixPrompt = `Fix these critical design issues in Figma. The root frame ID is "${buildResult.rootId}".

Issues:
${criticalIssues.map((i, idx) => `${idx + 1}. ${i.description}${i.nodeId ? ` (node: ${i.nodeId})` : ''}${i.suggestedFix ? ` — suggested: ${i.suggestedFix}` : ''}`).join('\n')}

Available tools: set_text_content, set_fill_color, set_stroke_color, set_corner_radius, resize_node, move_node, set_auto_layout, set_layout_sizing, set_text_properties, set_font_size, set_font_weight, set_image_fill, delete_node, set_effects.

Generate an array of tool call patches to fix these issues.`;

      const fixResult = await callLLMWithTool<FixResult>({
        client,
        systemPrompt: 'You are a Figma design fixer. Generate precise tool call patches to fix design issues.',
        messages: [{ role: 'user', content: fixPrompt }],
        toolName: 'submit_fixes',
        toolDescription: 'Submit fix patches as an array of tool calls.',
        toolSchema: {
          type: 'object',
          properties: {
            patches: {
              type: 'array',
              items: {
                type: 'object',
                properties: {
                  tool: { type: 'string', description: 'Figma tool name (e.g., set_text_content, set_fill_color)' },
                  params: { type: 'object', description: 'Tool parameters' },
                },
                required: ['tool', 'params'],
              },
            },
            summary: { type: 'string' },
          },
          required: ['patches', 'summary'],
        },
        signal,
      });

      // Apply patches with retry
      for (const patch of fixResult.patches) {
        try {
          const tool = this.config.tools.get(patch.tool);
          if (tool) {
            await this.callWithRetry(
              () => tool.handler(patch.params) as Promise<unknown>,
              { timeoutMs: DEFAULT_TIMEOUT_MS, label: `fix:${patch.tool}` },
            );
            console.log(`[Pipeline] Fix applied: ${patch.tool}`);
          } else {
            console.warn(`[Pipeline] Unknown fix tool: ${patch.tool}`);
          }
        } catch (e) {
          console.error(`[Pipeline] Fix failed for ${patch.tool}:`, e);
        }
      }

      console.log(`[Pipeline] Fix iteration ${iteration + 1}: ${fixResult.patches.length} patches, "${fixResult.summary}"`);
    }
  }

  // ============================================================
  // Modification Mode — 파이프라인 완료 후 후속 수정
  // ============================================================

  async sendModification(userMessage: string, signal?: AbortSignal): Promise<ModificationResult> {
    if (!this.lastBuildResult) {
      throw new Error('No previous build result. Run pipeline first.');
    }

    const client = await this.getClient();
    const buildResult = this.lastBuildResult;

    const modPrompt = `You are modifying an existing Figma design. The root frame ID is "${buildResult.rootId}".

Node map (name → nodeId):
${JSON.stringify(buildResult.nodeMap, null, 2)}

User request: ${userMessage}

Generate tool call patches to fulfill the user's modification request.
Available tools: set_text_content, set_multiple_text_contents, set_fill_color, set_stroke_color, set_corner_radius, resize_node, move_node, set_auto_layout, set_layout_sizing, set_text_properties, set_font_size, set_font_weight, set_image_fill, delete_node, set_effects.`;

    const fixResult = await callLLMWithTool<FixResult>({
      client,
      systemPrompt: 'You are a Figma design modifier. Generate precise tool call patches.',
      messages: [{ role: 'user', content: modPrompt }],
      toolName: 'submit_modifications',
      toolDescription: 'Submit modification patches.',
      toolSchema: {
        type: 'object',
        properties: {
          patches: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                tool: { type: 'string' },
                params: { type: 'object' },
              },
              required: ['tool', 'params'],
            },
          },
          summary: { type: 'string' },
        },
        required: ['patches', 'summary'],
      },
      signal,
    });

    // Apply patches with retry
    let applied = 0;
    let failed = 0;
    for (const patch of fixResult.patches) {
      try {
        const tool = this.config.tools.get(patch.tool);
        if (tool) {
          await this.callWithRetry(
            () => tool.handler(patch.params) as Promise<unknown>,
            { timeoutMs: DEFAULT_TIMEOUT_MS, label: `mod:${patch.tool}` },
          );
          applied++;
        } else {
          console.warn(`[Pipeline] Unknown modification tool: ${patch.tool}`);
          failed++;
        }
      } catch (e) {
        console.error(`[Pipeline] Modification failed for ${patch.tool}:`, e);
        failed++;
      }
    }

    return {
      appliedCount: applied,
      failedCount: failed,
      summary: fixResult.summary,
    };
  }

  // ============================================================
  // Helpers
  // ============================================================

  /** 이전 빌드 결과가 있는지 (수정 모드 가능 여부) */
  get hasPreviousBuild(): boolean {
    return this.lastBuildResult !== null;
  }

  /** 빌드 결과 초기화 */
  clearBuildState(): void {
    this.lastBuildResult = null;
    this.lastBlueprint = null;
  }

  private emitStep(step: number, name: PipelineStepName, status: PipelineStepState['status'], detail?: string): void {
    const event: PipelineStepState = { step, name, status, detail };
    this.emit('pipeline:step', event);
  }
}
