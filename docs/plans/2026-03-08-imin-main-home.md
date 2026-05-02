# 아이민(imin) 메인 홈 화면 구현 계획

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** PRD 기반 아이민 메인 홈 화면을 Figma에 생성 (멀티에이전트 모드)

**Architecture:** Blueprint JSON → batch_build_screen → 후처리(Status Bar, Tab Bar ABSOLUTE, FILL 사이징) → Gemini 이미지 생성(병렬) → 이미지 적용 → DS 변수 바인딩 → QA 2회

**Tech Stack:** Python figma_mcp_client.py, Gemini API (nano-banana-pro-preview), rembg, DS v1 토큰

---

### Task 1: DS 토큰 동기화 + HTTP 서버 시작

**Step 1: DS 토큰 동기화**
```bash
cd /Users/julee/figma-design-agent && bash scripts/sync-tokens-from-github.sh
```

**Step 2: HTTP 서버 시작 (이미지 서빙용)**
```bash
cd /Users/julee/figma-design-agent && python3 -m http.server 18765 &
```

**Step 3: MCP 세션 초기화**
```bash
python3 scripts/figma_mcp_client.py init
```

---

### Task 2: Blueprint JSON 작성

**Files:**
- Create: `scripts/blueprint_imin_home_v2.json`

기존 `blueprint_main_home.json`을 기반으로 아래 변경사항 반영:

**변경 사항:**
1. **Stage Card 3 추가** — "여행 자금 모으기" 150만원, 연 4.8%, 6개월, +포인트 2배
2. **FAB 텍스트 수정** — "마이 월렛" → "마이 원릿"
3. **Stage Card 상품명 추가** — 각 카드에 상품명 텍스트 노드 추가 (Card Title: "직장인 월급 스테이지" 등)
4. **Stage Card 태그 다양화** — 카드별 다른 혜택 태그 (포인트, 기프트카드, 2배 적립)
5. **y 좌표 재계산** — 카드 3개로 늘어난 Stage Section 높이 반영

**규칙 체크리스트 (빌드 전 확인):**
- [ ] 모든 컬러 → `$token()` 참조 (RGBA 하드코딩 없음, 흰색/검정/투명 제외)
- [ ] NavBar 로고 → `"Logo Placeholder"` 텍스트 (빌드 후 인스턴스로 교체)
- [ ] 태그/칩 → `layoutSizingHorizontal` 미지정 또는 HUG
- [ ] SPACE_BETWEEN + FILL 자식 조합 없음
- [ ] 섹션 타이틀 → Bold
- [ ] Tab Bar 아이템 → FILL 균등
- [ ] 리본 배경 → 연한 색 ($token(bg-brand-primary))
- [ ] 아이콘 type → "icon" (svg_icon 아님)

**Step 1: 블루프린트 JSON 작성**
기존 `blueprint_main_home.json` 구조를 참고하되 **새로 작성** (재사용 금지). 위 변경사항 반영.

**Step 2: 블루프린트 검증**
```bash
python3 scripts/figma_mcp_client.py validate scripts/blueprint_imin_home_v2.json
```

---

### Task 3: Figma 빌드 (batch_build_screen)

**Step 1: 빌드 실행**
```bash
python3 scripts/figma_mcp_client.py build scripts/blueprint_imin_home_v2.json
```
- 결과에서 `rootId`와 `nodeMap` 저장 (이후 모든 작업에 사용)

**Step 2: 빌드 직후 스크린샷 확인**
MCP HTTP로 스크린샷 촬영 → `/tmp/qa_build.png` 저장 → Read로 시각적 확인
- 레이아웃 깨짐, 텍스트 잘림, 아이콘 미표시 확인

---

### Task 4: 후처리 — Status Bar + NavBar 로고 + Tab Bar/FAB ABSOLUTE

**Step 1: Status Bar 삽입**
```bash
# clone_node로 Status Bar 인스턴스 복제
python3 scripts/figma_mcp_client.py call clone_node '{"nodeId":"1:3448","targetParentId":"<ROOT_ID>"}'
# insert_child로 index=0에 배치
python3 scripts/figma_mcp_client.py call insert_child '{"parentId":"<ROOT_ID>","childId":"<STATUS_BAR_ID>","index":0}'
# FILL 사이징 + 리사이즈
python3 scripts/figma_mcp_client.py call set_layout_sizing '{"nodeId":"<STATUS_BAR_ID>","horizontal":"FILL"}'
python3 scripts/figma_mcp_client.py call resize_node '{"nodeId":"<STATUS_BAR_ID>","width":393,"height":54}'
```

**Step 2: NavBar 로고 인스턴스 교체**
```bash
# 로고 텍스트 노드 삭제 → 컴포넌트 인스턴스 생성 → insert_child
python3 scripts/figma_mcp_client.py call create_component_instance '{"componentKey":"81efeddd245e95f31a2724aa370ee54d3caf93d0"}'
python3 scripts/figma_mcp_client.py call insert_child '{"parentId":"<NAVBAR_ID>","childId":"<LOGO_INSTANCE_ID>","index":0}'
# 기존 "Logo Placeholder" 텍스트 삭제
python3 scripts/figma_mcp_client.py call delete_node '{"nodeId":"<LOGO_PLACEHOLDER_ID>"}'
```

