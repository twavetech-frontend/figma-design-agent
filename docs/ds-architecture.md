# Design System Architecture

## Current DS: DS v1

| 파일 | 역할 | 생성 방법 |
|------|------|-----------|
| [`src/DS_PROFILE.md`](../src/DS_PROFILE.md) | Variant Key, Suffix Map, 속성명, 아이콘 소스 | `generate-ds-profile` 스크립트 |
| [`src/DESIGN_TOKENS.md`](../src/DESIGN_TOKENS.md) | 색상 hex, spacing px, radius px, typography, **Text Styles key/ID (44)**, **Effect Styles key/ID (24)** | `generate-ds-profile` 스크립트 (REST API `/files/:key/styles` + 변수) |
| `ds/ds-1-icons.json` | icon name → componentId 매핑 (1141개) | MCP `scan_instances_for_swap` |
| `ds/ds-1-variants.jsonl` | 154 컴포넌트, 4716 배리언트 | `generate-ds-profile` 스크립트 |

DS 교체 시 위 파일만 교체하면 됨. 아이콘 파일은 DS별로 분리: `ds-1-icons.json`, `ds-2-icons.json` 등.

## 대용량 파일 접근 규칙
- **`DS_PROFILE.md` (483KB)**: Read 도구의 256KB 제한 초과 → **반드시 `offset`/`limit` 파라미터로 부분 읽기하거나, Grep 도구로 검색**. 전체 Read 시도 금지
  - 섹션 1~5 (1~42줄): Identity, INSTANCE_SWAP, Text Node, Button, Icon 정보
  - 섹션 6 (43줄~끝): Variant Key Index → **`ds-1-variants.jsonl` 사용** (아래 참고)
- **`DESIGN_TOKENS.md`**: 크기에 따라 동일 규칙 적용

## Variant Key 조회 (필수: ds-1-variants.jsonl 사용)
- DS_PROFILE.md의 섹션 6 대신 **`ds-1-variants.jsonl`** 파일로 Variant Key 조회 — 154개 컴포넌트, 4716개 변형
- **JSONL 형식**: 한 줄 = 하나의 컴포넌트 (`{"name":"...", "setKey":"...", "variants":{...}}`)
- **사용법**: `Grep "컴포넌트명" ds-1-variants.jsonl` → 해당 컴포넌트의 setKey와 전체 variants가 한 줄로 반환
- **예시**: `Grep "Checkbox"` → `{"name":"Checkboxes","setKey":"...","variants":{"Size=sm, Type=Checkbox, Checked=False":"key1",...}}`
- DS_PROFILE.md에서 Variant Key Index를 직접 검색하지 말 것 — 느리고 비효율적

## DS 토큰 소스: GitHub (stresslee/design-system) — 절대 규칙

> **디자인 생성 시 토큰(컬러, 스페이싱, 타이포그래피, 효과)은 반드시 GitHub에서 최신 데이터를 가져와서 사용한다.**
> 로컬 `ds/DESIGN_TOKENS.md`가 오래된 값일 수 있으므로, **디자인 생성 전 반드시 동기화 스크립트를 실행**한다.

**토큰 흐름:**
```
Figma Token Studio → git push → GitHub(stresslee/design-system/tokens.json)
                                      ↓ sync-tokens-from-github.sh
                                ds/DESIGN_TOKENS.md + ds/TOKEN_MAP.json (최신 값)
                                      ↓
                                디자인 생성 (batch_build_screen, set_bound_variables 등)
```

**동기화 실행:**
```bash
bash scripts/sync-tokens-from-github.sh
```

**규칙:**
- **디자인 생성 요청마다 매번 실행** — `batch_build_screen` 또는 blueprint 빌드 직전에 항상 `sync-tokens-from-github.sh` 실행. 같은 세션이라도 사용자가 중간에 DS를 변경하고 푸시했을 수 있으므로 캐싱하지 않는다
- 동기화 스크립트는 실행 시간이 짧으므로(수 초) 매번 실행해도 부담 없음
- 스크립트가 GitHub에서 `tokens.json` + `sync-to-agent.js`를 fetch → `DESIGN_TOKENS.md` + `TOKEN_MAP.json` 재생성
- 이렇게 해야 사용자가 Figma에서 컬러를 바꾸고 Token Studio로 push하면 자동 반영됨
- 로컬 `ds/` 파일을 수동으로 편집하는 것은 금지 — 항상 GitHub이 소스

**GitHub Actions (CI 자동 동기화):**
- `.github/workflows/sync-tokens.yml` — `repository_dispatch` 또는 수동 트리거 시 동일 로직 실행
- design-system 레포에서 push 시 figma-design-agent의 `ds/` 파일 자동 업데이트

## DS 토큰 업데이트 워크플로우

DS 라이브러리에서 변수를 변경한 후:
1. 사용자가 "변수 업데이트했어" 라고 말하면
2. `get_local_variables(includeLibrary: true)` 실행 — 355+ 변수 값 resolve (alias 재귀 포함)
3. 현재 `DESIGN_TOKENS.md`와 diff 비교
4. 변경된 값 자동 업데이트

DS 라이브러리에서 Text Style/Effect Style을 변경한 후:
1. `generate-ds-profile.js` 재실행 (REST API `/files/:key/styles`에서 자동 추출)
2. 또는 수동: `DESIGN_TOKENS.md`의 "## Text Styles" / "## Effect Styles" 섹션 업데이트

## Text Style 바인딩 체계

