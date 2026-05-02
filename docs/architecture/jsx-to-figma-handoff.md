# JSX-to-Figma 핸드오프 노트

**작성일**: 2026-05-02
**브랜치**: `poc/jsx-to-figma`
**최근 커밋**: `eb4b8e5`, `18e9e9a`

새 세션에서 이 작업을 이어가는 사람이 빠르게 컨텍스트를 잡기 위한 문서. CLAUDE.md / docs/design.md / 기타 룰 문서는 별도. 이 문서는 **JSX-to-Figma 파이프라인의 현재 상태**만 다룬다.

---

## 1. 왜 이 방식인가 (Why)

### 옛 방식의 한계
Agent가 Blueprint JSON을 매번 창작 → `batch_build_screen` 호출. 문제:
- 비결정적 (같은 PRD가 매번 다른 결과)
- 복잡 속성 조합에서 plugin 파싱 실패 (구조 붕괴)
- raw frame 트리 → end-user(비디자이너)가 받는 figma 파일 품질 낮음

### 새 방식: claude.ai/design 패턴을 그대로 옮김
```
PRD/wireframe → Agent가 ScreenSpec 작성 (데이터만)
              → renderers/ 가 결정적으로 plugin JS 생성
              → Figma에 그려짐 (raw frame 아닌 진짜 component instance)
```

JSX 멘탈 모델:
| JSX 세계 | 이 프로젝트 |
|---------|-----------|
| `<HomeScreen sections={[...]} />` | `ScreenSpec` |
| `<FilterChip text="..." selected />` | `SectionSpec` (`type: "filterChipRow"`) |
| 컴포넌트 함수 본문 | `renderFilterChipRow()` |
| React가 같은 컴포넌트를 N번 호출해도 1번 정의 | `ensureComponent()` master 1개 + N instance |
| ReactDOM.render | `buildScreenJS()` |

### 비디자이너 가치 사슬 (핵심 약속)
1. 비디자이너가 figma에 와이어프레임 그림
2. agent에 "디자인 만들어줘"
3. 도구가 자동으로 `❖ AGENT_LIBRARY` 페이지 + sharedPluginData에 component 등록 → polished design
4. **사용자가 figma에서 master 수정하면 모든 instance 자동 동기화**

비디자이너는 "AGENT_LIBRARY가 뭐냐" 물을 필요 없는 figma 표준 DS 패턴.

---

## 2. 무엇이 완성됐나 (What's Done)

### 인프라
- ✅ `src/main/renderers/{types,setup,components,orchestrate}.ts` — 17개 SectionSpec, ScreenSpec → plugin JS
- ✅ `build_from_spec` MCP tool 노출 (`figma-mcp-embedded.ts`)
- ✅ `execute_js` plugin handler (`src/figma-plugin/code.js`)
- ✅ `ensureComponent` — file-local master + sharedPluginData 영속 cache
- ✅ `ensureDsSet` / `dsInstance` — published DS swap 인프라 (file-agnostic)
- ✅ Token binding + post-fix (이전 commit `d9cc61d`)
- ✅ Bridge 모드 동작 — `out/bridge/index.js` (Node, port 8767/8769)
- ✅ `system-prompt-builder.ts` — generic SectionSpec[] 가이드 + 빌드 흐름

### 마이그레이션 커버리지: 14/17 (82%)
| 패턴 | spec |
|------|------|
| **DS instance** (file-agnostic) | fab → DS Buttons |
| **file-local master** | sectionHeader, statsStrip3Col, summaryCardLinkRow, filterChip, tabBarItem-{iconKey}×N, transactionTimelineRow, backHeader, modalHeader, segmentedTabItem, underlineTabItem, stepperCardRow, avatarMaker, monthCell |
| **raw frame** (가변 자식 복잡) | appHeader, stageCardList, footerLegal |

### 운영 상태 (2026-05-02 마지막 빌드 기준)
- Figma file: `SsgiLsXVMkf0wv8OhRGwks` (Imin Design System)
- `❖ AGENT_LIBRARY` 페이지: 14개 master (registry와 1:1 일치, 중복 cleanup 완료)
- sharedPluginData namespace: `fda_renderer` (hyphen 금지)
- Bridge 서버: 마지막 PID 67785 (사용자가 끄거나 다시 띄울 수 있음)

