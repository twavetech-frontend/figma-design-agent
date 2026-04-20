# DS 자동 동기화 + 인라인 코멘트 기능 설계

- **작성일**: 2026-04-20
- **대상**: figma-design-agent (Electron + React + Anthropic SDK)
- **모티베이션**: Anthropic Claude Design(2026-04-17 출시) 기능 중 1) 코드베이스/디자인 파일 자동 DS 추출, 2) 인라인 코멘트 기반 refinement를 프로젝트에 도입하여 반복 수작업을 줄임

## 목표

1. **DS 자동 동기화**: 디자인 빌드 직전 `ds/` 폴더의 토큰/컴포넌트/variants를 자동 최신화하여 DS 불일치 수작업 제거
2. **인라인 코멘트**: Figma 플러그인 UI에서 선택한 노드에 대한 수정 지시를 직접 전송하여, 앱 ChatPanel로 창 전환 없이 핀포인트 수정 가능

## 비목표 (YAGNI)

- Figma Local Variables 자동 추출 (GitHub tokens.json이 진실의 원천 — 충돌 회피)
- 아이콘 자동 동기화 (1141개 정적 충분)
- Multi-node inline comment (단일 노드만)
- Figma 플러그인 UI에서 채팅 히스토리 표시 (앱 ChatPanel이 단일 소스)
- 자동화 테스트 추가 (이 프로젝트에 테스트 인프라 없음 — 수동 QA)

## 결정 사항 요약

| 항목 | 결정 |
|------|------|
| DS 동기화 소스 | 하이브리드 (토큰 = GitHub repo, 컴포넌트/variants = Figma) |
| 동기화 트리거 | 앱 시작 시 + 빌드 직전 + 수동 버튼 |
| 빌드 감지 신호 | `sendMessage(attachments.length > 0)` |
| 쿨다운 | 5분 (마지막 sync 기준) |
| Figma 추출 범위 | 컴포넌트 + variants만 (아이콘/local variables 제외) |
| 동기화 실패 시 | stale 그대로 사용 + 로그 (빌드 중단 X) |
| 인라인 코멘트 입력 위치 | Figma 플러그인 UI (ui.html) |
| 인라인 코멘트 수신처 | 앱 ChatPanel 메시지로 기록 + 플러그인에 진행 상태 표시 |
| 선택 노드 수 | 1개만 |

## 아키텍처

### 전체 데이터 흐름

```
┌────────────────────────────────────────────────────────────┐
│  Figma Plugin (ui.html + code.js)                          │
│  ┌─ Status UI (기존)                                        │
│  ├─ Selection Info UI (신규) ← figma.on('selectionchange') │
│  └─ Comment Input UI (신규)  → WS: inline_comment          │
└────────────────────────────────────────────────────────────┘
         ↕ WS :8767
┌────────────────────────────────────────────────────────────┐
│  Main Process (Electron)                                    │
│  ┌─ FigmaWSServer (기존, case 추가)                         │
│  ├─ InlineCommentHandler (신규)                             │
│  │  └─ orchestrator.sendMessage() 호출                      │
│  ├─ DSSyncService (신규)                                    │
│  │  ├─ GitHub sync (기존 .sh 래핑)                          │
│  │  ├─ Figma sync (get_local_components + variants)        │
│  │  ├─ invalidateDSCaches() 호출                            │
│  │  └─ 트리거: app ready / pre-build hook / IPC             │
│  └─ AgentOrchestrator (기존, sendMessage 확장)              │
└────────────────────────────────────────────────────────────┘
         ↕ IPC
┌────────────────────────────────────────────────────────────┐
│  Renderer (React)                                           │
│  ├─ ChatPanel: 📌 InlineCommentMessage 렌더링 (신규)        │
│  └─ SettingsPanel: "Sync DS" 버튼 + 마지막 sync 시각 (신규) │
└────────────────────────────────────────────────────────────┘
```

### 기능 1: DS 자동 동기화

#### 모듈
- **신규**: `src/main/ds-sync-service.ts` (~200줄)
- **재사용**: `scripts/sync-tokens-from-github.sh` (child_process.exec로 래핑)
- **재사용**: `src/shared/ds-data.ts::invalidateDSCaches()`

#### Public API
```ts
class DSSyncService {
  async sync(opts?: { force?: boolean }): Promise<SyncResult>
  getLastSyncAt(): Date | null
  getStatus(): 'idle' | 'syncing' | 'error'
  onStatusChange(cb: (s: Status) => void): Unsubscribe
}

type SyncResult = {
  ok: boolean
  githubTokens: { ok: boolean; error?: string; durationMs: number }
  figmaComponents: { ok: boolean; error?: string; durationMs: number;
                     counts?: { components: number; variants: number } }
  skipped?: 'cooldown' | 'in-flight'
}
```

#### 내부 동작 (병렬 2단계 → 캐시 무효화)

