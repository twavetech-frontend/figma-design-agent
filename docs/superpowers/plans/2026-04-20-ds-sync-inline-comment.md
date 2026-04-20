# DS 자동 동기화 + 인라인 코멘트 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Anthropic Claude Design에서 영감 받은 (1) DS 자동 동기화 파이프라인과 (2) Figma 플러그인 UI 기반 인라인 코멘트 핀포인트 수정 기능을 프로젝트에 추가한다.

**Architecture:** DSSyncService가 GitHub tokens(기존 .sh 래핑) + Figma 로컬 컴포넌트/variants를 병렬 동기화, `ds/` 파일을 갱신하고 캐시 무효화. InlineCommentHandler는 Figma 플러그인 UI의 선택 노드 + 코멘트를 WS로 받아 orchestrator에 inlineContext와 함께 전달, ChatPanel에 메시지로 기록하고 진행 상태를 플러그인 UI에 피드백한다.

**Tech Stack:** TypeScript, Electron, React 19, Anthropic SDK, WebSocket(ws), tsup+vite 빌드, `npm run build`로 타입체크 검증 (프로젝트에 자동 테스트 없음 — 구조 검증은 tsc, 동작 검증은 수동 QA)

**Spec:** `docs/superpowers/specs/2026-04-20-ds-sync-inline-comment-design.md`

---

## File Structure

| 파일 | 생성/수정 | 책임 |
|------|----------|------|
| `src/shared/types.ts` | 수정 | IPC 채널/WS 메시지 타입/payload/ChatMessage 확장 |
| `src/main/ds-sync-service.ts` | 생성 | DS sync 오케스트레이터 (쿨다운, 병렬, 재시도 X) |
| `src/main/inline-comment-handler.ts` | 생성 | 플러그인 inline_comment → orchestrator + renderer 브로드캐스트 |
| `src/main/settings-store.ts` | 수정 | `lastDSSyncAt` 저장/읽기 |
| `src/main/figma-ws-server.ts` | 수정 | `inline_comment` 케이스 분기 + progress_update broadcast 메서드 |
| `src/main/agent-orchestrator.ts` | 수정 | `sendMessage` 시그니처에 `opts` 추가, inlineContext를 content prefix로 주입 |
| `src/main/index.ts` | 수정 | DSSyncService/InlineCommentHandler 인스턴스화, IPC 핸들러 등록, pre-sync 훅 |
| `src/preload/index.ts` | 수정 | 새 IPC 메서드 노출 (requestDSSync, onDSSyncStatus, onInlineComment) |
| `src/figma-plugin/code.js` | 수정 | `figma.on("selectionchange")` 훅 + UI ↔ plugin 메시지 중계 |
| `src/figma-plugin/ui.html` | 수정 | selection-section + comment-input + progress UI + WS send 로직 |
| `src/renderer/hooks/useAgent.ts` | 수정 | electronAPI 타입 확장, INLINE_COMMENT_RECEIVED/DS_SYNC_STATUS 구독 |
| `src/renderer/components/ChatPanel.tsx` | 수정 | ChatMessage에 `inlineContext` 있으면 📌 배지 렌더링 |
| `src/renderer/components/SettingsPanel.tsx` | 수정 | "Sync DS" 버튼 + 마지막 sync 시각 + 상태 표시 |

---

## Task 1: 공통 타입과 IPC/WS 채널 추가

**Files:**
- Modify: `src/shared/types.ts`

- [ ] **Step 1: `IPC_CHANNELS`에 새 채널 3개 추가**

`src/shared/types.ts` line 70-108의 `IPC_CHANNELS` 객체를 수정:

```ts
export const IPC_CHANNELS = {
  // ... 기존 채널 유지 ...

  // DS Sync (신규)
  DS_SYNC_REQUEST: 'ds-sync:request',
  DS_SYNC_STATUS: 'ds-sync:status',

  // Inline Comment (신규)
  INLINE_COMMENT_RECEIVED: 'inline-comment:received',
} as const;
```

- [ ] **Step 2: 새 타입 3개 추가 (파일 하단에 append)**

`src/shared/types.ts` 끝에 추가:

```ts
// --- DS Sync Types ---

export type DSSyncPhase = 'idle' | 'syncing' | 'error';

export interface DSSyncResult {
  ok: boolean;
  githubTokens: { ok: boolean; error?: string; durationMs: number };
  figmaComponents: {
    ok: boolean;
    error?: string;
    durationMs: number;
    counts?: { components: number; variants: number };
  };
  skipped?: 'cooldown' | 'in-flight' | 'figma-not-connected';
}

export interface DSSyncStatusEvent {
  phase: DSSyncPhase;
  lastSyncAt: number | null;  // epoch ms
  lastResult?: DSSyncResult;
}

// --- Inline Comment Types ---

export interface InlineCommentPayload {
  nodeId: string;
  name: string;
  nodeType: string;  // 'FRAME' | 'TEXT' | 'RECTANGLE' | ...
  comment: string;
  timestamp: number;
}
```

- [ ] **Step 3: `ChatMessage`에 `inlineContext` 필드 추가**

`src/shared/types.ts` line 37-45의 `ChatMessage` 인터페이스 수정:

```ts
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  agentId?: string;
  toolCalls?: ToolCallInfo[];
  attachments?: AttachmentData[];
  inlineContext?: {               // 신규
    nodeId: string;
    name: string;
    nodeType: string;
  };
}
```

- [ ] **Step 4: 구조 검증 (타입체크)**

Run: `cd /Users/julee/figma-design-agent && npm run build`
Expected: 에러 없이 빌드 성공 (새 타입은 아직 사용처 없으니 경고/에러 없음)

- [ ] **Step 5: 커밋**

```bash
git add src/shared/types.ts
git commit -m "feat(types): DS sync + inline comment 타입 및 IPC 채널 추가"
```

---

## Task 2: settings-store에 lastDSSyncAt 추가

**Files:**
- Modify: `src/main/settings-store.ts`

- [ ] **Step 1: `SettingsData` 확장**

`src/main/settings-store.ts` line 14-17의 `SettingsData` 인터페이스 수정:

```ts
interface SettingsData {
  geminiApiKey?: string;
  anthropicApiKey?: string;
  lastDSSyncAt?: number;  // epoch ms
}
```

- [ ] **Step 2: getter/setter 함수 추가**

`src/main/settings-store.ts` 파일 끝(`setAnthropicApiKey` 바로 아래)에 추가:

```ts
// ============================================================
// DS Sync Timestamp
// ============================================================

export function getLastDSSyncAt(): number | null {
  const v = readSettings().lastDSSyncAt;
  return typeof v === 'number' ? v : null;
}

export function setLastDSSyncAt(epochMs: number): void {
  const data = readSettings();
  data.lastDSSyncAt = epochMs;
  writeSettings(data);
}
```

- [ ] **Step 3: 검증**

Run: `cd /Users/julee/figma-design-agent && npm run build`
Expected: 빌드 성공.

- [ ] **Step 4: 커밋**

```bash
git add src/main/settings-store.ts
git commit -m "feat(settings): lastDSSyncAt getter/setter 추가"
```

---

## Task 3: DSSyncService 스켈레톤 + 쿨다운/in-flight 로직

**Files:**
- Create: `src/main/ds-sync-service.ts`

- [ ] **Step 1: 파일 생성 — 스켈레톤 + 동시성 제어**

`src/main/ds-sync-service.ts` (신규):

