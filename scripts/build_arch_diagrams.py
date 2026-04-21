#!/usr/bin/env python3
"""Build architecture diagrams for the 구조도 page."""
import json, sys, os, time
sys.path.insert(0, os.path.dirname(__file__))
from figma_mcp_client import ensure_session, call_tool, parse_content

# ── Colors ──
BG = {"r":0.96,"g":0.95,"b":1,"a":1}
W  = {"r":1,"g":1,"b":1,"a":1}
USR= {"r":0.91,"g":0.96,"b":0.91,"a":1}
CLD= {"r":0.89,"g":0.95,"b":0.99,"a":1}
SRV= {"r":0.95,"g":0.90,"b":0.96,"a":1}
PLG= {"r":1,"g":0.97,"b":0.88,"a":1}
FIG= {"r":0.99,"g":0.89,"b":0.93,"a":1}
DS = {"r":0.88,"g":0.95,"b":0.95,"a":1}
IMG= {"r":1,"g":0.95,"b":0.88,"a":1}
STP= {"r":0.93,"g":0.93,"b":1,"a":1}
BRD= {"r":0.41,"g":0.22,"b":0.94,"a":1}
GRN= {"r":0.18,"g":0.69,"b":0.29,"a":1}
DK = {"r":0.1,"g":0.1,"b":0.15,"a":1}
GY = {"r":0.4,"g":0.4,"b":0.45,"a":1}
LG = {"r":0.55,"g":0.55,"b":0.6,"a":1}

# ── Helpers ──
def bx(name, title, sub, detail, c, w=280):
    return {"name":name,"type":"frame","width":w,
        "autoLayout":{"layoutMode":"VERTICAL","paddingTop":16,"paddingBottom":16,"paddingLeft":20,"paddingRight":20,"itemSpacing":6},
        "cornerRadius":12,"fill":c,
        "children":[
            {"type":"text","text":title,"fontSize":20,"fontWeight":700,"fontColor":DK},
            {"type":"text","text":sub,"fontSize":14,"fontColor":GY},
            {"type":"text","text":detail,"fontSize":13,"fontColor":LG,"width":w-40}]}

def bx_sm(name, title, sub, c, w=220):
    return {"name":name,"type":"frame","width":w,
        "autoLayout":{"layoutMode":"VERTICAL","paddingTop":12,"paddingBottom":12,"paddingLeft":16,"paddingRight":16,"itemSpacing":4},
        "cornerRadius":10,"fill":c,
        "children":[
            {"type":"text","text":title,"fontSize":16,"fontWeight":700,"fontColor":DK},
            {"type":"text","text":sub,"fontSize":12,"fontColor":GY,"width":w-32}]}

def arr():
    return {"type":"text","text":"→","fontSize":32,"fontWeight":700,"fontColor":GY}

def arr_down():
    return {"type":"text","text":"↓","fontSize":32,"fontWeight":700,"fontColor":GY}

def hr(name, ch, gap=16):
    return {"name":name,"type":"frame",
        "autoLayout":{"layoutMode":"HORIZONTAL","itemSpacing":gap,"counterAxisAlignItems":"CENTER"},
        "children":ch}

def vr(name, ch, gap=12):
    return {"name":name,"type":"frame",
        "autoLayout":{"layoutMode":"VERTICAL","itemSpacing":gap},
        "children":ch}

def hd(text, sub=""):
    ch = [{"type":"text","text":text,"fontSize":28,"fontWeight":700,"fontColor":DK}]
    if sub: ch.append({"type":"text","text":sub,"fontSize":16,"fontColor":GY,"width":1900})
    return vr(text, ch, gap=8)

def step_num(n, title, detail, c=STP, w=300):
    return {"name":f"Step {n}","type":"frame","width":w,
        "autoLayout":{"layoutMode":"VERTICAL","paddingTop":16,"paddingBottom":16,"paddingLeft":20,"paddingRight":20,"itemSpacing":8},
        "cornerRadius":12,"fill":c,
        "children":[
            hr(f"Step {n} Header",[
                {"type":"text","text":str(n),"fontSize":24,"fontWeight":800,"fontColor":BRD},
                {"type":"text","text":title,"fontSize":18,"fontWeight":700,"fontColor":DK}
            ], gap=10),
            {"type":"text","text":detail,"fontSize":13,"fontColor":LG,"width":w-40}]}