1. **GitHub tokens sync**
   - `child_process.exec('bash scripts/sync-tokens-from-github.sh')`
   - 성공 시 `ds/DESIGN_TOKENS.md`, `ds/TOKEN_MAP.json` 갱신
   - 실패 시 로그만, 진행 계속

2. **Figma components/variants sync**
   - FigmaWSServer에 `get_local_components` + `get_local_component_sets` 명령 실행
   - 결과를 **기존 포맷과 동일하게** 변환 후 `ds/DS_COMPONENT_DOCS.json` / `ds/ds-1-variants.jsonl` 덮어쓰기
   - Figma WS 미연결 시 `{ ok: false, error: 'figma-not-connected' }`

3. **캐시 무효화**: 두 단계 완료 후 `invalidateDSCaches()` 호출

#### 동시성/쿨다운
- `isSyncing` 플래그로 in-flight 방지 (동시 호출 시 진행 중 Promise 공유)
- `lastSyncAt`으로 5분 쿨다운 체크 (`force: true`면 우회)
- `settings.json`에 `lastSyncAt` 저장 → 재시작 후에도 유지

#### 트리거 포인트
1. Electron `app.whenReady()` 직후 → `sync({ force: false })` 백그라운드
2. `orchestrator.sendMessage` 진입 시 `attachments.length > 0`이면 await
3. SettingsPanel의 "Sync Now" 버튼 → IPC `DS_SYNC_REQUEST` → `sync({ force: true })`

#### 에러 핸들링
- 둘 다 실패 → stale 사용 + 경고 로그
- 부분 실패 → 성공한 쪽만 반영
- Figma WS 미연결 → GitHub만 진행

### 기능 2: 인라인 코멘트

#### 모듈
- **신규**: `src/main/inline-comment-handler.ts` (~80줄)
- **수정**: `src/figma-plugin/ui.html` (selection + comment UI 추가)
- **수정**: `src/figma-plugin/code.js` (selectionchange 훅 + WS 메시지 발송)
- **수정**: `src/main/figma-ws-server.ts` (`inline_comment` 케이스 분기)
- **수정**: `src/main/agent-orchestrator.ts` (`inlineContext` opt 추가)
- **수정**: `src/shared/types.ts` (타입/채널 추가)
- **수정**: `src/renderer/components/ChatPanel.tsx` (배지 렌더링)
- **수정**: `src/renderer/hooks/useAgent.ts` (INLINE_COMMENT_RECEIVED 구독)

#### Figma 플러그인 (ui.html + code.js)

**ui.html 신규 섹션**:
```html
<div id="selection-section" class="selection-section hidden">
  <div class="selection-header">
    <span>📌 Selected</span>
    <button id="clear-selection">×</button>
  </div>
  <div id="selection-info" class="selection-info"></div>
  <textarea id="comment-input" placeholder="이 노드에 대한 수정 지시..." rows="3"></textarea>
  <button id="send-comment" disabled>Send to Claude</button>
</div>
<div id="comment-progress" class="comment-progress hidden">
  <div class="spinner"></div>
  <span id="progress-text">Claude 작업 중...</span>
</div>
```

**code.js 훅**:
```js
figma.on('selectionchange', () => {
  const sel = figma.currentPage.selection[0]
  figma.ui.postMessage({
    type: 'selection-info',
    payload: sel ? { id: sel.id, name: sel.name, type: sel.type } : null,
  })
})
```

**ui.html WS 발송** (기존 WS 재사용):
```js
socket.send(JSON.stringify({
  type: 'inline_comment',
  payload: { nodeId, name, nodeType, comment, timestamp: Date.now() }
}))
```

#### 메인 프로세스 (InlineCommentHandler)
```ts
class InlineCommentHandler {
  constructor(
    private orchestrator: AgentOrchestrator,
    private mainWindow: BrowserWindow,
    private wsServer: FigmaWSServer,
  ) {}

  async handle(payload: InlineCommentPayload) {
    // 1. renderer에 broadcast (ChatPanel에 사용자 메시지로 표시)
    this.mainWindow.webContents.send(IPC_CHANNELS.INLINE_COMMENT_RECEIVED, payload)

    // 2. orchestrator에 inlineContext 포함하여 전달
    const formattedMessage =
      `[Inline context: Node "${payload.name}" (${payload.nodeType}, id="${payload.nodeId}")]\n\n${payload.comment}`
    await this.orchestrator.sendMessage(formattedMessage, [], { inlineContext: payload })

    // 3. 진행 상태를 WS로 플러그인에 피드백
    // (orchestrator의 AGENT_CHAT_UPDATE 이벤트 구독 → wsServer.broadcast 'progress_update')
  }
}
```

#### Renderer (ChatPanel)
- `ChatMessage`에 `inlineContext?: { nodeId, name, nodeType }` 추가
- 배지 UI: 메시지 상단에 작은 📌 태그 + nodeId tooltip
- `useAgent` hook이 `INLINE_COMMENT_RECEIVED` 구독 → messages에 추가 (이미 main에서 orchestrator 발동했으므로 renderer는 **구독만**, 재발송 금지)