```ts
/**
 * DSSyncService — Design System 자동 동기화
 *
 * 1. GitHub tokens (sync-tokens-from-github.sh 래핑) → ds/DESIGN_TOKENS.md, ds/TOKEN_MAP.json
 * 2. Figma local components/variants → ds/DS_COMPONENT_DOCS.json, ds/ds-1-variants.jsonl
 * 3. invalidateDSCaches()로 인메모리 캐시 플러시
 *
 * 트리거: Electron app ready, orchestrator.sendMessage pre-sync, 수동 "Sync Now"
 * 쿨다운: 5분. force=true면 우회.
 * 실패: stale 사용, 로그만, 빌드 중단 X.
 */

import { EventEmitter } from 'events';
import type { DSSyncPhase, DSSyncResult, DSSyncStatusEvent } from '../shared/types';
import { getLastDSSyncAt, setLastDSSyncAt } from './settings-store';

const COOLDOWN_MS = 5 * 60 * 1000;  // 5분

export class DSSyncService extends EventEmitter {
  private phase: DSSyncPhase = 'idle';
  private inflight: Promise<DSSyncResult> | null = null;
  private lastResult: DSSyncResult | null = null;

  constructor() {
    super();
  }

  getPhase(): DSSyncPhase {
    return this.phase;
  }

  getLastSyncAt(): number | null {
    return getLastDSSyncAt();
  }

  getLastResult(): DSSyncResult | null {
    return this.lastResult;
  }

  /**
   * 동기화 실행. force=false면 쿨다운 내에서는 skip.
   * 동시 호출 시 진행 중인 Promise 공유 (in-flight 보호).
   */
  async sync(opts?: { force?: boolean }): Promise<DSSyncResult> {
    const force = opts?.force ?? false;

    // In-flight 공유
    if (this.inflight) {
      console.log('[DSSync] Already in-flight, returning existing promise');
      return this.inflight;
    }

    // 쿨다운 체크
    const lastAt = getLastDSSyncAt();
    if (!force && lastAt !== null && Date.now() - lastAt < COOLDOWN_MS) {
      const remainSec = Math.ceil((COOLDOWN_MS - (Date.now() - lastAt)) / 1000);
      console.log(`[DSSync] Skipped (cooldown, ${remainSec}s left)`);
      const skipped: DSSyncResult = {
        ok: true,
        githubTokens: { ok: true, durationMs: 0 },
        figmaComponents: { ok: true, durationMs: 0 },
        skipped: 'cooldown',
      };
      return skipped;
    }

    this.inflight = this.runSync();
    try {
      const result = await this.inflight;
      this.lastResult = result;
      return result;
    } finally {
      this.inflight = null;
    }
  }

  private async runSync(): Promise<DSSyncResult> {
    this.setPhase('syncing');

    // 실제 작업은 Task 4, 5에서 구현. 현재는 플레이스홀더.
    const result: DSSyncResult = {
      ok: true,
      githubTokens: { ok: true, durationMs: 0 },
      figmaComponents: { ok: true, durationMs: 0 },
    };

    setLastDSSyncAt(Date.now());
    this.setPhase('idle');
    return result;
  }

  private setPhase(phase: DSSyncPhase): void {
    this.phase = phase;
    const event: DSSyncStatusEvent = {
      phase,
      lastSyncAt: getLastDSSyncAt(),
      lastResult: this.lastResult || undefined,
    };
    this.emit('status', event);
  }
}
```

- [ ] **Step 2: 검증**

Run: `cd /Users/julee/figma-design-agent && npm run build`
Expected: 빌드 성공.

- [ ] **Step 3: 커밋**

```bash
git add src/main/ds-sync-service.ts
git commit -m "feat(ds-sync): DSSyncService 스켈레톤 + 쿨다운/in-flight 로직"
```

---

## Task 4: DSSyncService — GitHub tokens sync 구현

**Files:**
- Modify: `src/main/ds-sync-service.ts`

- [ ] **Step 1: `runSync` 내 GitHub 단계 구현**

`src/main/ds-sync-service.ts`의 `runSync` 메서드를 아래처럼 교체:

```ts
private async runSync(): Promise<DSSyncResult> {
  this.setPhase('syncing');

  // 병렬 실행 준비
  const t0 = Date.now();
  const githubPromise = this.syncGitHubTokens();
  // Figma는 Task 5에서 추가. 지금은 placeholder.
  const figmaPromise: Promise<DSSyncResult['figmaComponents']> = Promise.resolve({
    ok: true,
    durationMs: 0,
  });

  const [githubRes, figmaRes] = await Promise.all([githubPromise, figmaPromise]);

  const result: DSSyncResult = {
    ok: githubRes.ok || figmaRes.ok,  // 한쪽이라도 성공하면 ok (stale 허용)
    githubTokens: githubRes,
    figmaComponents: figmaRes,
  };

  setLastDSSyncAt(Date.now());
  this.setPhase('idle');
  console.log(`[DSSync] Complete in ${Date.now() - t0}ms`, result);
  return result;
}

private syncGitHubTokens(): Promise<DSSyncResult['githubTokens']> {
  return new Promise((resolve) => {
    const start = Date.now();
    const { exec } = require('child_process') as typeof import('child_process');
    const path = require('path') as typeof import('path');

    // 프로젝트 루트를 기준으로 스크립트 경로 해석
    const scriptPath = path.resolve(__dirname, '..', '..', 'scripts', 'sync-tokens-from-github.sh');

    exec(`bash "${scriptPath}"`, { timeout: 60_000 }, (err, stdout, stderr) => {
      const durationMs = Date.now() - start;
      if (err) {
        console.warn('[DSSync][GitHub] failed:', err.message);
        if (stderr) console.warn('[DSSync][GitHub] stderr:', stderr.slice(0, 500));
        resolve({ ok: false, error: err.message, durationMs });
        return;
      }
      console.log(`[DSSync][GitHub] ok in ${durationMs}ms`);
      resolve({ ok: true, durationMs });
    });
  });
}
```

- [ ] **Step 2: 검증 (타입체크)**

Run: `cd /Users/julee/figma-design-agent && npm run build`
Expected: 빌드 성공.

- [ ] **Step 3: 수동 테스트 — 스크립트 수동 실행**

Run: `bash /Users/julee/figma-design-agent/scripts/sync-tokens-from-github.sh`
Expected: `ds/DESIGN_TOKENS.md`, `ds/TOKEN_MAP.json`가 갱신됨 (git status로 확인). 네트워크 이슈가 있으면 에러 메시지 확인.

- [ ] **Step 4: 커밋**

```bash
git add src/main/ds-sync-service.ts
git commit -m "feat(ds-sync): GitHub tokens sync 래핑"
```

---

## Task 5: DSSyncService — Figma components/variants sync 구현

**Files:**
- Modify: `src/main/ds-sync-service.ts`

- [ ] **Step 1: FigmaWS 의존성을 생성자에 추가**

`src/main/ds-sync-service.ts`의 import 및 constructor 교체:

```ts
import { EventEmitter } from 'events';
import { writeFileSync, readFileSync, existsSync, copyFileSync, mkdirSync } from 'fs';
import { join, dirname, resolve } from 'path';
import type { DSSyncPhase, DSSyncResult, DSSyncStatusEvent } from '../shared/types';
import { getLastDSSyncAt, setLastDSSyncAt } from './settings-store';
import type { FigmaWSServer } from './figma-ws-server';
import { invalidateDSCaches } from '../shared/ds-data';

const COOLDOWN_MS = 5 * 60 * 1000;

export class DSSyncService extends EventEmitter {
  private phase: DSSyncPhase = 'idle';
  private inflight: Promise<DSSyncResult> | null = null;
  private lastResult: DSSyncResult | null = null;

  constructor(
    private readonly figmaWS: FigmaWSServer,
    private readonly projectRoot: string,
  ) {
    super();
  }

  // getPhase/getLastSyncAt/getLastResult/sync는 기존 그대로 유지
  // (Task 3에서 작성한 코드 유지)
```