# ── Section 1: System Architecture ──
def section1():
    return {"name":"Section 1: 시스템 아키텍처","type":"frame","width":1800,
        "fill":BG,"x":0,"y":0,
        "autoLayout":{"layoutMode":"VERTICAL","paddingTop":60,"paddingBottom":60,"paddingLeft":60,"paddingRight":60,"itemSpacing":40},
        "children":[
            vr("Title",[
                {"type":"text","text":"Section 1: 시스템 아키텍처","fontSize":40,"fontWeight":800,"fontColor":DK},
                {"type":"text","text":"Claude Code CLI + Bridge Server + Python HTTP Client 기반 디자인 자동화 시스템","fontSize":20,"fontColor":GY}
            ], gap=12),
            hd("메인 파이프라인","사용자 요청이 Figma 디자인으로 변환되는 전체 흐름"),
            hr("Flow Row 1",[
                bx("User","사용자 (Designer)","자연어로 디자인 요청","PRD 파일 또는 자연어\n\"스테이지 목록 화면 만들어줘\"",USR,260),
                arr(),
                bx("Claude","Claude Code (CLI)","Orchestrator + Agent","CLAUDE.md 규칙 기반\n디자인 계획 수립 + 도구 호출\n멀티에이전트 병렬 실행",CLD,300),
                arr(),
                bx("Python","Python HTTP Client","figma_mcp_client.py","Blueprint JSON build\n$token() → RGBA resolve\nbind / bind-text-styles",CLD,300),
            ]),
            hr("Flow Arrow",[{"type":"text","text":"","fontSize":10,"width":600},arr_down()],gap=0),
            hr("Flow Row 2",[
                bx("Bridge","Bridge Server","HTTP :8769 + WS :8767","JSON-RPC → WebSocket 변환\nElectron 없이 독립 실행\nnpm run bridge",SRV,300),
                arr(),
                bx("Plugin","Figma Plugin","code.js (WS Client)","62+ 커맨드 핸들러\nbatch_build_screen\nPlugin API로 노드 조작",PLG,300),
                arr(),
                bx("Figma","Figma Design","최종 산출물","DS 변수 바인딩 완료\n컴포넌트 인스턴스 + 아이콘\nGemini 이미지 삽입",FIG,280),
            ]),
            hd("디자인 시스템 레이어","Claude가 디자인 생성 시 참조하는 5개의 핵심 파일 — GitHub에서 자동 동기화"),
            hr("DS Row 1",[
                bx("DSP","DS_PROFILE.md","컴포넌트 프로필","154 컴포넌트, 4716 변형\nVariant Key, Suffix Map",DS,320),
                bx("DT","DESIGN_TOKENS.md","디자인 토큰 (GitHub Sync)","407 컬러, spacing, radius\n44 Text Styles, 24 Effects",DS,320),
                bx("TM","TOKEN_MAP.json","$token() resolve 맵","CSS변수 → figmaPath 매핑\nhex → RGBA 자동 변환",DS,320),
            ]),
            hr("DS Row 2",[
                bx("IC","ds-1-icons.json","아이콘 매핑 (1,141개)","icon name → componentId\nclone_node로 삽입",DS,320),
                bx("VR","ds-1-variants.jsonl","컴포넌트 변형 (JSONL)","154 컴포넌트 × 4,716 변형\nGrep 한 줄 조회",DS,320),
                bx("DST","DS Lookup Tools","MCP 내장 4종","lookup_icon / lookup_variant\nlookup_design_token / lookup_text_style\nGrep/Read 대신 사용 → 토큰 절약",DS,320),
            ]),
            hd("AI 이미지 생성 파이프라인","Gemini API → 로컬 저장 → rembg 배경 제거 → HTTP 서빙 → Figma 적용"),
            hr("Image Row 1",[
                bx("Gen","Gemini API","gemini-2.0-flash-exp","3D 소프트 매트 스타일\n노드 크기 × 3 해상도",IMG,280),
                arr(),
                bx("Save","로컬 저장","assets/generated/","PNG 저장, PIL crop\n타겟 크기 리사이즈",IMG,260),
                arr(),
                bx("Rembg","rembg 배경 제거","투명 PNG 생성","히어로/배너는 유지\nPython API 호출",IMG,260),
            ]),
            hr("Image Row 2",[{"type":"text","text":"","fontSize":10,"width":470},arr_down()],gap=0),
            hr("Image Row 3",[
                bx("HTTP","HTTP 서버","localhost:18765","python3 -m http.server\n프로젝트 루트 기준",IMG,280),
                arr(),
                bx("Apply","Figma 적용","set_image_fill","FILL (배너), FIT (아이콘)\nURL → 이미지 다운로드",FIG,280),
            ]),
        ]}