---

## 3. 무엇이 남았나 (What's Left)

### 사용자가 검증해야 할 것
1. **End-to-end agent 테스트**: 새 agent 세션에서 figma 와이어프레임 선택 후 "디자인 만들어줘" → agent가 `build_from_spec`을 자발적으로 선택하는가, ScreenSpec을 잘 작성하는가, 결과 품질이 80%+ 시각 유사도를 충족하는가
2. **새 file 동작 검증**: 다른 figma file에서 동일 호출 → file-local master 14개 새로 생성, DS Buttons(fab)는 같은 master 공유

### 코드 작업으로 남은 것
3. **`appHeader` / `stageCardList` / `footerLegal` 마이그레이션** (선택)
   - 가변 자식 (rightIcons[], items[], legalLinks[]) 때문에 보류
   - 패턴: max-N slot + BOOLEAN visibility, 또는 row 단위 master + N instance
4. **DS swap 확장** (선택)
   - 현재 fab만 DS instance. 다른 spec도 시도했으나 미학·레이아웃 깨져서 회귀
   - 가능성: avatarMaker → DS Avatar (단 gradient/crown 손실 trade-off)
5. **stale globalThis cache 정리**
   - cleanup 후에도 plugin process가 살아있으면 globalThis.__fdaComponents에 stale node 잔존 가능
   - 영향: 거의 없음 (다음 호출 시 `node.removed` 체크로 fall-through)

---

## 4. 핵심 파일 위치 (How it Works)

| 파일 | 역할 |
|------|------|
| `src/main/renderers/types.ts` | `ScreenSpec`, `SectionSpec` (17 types), `OverlaySpec` |
| `src/main/renderers/setup.ts` | `buildSetupJS()`: VK/IK 변수 + helper 함수 (cAL/solid/txt/HUE 등) + `ensureComponent`/`ensureDsSet`/`setComponentProperties` |
| `src/main/renderers/components.ts` | 17개 `renderXxx(s)` 함수 + dispatch (`renderSection`/`renderOverlay`) |
| `src/main/renderers/orchestrate.ts` | `buildScreenJS(spec)`: setup + wrapper + sections + overlays + tail (registry sync) |
| `src/main/figma-mcp-embedded.ts` | `build_from_spec` MCP tool 등록 (line ~880) |
| `src/figma-plugin/code.js` | `execute_js` handler (line 285) — 받은 코드를 async wrapped Function으로 실행 |
| `src/main/system-prompt-builder.ts` | ROLE_PROMPT — agent에 build_from_spec 우선 사용 가이드 |
| `ds/ds-1-variants.jsonl` | DS 컴포넌트 setKey + variant key 매핑 (DS swap 시 참조) |

### `ensureComponent` 호출 패턴 (예: `filterChip`)
```js
const { component: chipComp } = await ensureComponent("filterChip", async (parent) => {
  parent.layoutMode = "HORIZONTAL";
  // ... master 구조 정의
  const labelNode = txt("Chip", { ... });
  parent.appendChild(labelNode);
  return {
    properties: [
      { name: "label", type: "TEXT", default: "Chip", bindNodeToCharacters: labelNode },
    ],
  };
});

for (const c of s.chips) {
  const inst = chipComp.createInstance();
  row.appendChild(inst);
  await setComponentProperties(inst, { label: c.text });
  // per-instance overrides (variant 표현)
  if (c.selected) {
    inst.fills = [solid(v.bgBrandSection)];
    // ...
  }
}
```

### DS instance 호출 패턴 (예: `fab`)
```js
const btnSet = await ensureDsSet(DS_KEYS.buttons);
const fab = btnSet.defaultVariant.createInstance();
// setProperties로 variant 선택
const defs = fab.componentProperties || {};
const find = (n) => Object.keys(defs).find(k => k === n || k.startsWith(n + "#"));
const props = {};
const sk = find("Size"); if (sk) props[sk] = "lg";
// ...
fab.setProperties(props);
// inner icon swap
const iconNode = fab.findOne(n => n.type === "INSTANCE");
if (iconNode && ic[s.iconKey]) iconNode.swapComponent(ic[s.iconKey]);
```

---