**Step 3: Tab Bar + FAB → ABSOLUTE 포지셔닝**
```bash
python3 scripts/figma_mcp_client.py call set_layout_positioning '{"nodeId":"<TAB_BAR_ID>","positioning":"ABSOLUTE","constraints":{"horizontal":"STRETCH","vertical":"MAX"}}'
python3 scripts/figma_mcp_client.py call set_layout_positioning '{"nodeId":"<FAB_ID>","positioning":"ABSOLUTE","constraints":{"horizontal":"MAX","vertical":"MAX"}}'
```

**Step 4: Tab Bar 아이템 FILL 사이징 + 텍스트 CENTER**
nodeMap에서 각 탭 아이템 ID 확인 → `set_layout_sizing(horizontal: "FILL", vertical: "FILL")` 적용

**Step 5: zero-width 텍스트 수정**
빌드 후 width=0인 텍스트 노드가 있으면:
```bash
python3 scripts/figma_mcp_client.py call set_text_properties '{"nodeId":"<TEXT_ID>","textAutoResize":"WIDTH_AND_HEIGHT"}'
python3 scripts/figma_mcp_client.py call set_layout_sizing '{"nodeId":"<TEXT_ID>","horizontal":"FILL"}'
```

**Step 6: 후처리 스크린샷 확인**
스크린샷 촬영 → `/tmp/qa_postprocess.png` → Read로 확인

---

### Task 5: Gemini 이미지 생성 (병렬 실행)

> 이 태스크는 Task 4와 **병렬로** 실행 가능 (Agent run_in_background)

**생성할 이미지 목록:**

| # | 용도 | 프레임 크기 | 이미지 크기(3x) | 스타일 | rembg |
|---|------|-----------|---------------|--------|-------|
| 1 | Hero 배너 1 "친구 초대" | 353×200 | 1059×600 | 소프트 매트 히어로 | No |
| 2 | Hero 배너 2 "봄맞이 프로모션" | 353×200 | 1059×600 | 소프트 매트 히어로 | No |
| 3 | Hero 배너 3 "첫 스테이지 보너스" | 353×200 | 1059×600 | 소프트 매트 히어로 | No |
| 4 | 랜덤박스 3D 아이콘 | 50×50 | 150×150 | 비비드 글로시 3D | Yes |
| 5 | 기프트샵 3D 아이콘 | 50×50 | 150×150 | 비비드 글로시 3D | Yes |

**Step 1: Gemini API 키 확인**
```bash
python3 -c "
from scripts.figma_mcp_client import *
# settings에서 API 키 확인
"
```
또는 환경변수/settings-store에서 키 로드

**Step 2: Hero 배너 3장 생성**
각 배너 프롬프트:
- 배너 1: `"3D rendered gift box with ribbon and sparkles. Cinema4D Octane render, soft matte finish, pastel purple gradient background. Place the 3D object on the RIGHT side of the image, leave the LEFT half completely empty with solid color background for text overlay. ONLY ONE single object. No text. No shadow. Aspect ratio 16:9."`
- 배너 2: `"3D rendered spring sprout with leaves growing from a pot. Cinema4D Octane render, soft matte finish, pastel mint/green gradient background. Place the 3D object on the RIGHT side, leave LEFT half empty. ONLY ONE single object. No text. No shadow. Aspect ratio 16:9."`
- 배너 3: `"3D rendered stack of golden coins with upward arrow. Cinema4D Octane render, soft matte finish, pastel warm orange gradient background. Place the 3D object on the RIGHT side, leave LEFT half empty. ONLY ONE single object. No text. No shadow. Aspect ratio 16:9."`

레퍼런스 이미지: `assets/reference-images/hero/` 에서 랜덤 2장 포함

**Step 3: 3D 아이콘 2개 생성**
프롬프트 (비비드 글로시 스타일):
- 랜덤박스: `"3D rendered icon of a gift box with question mark, in the style of Korean travel apps like Yeogieoddae and Yanolja. Vibrant saturated colors, glossy plastic finish, rounded toy-like proportions, playful and fun. Slightly glossy highlight on top. Single centered object. Pure white background. No text. No shadow. chunky, compact, equal width and height, square proportions"`
- 기프트샵: `"3D rendered icon of a shopping bag with sparkles, in the style of Korean travel apps like Yeogieoddae and Yanolja. Vibrant saturated colors, glossy plastic finish, rounded toy-like proportions, playful and fun. Slightly glossy highlight on top. Single centered object. Pure white background. No text. No shadow. chunky, compact, equal width and height, square proportions"`

레퍼런스 이미지: `assets/reference-images/icon/` 에서 랜덤 2장 포함

**Step 4: rembg 배경 제거 (3D 아이콘만)**
```python
from rembg import remove
for fname in ["random_box_icon.png", "gift_shop_icon.png"]:
    output = remove(open(f"assets/generated/{fname}", "rb").read())
    open(f"assets/generated/{fname}", "wb").write(output)
```