- [ ] **Step 2: `syncFigmaComponents` 메서드 추가**

`syncGitHubTokens` 바로 아래에 추가:

```ts
private async syncFigmaComponents(): Promise<DSSyncResult['figmaComponents']> {
  const start = Date.now();

  if (!this.figmaWS.isConnected) {
    console.log('[DSSync][Figma] Skipped (not connected)');
    return { ok: false, error: 'figma-not-connected', durationMs: 0 };
  }

  try {
    const [components, componentSets] = await Promise.all([
      this.figmaWS.sendCommand('get_local_components'),
      this.figmaWS.sendCommand('get_local_component_sets'),
    ]);

    const compCount = Array.isArray(components) ? components.length : 0;
    const setCount = Array.isArray(componentSets) ? componentSets.length : 0;
    console.log(`[DSSync][Figma] got ${compCount} components, ${setCount} sets`);

    // 기존 파일 백업 (롤백 대비)
    const dsDir = join(this.projectRoot, 'ds');
    const docsPath = join(dsDir, 'DS_COMPONENT_DOCS.json');
    const variantsPath = join(dsDir, 'ds-1-variants.jsonl');
    this.backupFile(docsPath);
    this.backupFile(variantsPath);

    // DS_COMPONENT_DOCS.json 덮어쓰기 (Figma 원본 구조 유지)
    const docsPayload = {
      fetchedAt: new Date().toISOString(),
      components,
      componentSets,
    };
    writeFileSync(docsPath, JSON.stringify(docsPayload, null, 2), 'utf-8');

    // ds-1-variants.jsonl 덮어쓰기 (각 componentSet을 한 줄씩)
    const jsonlLines = (Array.isArray(componentSets) ? componentSets : [])
      .map((set) => JSON.stringify(set))
      .join('\n');
    writeFileSync(variantsPath, jsonlLines, 'utf-8');

    return {
      ok: true,
      durationMs: Date.now() - start,
      counts: { components: compCount, variants: setCount },
    };
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    console.warn('[DSSync][Figma] failed:', msg);
    return { ok: false, error: msg, durationMs: Date.now() - start };
  }
}

private backupFile(filePath: string): void {
  try {
    if (existsSync(filePath)) {
      const backupPath = filePath + '.bak';
      copyFileSync(filePath, backupPath);
    }
  } catch (e) {
    console.warn('[DSSync] backup failed for', filePath, e);
  }
}
```

- [ ] **Step 3: `runSync`에서 Figma 호출과 캐시 무효화 연결**

`runSync` 내부의 placeholder `figmaPromise`를 실제 호출로 교체, 완료 후 `invalidateDSCaches()` 호출:

```ts
private async runSync(): Promise<DSSyncResult> {
  this.setPhase('syncing');

  const t0 = Date.now();
  const githubPromise = this.syncGitHubTokens();
  const figmaPromise = this.syncFigmaComponents();

  const [githubRes, figmaRes] = await Promise.all([githubPromise, figmaPromise]);

  // 한쪽이라도 성공하면 캐시 무효화
  if (githubRes.ok || figmaRes.ok) {
    invalidateDSCaches();
  }

  const result: DSSyncResult = {
    ok: githubRes.ok || figmaRes.ok,
    githubTokens: githubRes,
    figmaComponents: figmaRes,
  };

  setLastDSSyncAt(Date.now());
  this.setPhase('idle');
  console.log(`[DSSync] Complete in ${Date.now() - t0}ms`, {
    github: githubRes.ok,
    figma: figmaRes.ok,
  });
  return result;
}
```

- [ ] **Step 4: 검증**

Run: `cd /Users/julee/figma-design-agent && npm run build`
Expected: 빌드 성공.

- [ ] **Step 5: 커밋**

```bash
git add src/main/ds-sync-service.ts
git commit -m "feat(ds-sync): Figma components/variants 추출 + 캐시 무효화"
```

---

## Task 6: IPC 핸들러 등록 + 앱 시작 시 sync 트리거

**Files:**
- Modify: `src/main/index.ts`

- [ ] **Step 1: DSSyncService 인스턴스화 + IPC 핸들러 등록**

`src/main/index.ts`의 import 블록 상단 근처에 추가:

```ts
import { DSSyncService } from './ds-sync-service';
```

app ready 이후 `figmaWS`가 이미 초기화되어 있는 위치(주로 `app.whenReady().then(...)` 콜백 안)에 추가. 검색어: `figmaWS = new FigmaWSServer`. 그 바로 뒤에:

```ts
// DS Sync Service
const dsSyncService = new DSSyncService(figmaWS, PROJECT_ROOT);
dsSyncService.on('status', (status) => {
  mainWindow?.webContents.send(IPC_CHANNELS.DS_SYNC_STATUS, status);
});

// 앱 시작 시 백그라운드 sync (쿨다운 내면 skip)
dsSyncService.sync({ force: false }).catch((e) => {
  console.warn('[Main] Initial DS sync failed:', e);
});

// 수동 sync 요청 IPC
ipcMain.handle(IPC_CHANNELS.DS_SYNC_REQUEST, async () => {
  return await dsSyncService.sync({ force: true });
});
```

`dsSyncService`를 `setupIPC`에서도 참조하려면, 모듈 스코프 `let dsSyncService: DSSyncService | null = null;` 선언 후 위 코드에서 `dsSyncService = new ...`로 할당. (기존 `orchestrator`, `figmaWS` 패턴과 동일)

- [ ] **Step 2: 검증 (빌드)**

Run: `cd /Users/julee/figma-design-agent && npm run build`
Expected: 빌드 성공.

- [ ] **Step 3: 수동 스모크 테스트**

Run: `cd /Users/julee/figma-design-agent && npm run dev`
Expected 로그:
- 콘솔에 `[DSSync] ...` 라인이 뜸
- Figma 연결 안 된 상태라면 `[DSSync][Figma] Skipped (not connected)` 나옴
- GitHub 쪽은 성공/실패 각각 한 줄

앱 창이 열리면 닫음 (`Cmd+Q`).

- [ ] **Step 4: 커밋**

```bash
git add src/main/index.ts
git commit -m "feat(main): DSSyncService 연결 + app ready 자동 sync + 수동 IPC"
```

---

## Task 7: Preload + useAgent에 DS sync API 노출

**Files:**
- Modify: `src/preload/index.ts`
- Modify: `src/renderer/hooks/useAgent.ts`

- [ ] **Step 1: preload에 `requestDSSync`, `onDSSyncStatus` 추가**

`src/preload/index.ts`의 `ElectronAPI` 인터페이스에 추가:

```ts
  // DS Sync
  requestDSSync: () => Promise<import('../shared/types').DSSyncResult>;
  onDSSyncStatus: (
    callback: (status: import('../shared/types').DSSyncStatusEvent) => void
  ) => () => void;
```

`contextBridge.exposeInMainWorld` 객체에 구현 추가 (DS Cache 근처):