# ── Section 2: Design Generation Flow ──
def section2():
    return {"name":"Section 2: 디자인 생성 흐름","type":"frame","width":2100,
        "fill":{"r":0.95,"g":0.97,"b":1,"a":1},"x":2300,"y":0,
        "autoLayout":{"layoutMode":"VERTICAL","paddingTop":60,"paddingBottom":60,"paddingLeft":60,"paddingRight":60,"itemSpacing":32},
        "children":[
            vr("Title",[
                {"type":"text","text":"Section 2: 디자인 생성 흐름","fontSize":40,"fontWeight":800,"fontColor":DK},
                {"type":"text","text":"PRD → Blueprint → Figma 빌드 → 후처리 → 이미지 → DS 바인딩 → QA (싱글 에이전트 모드)","fontSize":20,"fontColor":GY}
            ], gap=12),
            # Row 1: Steps 1-3
            hr("Steps 1-3",[
                step_num(1,"PRD / 요구사항 입력","사용자가 PRD 파일 또는\n자연어로 디자인 요청\n화면 구성, 섹션, 기능 명세",USR,340),
                arr(),
                step_num(2,"DS 토큰 동기화","bash scripts/sync-tokens-from-github.sh\nGitHub에서 최신 tokens.json fetch\n→ DESIGN_TOKENS.md + TOKEN_MAP.json",DS,380),
                arr(),
                step_num(3,"Blueprint JSON 작성","$token() 참조로 컬러 지정\nauto-layout 구조 설계\n아이콘/인스턴스 명세\nscripts/ 폴더에 저장",CLD,380),
            ]),
            hr("Arrow 1-2",[{"type":"text","text":"","fontSize":10,"width":650},arr_down()],gap=0),
            # Row 2: Steps 4-5
            hr("Steps 4-5",[
                step_num(4,"Python Build 실행","figma_mcp_client.py build blueprint.json\n$token() → TOKEN_MAP.json → RGBA resolve\n→ batch_build_screen 호출\n루트 프레임 + 전체 자식 한번에 생성",SRV,500),
                arr(),
                step_num(5,"후처리","Tab Bar/FAB → ABSOLUTE positioning\nFILL sizing, zero-width 텍스트 수정\nStatus Bar clone (1:3448)\nNavBar 로고 clone (64:1449)",PLG,480),
            ]),
            hr("Arrow 2-3",[{"type":"text","text":"","fontSize":10,"width":650},arr_down()],gap=0),
            # Row 3: Steps 6-7
            hr("Steps 6-7",[
                step_num(6,"중간 QA 스크린샷","export_node_as_image → PNG 저장\nRead 도구로 시각적 확인\n레이아웃/텍스트/아이콘 검증\n문제 발견 시 즉시 수정",{"r":1,"g":0.92,"b":0.93,"a":1},480),
                arr(),
                step_num(7,"AI 이미지 생성","Gemini API로 히어로/배너/카드 그래픽\nrembg 배경 제거 → HTTP 서빙\nset_image_fill로 Figma 적용\n레퍼런스 이미지 스타일 유지",IMG,480),
            ]),
            hr("Arrow 3-4",[{"type":"text","text":"","fontSize":10,"width":650},arr_down()],gap=0),
            # Row 4: Steps 8-9
            hr("Steps 8-9",[
                step_num(8,"DS 변수 바인딩","① set_text_style_id (Text Style)\n② set_bound_variables (fontSize, lineHeight)\n③ set_bound_variables (cornerRadius)\n④ set_bound_variables (fills/0, strokes/0)\nfigma_mcp_client.py bind bindings.json",DS,500),
                arr(),
                step_num(9,"최종 QA (2회 필수)","스크린샷 촬영 → Read로 확인\n13개 체크리스트 항목 검증\n1회차 수정 → 2회차 재검증\n전체 통과 후 사용자에게 전달",{"r":0.91,"g":0.97,"b":0.91,"a":1},480),
            ]),
            hd("핵심 파일 흐름"),
            hr("File Flow",[
                bx_sm("BP","Blueprint JSON","scripts/blueprint_*.json\n$token() 컬러 참조\nautoLayout 구조 정의",CLD,300),
                arr(),
                bx_sm("TM","TOKEN_MAP.json","figmaPath → hex 매핑\n$token(name) → RGBA\nbuild 시 자동 resolve",DS,300),
                arr(),
                bx_sm("MCP","Bridge Server","batch_build_screen 실행\n루트 프레임 생성\n전체 노드 트리 빌드",SRV,300),
                arr(),
                bx_sm("BD","Bindings JSON","scripts/bindings_*.json\nnodeId → DS 변수 매핑\nbind 명령으로 일괄 적용",DS,300),
            ]),
        ]}

