# 디자인 완료 QA 절대 규칙 (ABSOLUTE RULES)

> 이 규칙은 **모든 디자인 생성 작업**에서 반드시 적용된다. 예외 없음.

## 스크린샷 촬영 방법 (필수 — MCP HTTP 직접 호출)
MCP 도구(`export_node_as_image`)가 "Server not initialized" 에러를 내는 경우, **MCP HTTP 엔드포인트를 직접 호출**하여 스크린샷을 로컬 PNG로 저장한 뒤 `Read` 도구로 이미지를 확인한다.

```python
import json, urllib.request, base64

url = 'http://localhost:8769/mcp'

# 1. Initialize session
init_body = json.dumps({'jsonrpc':'2.0','method':'initialize','params':{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'qa','version':'1.0'}},'id':1})
req = urllib.request.Request(url, init_body.encode(), {'Content-Type':'application/json'})
resp = urllib.request.urlopen(req, timeout=10)
sid = resp.headers.get('Mcp-Session-Id','')

# 2. Export screenshot
body = json.dumps({'jsonrpc':'2.0','method':'tools/call','params':{'name':'export_node_as_image','arguments':{'nodeId':'<ROOT_ID>','format':'PNG','scale':1}},'id':2})
req = urllib.request.Request(url, body.encode(), {'Content-Type':'application/json','Mcp-Session-Id':sid})
resp = urllib.request.urlopen(req, timeout=30)
data = json.loads(resp.read())

# 3. Save image
for part in data.get('result',{}).get('content',[]):
    if part.get('type') == 'image':
        img = base64.b64decode(part['data'])
        with open('/tmp/qa_screenshot.png','wb') as f:
            f.write(img)
        break
```

저장 후 `Read("/tmp/qa_screenshot.png")`로 이미지를 **직접 눈으로 확인**한 뒤 QA를 수행한다. **스크린샷을 Read로 열어보지 않고 QA를 통과시키는 것은 금지.**

## 빌드 중간 QA (단계별 스크린샷 필수)
디자인은 **한 번에 완벽하게 끝나지 않는다.** 빌드 직후 반드시 스크린샷을 찍고 문제를 즉시 수정해야 한다.

**필수 스크린샷 시점:**
1. **`batch_build_screen` 직후** — 빌드 결과를 스크린샷으로 확인. 레이아웃 깨짐, 텍스트 잘림, 아이콘 미표시, 색상 오류 등 즉시 수정
2. **후처리(Tab Bar absolute, FILL 사이징, 아이콘 색상 등) 적용 후** — 후처리가 올바르게 적용되었는지 스크린샷 확인
3. **이미지 생성 및 적용 후** — Gemini 이미지가 올바른 노드에 올바른 크기로 적용되었는지 확인
4. **수정 작업 후 매번** — 어떤 수정이든 적용 후 반드시 스크린샷으로 결과 검증

**스크린샷 촬영 → Read로 확인 → 문제 발견 → 수정 → 다시 촬영** 사이클을 반복한다. Read로 이미지를 열어보지 않은 QA는 무효.

**중간 QA 체크 항목:**
- 아이콘이 실제로 보이는가? (프레임만 있고 빈 상태가 아닌가?)
- 아이콘/텍스트가 배경 대비 보이는가? (명도 대비 4:1 이상)
- 텍스트가 잘리지 않는가?
- 섹션 너비가 화면 전체(393px)를 채우는가?
- Auto Layout이 의도대로 동작하는가? (HUG vs FILL)
- **Status Bar가 빌드 자동 삽입된 DS 인스턴스(INSTANCE "Status Bar")인가?** blueprint에 직접 넣었으면 실패 (CLAUDE.md 규칙 1)

**규칙: 스크린샷 없이 다음 단계로 넘어가지 말 것.** 눈으로 확인하지 않은 변경은 문제를 누적시킨다.

## 완료 전 필수 QA (스크린샷 체크리스트)
디자인 생성/수정 후 "확인해주세요"를 말하기 전 **반드시 스크린샷을 찍고 아래 6개 항목을 하나씩 확인**:

