# Python HTTP MCP 클라이언트 (디자인 생성/수정/바인딩)

MCP 도구 호출이 불안정할 때(세션 끊김, 파라미터 매핑 버그) **Python HTTP 클라이언트**를 사용.
스크립트: `scripts/figma_mcp_client.py`

## 사용법
```bash
# 세션 초기화 (필수 — 첫 실행 시)
python3 scripts/figma_mcp_client.py init

# Blueprint 사전 검증 (빌드 전 필수)
python3 scripts/figma_mcp_client.py validate <blueprint.json>

# 디자인 생성 (blueprint JSON 파일 — 자동 검증 포함)
python3 scripts/figma_mcp_client.py build <blueprint.json>

# DS 변수 바인딩 (bindings JSON 파일)
python3 scripts/figma_mcp_client.py bind <bindings.json>

# 텍스트 스타일 바인딩
python3 scripts/figma_mcp_client.py bind-text-styles <styles.json>

# 빌드 후 자동 후처리 (FILL 사이징, Tab Bar/FAB 배치, 섹션 간격, 텍스트 수정)
python3 scripts/figma_mcp_client.py post-fix <rootNodeId>

# 단일 도구 호출
python3 scripts/figma_mcp_client.py call <tool_name> '<args_json>'

# 템플릿 기반 Blueprint 조립 (고정 섹션 자동 생성)
python3 scripts/figma_mcp_client.py assemble <config.json>

# 인터랙티브 모드
python3 scripts/figma_mcp_client.py interactive
```

## 언제 Python HTTP를 사용하는가
| 작업 | MCP 도구 | Python HTTP | 권장 |
|------|---------|-------------|------|
| 단건 조회/수정 | ✅ 빠름 | ✅ | MCP 도구 |
| 디자인 생성 (batch_build_screen) | ⚠️ 세션 끊김 빈번 | ✅ 안정적 | **Python** |
| DS 변수 바인딩 (대량) | ❌ 파라미터 버그 | ✅ 262건+ 검증 | **Python** |
| 텍스트 스타일 바인딩 | ❌ 파라미터 버그 | ✅ 183건+ 검증 | **Python** |

## Blueprint JSON 규칙
- `scripts/` 폴더에 blueprint JSON 저장 → 재사용 가능
- blueprint 내 `layoutPositioning: "ABSOLUTE"` + `constraints`는 batch_build_screen에서 미적용 → 빌드 후 `set_layout_positioning` 별도 호출 필요
- 텍스트 노드 width=0 버그: `textAutoResize: "WIDTH_AND_HEIGHT"` 재설정 후 `layoutSizingHorizontal: "FILL"` 적용으로 해결
- 프레임 fill 판단: 자식이 있는 layout 프레임은 fill 숨김(투명), 카드/배너 등 배경이 필요한 프레임만 fill 적용

## 디자인 생성 → 후속 수정 흐름 (Python)
```bash
# Step 0: Blueprint 사전 검증
python3 scripts/figma_mcp_client.py validate scripts/my_blueprint.json

# Step 1: Blueprint JSON 작성 → 빌드 (post-fix 자동 실행됨)
python3 scripts/figma_mcp_client.py build scripts/my_blueprint.json
# → 빌드 완료 후 자동으로 post-fix 실행 (FILL, Tab Bar/FAB, 섹션 간격, 텍스트)

# Step 2: (필요시) post-fix만 별도 실행
python3 scripts/figma_mcp_client.py post-fix <rootNodeId>

# Step 3: DS 변수 바인딩
python3 scripts/figma_mcp_client.py bind scripts/my_bindings.json

# Step 4: 스크린샷 QA
python3 scripts/figma_mcp_client.py call export_node_as_image '{"nodeId":"ROOT_ID","format":"PNG","scale":1}'
```

## 템플릿 기반 Blueprint 조립 (`assemble` 명령)
고정 섹션(NavBar, TabBar, FAB, Hero, Ribbon)을 템플릿에서 자동 조립하여 Blueprint 작성 시간을 대폭 단축.

```bash
python3 scripts/figma_mcp_client.py assemble scripts/my_config.json
```

**config.json 형식:**
```json
{
  "rootName": "Screen Name",
  "width": 393,
  "height": 1680,
  "fill": "$token(bg-primary)",
  "sections": ["NavBar", "TransactionRibbon", "HeroSection", "custom", "FAB", "TabBar"],
  "variables": {
    "FAB": {"label": "마이 월렛", "icon": "wallet-02"},
    "TransactionRibbon": {"text": "누적 거래 5,000,000건"},
    "HeroSection": {
      "banners": [
        {"tag": "HOT", "title": "이벤트 제목"},
        {"tag": "NEW", "title": "두번째 배너"}
      ]
    },
    "TabBar": {"activeTab": "홈"}
  },
  "customSections": [ ... PRD 고유 섹션들 ... ]
}
```

- **템플릿 파일**: `scripts/blueprint_templates.json` (5개 섹션 정의)
- **custom 섹션**: `sections` 배열에 `"custom"` 지정 → `customSections`에서 순서대로 삽입
- **출력**: `scripts/blueprint_assembled_<name>.json` → `build` 명령으로 빌드
- **효과**: NavBar+TabBar+FAB+Hero+Ribbon = ~400줄 자동 생성 → Claude는 custom 섹션만 작성