## 5. 알려진 함정 (Known Pitfalls — 회귀 방지)

이미 fix됐지만 동일 실수 반복 방지용 기록.

### A. namespace에 hyphen 금지
- `figma.root.setSharedPluginData(NS, KEY, val)` — NS는 `[a-zA-Z0-9_.]+` 만 허용
- 옛 `"fda-renderer"` → silent fail (try/catch에 잡혀 영원히 영속 안 됨)
- 현재 `"fda_renderer"` 사용

### B. `importComponentByKeyAsync`는 published library만 동작
- 로컬 unpublished component는 `key`로 import 불가 → fall-through로 매번 새 master
- 해결: `getNodeByIdAsync(node.id)` 사용. registry에 `{ id, key }` 둘 다 저장하지만 lookup은 id

### C. in-memory cache가 sharedPluginData write를 short-circuit
- `globalThis.__fdaComponents`에 hit하면 즉시 return → `writeRegistry` 호출 안 됨
- plugin process가 살아있는 동안은 OK이지만 plugin reload 후엔 sharedPluginData가 stale
- 해결: `orchestrate.ts` tail에서 globalThis → sharedPluginData sync

### D. DS internal `_` prefix 컴포넌트 사용 금지
- `_Tab button base`, `_segmented_button` 등 internal은 layoutSizing 호환 안 됨
- 빌드 에러 발생. public top-level DS만 import (`Buttons`, `Tag`, `Metric item` 등)

### E. DS instance vs custom — 미학 우선
- DS swap 후 빌드 결과를 **반드시 시각 검증**
- 깨지면 즉시 file-local custom master로 회귀 (사용자 명시 가이드)
- 구체적 회귀 사례: Tag.Checkbox=True가 filter chip selected 의도와 다름, Metric item이 자동 sub-component(_Change/Dropdown) 포함해 무거움
- 메모리: `feedback_ds_aesthetics_first.md`

### F. 가변 N children spec은 row 단위 master 패턴
- `Horizontal tabs` 같은 top-level DS는 한 번에 모든 tabs를 그림 → 가변 N 미대응
- file-local master 1개 + N instance가 정답 (filterChip, summaryCardLinkRow, transactionTimelineRow, tabBarItem-{iconKey}, avatarMaker, monthCell 모두 이 패턴)

---

## 6. 새 세션에서 우선순위 (Next Steps)

### 즉시 실행 가능 (사용자 행동 필요)
1. **agent end-to-end 테스트**: 새 채팅에서 와이어프레임 선택 후 `"이 와이어프레임으로 디자인 만들어줘"` — agent가 `build_from_spec`을 호출하고 결과 품질 확인
2. **새 figma file에서 같은 테스트**: file-agnostic 동작 검증

### 코드 작업
3. agent prompt 추가 보강 — `build_from_spec` 도구 description에 정확한 schema가 있지만, agent가 wireframe → spec 변환 시 hallucinate 방지를 위한 예시 추가 가능
4. `appHeader`/`stageCardList`/`footerLegal` 마이그레이션 (선택)
5. DS swap 추가 시도 (위험 — 미학 회귀 가능성)

### 운영
6. 사용자가 figma에서 직접 master 수정 → instance 자동 동기화 시나리오 실측

---

## 7. 빠른 참조: 빌드 + 재시작

```bash
# 코드 변경 후
npm run build

# bridge 재시작 (필요 시)
pkill -f "out/bridge/index.js"
nohup node out/bridge/index.js > /tmp/bridge-server.log 2>&1 &

# bridge 로그 모니터링
tail -f /tmp/bridge-server.log

# AGENT_LIBRARY / registry 상태 확인 (use_figma 또는 figma_mcp_client.py)
# fileKey: SsgiLsXVMkf0wv8OhRGwks
```

---

## 8. 관련 메모리 파일 (사용자 명시 지시)

- `feedback_bridge_mode_not_electron.md` — electron 진단 금지
- `feedback_ds_aesthetics_first.md` — DS swap 시 미학 검증 + 회귀 기준
- `feedback_ds_components_first.md` — DS 컴포넌트 우선 사용 (raw frame 금지)
- `feedback_scratch_quality_required.md` — clone_node 금지, scratch에서 정밀 재현