1. **모든 full-width 요소는 width=393** — NavBar, TabBar, 섹션 프레임 등 루트 직접 자식은 반드시 화면 폭과 동일 (393px)
2. **텍스트 가시성** — 모든 텍스트가 배경 대비 읽히는지 확인. 특히 컬러 배경 위 버튼 텍스트는 **명시적으로 fontColor 설정**
3. **최소 폰트 12px** — 9px, 10px 등 사용 금지. 예외: 탭 라벨/FAB 라벨은 최소 11px 허용
4. **PRD 1:1 매핑 (섹션 전수 검사)** — PRD에 명시된 모든 섹션/UI 요소를 **목록으로 나열**하고, 스크린샷에서 **각 섹션이 눈에 보이는지 하나씩 체크**. 하나라도 안 보이면 실패. "스크롤 영역이라 정상"으로 넘기지 말 것 — 디자인 프레임에 전체 콘텐츠가 보여야 함. 루트 프레임 높이가 부족하면 늘릴 것
5. **아이콘/북마크 시각적 확인** — 프레임만 만들고 끝내지 말 것. 반드시 아이콘이 렌더링되는지 스크린샷으로 확인. `_fallback: true` 프레임 없어야 함
6. **이미지 필요 영역** — placeholder 프레임(빈 사각형)을 남기지 말 것. Gemini 이미지 생성 또는 DS 아이콘으로 반드시 채울 것
7. **자식 프레임 불필요 fill 없음** — 부모에 배경색이 있는 카드/섹션 내부 레이아웃 프레임(Top, Tags, Title Group)에 흰색 fill이 있으면 실패
8. **아이콘-텍스트 간격 확인** — 리스트 아이템, 탭 등에서 아이콘과 텍스트가 붙어있으면 실패 (최소 12px)
9. **FAB-TabBar 간격 확인** — FAB가 Tab Bar와 붙어있으면 실패 (최소 16px)
10. **Tab Bar 정렬** — 모든 탭 아이템 균등 배분(FILL), 아이콘+라벨 수직 중앙 정렬, 외곽선 없음
11. **SPACE_BETWEEN + FILL 충돌** — HORIZONTAL auto-layout에서 `SPACE_BETWEEN` + 자식 `FILL` 조합이 있으면 실패 (간격이 0이 됨)
12. **텍스트 weight 위계** — 섹션 타이틀이 Bold가 아니거나, 화면 전체가 동일 weight이면 실패. 타이틀→Bold, 핵심 정보→Bold/SemiBold, 보조→Medium, 설명→Regular
13. **섹션 간 간격 균일성 (24px)** — 루트 프레임의 직접 자식 콘텐츠 섹션 간 간격이 **일관되게 24px**인지 `get_nodes_info`로 각 섹션의 y, height를 조회하여 프로그래밍적으로 검증. `gap = next_section.y - (current_section.y + current_section.height)`. 간격이 24px ± 2px 범위를 벗어나면 실패. **겹침(음수 gap)은 절대 금지**. 예외: NavBar↔Ribbon↔Hero는 0px(밀착), FAB↔TabBar는 16px

## 레이아웃 절대 규칙
- **루트 프레임 높이 = 모든 UI가 보이는 높이** — 콘텐츠가 852px(뷰포트)를 초과하면 루트 프레임 height를 늘려서 **모든 UI 요소가 스크린샷에 보이도록** 할 것. 잘리는 콘텐츠 절대 금지
- **TabBar/FAB는 Constraints: Bottom** — 루트 프레임 높이를 늘릴 때 TabBar와 FAB는 항상 루트 프레임 하단에 고정
- 루트 프레임 자식 중 가로 전체를 차지하는 프레임: **반드시 width=393, x=0**
- Auto Layout 자식: **set_layout_sizing(horizontal: "FILL")** 적용
- 버튼/태그 텍스트: 배경색과 텍스트 색상 대비 반드시 확인 후 명시적 color 설정
- 프레임 안에 아이콘이 있으면 아이콘이 보이는 크기인지 확인 (최소 16×16)

## 디자인 완료 후 워크플로우 (순서대로 실행)
QA 체크리스트 통과 후, 아래 단계를 **순서대로** 진행:

1. **히어로/배너 그래픽 생성 확인** — 히어로 섹션이나 배너에 그래픽·일러스트가 필요한 경우 사용자에게 물어본다: "히어로 섹션에 그래픽 이미지를 생성할까요?" → 사용자가 허락하면 Gemini로 생성, 거부하면 패스
2. **DS 변수 바인딩 확인** — "디자인 시스템 변수 바인딩을 진행할까요?" → 사용자가 허락하면 바인딩 수행 (Text Style → Typography → Radius → Color 순서), 거부하면 패스
3. **최종 전달** — "확인해주세요"로 전달

## 완료 판단 기준 (QA 2회 필수 — 스크린샷 실물 확인)
- "완료"라고 말하면 **절대 안 됨** — 항상 "확인해주세요"로 전달
- **QA는 반드시 2회(2 pass) 수행** — 매 pass마다 스크린샷을 MCP HTTP로 저장 → `Read`로 이미지를 직접 열어서 확인 → 체크리스트 항목별 서술형 확인
- 1회차 QA에서 발견된 문제 수정 → 2회차 QA 스크린샷 촬영 + `Read`로 열어서 재확인. 2회차도 통과해야만 사용자에게 전달
- **스크린샷을 `Read`로 열어보지 않고 "통과"라고 하는 것은 절대 금지** — 프로그래밍적 치수 확인만으로는 부족, 반드시 시각적 확인 필수
- 하나라도 실패하면 수정 후 다시 스크린샷 → `Read` → 재확인 (2회 통과할 때까지 반복)
- 체크리스트 전체 통과 × 2회 후에만 사용자에게 전달