# ── Section 3: Design Token Flow ──
def section3():
    return {"name":"Section 3: 디자인 토큰 흐름","type":"frame","width":2100,
        "fill":{"r":0.97,"g":0.96,"b":1,"a":1},"x":4600,"y":0,
        "autoLayout":{"layoutMode":"VERTICAL","paddingTop":60,"paddingBottom":60,"paddingLeft":60,"paddingRight":60,"itemSpacing":36},
        "children":[
            vr("Title",[
                {"type":"text","text":"Section 3: 디자인 토큰 흐름","fontSize":40,"fontWeight":800,"fontColor":DK},
                {"type":"text","text":"Figma Token Studio → GitHub → 로컬 동기화 → Blueprint $token() → DS 변수 바인딩","fontSize":20,"fontColor":GY}
            ], gap=12),
            hd("① 토큰 소스 (Source of Truth)","Figma Token Studio에서 디자인 토큰을 관리하고 GitHub에 push"),
            hr("Source",[
                bx("TS","Figma Token Studio","Figma 플러그인","Variables, Text Styles,\nEffect Styles 관리\n디자이너가 직접 편집",PLG,350),
                arr(),
                bx("Git","git push","자동 동기화","tokens.json 파일\ndesign-system 레포에\n자동 커밋/푸시",{"r":0.93,"g":0.93,"b":0.93,"a":1},300),
                arr(),
                bx("GH","GitHub Repository","twavetech-frontend/design-system","tokens.json (원본 토큰)\nsync-to-agent.js (변환기)\n단일 진실 소스 (SSOT)",{"r":0.92,"g":0.92,"b":0.95,"a":1},350),
            ]),
            hd("② 로컬 동기화","sync-tokens-from-github.sh — 디자인 생성 요청마다 매번 실행 (필수)"),
            hr("Sync",[
                bx("Fetch","GitHub에서 fetch","curl raw URL","tokens.json 다운로드\nsync-to-agent.js 다운로드\n최신 데이터 확보",CLD,320),
                arr(),
                bx("Conv","sync-to-agent.js 실행","Node.js 변환","tokens.json 파싱\nDESIGN_TOKENS.md 생성\nTOKEN_MAP.json 생성",SRV,320),
                arr(),
                bx("Out","출력 파일","ds/ 디렉토리","DESIGN_TOKENS.md (토큰 값)\nTOKEN_MAP.json (매핑)\n로컬 파일 업데이트 완료",DS,320),
            ]),
            hd("③ Blueprint에서 $token() 사용","RGBA 하드코딩 대신 $token(이름) 참조 — 빌드 시 자동 resolve"),
            hr("Token Usage",[
                bx("Before","❌ 하드코딩 (금지)","fill 직접 지정","\"fill\": {\"r\":0.41, \"g\":0.22,\n\"b\":0.94, \"a\":1}\n토큰 변경 시 불일치 발생",FIG,400),
                {"type":"text","text":"VS","fontSize":24,"fontWeight":700,"fontColor":GY},
                bx("After","✅ $token() 참조 (필수)","$token() 참조","\"fill\": \"$token(bg-brand-solid)\"\n→ TOKEN_MAP.json에서 resolve\n→ 항상 최신 값 반영",DS,400),
            ], gap=40),
            hd("④ 변수 바인딩 (4단계)","빌드 완료 후 DS 변수를 노드에 바인딩 — Text Style → Typography → Radius → Color"),
            hr("Binding Steps",[
                step_num(1,"Text Style","set_text_style_id\nStyle ID: S:{key},{nodeId}\n리모트 라이브러리 자동 import",STP,320),
                arr(),
                step_num(2,"Typography","set_bound_variables\nfontSize, lineHeight\n변수 바인딩",STP,300),
                arr(),
                step_num(3,"Radius","set_bound_variables\ntopLeftRadius 등\ncornerRadius 변수",STP,280),
                arr(),
                step_num(4,"Colors","set_bound_variables\nfills/0, strokes/0\n시맨틱 컬러 토큰",STP,280),
            ]),
            hd("⑤ 토큰 업데이트 워크플로우","디자이너가 Figma에서 변수 변경 → Token Studio push → 자동 반영"),
            hr("Update Flow",[
                bx_sm("Edit","디자이너: 변수 편집","Figma에서 색상/spacing 변경\nToken Studio로 push",PLG,300),
                arr(),
                bx_sm("Push","GitHub 반영","design-system 레포 업데이트\ntokens.json 갱신",{"r":0.93,"g":0.93,"b":0.93,"a":1},280),
                arr(),
                bx_sm("Sync","동기화 실행","sync-tokens-from-github.sh\nDESIGN_TOKENS.md 재생성",DS,300),
                arr(),
                bx_sm("Build","다음 디자인 생성","$token() 자동 최신 값\n변경사항 즉시 반영",CLD,280),
            ]),
        ]}

