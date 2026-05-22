/**
 * Pipeline Types — 결정론적 7단계 파이프라인 타입 정의
 */

// ============================================================
// Blueprint — LLM이 생성하는 디자인 설계도
// ============================================================

export interface BlueprintNode {
  type: 'frame' | 'text' | 'rectangle' | 'ellipse' | 'instance' | 'clone' | 'icon';
  name?: string;
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  children?: BlueprintNode[];
  /** 기타 모든 Figma 속성 (fill, autoLayout, fontSize, etc.) */
  [key: string]: unknown;
}

export interface BlueprintResult {
  /** 루트 프레임 블루프린트 */
  blueprint: BlueprintNode;
  /** LLM이 생성한 디자인 의도 요약 */
  designSummary: string;
}

// ============================================================
// QA — LLM 기반 디자인 품질 검증
// ============================================================

export interface QAIssue {
  /** 이슈 심각도 */
  severity: 'critical' | 'warning' | 'info';
  /** 이슈 설명 */
  description: string;
  /** 관련 노드 ID (있으면) */
  nodeId?: string;
  /** 수정 제안 */
  suggestedFix?: string;
}

export interface QAResult {
  /** 전체 합격 여부 */
  passed: boolean;
  /** 발견된 이슈 목록 */
  issues: QAIssue[];
  /** QA 요약 */
  summary: string;
}

// ============================================================
// Fix — QA 이슈 수정 패치
// ============================================================

export interface FixPatch {
  /** Figma 도구 이름 */
  tool: string;
  /** 도구 파라미터 */
  params: Record<string, unknown>;
}

export interface FixResult {
  /** 생성된 수정 패치 배열 */
  patches: FixPatch[];
  /** 수정 요약 */
  summary: string;
}

// ============================================================
// Build — Figma 빌드 결과
// ============================================================

export interface BuildResult {
  /** 루트 프레임 ID */
  rootId: string;
  /** 노드 맵 (이름 → ID) — batch_build_screen 결과에서 추출 */
  nodeMap: Record<string, string>;
  /** 생성된 총 노드 수 */
  totalNodes: number;
  /** 빌드 원본 결과 */
  raw: Record<string, unknown>;
}

// ============================================================
// Pipeline State & Events
// ============================================================

export type PipelineStepName = 'blueprint' | 'resolve' | 'build' | 'variables' | 'qa' | 'fix';
export type PipelineStepStatus = 'pending' | 'running' | 'done' | 'error' | 'skipped';

export interface PipelineStepState {
  step: number;
  name: PipelineStepName;
  status: PipelineStepStatus;
  detail?: string;
  duration?: number;
}

export interface PipelineState {
  /** 전체 파이프라인 상태 */
  status: 'idle' | 'running' | 'done' | 'error';
  /** 각 단계 상태 */
  steps: PipelineStepState[];
  /** 현재 실행 중인 단계 (1-7) */
  currentStep: number;
  /** 전체 소요 시간 (ms) */
  totalDuration?: number;
  /** 에러 메시지 */
  error?: string;
}

export interface PipelineResult {
  /** 성공 여부 */
  success: boolean;
  /** 루트 프레임 ID */
  rootId?: string;
  /** 전체 소요 시간 (ms) */
  totalDuration: number;
  /** 각 단계 결과 요약 */
  stepDurations: Record<PipelineStepName, number>;
  /** QA 결과 */
  qaResult?: QAResult;
  /** 에러 메시지 */
  error?: string;
}

// ============================================================
// Modification Mode — 파이프라인 완료 후 수정 모드
// ============================================================

export interface ModificationResult {
  /** 적용된 패치 수 */
  appliedCount: number;
  /** 실패한 패치 수 */
  failedCount: number;
  /** 수정 요약 */
  summary: string;
}