## IPC / WS 계약

### IPC 채널 (신규)

```ts
// src/shared/types.ts
DS_SYNC_REQUEST: 'ds-sync:request',           // renderer → main
DS_SYNC_STATUS: 'ds-sync:status',             // main → renderer broadcast
INLINE_COMMENT_RECEIVED: 'inline-comment:received',  // main → renderer
```

### WS 메시지 타입 (신규)

Plugin → Main:
```ts
{
  type: 'inline_comment',
  payload: {
    nodeId: string,
    name: string,
    nodeType: string,
    comment: string,
    timestamp: number,
  }
}
```

Main → Plugin (기존 `progress_update` 확장):
```ts
{
  type: 'progress_update',
  context: 'inline_comment',   // 신규 필드
  phase: 'thinking' | 'tool_use' | 'done' | 'error',
  message?: string,
}
```

### orchestrator.sendMessage 시그니처 확장
```ts
sendMessage(
  message: string,
  attachments?: AttachmentData[],
  opts?: { inlineContext?: InlineCommentPayload; preSyncDS?: boolean }
): Promise<void>
```

- `preSyncDS` 기본값: `attachments.length > 0`이면 true
- `inlineContext` 있으면 시스템 프롬프트에 "해당 nodeId를 대상으로 수정하라" 지시 append

## 구현 순서

### Phase 1: DS Sync 하부
1. DSSyncService 스켈레톤 + 쿨다운 로직
2. GitHub sync 래핑
3. Figma components/variants sync
4. settings-store에 lastSyncAt 저장/읽기
5. IPC DS_SYNC_REQUEST/DS_SYNC_STATUS 연결
6. SettingsPanel에 "Sync Now" 버튼 + 상태 표시
7. orchestrator.sendMessage 앞단 pre-sync 훅 추가

### Phase 2: 인라인 코멘트 하부
1. types.ts 타입/채널 추가
2. plugin code.js: selectionchange 훅
3. plugin ui.html: selection/comment UI
4. plugin ui.html: WS send 'inline_comment'
5. figma-ws-server.ts: 'inline_comment' 케이스 분기
6. InlineCommentHandler 구현
7. orchestrator.sendMessage 시그니처 확장 (inlineContext opt)
8. ChatPanel 배지 렌더링
9. useAgent hook: INLINE_COMMENT_RECEIVED 구독
10. WS progress_update → 플러그인 UI 피드백

### Phase 3: 통합 검증
- 수동 E2E: PRD 첨부 → 디자인 생성 (DS sync 발동 확인)
- 수동 E2E: Figma 노드 선택 → 플러그인 코멘트 → ChatPanel 반영
- 실패 케이스: Figma WS 끊긴 상태에서 DS sync → stale 동작 확인
- 쿨다운: 연속 PRD 첨부 2회 → 두 번째 skip 로그 확인

Phase 1과 2는 독립이라 병렬 가능. 순서대로 진행이 리뷰 쉬움.

## 리스크 & 완화

| 리스크 | 영향 | 완화 |
|------|-----|-----|
| Figma → `DS_COMPONENT_DOCS.json` 포맷 변환 오류 | DS 조회 도구 전체 망가짐 | 쓰기 전 백업 파일 생성. 실패 시 이전 파일 rollback |
| `get_local_components`가 teamLibrary 한계로 일부 누락 | 변환 결과 불완전 | Bridge 모드 기존 수준 유지가 목표 (regress 방지) |
| 플러그인 ui.html 확장 시 CSS 충돌 | UI 깨짐 | 신규 요소는 새 CSS 클래스만 사용, 기존 스타일 변경 금지 |
| orchestrator.sendMessage 시그니처 변경 | 기존 renderer 호출부 깨짐 | 신규 파라미터는 optional, 기존 호출 그대로 작동 |
| pre-sync 지연 2-5초 | 사용자 체감 느려짐 | 쿨다운 5분으로 대부분 skip. 첫 빌드만 체감 |
| WS disconnect 중 selection 유실 | comment 전송 실패 | 플러그인 WS 재연결 시 현재 selection 재전송 |

## 검증 전략

- **자동 테스트 없음** (프로젝트에 테스트 인프라 없음)
- **수동 QA**: Phase 3 스크립트 순서대로
- **로깅**: DSSyncService / InlineCommentHandler 둘 다 `[DSSync] ...`, `[InlineComment] ...` prefix로 로그 → DevTools 콘솔로 추적

## 알려진 한계

- 현재 orchestrator는 `AskUserQuestion` 도구를 차단하므로 agent 루프 중 사용자 질문 불가 (원하는 동작 — one-shot 플로우 유지)
- DS sync는 Figma Bridge 모드 연결 필수(Figma 쪽). 미연결 시 GitHub 토큰만 갱신됨
- 쿨다운 5분은 하드코딩 — 설정 UI 노출은 별도 후속 작업