```ts
  // DS Sync
  requestDSSync: () => {
    return ipcRenderer.invoke(IPC_CHANNELS.DS_SYNC_REQUEST);
  },
  onDSSyncStatus: (callback) => {
    const handler = (_: unknown, status: unknown) =>
      callback(status as import('../shared/types').DSSyncStatusEvent);
    ipcRenderer.on(IPC_CHANNELS.DS_SYNC_STATUS, handler);
    return () => ipcRenderer.removeListener(IPC_CHANNELS.DS_SYNC_STATUS, handler);
  },
```

- [ ] **Step 2: useAgent에 타입/구독 추가**

`src/renderer/hooks/useAgent.ts` line 1-31의 `declare global` 블록의 electronAPI 타입에 추가:

```ts
      requestDSSync: () => Promise<import('../../shared/types').DSSyncResult>;
      onDSSyncStatus: (
        callback: (status: import('../../shared/types').DSSyncStatusEvent) => void
      ) => () => void;
```

그리고 state + subscription 추가. `useAgent` 함수 내 `const [pipelineSteps, ...] = ...` 아래에 추가:

```ts
  const [dsSyncStatus, setDSSyncStatus] = useState<
    import('../../shared/types').DSSyncStatusEvent
  >({ phase: 'idle', lastSyncAt: null });
```

`useEffect` 내 cleanups 배열 누적 후반부에 추가 (DS Cache 구독 근처):

```ts
    // DS sync status
    cleanups.push(api.onDSSyncStatus((status) => {
      setDSSyncStatus(status);
    }));
```

마지막 `return { ... }` 객체에 추가:

```ts
    dsSyncStatus,
    requestDSSync: () => window.electronAPI?.requestDSSync(),
```

- [ ] **Step 3: 검증**

Run: `cd /Users/julee/figma-design-agent && npm run build`
Expected: 빌드 성공.

- [ ] **Step 4: 커밋**

```bash
git add src/preload/index.ts src/renderer/hooks/useAgent.ts
git commit -m "feat(renderer): DS sync API preload/hook 노출"
```

---

## Task 8: SettingsPanel에 Sync Now 버튼 + 상태 표시

**Files:**
- Modify: `src/renderer/components/SettingsPanel.tsx`

- [ ] **Step 1: 현재 SettingsPanel 구조 확인**

Read `/Users/julee/figma-design-agent/src/renderer/components/SettingsPanel.tsx` 상단 ~60줄. 기존 Gemini API Key 섹션의 JSX/state 패턴 파악 후 그 패턴을 다음 단계에서 재사용.

- [ ] **Step 2: DS Sync 섹션 추가**

SettingsPanel 컴포넌트 내부에서 (기존 Gemini 키 섹션 **아래**에) 아래 JSX 블록을 추가. state/hook은 파일 상단에 선언:

```tsx
// 파일 상단 import 블록에 추가
import { useAgent } from '../hooks/useAgent';

// 컴포넌트 내부 (기존 훅 사용 지점 옆)
const { dsSyncStatus, requestDSSync } = useAgent();
const [syncing, setSyncing] = useState(false);

const handleSyncNow = async () => {
  setSyncing(true);
  try {
    const res = await requestDSSync?.();
    console.log('[SettingsPanel] manual sync result:', res);
  } finally {
    setSyncing(false);
  }
};

const lastSyncLabel = (() => {
  if (!dsSyncStatus.lastSyncAt) return 'Never';
  const seconds = Math.floor((Date.now() - dsSyncStatus.lastSyncAt) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  return new Date(dsSyncStatus.lastSyncAt).toLocaleString();
})();
```

JSX 블록 (Gemini 섹션 아래):

```tsx
<section className="settings-section">
  <h3>Design System Sync</h3>
  <div className="ds-sync-row">
    <div className="ds-sync-info">
      <div>Status: {dsSyncStatus.phase}</div>
      <div>Last sync: {lastSyncLabel}</div>
      {dsSyncStatus.lastResult?.figmaComponents?.counts && (
        <div className="muted">
          {dsSyncStatus.lastResult.figmaComponents.counts.components} components,
          {' '}{dsSyncStatus.lastResult.figmaComponents.counts.variants} variant sets
        </div>
      )}
    </div>
    <button
      onClick={handleSyncNow}
      disabled={syncing || dsSyncStatus.phase === 'syncing'}
    >
      {syncing || dsSyncStatus.phase === 'syncing' ? 'Syncing...' : 'Sync Now'}
    </button>
  </div>
</section>
```

경고: `useAgent`는 App 레벨 훅이라 SettingsPanel에서 재호출 시 별도 구독 인스턴스가 생긴다. 기존 App.tsx가 useAgent 결과를 props로 내려주는 패턴이라면, 그 패턴을 따라 `dsSyncStatus`와 `requestDSSync`를 props로 전달하도록 수정. 파일 열어 확인 후 패턴 맞출 것.

- [ ] **Step 3: 검증**

Run: `cd /Users/julee/figma-design-agent && npm run build`
Expected: 빌드 성공. TypeScript 에러가 나오면 props 타입 정의를 App→SettingsPanel에 맞춰 조정.

- [ ] **Step 4: 수동 스모크 테스트**

Run: `cd /Users/julee/figma-design-agent && npm run dev`
Settings 패널 열어서 "Sync Now" 버튼이 표시되는지, 누르면 "Syncing..." 상태로 바뀌고 완료 후 복귀하는지 확인.

- [ ] **Step 5: 커밋**

```bash
git add src/renderer/components/SettingsPanel.tsx
git commit -m "feat(ui): SettingsPanel에 DS Sync Now 버튼 + 상태 표시"
```

---

## Task 9: orchestrator.sendMessage 시그니처 확장 + inlineContext 주입

**Files:**
- Modify: `src/main/agent-orchestrator.ts`

- [ ] **Step 1: 시그니처 확장**

`src/main/agent-orchestrator.ts` line 129-161의 `sendMessage` 메서드 교체:

```ts
/** Send a user message and run the agent loop */
async sendMessage(
  userMessage: string,
  attachments?: AttachmentData[],
  opts?: {
    inlineContext?: {
      nodeId: string;
      name: string;
      nodeType: string;
    };
  },
): Promise<void> {
  if (this.busy) {
    console.warn('[Agent] sendMessage called while busy — ignoring');
    this.emitEvent('orchestrator', 'error', { error: '이전 요청이 아직 처리 중입니다.' });
    return;
  }

  this.busy = true;
  this.abortController = new AbortController();

  // inlineContext 있으면 메시지 본문 앞에 prefix 붙임 (Claude가 인식할 수 있도록)
  const effectiveMessage = opts?.inlineContext
    ? `[Inline context: Node "${opts.inlineContext.name}" (${opts.inlineContext.nodeType}, id="${opts.inlineContext.nodeId}")]\n\n${userMessage}`
    : userMessage;

  // Emit user message — inlineContext는 ChatMessage에 붙여 UI에서 배지 렌더링
  this.emitChatMessage({
    id: uuidv4(),
    role: 'user',
    content: userMessage,  // UI에는 원본 사용자 메시지만 (prefix는 agent만 봄)
    timestamp: Date.now(),
    attachments,
    inlineContext: opts?.inlineContext,
  });

  try {
    if (this.useAgentSdk) {
      await this.sendAgentSdkMessage(effectiveMessage, attachments);
    } else if (this.pipeline) {
      await this.runPipelineMode(effectiveMessage, attachments);
    } else {
      await this.runDirectApiLoop(effectiveMessage, attachments);
    }
  } finally {
    this.busy = false;
  }
}
```

- [ ] **Step 2: 검증**

Run: `cd /Users/julee/figma-design-agent && npm run build`
Expected: 빌드 성공.