# ── Section 4: Multi-Agent Pipeline ──
def section4():
    return {"name":"Section 4: 멀티에이전트 파이프라인","type":"frame","width":2100,
        "fill":{"r":0.96,"g":0.95,"b":1,"a":1},"x":2300,"y":2600,
        "autoLayout":{"layoutMode":"VERTICAL","paddingTop":60,"paddingBottom":60,"paddingLeft":60,"paddingRight":60,"itemSpacing":36},
        "children":[
            vr("Title",[
                {"type":"text","text":"Section 4: 멀티에이전트 파이프라인","fontSize":40,"fontWeight":800,"fontColor":DK},
                {"type":"text","text":"화면 섹션 3+개, 이미지 1+개, 아이콘 5+개, 바인딩 20+노드 시 자동 발동","fontSize":20,"fontColor":GY}
            ], gap=12),
            hd("실행 흐름","Orchestrator → Wave 1 (구조+이미지 병렬) → Wave 2 (토큰+아이콘 병렬) → QA → Fix"),
            # Orchestrator
            hr("Orch Row",[
                {"type":"text","text":"","fontSize":10,"width":300},
                bx("Orch","Orchestrator","계획 수립 + 루트 프레임 생성","PRD 분석 → 섹션 분할\n루트 프레임 생성 (393×h)\n에이전트 태스크 분배\n이미지 머지 + Fix 루프",{"r":0.95,"g":0.93,"b":1,"a":1},400),
            ]),
            hr("Arrow Orch",[{"type":"text","text":"","fontSize":10,"width":470},arr_down()],gap=0),
            # Wave 1
            hd("병렬 Wave 1","구조 빌드 + 이미지 생성을 동시에 실행"),
            hr("Wave 1",[
                bx("AgentA","Agent A: 구조 빌드","batch_build_screen","섹션 프레임 생성\n컴포넌트 인스턴스\n텍스트 노드 배치\nHeader → 각 섹션 순서",CLD,420),
                {"type":"text","text":"‖","fontSize":48,"fontWeight":700,"fontColor":BRD},
                bx("AgentB","Agent B: Gemini 이미지","이미지 생성 + 로컬 저장","Gemini API 호출\n3D 소프트 매트 스타일\nrembg 배경 제거\nassets/generated/ 저장",IMG,420),
            ], gap=40),
            hr("Arrow W1",[{"type":"text","text":"","fontSize":10,"width":470},arr_down()],gap=0),
            hr("Merge Row",[
                {"type":"text","text":"","fontSize":10,"width":200},
                bx_sm("MG","Orchestrator: 이미지 머지","Agent B 결과를 Agent A 프레임에 set_image_fill로 적용",SRV,500),
            ],gap=0),
            hr("Arrow Merge",[{"type":"text","text":"","fontSize":10,"width":470},arr_down()],gap=0),
            # Wave 2
            hd("병렬 Wave 2","DS 토큰 바인딩 + 아이콘 삽입을 동시에 실행"),
            hr("Wave 2",[
                bx("AgentC","Agent C: DS 토큰 바인딩","Text Style → Typography → Color","set_text_style_id\nset_bound_variables\nfontSize, lineHeight, radius\nfills/0, strokes/0",DS,420),
                {"type":"text","text":"‖","fontSize":48,"fontWeight":700,"fontColor":BRD},
                bx("AgentD","Agent D: 아이콘 삽입","clone_node + insert_child","ds-1-icons.json 검색\nclone_node로 복제\ninsert_child로 삽입\nset_selection_colors 색상",PLG,420),
            ], gap=40),
            hr("Arrow W2",[{"type":"text","text":"","fontSize":10,"width":470},arr_down()],gap=0),
            # QA + Fix
            hr("QA Row",[
                {"type":"text","text":"","fontSize":10,"width":100},
                bx("QA","QA Agent","13개 체크리스트 검증","스크린샷 촬영 + Read 확인\nwidth=393, 텍스트 가시성\n섹션 간격 24px 균일\nfixInstructions 생성",{"r":1,"g":0.92,"b":0.93,"a":1},380),
                arr(),
                bx("Fix","Fix 루프 (최대 2회)","Orchestrator 직접 수정","QA 실패 시 fixInstructions\n기반으로 수정\n재QA → 통과 시 완료",SRV,380),
                arr(),
                bx("Done","완료","사용자에게 전달","\"확인해주세요\"\n(\"완료\" 금지)",USR,240),
            ]),
            hd("에이전트별 출력 형식"),
            hr("Output",[
                bx_sm("A-Out","Agent A 출력","nodeId 포함 JSON\n{rootId, sections: [{id, name}]}",CLD,340),
                bx_sm("B-Out","Agent B 출력","이미지 파일 경로 JSON\n{images: [{path, targetNodeId}]}",IMG,340),
                bx_sm("C-Out","Agent C 출력","바인딩 결과 JSON\n{bound: count, failed: count}",DS,340),
                bx_sm("QA-Out","QA Agent 출력","체크 결과 + 수정 지시\n{pass: bool, fixInstructions: []}",FIG,340),
            ]),
        ]}