DS v1은 Typography **Variables** (fontSize, lineHeight) + **Text Styles** 이중 시스템 사용.
둘 다 적용해야 완전한 DS 연결:
- `set_bound_variables` → fontSize, lineHeight 변수 바인딩
- `set_text_style_id` → Text Style 바인딩 (DESIGN_TOKENS.md에서 Style ID 참조)
- Style ID 형식: `S:{key},{nodeId}` — 리모트 라이브러리 스타일 자동 import
- DS 인스턴스(Button, Checkbox 등) 내부 텍스트는 이미 적용됨 → `create_text`로 직접 생성한 노드만 바인딩

## 새 DS 생성 워크플로우 (DS-2 등)

```bash
# Step 1: 컴포넌트 + 변수 + Text/Effect Styles 프로필 생성
npm run generate-ds-profile -- "<figma-file-url>" \
  --token <token> --name "DS-2" --exclude-icons \
  --variables-json /path/to/variables.json

# Step 2: 아이콘 매핑 생성 (DS 파일에서 플러그인 실행 후)
# MCP: scan_instances_for_swap → ds-2-icons.json 저장

# Step 3: 수동 보완 (MCP 도구로 탐색)
```

## generate-ds-profile 스크립트

```
scripts/generate-ds-profile.js

옵션:
  --token <token>          Figma Personal Access Token (또는 FIGMA_ACCESS_TOKEN 환경변수)
  --name <name>            DS 이름 (기본: 파일명에서 추출)
  --out <dir>              출력 디렉토리 (기본: src/)
  --variables-json <path>  MCP로 추출한 변수 JSON 경로 (하이브리드 모드)
  --exclude-icons          아이콘 페이지 제외 (아이콘은 별도 JSON으로 관리)
  --dry-run                파일 쓰기 없이 미리보기
```

## DS Lookup Tools (MCP 내장 — Grep 대신 사용)

DS 데이터 조회 시 **Grep/Read 대신 아래 MCP 도구 사용** — 컨텍스트 토큰 절약 + 라운드트립 감소.

| 도구 | 용도 | 예시 |
|------|------|------|
| `lookup_icon` | 아이콘 이름 → componentId | `lookup_icon("arrow")` → arrow 관련 아이콘 20개 |
| `lookup_variant` | 컴포넌트 → setKey + variants | `lookup_variant("Button")` → Button variants |
| `lookup_design_token` | 토큰 이름 → 값 | `lookup_design_token("bg-primary", category="colors")` |
| `lookup_text_style` | 스타일 이름 → Style ID | `lookup_text_style("Text sm")` → Style ID |

### 사용 규칙
- `ds-1-icons.json` 검색 → `lookup_icon` 사용
- `ds-1-variants.jsonl` 검색 → `lookup_variant` 사용
- `DESIGN_TOKENS.md` 색상/spacing/radius 검색 → `lookup_design_token` 사용
- `DESIGN_TOKENS.md` Text Style/Effect Style 검색 → `lookup_text_style` 사용
- **Figma 채널 연결 불필요** — 로컬 파일에서 직접 읽기, 서버 시작 시 자동 캐싱

## 사용 가능 MCP 도구 목록 (63개)

> 이 목록에 없는 도구를 호출하면 "Unknown tool" 에러 발생. **반드시 이 목록에서 확인 후 호출.**

| 카테고리 | 도구명 |
|---------|-------|
| **문서/조회** | `join_channel`, `get_document_info`, `get_selection`, `get_node_info`, `get_nodes_info`, `get_styles`, `get_local_components`, `get_remote_components`, `get_pages`, `manage_pages`, `scan_text_nodes`, `export_node_as_image` |
| **생성** | `create_rectangle`, `create_frame`, `create_text`, `create_shape` |
| **수정** | `move_node`, `resize_node`, `delete_node`, `set_fill_color`, `set_stroke_color`, `set_corner_radius`, `set_auto_layout`, `set_effects`, `set_effect_style_id`, `set_layout_sizing`, `set_layout_positioning`, `set_layout_sizing_batch` |
| **텍스트** | `set_text_align`, `set_text_case`, `set_text_content`, `set_text_decoration`, `set_text_properties`, `set_font_name`, `set_font_size`, `set_font_weight`, `set_letter_spacing`, `set_line_height`, `set_paragraph_spacing`, `set_text_style_id`, `get_styled_text_segments` |
| **이미지/색상** | `set_image_fill`, `set_selection_colors`, `set_bound_variables`, `get_bound_variables` |
| **인스턴스/컴포넌트** | `create_component_instance`, `get_instance_properties`, `set_instance_properties`, `clone_node`, `scan_instances_for_swap`, `create_component_from_node`, `pre_cache_components` |
| **배치 작업** | `batch_bind_variables`, `batch_build_screen`, `batch_execute`, `batch_set_text_style_id` |
| **유틸리티** | `group_nodes`, `ungroup_nodes`, `flatten_node`, `rename_node`, `insert_child`, `load_font_async`, `get_local_variables` |
| **DS 조회** | `batch_ds_lookup`, `lookup_component_docs` |

### 존재하지 않는 도구 (호출 금지)
- `get_node_children`, `scan_page_frames`, `get_page_nodes`, `search_nodes`, `find_by_name`, `select_all`, `get_current_page_info`, `set_node_property` — 이 도구들은 존재하지 않음

## INSTANCE_SWAP Guide

INSTANCE_SWAP properties use **component node IDs** (e.g. `"12:3822"`), NOT component keys.
> DS별 속성명 패턴은 [`src/DS_PROFILE.md`](../src/DS_PROFILE.md) §2 참조

### Icon Swap Workflow

1. Look up the icon name in `ds-1-icons.json` to get its `componentId`
2. Use `set_instance_properties` with that `componentId` as the value
3. Use `get_instance_properties` first to discover exact property names

### Important Notes

- `getMainComponentAsync()` and `importComponentByKeyAsync()` hang for remote library components in Figma plugin sandbox
- No pre-import is needed for INSTANCE_SWAP — `setProperties()` accepts node IDs directly