- [ ] **Step 3: 커밋**

```bash
git add src/main/agent-orchestrator.ts
git commit -m "feat(orchestrator): inlineContext opt + 메시지 prefix 주입"
```

---

## Task 10: orchestrator pre-sync 훅 (main/index.ts)

**Files:**
- Modify: `src/main/index.ts`

- [ ] **Step 1: AGENT_SEND_MESSAGE 핸들러에 pre-sync 삽입**

`src/main/index.ts`의 `ipcMain.on(IPC_CHANNELS.AGENT_SEND_MESSAGE, ...)` 핸들러 내부에서 `await orchestrator.sendMessage(...)` 호출 **직전**에 pre-sync 로직 추가 (line ~462 부근):

```ts
try {
  // PRD 등 첨부가 있으면 디자인 빌드 흐름 → DS sync 선행
  if (attachments && attachments.length > 0 && dsSyncService) {
    try {
      await dsSyncService.sync({ force: false });  // 쿨다운 내면 skip
    } catch (e) {
      console.warn('[Main] pre-sync DS failed (continuing with stale):', e);
    }
  }

  await orchestrator.sendMessage(message, attachments);
} catch (error) {
  mainWindow?.webContents.send(IPC_CHANNELS.APP_ERROR,
    error instanceof Error ? error.message : String(error)
  );
}
```

- [ ] **Step 2: 검증**

Run: `cd /Users/julee/figma-design-agent && npm run build`
Expected: 빌드 성공.

- [ ] **Step 3: 수동 스모크 테스트**

Run: `cd /Users/julee/figma-design-agent && npm run dev`
- PRD 문서 없는 일반 메시지 전송: pre-sync 로그 안 뜸
- 임의 파일 attach 후 전송: `[DSSync] ...` 로그 뜸 (처음 한 번만, 두 번째는 쿨다운 skip)

- [ ] **Step 4: 커밋**

```bash
git add src/main/index.ts
git commit -m "feat(main): attachments 존재 시 orchestrator 진입 전 DS 선-동기화"
```

---

## Task 11: Figma 플러그인 — selectionchange 훅 + UI 메시지

**Files:**
- Modify: `src/figma-plugin/code.js`

- [ ] **Step 1: selectionchange 리스너 추가**

`src/figma-plugin/code.js`에서 초기화 영역 (기존 `figma.showUI(...)` 호출 부근) 바로 아래에 추가. 정확한 라인은 편집 시 파일 하단 searchlight로 확인하지만, 일반적으로 plugin boot 섹션에 위치:

```js
// Inline comment: selection change -> UI
function postSelectionToUI() {
  var sel = figma.currentPage.selection;
  if (sel.length === 0) {
    figma.ui.postMessage({ type: 'selection-info', payload: null });
    return;
  }
  var node = sel[0];
  figma.ui.postMessage({
    type: 'selection-info',
    payload: {
      id: node.id,
      name: node.name,
      type: node.type,
    },
  });
}

figma.on('selectionchange', postSelectionToUI);
// 초기 1회 푸시 (플러그인 열릴 때 현재 선택 상태를 UI에 반영)
postSelectionToUI();
```

**주의**: `code.js`는 Figma 샌드박스라 optional chaining (`?.`) 사용 금지. 위 코드는 준수.

- [ ] **Step 2: UI → plugin 메시지 라우팅 확인 (inline_comment WS 발송은 ui.html에서 직접 함)**

`code.js`는 WS 연결이 없음 (WS는 ui.html 쪽). 따라서 code.js의 `figma.ui.onmessage` 에서는 `inline_comment`를 plugin이 처리할 일은 없음. 기존 핸들러 그대로 유지.

- [ ] **Step 3: 수동 테스트 — 플러그인 리로드 후 selection 감지**

Run: `cd /Users/julee/figma-design-agent && npm run dev` 후 Figma 데스크톱에서 플러그인 리로드.
DevTools (Figma 플러그인 콘솔)에서 임의 노드 선택 시, UI 쪽 콘솔로 postMessage 로그가 찍히는지 확인. (현재 ui.html에는 아직 수신 핸들러 없음 — 다음 태스크에서 추가)

- [ ] **Step 4: 커밋**

```bash
git add src/figma-plugin/code.js
git commit -m "feat(plugin): selectionchange → UI 메시지 푸시"
```

---

## Task 12: 플러그인 ui.html — 선택 섹션 UI 추가

**Files:**
- Modify: `src/figma-plugin/ui.html`

- [ ] **Step 1: CSS 추가**

`src/figma-plugin/ui.html`의 `<style>` 블록 끝(line ~113, `.ds-loading-text.done {...}` 바로 아래)에 추가:

```css
.selection-section {
  display: none;
  flex-direction: column;
  gap: 8px;
  padding: 10px;
  border: 1px solid #3a3a3a;
  border-radius: 6px;
  background: #252525;
}
.selection-section.visible { display: flex; }
.selection-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
  color: #b0b0b0;
}
.selection-header button {
  background: transparent;
  border: none;
  color: #888;
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
}
.selection-info {
  font-size: 13px;
  color: #e0e0e0;
  word-break: break-all;
}
.selection-info .node-type {
  font-size: 11px;
  color: #888;
  margin-left: 6px;
}
#comment-input {
  width: 100%;
  box-sizing: border-box;
  background: #1a1a1a;
  color: #e0e0e0;
  border: 1px solid #444;
  border-radius: 4px;
  padding: 6px 8px;
  font-family: inherit;
  font-size: 12px;
  resize: vertical;
}
#send-comment {
  background: #7c3aed;
  color: white;
  border: none;
  border-radius: 4px;
  padding: 6px 10px;
  cursor: pointer;
  font-size: 12px;
}
#send-comment:disabled {
  background: #555;
  cursor: not-allowed;
}
.comment-progress {
  display: none;
  align-items: center;
  gap: 8px;
  padding: 8px;
  font-size: 12px;
  color: #fbbf24;
}
.comment-progress.visible { display: flex; }
.spinner {
  width: 12px;
  height: 12px;
  border: 2px solid #555;
  border-top-color: #7c3aed;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
```

- [ ] **Step 2: HTML 마크업 추가**

`<div class="container">` 내부, 기존 `<div id="ds-loading">` 블록 바로 **다음**에 추가:

```html
<div id="selection-section" class="selection-section">
  <div class="selection-header">
    <span>📌 Selected Node</span>
    <button id="clear-selection" title="Clear">×</button>
  </div>
  <div id="selection-info" class="selection-info"></div>
  <textarea id="comment-input" placeholder="이 노드에 대한 수정 지시..." rows="3"></textarea>
  <button id="send-comment" disabled>Send to Claude</button>
</div>
<div id="comment-progress" class="comment-progress">
  <div class="spinner"></div>
  <span id="progress-text">Claude 작업 중...</span>
</div>
```

- [ ] **Step 3: 검증 — 빌드는 없고 시각 확인만**

Run: 플러그인 리로드 후 UI 열림. 아직 selection 없으니 섹션은 보이지 않아야 함 (display: none 기본값).

- [ ] **Step 4: 커밋**

```bash
git add src/figma-plugin/ui.html
git commit -m "feat(plugin-ui): inline comment UI 마크업/스타일 추가"
```

---

## Task 13: 플러그인 ui.html — selection-info 수신 + WS 발송 로직

**Files:**
- Modify: `src/figma-plugin/ui.html`

- [ ] **Step 1: UI state 확장**

`<script>` 블록 내 state 객체 (line ~135)에 필드 추가:

```js
const state = {
  connected: false,
  socket: null,
  channel: null,
  documentId: null,
  documentName: null,
  pendingRequests: new Map(),
  heartbeatInterval: null,
  reconnectTimer: null,
  reconnectAttempts: 0,
  maxReconnectAttempts: Infinity,
  intentionalDisconnect: false,
  currentSelection: null,  // 신규: {id, name, type} | null
};
```

- [ ] **Step 2: UI element 참조 추가**

기존 `const dsLoadingEl = ...` 아래에 추가:

```js
const selectionSectionEl = document.getElementById('selection-section');
const selectionInfoEl = document.getElementById('selection-info');
const commentInputEl = document.getElementById('comment-input');
const sendCommentBtn = document.getElementById('send-comment');
const clearSelectionBtn = document.getElementById('clear-selection');
const commentProgressEl = document.getElementById('comment-progress');
const progressTextEl = document.getElementById('progress-text');
```

- [ ] **Step 3: selection 수신 + UI 갱신 함수**

`<script>` 블록 적당한 위치(UI Update 근처)에 추가:

```js
function updateSelectionUI(selection) {
  state.currentSelection = selection;
  if (!selection) {
    selectionSectionEl.classList.remove('visible');
    commentInputEl.value = '';
    sendCommentBtn.disabled = true;
    return;
  }
  selectionSectionEl.classList.add('visible');
  selectionInfoEl.innerHTML =
    '<span>' + escapeHtml(selection.name) + '</span>' +
    '<span class="node-type">' + escapeHtml(selection.type) + '</span>';
  updateSendButton();
}

function updateSendButton() {
  sendCommentBtn.disabled =
    !state.connected ||
    !state.currentSelection ||
    commentInputEl.value.trim().length === 0;
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, function(c) {
    return { '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c];
  });
}
```

- [ ] **Step 4: plugin → ui 메시지 수신 (window.onmessage)**

기존 `window.onmessage` 핸들러에 `selection-info` 케이스를 추가. 없다면 새로 작성:

```js
window.onmessage = function(event) {
  var msg = event.data.pluginMessage;
  if (!msg) return;
  if (msg.type === 'selection-info') {
    updateSelectionUI(msg.payload);
    return;
  }
  // 기존 다른 케이스들 유지
};
```

**주의**: 기존 onmessage 핸들러에 다른 케이스가 이미 있을 수 있음 — 파일 검색 후 해당 핸들러 내부에 `selection-info` 케이스만 추가. 기존 로직은 유지할 것.

- [ ] **Step 5: 이벤트 리스너 연결 (comment input, send button, clear)**

`<script>` 블록 끝(기존 `connectToServer()` 호출 근처)에 추가:

```js
commentInputEl.addEventListener('input', updateSendButton);

sendCommentBtn.addEventListener('click', function() {
  if (!state.connected || !state.currentSelection) return;
  var comment = commentInputEl.value.trim();
  if (!comment) return;

  state.socket.send(JSON.stringify({
    type: 'inline_comment',
    payload: {
      nodeId: state.currentSelection.id,
      name: state.currentSelection.name,
      nodeType: state.currentSelection.type,
      comment: comment,
      timestamp: Date.now(),
    },
  }));

  // 진행 표시
  commentProgressEl.classList.add('visible');
  progressTextEl.textContent = 'Claude 작업 중...';
  commentInputEl.value = '';
  sendCommentBtn.disabled = true;
});

clearSelectionBtn.addEventListener('click', function() {
  // 선택 자체는 Figma 쪽 상태 — 여기서는 UI만 접음
  updateSelectionUI(null);
});
```

- [ ] **Step 6: connected 상태 변화 시 send 버튼 재평가**

`updateUI` 함수 내부 마지막에 한 줄 추가:

```js
function updateUI(statusClass, dotClass, text, info) {
  statusRow.className = "status-row " + statusClass;
  statusDot.className = "dot " + dotClass;
  statusText.textContent = text;
  if (info) infoText.textContent = info;
  state.connected = statusClass === 'connected';
  updateSendButton();  // 신규
}
```

- [ ] **Step 7: 수동 테스트**

Run: `cd /Users/julee/figma-design-agent && npm run dev`
Figma 플러그인 리로드 → Figma에서 임의 노드 선택 → 플러그인 UI에 "📌 Selected Node" 박스 + 노드 이름/타입 표시 → textarea에 코멘트 입력 → "Send to Claude" 버튼 활성화 → 클릭 시 진행 표시로 전환되는지 확인. 아직 서버 측 처리 없으니 메시지는 전송만 됨.

- [ ] **Step 8: 커밋**

```bash
git add src/figma-plugin/ui.html
git commit -m "feat(plugin-ui): selection 수신 + comment 입력/전송 로직"
```

---

## Task 14: figma-ws-server — inline_comment 케이스 + broadcast 메서드

**Files:**
- Modify: `src/main/figma-ws-server.ts`

- [ ] **Step 1: 핸들러 등록 메커니즘 추가**

`src/main/figma-ws-server.ts`의 `FigmaWSServer` 클래스 최상단 필드 블록에 추가:

```ts
private inlineCommentHandler: ((payload: import('../shared/types').InlineCommentPayload) => void) | null = null;
```

그리고 public setter:

```ts
setInlineCommentHandler(
  handler: (payload: import('../shared/types').InlineCommentPayload) => void
): void {
  this.inlineCommentHandler = handler;
}
```

- [ ] **Step 2: handleMessage에 케이스 추가**

`src/main/figma-ws-server.ts` line 179-232의 `handleMessage` 내부 분기에 (input-mode 케이스 바로 아래에) 추가:

```ts
// Inline comment from plugin UI
if (json.type === 'inline_comment') {
  const payload = json.payload as import('../shared/types').InlineCommentPayload;
  if (!payload || !payload.nodeId || !payload.comment) {
    console.warn('[FigmaWS] inline_comment missing fields');
    return;
  }
  console.log('[FigmaWS] inline_comment received:', payload.nodeId, payload.name);
  if (this.inlineCommentHandler) {
    this.inlineCommentHandler(payload);
  } else {
    console.warn('[FigmaWS] inline_comment received but no handler registered');
  }
  return;
}
```

- [ ] **Step 3: broadcast 메서드 (플러그인에 progress 전달)**

파일 하단 public 메서드 영역에 추가:

```ts
/** Broadcast raw message to the plugin UI (e.g., progress updates from orchestrator) */
broadcastToPlugin(message: Record<string, unknown>): void {
  if (this.pluginSocket && this.pluginSocket.readyState === 1 /* OPEN */) {
    this.pluginSocket.send(JSON.stringify(message));
  }
}
```

- [ ] **Step 4: 검증**

Run: `cd /Users/julee/figma-design-agent && npm run build`
Expected: 빌드 성공.

- [ ] **Step 5: 커밋**

```bash
git add src/main/figma-ws-server.ts
git commit -m "feat(ws): inline_comment 분기 + broadcastToPlugin 메서드"
```

---

## Task 15: InlineCommentHandler 구현

**Files:**
- Create: `src/main/inline-comment-handler.ts`

- [ ] **Step 1: 파일 생성**

`src/main/inline-comment-handler.ts` (신규):