# ── Main ──
def build(blueprint, label):
    path = f"/tmp/arch_{label}.json"
    with open(path, "w") as f:
        json.dump(blueprint, f, ensure_ascii=False)
    print(f"\n{'='*60}")
    print(f"Building {label}...")
    content = call_tool("batch_build_screen", {"blueprint": blueprint})
    result = parse_content(content)
    if result["json"]:
        rid = result["json"].get("rootId") or result["json"].get("nodeId")
        print(f"  Root ID: {rid}")
        return rid
    for t in result["texts"]:
        print(f"  {t[:200]}")
    return None

def main():
    ensure_session()

    # Rebuild S3 only (S1=71:1009, S2=71:528, S4=71:922 already exist)
    # Delete old S3 first
    try:
        call_tool("delete_node", {"nodeId": "71:631"})
        print("Deleted old S3 (71:631)")
    except Exception as e:
        print(f"Skip delete S3: {e}")
    time.sleep(0.5)
    ids = {}
    for label, fn in [("s3", section3)]:
        bp = fn()
        rid = build(bp, label)
        ids[label] = rid
        time.sleep(0.5)

    print(f"\n{'='*60}")
    print("Rebuilt sections:")
    for k, v in ids.items():
        print(f"  {k}: {v}")

if __name__ == "__main__":
    main()