**Step 5: PIL center-crop + 리사이즈**
```python
from PIL import Image
# 히어로 배너: 1059×600으로 crop+resize
# 아이콘: 150×150으로 crop+resize (정사각형)
```

---

### Task 6: 이미지 적용 (set_image_fill)

**Step 1: Hero 배너 이미지 적용**
nodeMap에서 "Banner Card" ID 확인 → set_image_fill
```bash
python3 scripts/figma_mcp_client.py call set_image_fill '{"nodeId":"<BANNER_CARD_ID>","url":"http://localhost:18765/assets/generated/hero_banner_1.png","scaleMode":"FILL"}'
```
배너 2, 3은 추가 배너 프레임에 적용 (현재 블루프린트에는 배너 1개만 → 빌드 후 추가 배너 프레임 생성 필요하거나, 블루프린트에 3개 배너를 미리 포함)

> **중요**: 블루프린트에 배너 3개를 가로 나열로 포함하되, 카루셀 형태로 첫 번째만 보이도록 설계. 또는 별도 프레임으로 캔버스에 나란히 배치.

**Step 2: 3D 아이콘 적용**
```bash
python3 scripts/figma_mcp_client.py call set_image_fill '{"nodeId":"<RANDOM_ICON_FRAME_ID>","url":"http://localhost:18765/assets/generated/random_box_icon.png","scaleMode":"FIT"}'
python3 scripts/figma_mcp_client.py call set_image_fill '{"nodeId":"<GIFT_ICON_FRAME_ID>","url":"http://localhost:18765/assets/generated/gift_shop_icon.png","scaleMode":"FIT"}'
```

**Step 3: 이미지 적용 스크린샷 확인**
`/tmp/qa_images.png` → Read로 확인

---

### Task 7: DS 변수 바인딩

**Files:**
- Create: `scripts/bindings_imin_home.json`
- Create: `scripts/text_styles_imin_home.json`

**Step 1: Text Style 바인딩**
nodeMap의 모든 텍스트 노드에 대해 fontSize + fontWeight 매칭되는 Text Style ID 적용
```bash
python3 scripts/figma_mcp_client.py bind-text-styles scripts/text_styles_imin_home.json
```

**Step 2: Color + Radius + Spacing 바인딩**
```bash
python3 scripts/figma_mcp_client.py bind scripts/bindings_imin_home.json
```

---

### Task 8: QA Pass 1

**Step 1: 스크린샷 촬영**
```bash
python3 -c "
import json, urllib.request, base64
url = 'http://localhost:8769/mcp'
init_body = json.dumps({'jsonrpc':'2.0','method':'initialize','params':{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'qa','version':'1.0'}},'id':1})
req = urllib.request.Request(url, init_body.encode(), {'Content-Type':'application/json'})
resp = urllib.request.urlopen(req, timeout=10)
sid = resp.headers.get('Mcp-Session-Id','')
body = json.dumps({'jsonrpc':'2.0','method':'tools/call','params':{'name':'export_node_as_image','arguments':{'nodeId':'<ROOT_ID>','format':'PNG','scale':1}},'id':2})
req = urllib.request.Request(url, body.encode(), {'Content-Type':'application/json','Mcp-Session-Id':sid})
resp = urllib.request.urlopen(req, timeout=30)
data = json.loads(resp.read())
for part in data.get('result',{}).get('content',[]):
    if part.get('type') == 'image':
        img = base64.b64decode(part['data'])
        with open('/tmp/qa_pass1.png','wb') as f: f.write(img)
        break
"
```

**Step 2: Read로 시각적 확인 + 13개 체크리스트**
1. full-width 요소 width=393
2. 텍스트 가시성 (배경 대비)
3. 최소 폰트 12px (탭 라벨 11px 허용)
4. PRD 1:1 매핑 — 모든 UI 요소 존재
5. 아이콘 렌더링 확인
6. 이미지 영역 채움 확인
7. 자식 프레임 불필요 fill 없음
8. 아이콘-텍스트 간격 12px+
9. FAB-TabBar 간격 16px+
10. Tab Bar 균등 배분
11. SPACE_BETWEEN + FILL 충돌 없음
12. 텍스트 weight 위계
13. 섹션 간 간격 24px 균일

**Step 3: 프로그래밍적 검증**
```bash
# 각 섹션 y, height 조회 → gap 계산
python3 scripts/figma_mcp_client.py call get_nodes_info '{"nodeIds":["<SECTION_IDS>"]}'
```

**Step 4: 문제 수정** — 발견된 이슈 즉시 수정

---

### Task 9: QA Pass 2

**Step 1: 수정 후 스크린샷 재촬영**
`/tmp/qa_pass2.png` → Read로 확인

**Step 2: 13개 체크리스트 재확인**
모든 항목 통과 확인

**Step 3: 임시 파일 정리**
```bash
rm -f /tmp/qa_*.png
```

---

### Task 10: 완료 전달

사용자에게 "확인해주세요" + 최종 스크린샷 제시