```ts
/**
 * InlineCommentHandler
 *
 * Figma 플러그인 UI에서 발송한 inline_comment WS 메시지를 받아:
 * 1. 렌더러 ChatPanel에 사용자 메시지 broadcast (INLINE_COMMENT_RECEIVED IPC)
 * 2. orchestrator.sendMessage에 inlineContext 포함하여 전달
 * 3. orchestrator 진행 상태를 WS로 플러그인 UI에 피드백 (progress_update)
 *
 * renderer는 INLINE_COMMENT_RECEIVED를 구독하여 메시지를 표시만 함 (재발송 금지 — 중복 실행 방지).
 */

import type { BrowserWindow } from 'electron';
import type { AgentOrchestrator } from './agent-orchestrator';
import type { FigmaWSServer } from './figma-ws-server';
import type { InlineCommentPayload } from '../shared/types';
import { IPC_CHANNELS } from '../shared/types';

export class InlineCommentHandler {
  constructor(
    private readonly getOrchestrator: () => AgentOrchestrator | null,
    private readonly getMainWindow: () => BrowserWindow | null,
    private readonly wsServer: FigmaWSServer,
  ) {
    // orchestrator가 이미 존재하면 agent-event 구독해서 WS progress_update 브로드캐스트
    // (아직 없으면 main에서 orchestrator 생성 직후 bind 호출)
  }

  async handle(payload: InlineCommentPayload): Promise<void> {
    // 1. 렌더러에 user 메시지로 표시하도록 알림
    const mainWindow = this.getMainWindow();
    mainWindow?.webContents.send(IPC_CHANNELS.INLINE_COMMENT_RECEIVED, payload);

    // 2. orchestrator 준비 (없으면 에러만 플러그인으로)
    const orchestrator = this.getOrchestrator();
    if (!orchestrator) {
      console.warn('[InlineComment] orchestrator not ready');
      this.wsServer.broadcastToPlugin({
        type: 'progress_update',
        context: 'inline_comment',
        phase: 'error',
        message: 'Orchestrator not ready',
      });
      return;
    }

    // 3. orchestrator 호출
    try {
      this.wsServer.broadcastToPlugin({
        type: 'progress_update',
        context: 'inline_comment',
        phase: 'thinking',
      });

      await orchestrator.sendMessage(payload.comment, undefined, {
        inlineContext: {
          nodeId: payload.nodeId,
          name: payload.name,
          nodeType: payload.nodeType,
        },
      });

      this.wsServer.broadcastToPlugin({
        type: 'progress_update',
        context: 'inline_comment',
        phase: 'done',
      });
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      console.warn('[InlineComment] orchestrator failed:', msg);
      this.wsServer.broadcastToPlugin({
        type: 'progress_update',
        context: 'inline_comment',
        phase: 'error',
        message: msg,
      });
    }
  }
}
```

- [ ] **Step 2: 검증**

Run: `cd /Users/julee/figma-design-agent && npm run build`
Expected: 빌드 성공.

- [ ] **Step 3: 커밋**

```bash
git add src/main/inline-comment-handler.ts
git commit -m "feat(inline-comment): handler 모듈 추가"
```

---

## Task 16: main/index.ts에서 InlineCommentHandler 연결

**Files:**
- Modify: `src/main/index.ts`

- [ ] **Step 1: import 추가**

상단 import 블록에 추가:

```ts
import { InlineCommentHandler } from './inline-comment-handler';
```

- [ ] **Step 2: 인스턴스화 및 WS 핸들러 등록**

`figmaWS = new FigmaWSServer(...)` 생성 직후, `dsSyncService` 생성과 같은 위치에 추가:

```ts
const inlineCommentHandler = new InlineCommentHandler(
  () => orchestrator,           // orchestrator는 lazy 생성이라 getter로
  () => mainWindow,
  figmaWS,
);
figmaWS.setInlineCommentHandler((payload) => {
  inlineCommentHandler.handle(payload).catch((e) =>
    console.warn('[Main] inline comment handler failed:', e)
  );
});
```

- [ ] **Step 3: 검증**

Run: `cd /Users/julee/figma-design-agent && npm run build`
Expected: 빌드 성공. 타입 오류 시: `orchestrator`가 `let orchestrator: AgentOrchestrator | null = null;`로 선언되어 있는지 확인, `mainWindow`는 `BrowserWindow | null`인지 확인. 타입 불일치 시 getter return 타입에 `| null` 추가.

- [ ] **Step 4: 커밋**

```bash
git add src/main/index.ts
git commit -m "feat(main): InlineCommentHandler 연결 + WS 핸들러 등록"
```

---

## Task 17: Preload + useAgent — INLINE_COMMENT_RECEIVED 구독

**Files:**
- Modify: `src/preload/index.ts`
- Modify: `src/renderer/hooks/useAgent.ts`

- [ ] **Step 1: preload에 onInlineComment 추가**

`src/preload/index.ts`의 `ElectronAPI` 인터페이스에 추가:

```ts
  // Inline Comment
  onInlineComment: (
    callback: (payload: import('../shared/types').InlineCommentPayload) => void
  ) => () => void;
```

`contextBridge.exposeInMainWorld` 객체에 구현:

```ts
  // Inline Comment
  onInlineComment: (callback) => {
    const handler = (_: unknown, payload: unknown) =>
      callback(payload as import('../shared/types').InlineCommentPayload);
    ipcRenderer.on(IPC_CHANNELS.INLINE_COMMENT_RECEIVED, handler);
    return () => ipcRenderer.removeListener(IPC_CHANNELS.INLINE_COMMENT_RECEIVED, handler);
  },
```

- [ ] **Step 2: useAgent에 타입 추가**

`src/renderer/hooks/useAgent.ts`의 electronAPI 타입 블록에 추가:

```ts
      onInlineComment: (
        callback: (payload: import('../../shared/types').InlineCommentPayload) => void
      ) => () => void;
```

- [ ] **Step 3: useAgent 내부에서 구독**

`useEffect` 내 cleanups 배열 끝부분에 추가 (Errors 구독 위):

```ts
    // Inline comment (플러그인에서 트리거된 메시지를 ChatPanel에 표시용으로만)
    cleanups.push(api.onInlineComment((payload) => {
      // 주의: orchestrator는 이미 main에서 호출됨. 여기서는 표시용 메시지 추가만.
      // 메인이 emitChatMessage를 이미 발생시키므로 onChatUpdate가 커버함.
      // 이 구독은 로그용으로만 유지 (향후 배지/토스트 확장 대비).
      console.log('[Renderer] inline comment received from plugin:', payload);
    }));
```

**이유**: 메인이 이미 `orchestrator.emitChatMessage(...)`로 `AGENT_CHAT_UPDATE`를 발생시켜 `onChatUpdate`가 메시지를 state에 추가한다. `INLINE_COMMENT_RECEIVED`는 "플러그인에서 들어온 입력" 사실 자체에 렌더러가 반응할 필요가 생길 때를 위한 채널(예: 미래에 토스트, 사운드 등). 중복 발송을 피하기 위해 현재는 로그만.

- [ ] **Step 4: 검증**

Run: `cd /Users/julee/figma-design-agent && npm run build`
Expected: 빌드 성공.

- [ ] **Step 5: 커밋**

```bash
git add src/preload/index.ts src/renderer/hooks/useAgent.ts
git commit -m "feat(renderer): INLINE_COMMENT_RECEIVED 구독(로그) — 중복 메시지 방지"
```

---

## Task 18: ChatPanel — inlineContext 배지 렌더링

**Files:**
- Modify: `src/renderer/components/ChatPanel.tsx`

- [ ] **Step 1: 메시지 렌더링 JSX에 배지 추가**

`src/renderer/components/ChatPanel.tsx`에서 메시지 배열을 map하는 부분을 찾아 (일반적으로 `messages.map((msg) => ...)`), 각 메시지 렌더링 블록 상단에 배지 추가:

```tsx
{messages.map((msg) => (
  <div key={msg.id} className={`chat-message ${msg.role}`}>
    {msg.inlineContext && (
      <div className="inline-context-badge" title={`id: ${msg.inlineContext.nodeId}`}>
        📌 <span className="node-name">{msg.inlineContext.name}</span>
        <span className="node-type">{msg.inlineContext.nodeType}</span>
      </div>
    )}
    {/* 기존 attachments / content 렌더링은 그대로 */}
    {/* ... */}
  </div>
))}
```

- [ ] **Step 2: CSS 추가 (같은 파일의 style 블록 또는 연결된 CSS 파일)**

```css
.inline-context-badge {
  display: inline-flex;
  gap: 6px;
  font-size: 11px;
  background: rgba(124, 58, 237, 0.15);
  color: #a78bfa;
  padding: 2px 8px;
  border-radius: 10px;
  margin-bottom: 4px;
  align-items: center;
}
.inline-context-badge .node-type {
  color: #888;
  font-size: 10px;
}
```

(CSS 위치는 기존 ChatPanel 스타일 작성 방식 따를 것. inline `<style>`, CSS Module, CSS 파일 중 프로젝트 컨벤션에 맞춰서.)

- [ ] **Step 3: 검증**

Run: `cd /Users/julee/figma-design-agent && npm run build`
Expected: 빌드 성공.

- [ ] **Step 4: 수동 테스트 — 전체 E2E**

Run: `cd /Users/julee/figma-design-agent && npm run dev`
1. Figma 연결
2. Figma에서 노드 선택 → 플러그인 UI에 selection 표시
3. 코멘트 입력 후 "Send to Claude" 클릭
4. 앱 ChatPanel에 📌 배지가 붙은 사용자 메시지 표시 + Claude 응답 시작
5. 플러그인 UI에 "Claude 작업 중..." 표시 → 완료 후 사라짐

- [ ] **Step 5: 커밋**

```bash
git add src/renderer/components/ChatPanel.tsx
git commit -m "feat(ui): ChatPanel inlineContext 배지 렌더링"
```

---

## Task 19: 플러그인 UI — progress_update 수신 처리

**Files:**
- Modify: `src/figma-plugin/ui.html`

- [ ] **Step 1: WS onmessage에 progress_update 처리 추가**

`ui.html`의 `<script>` 블록에서 WS 메시지 수신 핸들러(`socket.onmessage`)에 케이스 추가. 기존 구조에 맞게 `data.type === 'progress_update'` 분기를 추가:

```js
socket.onmessage = function(evt) {
  var data = JSON.parse(evt.data);

  // 기존 처리들 유지 (pong, command_result 등)

  // 신규: 인라인 코멘트 진행 상태
  if (data.type === 'progress_update' && data.context === 'inline_comment') {
    if (data.phase === 'thinking') {
      commentProgressEl.classList.add('visible');
      progressTextEl.textContent = 'Claude 작업 중...';
    } else if (data.phase === 'tool_use') {
      progressTextEl.textContent = 'Claude가 도구 실행 중...';
    } else if (data.phase === 'done') {
      commentProgressEl.classList.remove('visible');
    } else if (data.phase === 'error') {
      progressTextEl.textContent = 'Error: ' + (data.message || 'unknown');
      setTimeout(function() { commentProgressEl.classList.remove('visible'); }, 3000);
    }
    return;
  }

  // 기존 다른 케이스 유지
};
```

**주의**: 기존 `socket.onmessage` 핸들러가 어떤 타입들을 이미 처리하는지 확인 후, 케이스 추가만 할 것. 전체를 덮어쓰지 말 것.

- [ ] **Step 2: 수동 E2E 테스트 (Task 18 Step 4와 동일하지만 피드백 검증)**

플러그인 UI에서 "Send to Claude" → `thinking` → `tool_use` → `done` 순서로 진행 메시지가 표시/사라지는지 확인.

- [ ] **Step 3: 커밋**

```bash
git add src/figma-plugin/ui.html
git commit -m "feat(plugin-ui): orchestrator progress_update 수신 표시"
```

---

## Task 20: 통합 QA + 회귀 검증

**Files:**
- 변경 없음 (검증만)

- [ ] **Step 1: 기본 디자인 빌드 회귀 검증 (PRD 첨부 플로우)**

Run: `cd /Users/julee/figma-design-agent && npm run dev`
1. Figma 플러그인 연결
2. ChatPanel에 PRD 마크다운 파일 첨부 + "홈 화면 디자인 빌드" 메시지
3. 로그 확인:
   - `[DSSync] ...` 로그가 orchestrator 시작 전에 뜨는지
   - GitHub sync 성공/실패 로그
   - Figma sync에서 components/sets 개수 출력
4. 디자인 빌드가 기존대로 끝까지 진행되는지 (회귀 없음)

- [ ] **Step 2: 쿨다운 검증**

같은 세션에서 PRD 첨부 후 재전송 2회:
- 두 번째는 `[DSSync] Skipped (cooldown, Xs left)` 로그가 떠야 함
- 빌드는 정상 진행

- [ ] **Step 3: Figma 끊긴 상태 DS sync**

Figma 플러그인 종료(연결 끊기) → Settings에서 "Sync Now" 클릭:
- `[DSSync][Figma] Skipped (not connected)` 로그
- GitHub만 sync, 에러 없이 완료
- SettingsPanel에 lastSyncAt이 갱신됨

- [ ] **Step 4: 인라인 코멘트 전체 플로우**

Figma 재연결 → 노드 선택 → 플러그인 UI 코멘트 입력 → Send:
- ChatPanel에 📌 배지 붙은 사용자 메시지
- Claude가 해당 nodeId를 인식하여 응답/수정
- 플러그인 UI에 진행 상태 표시 → 완료 시 사라짐

- [ ] **Step 5: 빈 코멘트 / 선택 없음 엣지 케이스**

- 선택 해제 상태: 플러그인 UI에 selection-section 감춰짐, Send 버튼 비활성
- 코멘트 비우고 Send 시도: 버튼 disabled 상태

- [ ] **Step 6: (선택) 최종 변경점 요약 커밋**

변경 없음이면 skip. `.bak` 파일이 `ds/` 폴더에 남았다면 `.gitignore` 패턴 확인:

```bash
git status
# ds/*.bak 가 untracked로 보이면:
echo "ds/*.bak" >> .gitignore
git add .gitignore
git commit -m "chore: DS sync 백업 파일 gitignore"
```

---

## 참고: 실패 시 롤백

DSSyncService가 `ds/DS_COMPONENT_DOCS.json` 또는 `ds/ds-1-variants.jsonl`를 덮어쓰기 전에 `.bak` 파일을 만든다. 동기화 결과가 명백히 깨진 경우 수동 롤백:

```bash
cp ds/DS_COMPONENT_DOCS.json.bak ds/DS_COMPONENT_DOCS.json
cp ds/ds-1-variants.jsonl.bak ds/ds-1-variants.jsonl
```

향후 자동 롤백(스키마 validation 후 재저장)은 별도 작업으로 분리.

---

## 체크리스트 완료 시

위 모든 태스크가 ✅ 된 뒤:
- `git log --oneline`으로 대략 20개 커밋이 누적되었는지 확인
- `npm run build`가 에러 없이 통과
- `docs/superpowers/specs/2026-04-20-ds-sync-inline-comment-design.md`의 모든 요구사항이 구현되었는지 최종 대조
