# 디자인 룰 상세 (전체 원문)

> 🔴 **이 문서는 CLAUDE.md 디자인 룰의 상세 원문이다** (2026-07-09 Phase 5 인덱스화로 CLAUDE.md
> 에서 이관 — Astryx 압축 인덱스 철학: CLAUDE.md 엔 인덱스만, 상세는 retrieval).
> - 조회: `python3 scripts/figma_mcp_client.py rule <id>` (예: `rule 0-J`, `rule 2-G-4`,
>   `rule post-fix`, `rule troubleshooting`, `rule --list`)
> - 컴포넌트 키/예시: `component "<이름>"` / `search "<쿼리>"`
> - ⚠️ 룰을 개정하면 **이 문서(원문)와 CLAUDE.md 인덱스(요약 한 줄)를 함께 갱신**할 것.
>   컴포넌트 룰이면 `ds/COMPONENT_GUIDANCE.json` 도.

## 디자인 생성 필수 규칙

> 🎨 **룰 2계층 (2026-06-12 전면 개편 — 사용자: "규칙과 코드 강제로 수천 번 생성해도 거의 똑같아.
> 창의적으로 나오길 원해")**
>
> 이 문서의 룰은 두 계층으로 나뉜다. **회귀 방지(=같음 보장)는 정합성에만 적용하고, 스타일에는
> 적용하지 않는다** — 스타일까지 하드 강제하면 모든 화면이 한 디자인으로 수렴한다(실제로 그랬다).
>
> **① 정합성 룰 (하드 — enforcer 가 강제, 변경 없음):** 콘텐츠 1:1(0-E)·DS 컴포넌트 사용/색
> 보존(0-K, 0-J, 0-M, 0-W, 2-G, 2-I)·토큰/텍스트스타일/spacing/radius 바인딩(0-S, post-fix 바인더)·
> 접근성(대비 QA, 최소 텍스트 크기)·레이아웃 무결성(FILL 붕괴, 셀 정렬, clip 0-Q, 스멜 검사)·
> 디바이스 규격(루트 bg 0, 852, Status Bar, Tab Bar 위치)·프로세스 게이트(통독, 레퍼런스 Read 0-G,
> self-verify 0-F, blueprint 정리 0-R).
>
> **② 스타일 룰 (기본값 — author 명시값이 항상 이긴다):** 아래 룰들은 2026-06-12 부로
> **fill-in-only**(명시 안 했을 때만 기본값 채움) 또는 **advisory WARN**(변경 없이 경고만)으로
> 강등됐다. 빌드 로그에 `[스타일-기본값]` 프리픽스로 표시된다:
> - **2-B** 흰 카드+보더 → 그레이 면 강제 flip 폐지(WARN만). 보더 자동부착은 **흰-on-흰(경계가
>   안 보이는 배치)만** 시인성 보더 추가 — 대비 있는 카드(흰 on 회색밴드, 회색 on 흰)는 미추가.
>   `_keepSurface` 마커는 이제 불필요(하위호환 유지).
> - **2-B-2** 브랜드 틴트 면 = bg-brand-primary → advisory WARN (live 교정 no-op).
> - **2-H** 큰 면적 brand fill 금지 → advisory WARN — **의도된 컬러 히어로 카드/밴드 허용**.
>   가독성은 대비 QA(_auto_fix_invisible_text + _qa_visual_checks)가 방어.
> - **규칙 13** 🔻 2026-06-18 **색 강제 삭제**: 중요 섹션을 bg-secondary 밴드로 고정 + 내부 블록 흰색화 →
>   둘 다 폐기. 강조 여부·섹션 색·내부 블록 색 **전부 작성자 자율**. `_band` 는 색 마커가 아니라 *풀폭
>   구조* 마커(FILL + padding fill-in)일 뿐 — 색면 원하면 `fill` 직접 명시.
> - **13-B** Content gap 20 → 명시 gap 존중(WARN), 미지정만 20.
> - **19-B** 세로 패딩 대칭(pt==pb) → 미세 차이(≤4px)만 fill-in 교정, **큰 비대칭은 디자인
>   도구로 존중**(advisory WARN). 의도면 `_asymPad` 로 침묵.
>
> **②-삭제 (2026-06-18 사용자 결정 — 창의 변형과 충돌해 *완전 삭제*):**
> - ⛔ **0-I 섹션 타이틀 좌측정렬 강제 → 삭제** (R59 파일 제거). 정렬은 작성자 자유(센터드 히어로 등).
> - ⛔ **`_enforce_text_hierarchy` 금액 30px 자동 승격 → 삭제(no-op)**. 타이포 위계는 작성자 자유.
>   (DS 스케일 2-C·접근성 하한만 정합성으로 유지.)
>
> 🔴 **③ 창의 프로세스 — "콘텐츠는 1:1, 비주얼은 매 시안 다르게" (2026-06-15 / 2026-06-18 사용자 핵심 룰):**
>
> 사용자 명시: *"생성되는 디자인들이 와이어프레임과 똑같다는 게 가장 큰 문제. 100번을 생성하면
> 100번 다 와이어와 똑같이 나오면 디자인이 의미가 없다. 콘텐츠 영역 안에서 레이아웃·컬러·간격·
> 배치·정렬·타이포 위계는 훨씬 창의적으로 나왔으면 한다."*
>
> 콘텐츠(텍스트/숫자/카운트)는 와이어 1:1(0-E)이되, **콘텐츠 영역 안의 디자인**(레이아웃·컬러·
> 간격·배치·정렬·타이포 위계)은 **매 시안 다르게** 도출한다. 와이어 레이아웃 미러링 = 디자인 안 한
> 것(0-C/0-N). 스타일 enforcer 는 ② 처럼 fill-in-only/advisory 로 강등돼 **내 명시 선택이 항상
> 이기므로**, 창의는 *내가* 매 시안 만들어야 한다. 이를 강제하는 게이트 2개:
>
> - 🔴 **S24 컨셉 선언 게이트**: imin_* 빌드는 root 에
>   `"_concept": {"idea": "<핵심 차별 아이디어>", "diffs": ["직전 버전과 달라지는 점 ≥3"]}` 필수 —
>   없으면 빌드 차단(ERROR). 단순 재빌드는 `_conceptSkipped: "<reason>"`. 형식 통과용 공허한 값 금지.
> - 🔴 **S25 디자인 방향 선언 게이트 (신규)**: imin_* 빌드는 root 에 **이번 시안의 *시각 방향*** 을
>   선언해야 통과 — `"_designDirection": {"id":"<짧은 고유 id>", "typography":"...", "color":"...",
>   "layout":"...", "spacing":"..."}` (4축 중 ≥3축 구체 전략). 예: `typography:"oversized-hero-32"`,
>   `color:"mono-brand+1pop"`, `layout:"asymmetric-cards"`, `spacing:"airy-loose"`. 없거나 불충분하면
>   빌드 차단(ERROR). bypass: `_designDirectionSkipped`. **id 는 직전 빌드와 달라야 한다**(아래 게이트).
> - 🔴 **novelty 소프트 게이트 (WARN→차단 승격, 신규)**: 빌드 성공 시 비주얼 시그니처(섹션 순서/
>   fill·radius·fontSize·**간격·layoutMode·정렬·weight** 분포)를 `scripts/.novelty/<화면>.json` 에
>   저장. 다음 빌드가 직전과 **시그니처 ≥80% 유사하거나 `_designDirection.id` 가 같으면 빌드 차단**
>   (ERROR `novelty-gate`) → 다른 방향으로 재구성 유도. 레이아웃·간격·정렬·타이포만 바꿔도 시그니처가
>   충분히 떨어진다(시그니처가 그 차원들을 측정). bypass: `_noveltySkipped` 또는 env
>   `IMIN_SKIP_NOVELTY_GATE=1`(사용자가 '그대로 다시' 원할 때). 테스트 `test_creative_divergence_gates.py`.
> - 🔴 **S26 와이어/PRD 발산 선언 게이트 (2026-06-18 신규 — 와이어 트레이싱 차단)**: 사용자 명시
>   *"PRD·특히 와이어프레임 이미지를 그대로 똑같은 UI로 구현하는 게 문제. 그 단계에서 레이아웃·정렬·
>   텍스트 위계·크기·컬러를 창의적으로 바꿔 생성하라."* → 0-C/0-N(와이어 1:1 복제 금지)을
>   **advisory→하드 게이트로 승격**. imin_* 빌드는 root 에 **와이어/PRD 대비 *시각 발산*** 을
>   선언해야 통과 — `"_wireframeDivergence": ["와이어는 …였는데 빌드는 …로 재배치", "...", "..."]`
>   (구체적 ≥3개, 각 ≥10자). 와이어의 레이아웃/정렬/타이포 위계/크기/컬러를 *어떻게 다르게* 했는지
>   적는다. 콘텐츠(텍스트/숫자)는 와이어 1:1(0-E)이되 **시각 표현은 트레이싱 금지**. 없거나 공허하면
>   빌드 차단. bypass: `_wireframeDivergenceSkipped`(와이어 없는 PRD-only / '와이어 그대로' 명시 /
>   단순 재빌드). ⚠️ 와이어를 px-perfect 로 옮기면 이 게이트에 걸린다 — 디자인적 판단을 더하라.
> - **워크플로**: 빌드 전 레퍼런스(0-G)·와이어를 보고 → `_designDirection` 을 직전과 다르게 정하고 →
>   그 방향으로 콘텐츠 영역의 레이아웃/컬러/간격/정렬/타이포를 **새로 설계**(와이어 미러링 금지, S26) →
>   `_concept`·`_designDirection`·`_wireframeDivergence` 박아 빌드. novelty·S26 게이트가 발산을 보증.
> - **3안 워크플로 (권장)**: 새 화면/리디자인은 **방향이 서로 다른 3안**을 생성해 사용자가 고른다.
>   취향은 룰로 박지 않고 *선택*으로 반영하며, 선택안의 방향이 다음 기본값이 된다.
> - **레퍼런스**: 레포 내장 uibowl(0-G 자동검색)이 표준 소스 — 모든 사용자 환경에서 동일하게 동작.
>   (사용자 개인 MCP 등 외부 레퍼런스 소스는 시스템 의존성으로 삼지 말 것 — 다른 사용자 컴에는 없다.)
>   🔵 **`references/external/<source>/` (2026-06-12 사용자 지시):** Mobbin MCP 등으로 검색해 좋았던
>   스크린은 **이미지+index.json 으로 깃에 보관**한다 — MCP 가 없는 다른 사용자도 디자인 생성 시
>   같은 레퍼런스를 받도록. `ref_search.py` 가 `references/external/*/index.json` 을 자동 로드해
>   uibowl 과 **번갈아 섞어** archetype 검색 결과에 포함시킨다(소스 표기 `mobbin:Chime` 식).
>   index.json 포맷은 uibowl 과 동일(patternCodeName 분류 공유: 메인/온보딩/생성하기 등,
>   localPath 는 references/ 상대). 새 스크린 수집 시: jpg 저장 + index.json records[] 에 추가 + 커밋.

> 🔴 **절대 규칙 0-K — DS 컴포넌트의 fill·stroke·label 색은 절대 변경 금지 (2026-06-01 사용자 명시)**
>
> 사용자 명시: *"1. badge fill, stroke color 절대 변경 금지 2. badge label text fill
> color 역시 절대 변경 금지 3. 모든 component의 fill, stroke, label color 변경하지 말 것!!"*
>
> **DS 컴포넌트 인스턴스(badge/button/tag/avatar/input 등)와 그 내부 노드(라벨 텍스트·
> 아이콘)의 색은 오직 master/variant/props 가 제어한다.** 토큰 바인딩·대비 보정·카드 표면
> 교정 등 어떤 일반 패스도 인스턴스 색을 덮으면 안 된다. 색을 바꾸고 싶으면 `set_instance_properties`
> 로 **variant/color prop 만** 선택한다.
>
> **🎨 Badge 색 변경 = `Color` prop 에서 선택 (2026-06-01 사용자 명시):**
> DS Badge 컴포넌트는 `Color` prop 에 **13개 옵션**이 있다 — fill/stroke 를 직접 바꾸지
> 말고 이 prop 에서 고른다. `set_instance_properties(nodeId, {"Color": "<옵션>"})`.
> 유효 옵션 (정확히 이 문자열):
> `Gray` · `Brand` · `Error` · `Warning` · `Success` · `Blue light` · `Blue` ·
> `Indigo` · `Purple` · `Pink` · `Orange` · `Blue gray` · `Gray blue`
> (코드 상수: `ds_catalog.BADGE_COLOR_PROP_OPTIONS`, 헬퍼: `figma_mcp_client.set_badge_color()`).
> R23 swap 시 라벨 의미(`_BADGE_COLOR_ROLE`)로 색 variant 를 고르고, 빌드 후 색을 바꿔야
> 하면 위 prop 으로만 바꾼다. **절대 fill/stroke 리터럴·토큰을 덮지 않는다.**
>
> **회귀 사례 (이번 뿌리)**: auto-bind 의 `_collect_bindings` 가 `original_blueprint`
> (R23 swap 전 복사본)를 보고 R23-swap 된 DS Badge Warning 을 raw frame 으로 오인 →
> 빌드된 INSTANCE 의 fills/0 에 bg-secondary, 내부 라벨에 text-tertiary 를 바인딩 →
> Warning variant 색이 깨짐.
>
> **시스템 강제 (코드 박힘, 자동):**
> 1. `figma_mcp_client.py call_tool` **중앙 가드**: `set_fill_color`/`set_stroke_color`/
>    `set_bound_variables(fills|strokes)` 의 대상이 **인스턴스 내부 노드(id 에 `;` =
>    `I{id};{sub}`)면 차단**한다. 의도적 enforcer(FAB 아이콘 fg-light 등)만 호출 args 에
>    `_allowComponentColor: True` 로 예외.
> 2. `_collect_bindings`: 빌드된 노드가 **INSTANCE 면 색 바인딩 안 함 + 자식 재귀도 skip**
>    (variant 가 제어하는 내부 색 보호). `original_blueprint` 가 swap 마커를 몰라도 안전.
> 3. `_strip_large_brand_fills`·`_auto_fix_invisible_text` 등 라이브 색 보정기는 이미
>    `;` 내부 노드 + INSTANCE type 을 skip.
>
> **빌드 후 검증:** badge/button 의 fill·stroke·라벨 색이 DS variant 기본값과 일치하는지
> (스크린샷). 회색으로 덮였으면 위반 — `_collect_bindings`/중앙 가드 점검.

> 🔴 **절대 규칙 0-J — 콘텐츠/뷰 전환 탭(2+ 텍스트 탭)은 underline tabs 가 기본, Segmented_control 은 명시적 토글만 (2026-06-01 / 🔴 2026-06-12 전면 개편)**
>
> 사용자 명시(2026-06-01): *"'거래현황', '누적거래' 2 tabs가 있는데 tabs component가
> 사용되지 않았다. 새 세션에서 생성했을때 또 지금과 같은 컴포넌트를 사용하지 않는 일이
> 없어야 된다."*
>
> 🔴 **사용자 명시(2026-06-12, 이 룰의 핵심 개편):** *"지금 화면에 내에서 tabs 컴포넌트로
> 쓰여야할 ui들이 segmented control로 쓰여지고 있어서. 그거 규칙 수정하고 코드도 수정해야한다.
> 예를들어 내가 지금 피그마에서 선택한 노드들이 그러해."* (입금/지급 'View Tabs' 가
> Segmented_control 인스턴스로 빌드된 것을 가리킴.)
>
> **🎯 판별 기준 (tabs vs segmented control):**
> - **underline tabs (= 기본/디폴트):** 콘텐츠·뷰를 전환하는 네비게이션 탭. 라벨이 *보여줄
>   내용/카테고리* 다 — **입금/지급**, 추천/전체, 거래현황/누적거래, 후기/문의/상세 등.
>   화면·카드의 뷰를 바꾸는 모든 멀티옵션 텍스트 컨트롤은 여기에 속한다. → **이게 표준.**
> - **Segmented_control (= 예외):** *같은 뷰 안*의 컴팩트 on/off 토글·필터(주/월/년,
>   On/Off 등). 오직 노드에 **`"_forceSegmented": true`** 마커가 있을 때만. (0-V 와 동일 철학)
>
> ⚠️ 헷갈리면 **underline tabs** 가 정답이다 — Segmented_control 은 의식적으로 컴팩트 토글을
> 원할 때만 `_forceSegmented` 로 옵트인한다.
>
> **금지:** "Mode Tabs Wrap" / "Section Tabs" / "Top Tabs" / "View Tabs" 등 이름의 HORIZONTAL
> frame 안에 raw tab cell frame 들을 직접 그리는 것(R60 이 styled underline 으로 자동 변환).
> 입금/지급 같은 뷰 전환 탭을 `_segLabels`(Segmented_control)로 작성하는 것(컴팩트 토글처럼 보임).
>
> **올바른 방법 — underline tabs styled frame** (`_underlineTabs: true` 마커, tab-hint 없는 이름은
> 굳이 필요 없음. R60 이 'view tabs' 등 이름도 인식):
>
> ```json
> {
>   "name": "View Tabs", "type": "frame", "_underlineTabs": true,
>   "layoutSizingHorizontal": "HUG",
>   "autoLayout": {"layoutMode": "HORIZONTAL", "itemSpacing": 18, "counterAxisAlignItems": "MIN"},
>   "children": [
>     {"name": "Tab 입금", "type": "frame", "layoutSizingHorizontal": "HUG",
>      "autoLayout": {"layoutMode": "VERTICAL", "itemSpacing": 7, "counterAxisAlignItems": "CENTER"},
>      "children": [
>        {"type": "text", "text": "입금", "fontSize": 16, "fontName": {"family": "Pretendard", "style": "Bold"},
>         "fontColor": "$token(text-primary)"},
>        {"name": "Tab Underline 입금", "type": "frame", "layoutSizingHorizontal": "FILL",
>         "layoutSizingVertical": "FIXED", "height": 3, "cornerRadius": 999, "fill": "$token(fg-primary)"}
>      ]},
>     {"name": "Tab 지급", "type": "frame", "layoutSizingHorizontal": "HUG",
>      "autoLayout": {"layoutMode": "VERTICAL", "itemSpacing": 7, "counterAxisAlignItems": "CENTER"},
>      "children": [
>        {"type": "text", "text": "지급", "fontSize": 16, "fontName": {"family": "Pretendard", "style": "Bold"},
>         "fontColor": "$token(text-tertiary)"},
>        {"name": "Tab Underline 지급", "type": "frame", "layoutSizingHorizontal": "FILL",
>         "layoutSizingVertical": "FIXED", "height": 3, "cornerRadius": 999, "fill": null}
>      ]}
>   ]
> }
> ```
> - active 탭: 텍스트 `text-primary` + 밑줄 bar `fg-primary` fill. inactive: 텍스트 `text-tertiary`
>   + 밑줄 bar fill `null`(투명). fontSize 는 DS 스케일(카드 내 16, 상단 페이지 탭은 20~24).
> - 큰 텍스트 페이지 탭(추천/전체)은 fontSize 22~24 로 키운다(0-V). 참조 구현:
>   `gen_stage_recommend_20260609.py` 의 `_utab`, `gen_schedule_20260609.py` 의 `_vtab`.
>
> **Segmented_control 이 정말 필요할 때만** (컴팩트 토글, `_forceSegmented: true`):
> ```json
> {"name": "Sort Toggle", "type": "instance",
>  "componentKey": "47a01673a46dc3bc9bfd62948c10e5fa9f2e5e78",
>  "_segLabels": ["주", "월", "년"], "_segActive": 0, "_forceSegmented": true}
> ```
> Segmented_control 키: Style=hug `47a01673a46dc3bc9bfd62948c10e5fa9f2e5e78` /
> Style=fill `2ee9d12d4c904650ab496b9bcdf874a648e73ceb` / set(import 불가) `143ee3e3…`.
> `_configure_segmented_control` 가 prop(Show Segment/Label#/Active)로 자동 설정. Size=md(0-P).
>
> **시스템 강제 (R60, 자동):** `scripts/design_rules/R60_tabs_ds_instance.py`
> - **L2 lint**: raw tab-nav frame / `_segLabels` 뷰 전환 탭(non-forced) 발견 시 WARN.
> - **L3 inject**: 빌드 직전 자동 변환 — raw tab-nav frame 과 `_segLabels`(Segmented_control)
>   뷰 전환 탭을 **underline tabs styled frame** 으로 변환(라벨·active 밑줄 직접 생성).
>   `_forceSegmented:true` 면 변환 안 함(Segmented_control 유지).
> - **L5 verify**: 뷰 전환 탭이 Segmented_control 인스턴스로 남으면 WARN.
>
> **빌드 후 검증:** 빌드 로그에 `[inject R60] Segmented_control 뷰 전환 탭 → underline tabs: N건`
> 또는 `[inject R60] raw tab-nav frame → underline tabs: N건` 라인 확인. 스크린샷에서 탭이
> **밑줄(underline) 스타일**(active 탭 아래 bar)인지 — 알약(pill) Segmented_control 이 아니어야 한다.
> 테스트: `scripts/tests/test_tabs_underline_default.py`.

### S27. 🔴 재구성 맵 하드 게이트 — 선언을 실물과 대조 (2026-07-15 사용자 룰)

> 사용자: *"자꾸 새 세션을 시작하고 디자인 생성하면 와이어프레임이랑 똑같이 생성하던데,
> 다신 그러지 않게 방법을 찾아봐."* — 선언형 게이트(S24~S26)는 새 세션이 형식적으로 채우면
> 뚫린다는 것이 반복 실측됨. S27 은 선언을 **blueprint 실물과 대조**하는 게이트다.
>
> **필수 선언 (root):**
> ```json
> "_restructureMap": {
>   "wireSections": ["헤드라인", "모집현황", "조건 테이블", "순번", "범례"],
>   "surfaces": [
>     {"name": "Overview Card", "absorbs": ["헤드라인", "모집현황"]},
>     {"name": "Cond Card",     "absorbs": ["조건 테이블"]},
>     {"name": "Seat Card",     "absorbs": ["순번", "범례"]}
>   ]
> }
> ```
> **코드 검증 3종:**
> 1. **커버리지** — 모든 wireSection 이 어떤 surface 에든 흡수 (콘텐츠 1:1 누락 방지)
> 2. **통합** — ≥1 surface 가 섹션 2개 이상 흡수. 섹션별 카드 1:1 래핑("포장된 트레이싱") 차단
> 3. **실재** — 선언된 surface name 이 blueprint 트리에 존재 + 표면 속성(fill/stroke/instance)
>
> bypass: `_restructureMapSkipped: "<reason>"` (설정 메뉴 등 정당한 평면 화면 / 사용자가
> '와이어 그대로' 명시 / 단순 재빌드). prebuild 도 사전 검사. 회귀 테스트:
> `scripts/tests/test_wire_tracing_gates.py` (S26-structural·R65·S27 3중 게이트 고정).

### 0-W-2. 🔴 _customNavBar 는 사유 문자열 필수 — 아이콘 미지원은 우회 사유가 아님 (2026-07-14)

> 사용자: *"너 왜 navigation bar 를 컴포넌트 인스턴스 안 쓰고 직접 만들어? 규칙이랑 코드에
> 박아뒀을텐데."* — joined/preparing 상세 4개 빌드에서 edit 아이콘이 NAV_ICON_KEYS 에 없다는
> 이유로 `_customNavBar: true` 우회가 반복·복붙 전파된 회귀.
>
> **원인:** ① `_customNavBar` 가 유일하게 **사유 없이 boolean 으로 뚫리는 탈출구**였음
> (다른 bypass 는 전부 사유 문자열 필수) ② 키맵에 없는 아이콘의 대응 절차(확보→등록)가
> 문서화돼 있지 않아 '없으면 우회'로 흘렀음.
>
> **룰 (R64-custom-navbar-reason, LINT ERROR):**
> 1. `_customNavBar` 는 사유 문자열 필수 — boolean `true` 는 빌드 차단.
> 2. 사유에 '아이콘 없음' 류가 들어가면 그것도 차단 — 정답은 우회가 아니라
>    `search_design_system` 으로 published key 확보 → `ds_catalog.NAV_ICON_KEYS` 등록.
>    (2026-07-14 에 edit-01/pencil = `cf4b7befec…` 등록 완료.)
> 3. 정당한 사유 예: 검색바 내장 헤더, 타이틀 좌측 커스텀 위젯 등 Tool Bar variant 로
>    구조적으로 표현 불가한 경우만.

### 0-J-2. 🔴 생애주기 상태 나열 = 탭이 아니라 진행 step (2026-07-14 사용자 룰)

> 사용자: *"상단 준비중, 참여중, 진행중, 스테이지완료는 탭메뉴가 아니라 진행 step 을 표시한거야.
> 그걸 이해를 못하겠어?"* — 스테이지 상세 와이어의 상태 나열을 underline tabs 로 오독한 회귀.
>
> **판별:** 라벨들이 기획서의 **생애주기 단계**(모집중→마감(준비중)→진행중→종료)에 대응하고
> 화면이 그 중 *한 단계의 상태*를 보여주는 상세라면 — 그것은 뷰 전환 탭이 아니라 **진행 step
> 표시**다. 탭(0-J)은 사용자가 눌러 뷰를 바꾸는 것, step 은 시스템 상태의 위치 표시.
> **표현:** step indicator — 현재 단계 강조(잉크 Bold + 도트/체크), 지난 단계 완료 표시,
> 남은 단계 저채도, 단계 간 연결(선/도트). underline bar 금지.
> **판별 근거는 기획 digest** — 통독한 생애주기와 화면 라벨을 대조하는 것이 이 룰의 실행법.


> 🔴 **절대 규칙 0-M — 하단 Tab Bar = DS 'Tab bar' 인스턴스 (2026-06-02 사용자 룰)**
>
> 하단 바텀 네비게이션은 raw frame(아이콘+라벨 직접 그리기) 금지. DS **'Tab bar'**
> 컴포넌트 인스턴스를 쓴다. `Selected` variant 로 active 탭을 정한다 — **탭 구성 고정:
> 홈 / 커뮤니티 / 스테이지 / 라운지 / 나** (라벨·아이콘·색 모두 컴포넌트 내장, override 불필요).
>
> **active 탭에 해당하는 variant key 로 인스턴스 생성** (variant flip 불필요):
> | active | component key |
> |--------|---------------|
> | 홈 | `0faaa55563de4da617964ea93ba07f09bc1279f6` |
> | 커뮤니티 | `b7d390e90bae2d41059671f4474102a2bd92b7c1` |
> | 스테이지 | `a56726e0de4bc0e71875159662b320e9b2ac695c` |
> | 라운지 | `7dcb6d5d2b97d36e0b5d601441f22f87e2d26f5c` |
> | 나 | `740120b5e954cae262d21fefffa946afc26f2d63` |
> (set key `f7de125d1aa57be1b3c5ec0757c3b3803d435c7e`. catalog `COMPONENT_KEYS["Tab Bar …"]`.)
>
> **시스템 박힘:** `unified_blueprint._gen_tab_bar` 가 active 탭 variant key 로 instance emit.
> custom blueprint 는 `{"name":"Tab Bar","type":"instance","componentKey":"<active key>"}` 직접 작성.
> ⚠️ DS 라이브러리에 **publish(게시)된 상태**여야 import 됨 — 미게시면 `⚠ Tab Bar` 에러 프레임.

> 🔴 **절대 규칙 0-L — R23 auto-swap 은 '이름 힌트' 있을 때만 / 콘텐츠 frame 은 DS 이름 금지 (2026-06-02 사용자 분노)**
>
> 사용자 명시: *"새 세션에서 디자인 생성하라고 하면 또 이렇게 이상하게 생성할거 아냐?"* —
> hand-authored blueprint 의 콘텐츠/장식 frame(금액 강조 pill·회차 1~13 셀·필터 칩·
> 드롭다운 헤더)이 DS 컴포넌트 **모양**과 우연히 겹쳐 R23 이 인스턴스로 오스왑 → 콘텐츠
> 파괴(드롭다운이 "Account" 더미 / 금액이 보라 버튼 / 회차 바 붕괴)되던 회귀.
>
> **시스템 강제 (코드 박힘, 2026-06-02):** `ds_catalog.detect_ds_role_structural` 의 confident
> auto-swap 은 이제 **이름 힌트가 있을 때만** True:
> - button → 이름에 `button/btn/cta/submit/버튼`
> - badge/tag → 이름에 `badge/태그/tag/chip` **또는 라벨이 status 어**(진행중/완료/미납 등)
> - dropdown/input/toggle/checkbox/radio/slider/progress/avatar → 이름에 해당 단어
> - **bare 숫자/단일 문자**("1"~"13"·"A") → step·회차 마커로 보고 badge 검출 자체 제외
> 이름 힌트 없는 순수 모양 일치는 **WARN-only(swap 안 함)**. 진짜 status badge·이름 명시
> 컴포넌트는 여전히 swap.
>
> **blueprint 작성 규칙 (새 세션 필수):** 콘텐츠/장식 frame 에 DS 컴포넌트 단어
> (`Pill`·`Chip`·`Badge`·`Dropdown`·`Button`·`Tag`)를 **이름으로 쓰지 말 것** — 중립 이름
> (`Amount Box`·`Filter Opt`·`Filter Header` 등) 사용. 진짜 DS 컴포넌트가 필요하면
> `type:instance` + componentKey 로 **직접** 작성한다(모양 의존 금지).

> ⛔ **절대 규칙 0-I — 폐기 (2026-06-18 사용자 결정: 섹션 타이틀 좌측정렬 강제 삭제)**
>
> 구 규칙(2026-06-01): 섹션 타이틀 텍스트를 **항상 좌측 정렬**로 강제(R59 lint/inject/post-fix/verify).
> → 2026-06-18 **삭제.** 사용자 결정: 와이어를 창의적으로 변형하려면 *정렬*도 작성자가 자유롭게
> 정해야 한다(센터드 히어로 타이틀·우측 정렬 등 허용). 정렬 획일화가 창의 변형과 충돌.
>
> **삭제 내역:** `scripts/design_rules/R59_section_title_left_align.py` 파일 삭제(auto-discovery
> 대상에서 제거). 더 이상 타이틀 정렬을 강제하지 않는다 — 정렬은 디자인 방향(S25)·발산(S26)에 따라
> 작성자가 선택. ⚠️ 과거 "왜 이것만 중앙?" 불만이 재발할 수 있으나, 그건 *의도적 정렬 선택*으로
> 다루며 룰로 막지 않는다(사용자 결정).

> 🔴 **절대 규칙 0-H — 새 root frame 은 기존 화면 우측 빈 공간에 자동 배치 (2026-06-01 사용자 룰)**
>
> `batch_build_screen` 은 새로 만든 root frame 을 항상 **(0,0) 에 박는다.** 같은 페이지에
> 이미 화면이 있으면 **정확히 겹쳐서** 사용자가 결과를 구분할 수 없다. 절대 금지.
>
> 🔴 **0-H-2 — 선택 노드 우선 배치 (2026-08-20 사용자 룰):** 사용자가 Figma 에서 노드를
> 선택한 채 빌드하면("선택 노드 분석해서 오른쪽에 생성" 표준 명령) 새 root 는 페이지
> maxRight 가 아니라 **선택 노드와 같은 부모에 insert_child 후 부모 상대좌표로 선택 노드
> 바로 오른쪽(gap 50, 같은 y)** 에 배치한다. 이유 2가지: ① 페이지가 거대(섹션 폭 1.5만px+)하면
> maxRight 배치는 화면 밖 저 멀리 떨어져 사용자가 결과를 못 찾는다. ② 선택 노드가 섹션
> 자식이면 그 (x,y)는 섹션 상대좌표라, 페이지 직속 root 에 같은 숫자를 넣어도 다른 위치다 —
> **같은 부모로 넣으면 좌표계 문제가 소멸.** `_position_new_root_to_right` 가 get_selection
> 으로 자동 판별(단일 선택 + 폭≥200 화면형 노드일 때만), 아니면 기존 maxRight 폴백.
> 성공 로그: `[auto-position] ✓ 새 root → 선택 노드(<이름>) 우측 동일 부모(...)`.
>
> **시스템 강제 (자동):**
> - `figma_mcp_client.py cmd_build` Step D.5 → `_position_new_root_to_right(root_id, gap=200)`
>   - batch_build_screen 직후, post-fix 전에 호출
>   - `get_document_info` 로 currentPage children + bounds 수집 → 다른 children(자기 자신 제외)
>     의 `maxRight = max(x + width)` 계산 → 새 root 를 `(maxRight + 200, 0)` 으로
>     `move_node` 자동 호출
>   - 페이지가 비었거나 bounds 정보가 부족하면 silent — (0,0) 유지 (첫 화면이라 OK)
> - `src/figma-plugin/code.js getDocumentInfo()` 는 children 매핑에 `x/y/width/height`
>   포함해 리턴 — 이 룰의 전제 조건. 제거하면 자동 배치가 silent fail 함.
>
> **빌드 후 검증:** 빌드 로그에 `[auto-position] ✓ 새 root → x=<N>, y=0` 라인이 보이면
> 자동 배치 성공. 없으면 페이지에 다른 화면이 없는 첫 빌드라 (0,0) 유지된 것 (OK).
>
> **수동 호출 (예: batch_build_screen 직접 호출 시):** 그 후 즉시
> `move_node({"nodeId": <root>, "x": maxRight + 200, "y": 0})` 호출 — Claude 가 수동
> 빌드 후에도 이 룰을 반드시 적용해야 한다.

> 🔴 **절대 규칙 0-G — references/uibowl REFERENCE READ 강제 (2026-05-28 사용자: "레퍼런스 이미지 검색은 하냐?")**
>
> `cmd_build` 빌드 로그에 **"📌 SECTION-REFERENCE-PNG"** 라인이 보이면, **빌드 진행
> 전에 반드시** 위에 출력된 PNG path 들 (`scripts/ref_thumbnails/*.png`) 을 모두
> **Read 도구로 열어 시각 학습**. 단순 path 만 보고 references[] 박지 말고
> **실제 이미지의 시각 위계/리듬/컬러 매핑/카드 패턴/CTA 위치를 참고**.
>
> **강제 절차:**
> 1. Step A.0 출력의 thumbPath 들 (보통 6장) `Read` 호출
> 2. 학습 결과를 references[] 의 `extract` / `copyNotes` 필드에 **실제 본 내용**으로 반영
>    (form 통과용 "card surface" 같은 공허한 값 금지)
> 3. 학습 결과로 archetype 별 polish 강화 — 시각 위계 / 컬러 절제 / 카드 패턴 직접 적용
> 4. **위반 신호**: PNG Read 0건 / extract 가 generic / references[] 가 path 만
>
> 🔴 **빠뜨리는 근본 원인 + 방지 (2026-06-08 사용자: "왜 자꾸 레퍼런스 검색을 빼먹지? 새 세션
> 최초 생성 때도 안 봤다"):**
> - **원인 ①(행동):** 빌드 명령 출력을 `tail -N` / `grep -E "..."` 로 필터해 보는 습관 때문에,
>   **빌드 *앞부분*(Step A.0)에 뜨는 `📌 SECTION-REFERENCE-PNG` 프롬프트를 통째로 못 봤다** →
>   Read 트리거를 놓침. **빌드 로그를 tail/grep 으로 필터하지 말 것**(최소한 `SECTION-REFERENCE-PNG`
>   포함). 이제 cmd_build **끝에서도** 레퍼런스 경로를 재출력하므로(`📌 SECTION-REFERENCE-PNG (재안내)`),
>   tail 로 봐도 잡힌다 — 보이면 반드시 Read.
> - **원인 ②(코드 버그·수정됨):** archetype 인식이 `'imin_home'` **정확 부분문자열**만 봐서
>   `imin_signup_home`·`imin_active_home`·`imin_*_home_creative` 가 미인식→일반 폴백 됐다(진짜 홈
>   레퍼런스 못 받음). → bare word(`home`/`stage`/…)가 이름에 있으면 해당 archetype 으로 인식하도록
>   수정. 테스트 `test_reference_archetype.py`.
> - **원인 ③(날조):** 생성기 REFS[] 에 실제로 안 본 uibowl 경로를 그럴듯하게 적어 "본 척" 하지 말 것
>   (0-G 위반). 반드시 Read 후 본 내용을 적는다.
>
> **시스템 박힘:** `figma_mcp_client.py _auto_search_uibowl_references()` (Step A.0)
> — `scripts/ref_search.py --archetype <imin_xxx> --thumbnail --limit 6` 자동 호출
> → `scripts/ref_thumbnails/` 에 LLM Read 가능 thumbnail (≤1200px) 자동 생성 →
> stdout 에 SECTION-REFERENCE-PNG 라인 출력(빌드 앞부분 + **끝부분 재안내**, 사용자 화면에도 보임).
> Claude self-verify 의 마지막 방어선.

> 🔴 **절대 규칙 0-G-2 — 같은 화면의 기존(특히 사용자 수정) 버전을 빌드 전에 반드시 학습 (2026-06-12 사용자 룰)**
>
> 회귀 사례: 어제 생성본을 사용자가 직접 수정해 둔 화면(`imin_stage_done_20260610`)이 같은
> 페이지 바로 옆에 있는데, 오늘 같은 화면을 다시 빌드하면서 그것을 보지 않고 와이어+일반
> 레퍼런스만으로 새로 도출 → 사용자가 교정한 컬러 시맨틱(완료=success)·타이포 스케일·레이아웃
> 재해석이 전부 누락됐다.
>
> **강제 절차 (빌드 전):**
> 1. `get_document_info` / `get_pages` 로 현재 페이지 children 이름을 훑어 **같은 화면**
>    (같은 archetype/유스케이스 — 이름에 같은 화면 키워드: home/stage_done/detail 등)의
>    기존 프레임을 찾는다.
> 2. 있으면 **export_node_as_image 로 Read 해 시각 학습** — 특히 **사용자가 수정한 버전이
>    최우선 레퍼런스**다 (uibowl 외부 레퍼런스(0-G)보다 강함: 사용자의 직접 교정 = 확정 피드백).
> 3. 거기서 본 **컬러 시맨틱·타이포 스케일·레이아웃 판단을 새 blueprint 에 반영**한다.
>    단순 복제가 아니라(0-C) 사용자가 *고친 의도*를 읽어 적용한다.
> 4. 코드 자동검출 불가(의미 판단) — 매 빌드 시 Claude 가 스스로 지킨다.
>
> 🔴 **컬러 시맨틱 (2026-06-12 사용자 확정 — 스테이지 완료 화면 수정에서):**
> - **완료된 행위/상태 (납입 완료 체크, 완료 확인 아이콘) = `success` 계열** —
>   `bg-success-solid`(#319f26) 솔리드 + 흰 체크, 타이틀 옆 `ic-check-circle`(success).
> - **brand 퍼플 = '나의 것'에 한정** (내 수령 셀·내 금액·CTA — [[stage-detail-color-semantics-2026-06-09]] 와 동일).
> - 완료 상태까지 퍼플로 칠하는 brand 남발 금지 — 의미가 다른 상태는 색으로 구분한다.

> 🔴 **절대 규칙 0-F — SELF-VERIFY 강제 (2026-05-28 옵션 B / 사용자 신뢰 파탄 후 박힘)**
>
> `cmd_build` 빌드 로그에 **"📸 SECTION-QA-PNG"** 라인이 보이면, **사용자에게 어떤
> 보고도 하기 전에 반드시 아래 절차 수행**. 1장 screenshot 만 보고 "검증 ✅" 보고
> 절대 금지 — 이전 5회 거짓 보고로 신뢰 파탄됨.
>
> **강제 절차:**
> 1. stdout 의 `📋 Checklist: scripts/qa_screenshots/<root>/self_verify_checklist.json` 경로 확인
> 2. `exported_sections[]` 의 모든 nodeId 를 `mcp__figma-tools__export_node_as_image` (scale=2) 로 재 export + **Read 강제**
> 3. checklist 12개 항목 (C01~C12) 각각 **PASS / FAIL / NA** + **evidence 1줄 인용** 채움
> 4. FAIL ≥1 건 → 즉시 라이브 fix 시도 → 재 export → 재 Read → checklist 갱신. 미 fix 시 사용자에게 **솔직 보고** (PASS X / FAIL Y / NA Z 명시)
> 5. **위반 신호**: 전체 1장만 보고 OK 보고 / PNG export 만 하고 Read skip / checklist 비워둠 / FAIL 있는데 "완료" 보고
>
> **시스템 박힘:** `figma_mcp_client.py _self_verify_section_qa_export()` (Step H)
> — 6장 PNG auto-export + checklist JSON 자동 생성 + stdout 강력 경고.
> 코드는 Claude 행동 강제 못하지만 stdout 경고가 사용자 화면에도 표시되므로
> Claude 의 self-verify skip 이 사용자에게 즉시 드러남.

> 🔴 **절대 규칙 0-F-2 — QA 스크린샷 + 레퍼런스 썸네일은 작업 완료 후 즉시 삭제 (2026-06-08 사용자 룰)**
>
> 사용자 명시: *"qa 용으로 스크린샷 찍어서 모든 작업 완료 후 qa screenshot json 파일 삭제할 것!"*
> + *"ref_thumbnails 도 작업 완료 후 자동 삭제되게 해줘."*
>
> 작업 중 Claude 가 소비하려고 만든 **임시 산출물 2종**은 검증·학습이 끝나면 불필요하므로
> **그 작업의 모든 단계가 끝난 직후 즉시 삭제**한다(7일 대기하는 `cleanup_old_blueprints.py`
> 와 별개로 그 자리에서 비움 — 폴더에 옛 산출물이 쌓이지 않게):
> - `scripts/qa_screenshots/<root>/` — self-verify(절대 규칙 0-F)용 PNG + `self_verify_checklist.json`
> - `scripts/ref_thumbnails/` — 레퍼런스 학습(절대 규칙 0-G)용 ≤1200px 썸네일
>
> **강제 절차 (Claude):** 화면 작업·검증·보고를 모두 마친 **마지막 단계**에서 1회 실행:
> ```bash
> python3 scripts/figma_mcp_client.py cleanup-qa
> ```
> → `scripts/qa_screenshots/` + `scripts/ref_thumbnails/` 안의 모든 항목 삭제 +
> `🧹 [cleanup-qa] … N개 항목 삭제` 로그.
>
> **순서 주의 (절대 규칙 0-F / 0-G 와 충돌 금지):** self-verify(0-F)는 **스크린샷을 읽고 끝낸 뒤**,
> 레퍼런스 학습(0-G)은 **썸네일을 Read 해 references[] 에 반영한 뒤**에 삭제한다. 검증/학습 전에
> 지우면 self-verify·레퍼런스 Read 를 못 한다. 즉 *빌드 → 썸네일 Read(0-G) → self-verify(0-F) →
> 보고 → `cleanup-qa`* 순서. 여러 화면이면 **모든 화면의 검증·학습이 끝난 뒤** 한 번만.
>
> **시스템 박힘:** `figma_mcp_client.py cmd_cleanup_qa()` (CLI `cleanup-qa`) — `qa_screenshots/`
> 와 `ref_thumbnails/` 하위 전체(디렉토리·파일) 삭제, 폴더 자체는 유지(다음 빌드가 재생성).
> 빌드 직후 자동 삭제는 self-verify·레퍼런스 Read 를 깨므로 **하지 않는다** — 작업 종료 시
> Claude 가 호출하는 방식.

> 🔴 **절대 규칙 0-E — 와이어프레임 콘텐츠 1:1 추출 의무 / archetype config 재사용 금지 (2026-05-27 사용자 분노)**
>
> 새 세션에서 와이어프레임을 받아 디자인을 빌드할 때, **와이어의 실제 텍스트/숫자/카운트
> 를 그대로 빌드에 박는다.** v12 같은 이전 archetype 빌드의 config(`config_*.json`)를
> 복사해 새 v13으로 재사용하지 말 것 — **콘텐츠가 v12 더미 데이터 그대로 박혀서 와이어 의도
> 무시 + 사용자 격분**.
>
> **사례 (이번 회귀)**:
> - 와이어: "진행중인 **0건**의 스테이지 내역 / 모은 금액 **+0원** / 빌린 금액 **-0원**"
> - 빌드(v13=v12 reuse): "3건 / +14,420,320원 / -5,240,020원" (v12 더미 그대로)
> - 와이어: Day Strip "**14~19일 6 cell × +0원**" / 빌드: "미납 28일/오늘 4일/지급 12일/예정 18일" (다른 컨셉)
> - 와이어 1.5: "**10만원 stepper + 13개월 stepper + 1~13 회차 round selector + 1회차 + 납입 후 목적 수령 + 총 1300만원 모으기 도전**"
> - 빌드: "예상 수령 금액/총 1,300만원/회차 stepper 3개" (1~13 round selector 누락)
>
> **워크플로우 — 무조건 이 순서**:
> 1. **와이어 export** (`mcp__figma-tools__export_node_as_image`) → 사람이 읽을 수 있는 이미지
> 2. **콘텐츠 추출 dict 작성** — 섹션별로 모든 텍스트/숫자/카운트/아이콘 종류를 추출:
>    ```json
>    {
>      "1.3 진행 현황 카드": {
>        "header": "진행중인 0건의 스테이지 내역",
>        "more": "자세히 >",
>        "rows": [{"label": "모은 금액", "value": "+0원"}, {"label": "빌린 금액", "value": "-0원"}],
>        "dayStrip": ["14일", "15일", "16일", "17일(today)", "18일", "19일"],
>        "dayValues": ["0원", "0원", "0원", "0원", "0원", "0원"],
>        "calcCTA": "얼마까지 모을 수 있는 지 확인해보세요"
>      },
>      ...
>    }
>    ```
> 3. **blueprint root._wireframeContent 필드에 dict 박기** — `cmd_build` Step E.6.5 의
>    `_qa_wireframe_content_match` 가 blueprint TEXT characters 와 dict 매치 검증. 미스매치 ≥30% 시 build 차단
> 4. **config 는 처음부터 작성** — `cp config_*.json` 금지. 와이어 dict 기반으로 새 config 작성
> 5. 그 다음 assemble → build → post-fix → token bind → QA 2 pass
>
> **자동 강제 (코드 박힘)**:
> 1. `figma_mcp_client.py cmd_build` Step E.0 `_check_no_archetype_reuse` (S22) —
>    config 의 textual 패턴이 이전 빌드 산출물과 70%+ 일치 시 build 차단(ERROR)
> 2. `cmd_build` Step E.0 `_check_wireframe_content_required` (S23) —
>    imin_* archetype 빌드인데 root._wireframeContent dict 도 _wireframeContentSkipped 도
>    없으면 build 차단(ERROR). bypass: `"_wireframeContentSkipped": "<reason>"`
> 3. `cmd_build` Step E.6.5 `_qa_wireframe_content_match` —
>    blueprint TEXT characters 가 root._wireframeContent dict 와 매치 검증. 30%+ 미스매치 시 WARN, 50%+ 시 ERROR
>
> **Why**: 새 세션 컨텍스트 부족 → "imin_home은 v12 있으니 base 가져가자" 본능 → 더미 데이터 박힘 → 사용자가 "와이어 무시"라고 분노. 시스템이 와이어 콘텐츠 추출을 강제하지 않으면 매번 새 세션마다 회귀.
>
> **참고**: 메모리 [feedback_no_wireframe_clone] 은 **시각 위계** 만 재해석하라는 뜻 — 카드 그림자/타이포/그룹화 같은 디자인 판단. **콘텐츠(텍스트/숫자/카운트)는 와이어 1:1**.

> 🔴 **절대 규칙 0-E-3 — 와이어/PRD 에 없는 콘텐츠를 만들어 넣지 말 것 (fabrication 금지, 2026-06-18 사용자)**
>
> 사용자 명시: *"상단 큰 가로 배너는 구지 안에 내용 넣지마. 애초에 와이어프레임에도 없는 내용은
> 만들어서 넣을려고 하지마."* (CMS 배너 영역에 "아임인 전용 특가 / 항공권 & 호텔 오픈!" + 비행기
> 이미지를 임의 생성해 넣은 것 + 2번째 배너 크기 안 맞아 이상해진 것을 가리킴.)
>
> 0-E(콘텐츠 1:1)는 누락 금지인 동시에 **날조 금지**다. 와이어/PRD 에 **없는** 마케팅 카피·제목·
> 이미지·리스트 항목·캐로셀 슬라이드를 **임의로 만들어 넣지 않는다.**
> - **CMS/동적/외부주입 영역**(예 "CMS 에서 등록한 배너 영역", 광고 배너, 추천 피드 등 콘텐츠가
>   런타임에 채워지는 곳)은 **placeholder 로 둔다** — **흰 면(`bg-primary`) + 보더(`border-secondary`)**
>   + (있으면) 와이어 자체의 영역 라벨만. 가짜 마케팅 콘텐츠/이미지를 생성하지 말 것. 노드에
>   `_placeholderAllowed` 마커를 달면 콘텐츠 매치 QA 가 빈/placeholder 를 허용하고,
>   **R52(라운지/상품 카드 imageQuery 필수)도 bypass** 된다 (2026-07-09 충돌 해소 — 와이어에
>   콘텐츠 없는 동적 카드에 imageQuery 를 요구하면 날조 금지와 모순. `test_r52_placeholder_bypass.py`).
>   ⚠️ **placeholder 를 `bg-secondary`(회색)로 만들지 말 것** — 바로 위/아래에 회색 밴드(규칙 13
>   강조 섹션)가 있으면 *같은 회색 + 0 gap* 으로 맞붙어 폭 불일치 계단처럼 어색해진다(2026-06-18
>   회귀). 흰 면+보더로 인접 회색 밴드와 구분하고, 섹션 간 gap(흰 여백)을 확보한다.
> - **개수가 와이어에 명시 안 된 반복 영역**(배너 N개 등)은 임의로 캐로셀·다중 카드·peek·인디케이터
>   dots 를 만들지 말 것. 와이어가 1개면 1개(스와이프 없음), 동적이면 단일 placeholder.
>   서로 크기 안 맞는 카드를 만들어 "이상해 보이게" 하지 말 것.
> - 디자인적 **시각 표현**(레이아웃·색·위계)은 자유롭게 재구성(S26)하되, **콘텐츠 자체를 늘리지
>   않는다.** "더 풍부해 보이게" 하려고 없는 정보를 채우는 건 0-E 위반.
> - 코드 자동검출 일부: `_qa_wireframe_content_match` 가 blueprint TEXT 를 `_wireframeContent` 와
>   대조. 하지만 *날조 방향*(빌드에 있는데 와이어엔 없음)은 사람(Claude)이 self-verify(0-F)에서
>   "이 텍스트/이미지가 와이어/PRD 에 실제로 있나?" 로 매 빌드 확인한다.

> 🔴 **절대 규칙 0-E-2 — 결정형 생성기는 fallback 일 뿐 / 비주얼은 매 세션 새로 도출 (2026-06-08 사용자 결정)**
>
> 사용자 지적: *"홈화면은 새 세션마다 디자인 생성해도 똑같이 나오는데, 내가 자율성을 완전
> 배제한건가?? 이렇게 되면 매번 레퍼런스 이미지를 읽어서 참조하는게 의미가 사라지잖어."*
> → 사용자 결정: **"콘텐츠+하드룰만 고정, 비주얼은 자유."**
>
> **문제:** `gen_signup_home_v4.py` 등 결정형 생성기가 blueprint 를 통째로 하드코딩 → 새
> 세션에서 몇 번 돌려도 **동일 출력**. 그 결과 레퍼런스 Read(0-G)·창의적 재해석(0-C/0-N)이
> **형식적 절차**가 됨(출력이 이미 정해져 변주 여지 0 = 자율성 0).
>
> **진짜 불변(고정)인 것 = 2가지뿐:**
> 1. **콘텐츠** — 와이어 텍스트/숫자/카운트 1:1 (0-E). `_wireframeContent` dict 캡처 + 하드
>    게이트(S22/S23)가 보장.
> 2. **하드 품질 룰** — root bg-primary(0), DS 컴포넌트 색 보존(0-K), 중요 섹션 밴드(13),
>    FILL 사이징(8), Aqua 자제(2-J), 스테퍼 2-row(14-B) 등 **시스템 강제 룰**.
>
> **자유(매 세션 새로 도출)인 것 =** 시각 위계 · 카드 그룹핑 · 어느 섹션을 강조할지 · 액센트
> 리듬 · 미세 레이아웃. **레퍼런스(0-G)를 보고 매번 다르게 판단** → polished 디자인 + 레퍼런스
> 읽는 의미 회복.
>
> **How to apply (새 세션 홈/반복 화면 생성 시):**
> - 결정형 생성기(`gen_*_home_v*.py`)를 **최종 출력으로 그대로 찍지 말 것**. 이제 이들은
>   **fallback/참조 구현**(콘텐츠 스펙 + 하드룰 적용법의 예시)일 뿐.
> - 절차: 와이어 콘텐츠 추출(`_wireframeContent`) → 레퍼런스 Read → **그 레퍼런스 기반으로
>   blueprint 를 새로 작성**(레이아웃/비주얼은 이번 세션 판단). 하드 게이트가 품질 방어.
> - 생성기에서 가져와도 되는 건 **콘텐츠 dict·하드룰 헬퍼(band()/stepper() 등)뿐**. 섹션
>   배치·시각 언어는 복붙하지 말 것.
> - 코드 자동검출 불가(의미적 판단) — 매 세션 Claude 가 스스로 지킨다. 상세: 메모리
>   [[generator-is-fallback-visual-free]].

> 🔴 **절대 규칙 0 — 루트 프레임(화면 최상위 프레임) 배경색은 반드시 `bg-primary`**
>
> 루트 프레임의 `fill`은 **무조건 `$token(bg-primary)`**(`#fcfcfd`, 거의 흰색)여야 한다.
> `bg-secondary`(`#f3f4f6`, 회색) 등 다른 값을 쓰면 **버그**다. 화면 배경이 회색으로
> 보이면 무조건 이 규칙 위반이다.
>
> - blueprint 작성 시 root `fill`을 처음부터 `$token(bg-primary)`로 쓸 것.
> - 이 규칙은 빌드 파이프라인 **3곳에서 자동 강제**된다 — 그래도 blueprint에서 직접 지킬 것:
>   1. `figma_mcp_client.py cmd_build` → `_enforce_root_bg_primary()`: 빌드 전 blueprint root fill을 `$token(bg-primary)`로 강제 교정
>   2. `figma_mcp_client.py post-fix` → `_enforce_root_bg_primary_live()`: 빌드된 루트 노드 배경을 bg-primary로 런타임 강제(리터럴 + DS 변수 바인딩)
>   3. `figma-mcp-embedded.ts enhanceBlueprint`: 모든 `batch_build_screen` 호출에서 root fill을 bg-primary로 교정
> - **빌드 후 검증**: 스크린샷에서 콘텐츠 카드 바깥 배경이 회색이 아닌 흰색(`bg-primary`)인지 확인.

> 🔴 **절대 규칙 0-D — Modal 기본형 = Bottom Sheet (2026-05-27)**
>
> Modal 의 **기본형은 bottom sheet** — 화면 세로의 절반 정도로 표시되고, 뒤에 원래
> 화면 위 **dimmed overlay** 가 깔린 채 **bottom 에 붙어서** 슬라이드업.
>
> Blueprint 작성 시 `_screenType: "bottom-sheet"` 명시. 빌드 후 자동:
> 1. **Root 852 FIXED** (디바이스 viewport) — 🔴 HUG 아님(2026-06-04 사용자: "root frame
>    높이는 852여야함"). 시트를 하단에 고정하려면 root 가 고정 높이여야 함.
> 2. 1st 자식 = **Dim Overlay** (FILL×FILL, alpha-black 50%) — 위쪽 가용 공간을 **세로로
>    채워** 시트를 화면 하단으로 민다(bottom 밀착).
> 3. 2nd 자식 = **Modal Sheet** (가로 FILL = **root 와 동일 풀폭**, 세로 HUG, bg-primary,
>    🔴 **top-left/top-right radius = 16**(2026-06-04 사용자 절대규칙), bottom radius 0) —
>    콘텐츠 wrap. 🔴 **시트 가로 = root 풀폭**(2026-06-04 사용자: "가로는
>    root frame과 동일"). **콘텐츠 가로 padding 20 은 Modal Sheet 가 가짐**(root 가로 padding=0
>    이라야 dim·시트가 풀폭). 사용자: "가로에 padding값을 20이 있어야하고".
> 4. 🔴 **Modal Sheet 세로 padding = 상단 8(spacing-md) / 하단 24(safe area) (2026-06-10 사용자 룰)** —
>    상단은 드래그 핸들이 타이트하게 붙도록 **8**(기존 12에서 축소), 하단은 safe-area 24. 의도적
>    비대칭이라 시트 dict 에 `_asymPad:True` 마커를 박아 `_enforce_symmetric_vpad`(pt==pb 강제)를
>    우회한다. `_enforce_bottom_sheet_pattern` 이 자동 적용(테스트 `test_modal_sheet_top_padding_8_asym`).
>
> 강제 함수: `_enforce_bottom_sheet_pattern` (cmd_build pre-process — root 852 FIXED +
> 가로 padding 0, Modal Sheet 가로 padding 20) + 라이브 후처리 `_fix_layout_and_positions`
> 의 bottom-sheet 분기(`_is_bottom_sheet_screen_type` → root 852 FIXED 재단언 + Dim FILL).
> 🔴 bottom-sheet 는 `_HUG_SCREEN_TYPES`(=modal 만)에서 **제외** — modal 처럼 root HUG 로
> 강제하면 dim 이 붕괴해 시트가 하단 밀착 안 됨. 회귀 테스트: `scripts/tests/test_bottom_sheet_pattern.py`.
>
> **Modal 두 가지 구분:**
> - `_screenType: "bottom-sheet"` (기본형) — root 852 FIXED + dim(FILL) + 시트 하단 밀착·풀폭·콘텐츠 padding 20
> - `_screenType: "modal"` (full modal) — 전체 화면 modal, root **HUG**, X 닫기만 (Footer/Tab 제거)
>
> ⚠️ 새 modal 빌드는 기본 `bottom-sheet` 사용. full modal 필요시에만 `modal` 명시.

> 🔴 **절대 규칙 0-C — 와이어프레임 1:1 복제 금지, 창의적 재해석 의무 (2026-05-27)**
>
> 와이어프레임의 **레이아웃 · 정보 위계 · 포인트 컬러**를 그대로 베끼면 안 된다.
> 와이어프레임은 **콘텐츠 source**일 뿐 layout/visual blueprint 가 아니다.
>
> **금지:**
> - 와이어프레임의 회색 박스 배치를 그대로 frame 배치로 옮기는 것
> - 와이어프레임의 글자 크기 위계를 그대로 fontSize 로 옮기는 것 (예: 와이어 본문이 다 같은 크기여도 디자인에선 hero/section/body 차등)
> - 와이어프레임의 포인트 컬러(빨강·파랑 등) 를 그대로 brand 외 컬러로 옮기는 것
>
> **필수:**
> - **가독성 / 시인성 / 미학** 우선으로 시각 위계 재구성
> - 핵심 수치는 hero size (28~36px Bold), 카드 그룹화로 정보 위계 차등
> - 반복 요소(카드 리스트 등)는 첫 번째를 강조하거나 차등 적용
> - **약간의 창의적 컬러 사용**: 상태 표시(성공/완료/주의) 에 brand tint + 시맨틱 액센트 소량 (브랜드 일관)
> - 와이어프레임에 없는 폴리시(카드 그림자/elevation, 도형-배경 대비, 강한 타이포 위계) 추가
>
> **Why:** 와이어프레임을 그대로 옮기면 "디자인을 한 게 아니라 와이어를 강화한 것"이 된다.
> 사용자가 디자이너에게 기대하는 건 **콘텐츠를 받아 디자인적 판단을 더한 결과물**이지,
> 와이어를 px-perfect 로 옮기는 게 아니다.
>
> **검증 (사람이 확인):**
> - 빌드 후 스크린샷을 와이어프레임 옆에 놓고 비교 — 시각 위계/그룹화/액센트가 **달라야** 정상
> - 똑같으면 룰 위반 → 재구성
>
> 코드로 자동 검출 불가능 (의미적 판단). 매 디자인 빌드 시 사람(Claude)이 자체 검증.

> 🔴 **절대 규칙 0-B — `-alt` / `_alt` 변형 토큰은 절대 쓰지 말 것**
>
> `bg-secondary-alt`, `border-secondary-alt` 같은 `-alt` 토큰은 **금지**다.
> `bg-secondary`가 필요하면 **반드시 `$token(bg-secondary)`** — 절대 `-alt`를 붙이지 말 것.
> (figmaPath에서는 `_alt`(언더스코어)로 표기되지만 blueprint에는 `-alt`·`_alt` 둘 다 쓰지 않는다.)
>
> - 빌드 파이프라인이 `$token(...-alt)` / `$token(..._alt)`를 자동으로 기본 토큰으로 교정한다:
>   1. `figma_mcp_client.py` `resolve_token_ref` / `_token_to_figma_path` → `_strip_alt_token()`으로 `-alt` 제거 + **마지막 세그먼트 '정확 일치' 우선 매칭**
>   2. `figma-mcp-embedded.ts` `set_bound_variables` → 바인딩 경로의 `_alt`/`-alt` 접미사 제거
> - ⚠️ 과거 버그: 토큰 매칭이 `startswith(name + "_")`를 허용해 `$token(bg-secondary)`가
>   `bg-secondary_alt`로 오매칭됐다 — 이제 '정확 일치' 우선이라 해결됨.

> 🔴 **절대 규칙 0-N — 다른 정보는 다른 레이아웃/UI / 와이어 1:1 복제 금지 (2026-06-04 사용자 룰)**
>
> 사용자 명시: *"다른 정보인데 같은 레이아웃, UI로 표현하지 말것! 똑같아서 같은 정보
> 같잖아. 와이어프레임 그대로 레이아웃과 정렬 및 크기 생성하지 말것!"*
>
> **두 가지 의무:**
> 1. **인접 섹션 시각 언어 차별화** — 내용이 다른 두 섹션을 **동일한 카드 구조**(같은
>    2-up 그리드 + 같은 [아이콘 원 + 제목 + 부제] 패턴)로 그리면 같은 정보처럼 보인다.
>    한쪽의 시각 언어를 바꾼다: **2-up 그리드 ↔ 리스트 행**, 카드 크기·틴트·아이콘 배치
>    차등, 강조 카드 등. (사례: '시작 방법 카드' vs '출석/초대 카드' 가 똑같던 회귀 →
>    시작=틴트 2-up 그리드, 출석/초대=흰 리스트 행으로 분리.)
> 2. **와이어프레임 레이아웃/정렬/크기 1:1 복제 금지** — 와이어는 **콘텐츠 source**일 뿐
>    레이아웃 blueprint 가 아니다(절대 규칙 0-C). 와이어의 박스 배치·정렬·크기를 그대로
>    옮기지 말고 **가독성·시각 위계·미학** 기준으로 재구성한다. 콘텐츠(텍스트/숫자)는 1:1
>    (0-E), **레이아웃/스타일은 창의적 재해석**.
>
> **시스템 강제 (코드 박힘):**
> - `scripts/design_rules/R63_distinct_section_ui.py` — **L2 lint**: root 직계 섹션 중
>   '카드 그리드'를 가진 인접 두 섹션의 구조 시그니처(텍스트/색 무시, layout mode +
>   rounded + 자식 구조)가 같으면 WARN("동일한 카드 레이아웃 — 시각 언어 차별화하라").
>   자동 차단 X(디자인 판단) — blueprint 작성 시 Claude 가 차별화.
> - 와이어 1:1 복제는 코드 자동검출 불가(와이어 ref 없음) — 매 빌드 시 사람(Claude)이
>   스크린샷을 와이어 옆에 놓고 **레이아웃/위계/액센트가 달라야 정상**임을 자체 검증(0-C).
>
> **빌드 후 검증:** 빌드 로그에 `R63-distinct-section-ui` WARN 이 보이면 인접 섹션 UI 가
> 똑같다는 뜻 → 한쪽 재설계. 스크린샷에서 인접 카드 영역이 서로 다른 시각 언어인지 확인.

> 🔴 **절대 규칙 0-O — 상단 NavBar 스타일 (2026-06-04 사용자 룰)**
>
> 1. **NavBar frame 의 fill = `$token(bg-primary)`** (투명/회색 금지). 상단 네비게이션 바 배경은
>    항상 흰색(bg-primary).
> 1-b. **NavBar frame 자체에 stroke(보더) 가 없어야 한다.** (상단 바에 테두리 금지.)
> 2. **NavBar 안 좌측 back 버튼 frame 에도 stroke(보더) 가 없어야 한다.** (흰 배경 위 back
>    아이콘 버튼에 테두리 금지 — fill 만 또는 fill 도 없이 아이콘만.)
> 3. 🔴 **back 버튼이 노출되면 Nav Back frame 의 오른쪽 padding = `spacing-xl`(16) 바인딩 (2026-06-10
>    사용자 룰).** back 아이콘↔타이틀 간격을 spacing 토큰으로 통일한다. paddingRight=16 + `spacing-xl`
>    변수 바인딩(절대값 아님). (40×40 FIXED back frame 이면 아이콘이 약간 좌측으로, 우측 16 여백 생김.)
>
> **시스템 강제 (코드 박힘, 자동):** `figma_mcp_client.py _enforce_navbar_style_live`
> (cmd_post_fix 맨 끝 + build Step E.7.7 — AUTO_FIX·white-card-border *이후* 라야 stroke 가
> 재부착 안 됨) — NavBar(이름에 navbar/nav bar/app bar/top bar/header bar 포함 HORIZONTAL frame)의
> fill 을 bg-primary 로 강제(리터럴+변수 바인딩) + NavBar frame 자체 stroke 제거 + NavBar 서브트리의
> back 버튼(이름에 back/뒤로, 또는 chevron-left/arrow-left 아이콘 든 frame) stroke 를 `strokeWeight 0`
> 으로 제거 + **back 버튼 frame paddingRight=16(spacing-xl) 설정·바인딩**(`_NAV_BACK_PAD_RIGHT`/
> `_NAV_BACK_PAD_TOKEN`). 빌드 후 검증: NavBar 배경 흰색 + NavBar·back 버튼 테두리 없음 +
> back 버튼 오른쪽 padding 16 이 spacing-xl 에 바인딩(get_nodes_info boundVariables.paddingRight).

> 🔴 **절대 규칙 0-P — Segmented_control 은 기본 Size=md (2026-06-04 사용자 룰)**
>
> DS **Segmented_control** 인스턴스는 **특수한 상황이 아니면 props 의 `Size` 를 `md` 로 고정**한다
> (기본 import 가 `sm` 이라 작게 나옴). 특수 케이스만 다른 size.
>
> **시스템 강제:** `_configure_segmented_control` (cmd_build, seg-tabs 설정 시) 이 인스턴스의
> `Size` variant 를 `md` 로 자동 설정(`config.size` 로 override 가능). blueprint 의 탭 인스턴스에
> `_segLabels` 마커만 박으면 라벨·선택과 함께 Size=md 가 자동 적용된다.

> 🔴 **절대 규칙 0-Q — radius 있는 frame 은 꼭 clipsContent=true (2026-06-04 사용자 룰)**
>
> 사용자 명시: *"frame에 radius 값을 넣으면 꼭!! Clip content 옵션 체크가 되어야 한다."*
>
> **cornerRadius(또는 개별 코너 radius)가 0보다 크면** 그 frame 의 `clipsContent` 는 **반드시
> true** — 둥근 모서리가 콘텐츠를 클립해야 내부 image/색 영역이 모서리 밖으로 안 삐져나온다.
> (예전엔 cr≥8 카드만 강제 → 2026-06-04 모든 radius>0 으로 확대.)
>
> **시스템 강제 (코드 박힘, 자동 — 3중):**
> 1. `_enforce_radius_clip_blueprint(bp)` (cmd_build pre-process) — blueprint 의 radius>0 FRAME 에
>    `clipsContent:true` 박음(batch_build 가 `spec.clipsContent` 반영). 명시 false 는 존중.
> 2. `_enforce_rounded_card_clip_live` (cmd_post_fix, R45 직후) — 라이브 백스톱(균일 cornerRadius).
> 3. 🔴 `_enforce_radius_clip_live(root_id, _collect_radius_clip_paths(bp))` (**Step E.7.7, AUTO_FIX
>    이후**) — R45 가 post-fix·AUTO_FIX 두 곳에서 시트/카드 clip 을 false 로 끄는데, **개별 코너
>    radius**(topLeftRadius 등)를 쓰는 frame(Modal Sheet)은 `get_nodes_info` 가 코너를 None 으로
>    직렬화해 R45 의 rounded 예외·라이브 검출이 모두 놓친다 → blueprint name-path 로 매칭해 clip=true
>    를 **최종 재단언**. (개별 코너 radius 회귀의 진짜 해법.) DS INSTANCE·root 제외.
> 빌드 후 검증: Modal Sheet 등 둥근 frame 의 Clip content 가 체크됨(내부 영역이 모서리 밖으로 안 튀어나옴).
> 테스트: `scripts/tests/test_radius_clip.py`.
>
> 🔴 **추가 (2026-06-04): radius 값은 `radius-*` DS 토큰에 바인딩.** cornerRadius(균일·개별
> 코너 모두)를 스케일 일치 `radius-*` 토큰에 자동 바인딩 — `_bind_radius_tokens_live`(post-fix,
> spacing 바인더 직후). 0=none 4=xxs 6=xs 8=sm 10=md 12=lg 14=xl 16=2xl 20=3xl 24=4xl 28=5xl
> 32=6xl, ≥100=full. 위 post-fix 항목 7-b 참조. blueprint 의 radius 는 이 스케일 값으로 쓸 것.

> 🔴 **절대 규칙 0-R — 디자인 생성 완료 시 사용한 blueprint json 자동 삭제 (2026-06-05 사용자 룰)**
>
> 사용자 명시: *"디자인 생성이 완료되면 디자인 생성 시 만들었던 블루프린트 json 파일은 자동 삭제
> 되도록 할 것! 코드로도 강제해."*
>
> 빌드가 끝나면 화면은 Figma 에 생성됐으니 그 빌드에 쓴 **blueprint/spec json 은 불필요** →
> `scripts/` 에 산출물이 쌓이지 않도록 **빌드 직후 즉시 자동 삭제**한다(생성 7일 대기하는
> `cleanup_old_blueprints.py` 와 별개 — 이건 즉시).
>
> **시스템 강제 (코드 박힘, 자동):** `figma_mcp_client.cmd_build` 가 빌드 성공(root_id 존재) 시
> 맨 끝에서 `_cleanup_build_input(blueprint_file)` 호출. 삭제 대상 = 빌드 입력으로 쓴
> `blueprint_*.json` · `spec_*.json` · `*assembled*.json` · `*_blueprint.json`.
> 🔴 **보존(소스/입력 자산은 삭제 안 함):** `blueprint_templates.json`(assemble 소스 템플릿) ·
> `archetype_specs/*.json`(unified spec 소스 — 홈 등 unified 빌드는 이 spec 으로 생성) ·
> 이름에 `PRD`(사용자 입력) · `wireframe_content`(와이어 콘텐츠 dict).
>
> **빌드 후 검증:** 빌드 로그에 `🧹 [cleanup] 빌드 완료 — 사용한 blueprint json 자동 삭제: <파일>`
> 라인이 보이면 자동 삭제 성공. 단위 테스트로 삭제 대상/보존 분기 검증됨.
> ⚠️ blueprint 가 삭제되므로 동일 화면을 다시 빌드하려면 blueprint 를 새로 작성/조립해야 한다
> (의도된 동작 — 화면은 Figma 에 이미 있고 source 만 정리).

> 🔴 **절대 규칙 0-T — 하단 월렛 바는 top-left/top-right radius 16 (2026-06-05 사용자 룰)**
>
> 하단 고정 **월렛 바('마이 월렛')** 는 시트처럼 **위쪽 두 코너만 둥글게(topLeftRadius=topRightRadius=16
> = radius-2xl)**, 아래 두 코너는 0. 평평한 사각형 금지. blueprint 작성 시 월렛 바 frame 에
> `topLeftRadius:16, topRightRadius:16, clipsContent:true` 명시.
>
> **시스템 강제 (코드 박힘, 자동):** `_enforce_wallet_bar_radius(root_id)` (cmd_post_fix, section-bg-gap
> 직후) — 이름에 'wallet'/'월렛' 든 frame 의 top-left/top-right radius 를 16 으로 강제(`set_corner_radius`
> corners=[T,T,F,F]). radius>0 이라 0-Q 클립 enforcer 가 clipsContent=true 보장, 16 은 radius 바인더가
> radius-2xl 토큰으로 자동 바인딩. 생성기 6종 wallet_bar 에도 topLeftRadius/topRightRadius=16 박음.
> ⚠️ 이전엔 이 룰이 **없어서** 월렛 바가 평평했음(위반이 아니라 미구현) — 이제 박혔으니 재빌드에도 유지.

> 🔴 **절대 규칙 0-U — 상단바/헤더 아이콘 버튼은 기본 '무chrome' (2026-06-09 사용자 룰)**
>
> 사용자 명시: *"상단바 좌/우 버튼에 왜 radius·stroke 를 넣냐 — 별도로 넣으라는 요청이 없을땐
> 기본으로 넣지마!"* 상단바/헤더의 **아이콘만 든 작은 버튼**(back/search/nav 등)에는 **fill 박스·
> radius·stroke(border)를 기본으로 넣지 않는다 — 아이콘만.** 별도 스타일 버튼이 필요할 때만 노드에
> `"_buttonChrome": true` 마커로 허용.
>
> **회귀 뿌리:** `_is_card_like`(cornerRadius≥8+fill+children)가 40×40 아이콘 버튼을 '카드'로 오인
> → `_enforce_card_surface`가 fill 을 bg-primary 로 바꾸고, `_enforce_white_card_border(_live)`가
> border-secondary 를 붙였다.
>
> **시스템 강제 (코드 박힘, 자동):**
> 1. `_is_icon_button(node)` — 작은 프레임(≤60px) + 자식이 전부 아이콘/vector('ic-' 프레임 포함) +
>    `_buttonChrome` 없음. blueprint·라이브 양쪽 자식 형태 인식.
> 2. `_is_card_like`(blueprint/라이브) + `_enforce_white_card_border(_live)` 가 아이콘 버튼을 **제외**
>    → fill 변환·border 자동부착 안 함.
> 3. `_strip_icon_button_chrome_live(root_id)` (cmd_post_fix, white-card-border **직후**) — 아이콘 버튼의
>    stroke 제거 + 중립 fill 박스(bg-primary/secondary/tertiary) 투명화 + cornerRadius 0. 의도된 색
>    fill 은 보존. DS INSTANCE·내부(';') 제외. 로그 `[icon-button-chrome] ✓ … chrome 제거`.
>    ⚠️ **하단 chrome 바(action bar/tab bar/fab/wallet) 안 버튼은 strip 제외** — 이 룰은 '상단바'
>    아이콘 버튼 대상. 하단 액션바 북마크/채팅 버튼 등은 의도된 스타일 박스라 보존(ancestor 이름으로
>    감지). (`_buttonChrome` blueprint 마커는 라이브 노드에 안 남으므로 라이브 strip 은 ancestor 로 판정.)
> 4. **작성 규칙:** 아이콘 버튼은 처음부터 fill/radius/stroke 없이 아이콘만(`fr(name, width, height,
>    children=[icon(...)])`). 스타일 버튼은 `_buttonChrome:true`.

> 🔴 **절대 규칙 0-V — 콘텐츠/뷰 전환 탭 = underline tabs (Segmented_control 아님) (2026-06-09 / 🔴 2026-06-12 확장)**
>
> 사용자 명시(2026-06-09): *"NavBar 추천/전체는 segmented control 말고 tabs component underline
> 스타일로. 텍스트가 크게 잘 보여야 할땐 tabs 를 쓰는게 좋아!"*
> 🔴 사용자 명시(2026-06-12): 입금/지급 'View Tabs' 도 Segmented 가 아니라 tabs 여야 한다.
>
> **콘텐츠/뷰를 전환하는 모든 탭은 underline tabs 가 기본** (절대 규칙 0-J 와 동일 — 0-V 는
> 그 구체 적용). active 탭 아래 underline bar(active=`fg-primary`·inactive=투명), 텍스트
> active=`text-primary`/inactive=`text-tertiary`. **컴팩트 on/off 토글만 Segmented_control**
> (`_forceSegmented:true`). 큰 페이지 탭(추천/전체)은 라벨 22~24 Bold 로, 카드 내 뷰 탭(입금/지급)은
> 16 Bold 로.
>
> ⚠️ **DS underline tabs 컴포넌트(143ee3e3…/f11bda3c…)는 import 불가**(deprecated set key, "Component
> not found"). 그래서 **styled raw frame 으로 작성**: View Tabs(HORIZONTAL) 안에 탭별 VERTICAL
> [라벨 Bold + underline bar(FILL h3, active=fg-primary·inactive=투명)]. (전체 JSON 예시는 0-J 참조.)
>
> **시스템 강제 (코드 박힘):** `scripts/design_rules/R60_tabs_ds_instance.py`
> - `_is_tab_nav_wrapper` 가 `"_underlineTabs": true`·`"_forceSegmented": true` 노드를 변환 대상에서 제외.
> - `_inject` 가 raw tab-nav frame + `_segLabels`(non-forced) 뷰 전환 탭을 **underline tabs 로 자동
>   변환**. 작성 시 underline tabs frame 에 `_underlineTabs:true`(이름은 'View Tabs' 등 자유).

> 🔴 **절대 규칙 0-W — 상단 툴바(NavBar) = DS 'Tool Bar' 컴포넌트 인스턴스 (2026-06-12 사용자 룰)**
>
> 사용자 명시: *"상단 tool bar(네비게이션바)를 매번 새로 그리는게 아니라, 컴포넌트 인스턴스를
> 쓸 것! 메인과 서브 화면은 컴포넌트 props 옵션을 선택해서 사용하는걸로"*
>
> 상단 네비게이션바를 raw frame(로고 placeholder + 아이콘 직접 그리기)으로 그리지 말고
> **Imin DS 'Tool Bar' 컴포넌트 인스턴스**를 쓴다. 메인/서브는 **`Type` variant** 로 선택:
> | 화면 | variant | componentKey |
> |------|---------|--------------|
> | 메인·탭바 홈 (로고+우측 아이콘) | Type=Home | `SET:c9299ef0c3c7cc271850a048025a3c8d0e82b230:Type=Home` |
> | 서브 (back+중앙 타이틀+우측 아이콘) | Type=Detail view | `SET:c9299ef0c3c7cc271850a048025a3c8d0e82b230:Type=Detail view` |
> | 모달 X 헤더 (타이틀 유/무 + X) | **View=modal** | Detail 키로 생성 후 `View=modal` flip |
>
> 🔴 **구버전 마스터 캐시 함정 — 타이틀 16px 회귀 (2026-08-06 사용자 보고 ×2: "tool bar
> title text가 16px인데 ds figma에는 20px", "또 또 tool bar title 텍스트 크기가 작아").**
> - **원인**: `importComponentSetByKeyAsync` 는 파일에 **이미 import 된 컴포넌트를 재사용**
>   한다. DS 라이브러리에서 타이틀이 20px(Body xl/Semibold)로 업데이트돼도, 파일 내 캐시
>   마스터가 구버전(16px Body md)이면 **새로 만드는 인스턴스마다 16px** 로 생성된다.
>   신선한 인스턴스 실측으로 확정(2026-08-06): 아무 패스도 안 거친 인스턴스가 이미 16px.
> - **백스톱(코드 강제)**: ① `_enforce_tool_bar_title_style_live` — cmd_post_fix 체인에서
>   루트 내 모든 Tool Bar/NavBar 인스턴스의 비어있지 않은 타이틀 TEXT 가 20px 가 아니면
>   Body xl/Semibold 재단언. ② `_configure_tool_bar` 도 타이틀 적용 직후 같은 재단언.
> - **근본 해결(수동)**: Figma **Assets > 라이브러리 업데이트 수락** — 파일 마스터가 최신이
>   되면 백스톱은 no-op. 이 함정은 Tool Bar 만이 아니라 **모든 import 캐시 DS 컴포넌트**에
>   해당([[verify-ds-keys-before-build]] 철학) — 마스터 갱신 의심 시 신선 인스턴스로 실측.
> - 수동 변환/스크립트 흐름에서 Tool Bar 인스턴스를 직접 만들 때도 생성 직후 타이틀 크기를
>   검증하고 20px 재단언을 포함할 것.
>
> 🔴 **모달 X 헤더도 Tool Bar 인스턴스 — 제외 아님 (2026-08-04 사용자 룰: "왜 tool bar
> instance 안 쓰고 일반 프레임으로 만든거야? 왜 규칙을 어긴거지").** 과거 R64 는 x-close
> 헤더를 swap 제외했으나(2-D 별도 패턴 근거), 실물 검증 결과 Tool Bar 는 **View=modal
> variant + Back button/Title/Num BOOLEAN prop** 으로 X-only·타이틀+X 헤더를 모두 표현
> 가능하다. blueprint 마커 `_navModal: true` → `_configure_tool_bar` 가 View=modal flip +
> (타이틀 없으면 Title off) + Back/Num off, X 는 `_navIcons:["x-close"]` (R64 inject 가
> x-close 헤더 감지 시 자동 부여). raw X 헤더 유지는 규칙 위반.
>
> 🔴 **바텀시트 헤더 Tool Bar + 시트 clipsContent (2026-08-14 사용자 룰: "시트 헤더에
> tool bar instance 를 사용할 경우, 시트 frame 의 Clip content 옵션 체크해야 한다. 그래야
> 상단 좌우로 corner radius 가 적용되어서 보여져").** Tool Bar 인스턴스는 사각이라, 시트
> 프레임(top radius 16)이 clipsContent=false 면 헤더 모서리가 라운드를 덮어 각지게 보인다.
> 시트 헤더를 Tool Bar 로 교체하는 모든 흐름(빌드·변환·convert_screen.py 자동 스왑)에서
> 교체 직후 시트 프레임 clipsContent=true 를 재단언할 것. 0-Q(radius>0 → clipsContent)의
> 시트 특화 케이스.
>
> ⚠️ **`SET:` 키 형식**: Tool Bar 는 variant 개별 키가 비공개(컴포넌트 셋만 게시)라
> `"SET:<setKey>:<Variant>"` 형식을 쓴다 — `code.js importComponentFlexible` 가
> `importComponentSetByKeyAsync` 로 셋을 import 후 variant 이름을 prop 단위로 매칭
> (플러그인 재실행 후 활성). catalog: `ds_catalog.COMPONENT_KEYS["Tool Bar Home"/"Tool Bar Detail"]`.
>
> **blueprint 작성:**
> ```json
> {"name": "NavBar", "type": "instance",
>  "componentKey": "SET:c9299ef0c3c7cc271850a048025a3c8d0e82b230:Type=Detail view",
>  "_navTitle": "내 스케줄", "_navIcons": ["bell-01", "share-07"],
>  "layoutSizingHorizontal": "FILL"}
> ```
> - 서브 화면 중앙 타이틀은 **`_navTitle` 마커** — 빌드 후 `_configure_tool_bar`(cmd_post_fix)가
>   인스턴스 내부 타이틀 TEXT 를 scan_text_nodes 로 찾아 자동 적용.
> - 🔴 **우측 버튼 = `_navIcons` 마커 + Right Buttons `Type` variant (2026-06-12 사용자 룰)** —
>   사용자 명시: *"오른쪽 버튼이 없어야 할때는 속성에서 empty를 선택하면 된다. 버튼이 하나면
>   1 button으로 두개면 2 button으로."*
>   | `_navIcons` | Right Buttons Type | 동작 |
>   |---|---|---|
>   | `[]` (빈 배열) | **`empty`** | 우측 버튼 없음 — 와이어에 아이콘 없으면 이것 (기본 버튼 방치 금지) |
>   | `["share-07"]` | **`1 button`** | 버튼 1개 + 아이콘 swap |
>   | `["bell-01","share-07"]` | **`2 button`** | 버튼 2개 + 아이콘 swap (최대 2개) |
>   | 마커 없음 (None) | (유지) | 마스터 기본 그대로 |
>   variant flip 후 각 버튼의 중첩 아이콘 인스턴스를 `swap_instance_component`(plugin, nested
>   instance swap override)로 교체. 구버전 variant 이름("N Symbol")은 자동 폴백. 이름→키 해석은
>   `ds_catalog.NAV_ICON_KEYS`(bell/chat/search/share/settings/dots-vertical/wallet/calendar 등) —
>   **맵에 없는 아이콘은 swap skip + WARN(마스터 기본 유지)**, 필요 시 Imin DS 에서 키 찾아 맵에
>   추가. 이 swap 은 variant/prop 과 같은 공식 override 라 0-K(인스턴스 색 변경 금지)와 충돌하지
>   않는다 — **색이 아니라 컴포넌트 교체만** 한다.
> - 검색바 등 Tool Bar 로 표현 불가한 특수 navbar 만 raw frame + **`_customNavBar: true`** 마커.
> - **modal/bottom-sheet 의 X-only 헤더는 별도 패턴(2-D) — Tool Bar 강제 대상 아님.**
>
> **시스템 강제 (코드 박힘, 자동):** `scripts/design_rules/R64_navbar_ds_instance.py`
> - **L2 lint**: raw NavBar frame 발견 시 WARN.
> - **L3 inject**: 빌드 직전 자동 swap — 로고 자식 있으면 Type=Home, back 버튼 있으면
>   Type=Detail view + 타이틀 텍스트를 `_navTitle` 로, **우측 아이콘들을 `_navIcons` 로 캡처**
>   (back/x-close 제외, 최대 2개 — **와이어에 우측 아이콘이 없으면 `[]` 명시 = Type=empty**).
>   x-close 헤더(모달)·로고/back 둘 다
>   없는 navbar(의도 불명)·`_customNavBar`·modal/bottom-sheet 화면은 swap 안 함.
> - **L4 (cmd_post_fix)**: `_collect_tool_bar_configs` + `_configure_tool_bar` 가 `_navTitle` 적용
>   + `_swap_tool_bar_icons` 가 Right Buttons `Type`(empty/1 button/2 button) flip + 아이콘 swap.
> - **L5 verify**: 빌드 후 NavBar 가 FRAME 으로 남으면 WARN.
> - 생성기/템플릿도 인스턴스 emit: `unified_blueprint._gen_nav_bar`(data.title 있으면 Detail),
>   `blueprint_templates.json` NavBar(assemble `variables.NavBar.title` 로 Detail 전환).
> - 절대 규칙 0-O(NavBar fill/stroke 강제)는 FRAME 만 대상이라 Tool Bar **인스턴스는 자동 제외**
>   (인스턴스 색/스타일은 0-K 에 따라 마스터가 제어). raw `_customNavBar` frame 에는 0-O 가 계속 적용.
>
> **빌드 후 검증:** 빌드 로그에 `[inject R64] NavBar raw frame → DS Tool Bar instance: N건` +
> (서브 화면) `[tool-bar] ✓ 'NavBar' 타이틀 → '<타이틀>'` 라인 확인. 스크린샷에서 NavBar 가
> DS Tool Bar(메인=로고, 서브=back+타이틀)인지 확인. 테스트: `scripts/tests/test_navbar_ds_instance.py`.

> 🔴 **절대 규칙 0-S — 텍스트 스타일 바인딩을 절대 깨지 말 것 (2026-06-05 사용자 룰)**
>
> 사용자 명시: *"텍스트 크기만 조절하려고 텍스트 스타일 바인딩이 깨졌는데 좀더 큰 사이즈를
> 적용하려면 텍스트 스타일에서 좀 더 큰걸 쓰면 되. 바인딩을 깨면 안된다!"*
>
> **텍스트 크기를 바꿀 때 raw `set_font_size` 로 styled 텍스트의 크기를 덮어쓰지 말 것** —
> 그러면 DS text style 바인딩이 detach(깨짐)된다. 크기를 키우려면 **같은 weight 의 더 큰
> DS 텍스트 스타일을 `set_text_style_id` 로 적용**한다(바인딩 유지). 줄이는 것도 동일.
>
> **시스템 강제 (코드 박힘, 자동):**
> - `_enforce_min_text_size_live(root_id)` (cmd_post_fix) 는 **절대 `set_font_size` 를 쓰지
>   않는다.** 작은 텍스트의 (size, weight) 를 읽어 floor 이상이 되는 DS 텍스트 스타일을
>   `set_text_style_id` 로 입힌다. DS 인스턴스 내부(';')·장식 기호 제외.
> - 🔴 **stale 맵 대응 — 실제 적용 크기 검증 + 에스컬레이션:** `ds/TEXT_STYLE_MAP.json` 이
>   stale 하면 (예: '14px' 키가 라이브 DS 에선 12px 로 import 됨) 적용 후 실제 size 가 floor
>   미달일 수 있다. 그래서 적용 후 `get_nodes_info` 로 실제 size 를 검증하고, 미달이면 다음
>   DS 스케일(16…)로 올려 재적용한다 — 항상 `set_text_style_id` 만 사용(바인딩 유지).
> - blueprint pre-process `_enforce_min_text_size` 는 fontSize 숫자만 올리고(텍스트 스타일
>   매핑 *전*), 이후 text-style 단계가 그 크기의 스타일을 바인딩 → raw size 가 남지 않는다.
>
> ⚠️ **TEXT_STYLE_MAP.json stale 시 (Pretendard 14px 등 일부 tier 가 깨졌을 때) 근본 해결:**
> 플러그인을 **DS 파일('Imin Design System')에 연결**한 뒤 `python3 scripts/figma_mcp_client.py
> sync-text-styles` 1회 실행 → 최신 키로 재추출·커밋. (variables 의 sync-variable-keys 와 동일 패턴.)
>
> **빌드 후 검증:** 텍스트 노드가 **size ≥ 하한 + textStyle 바인딩 유지**(get_nodes_info 의
> `styles.text` 존재) 인지 확인. raw fontSize 만 박히고 styles.text 가 빈 노드 = 위반.

### 1. ⚠️ Status Bar는 blueprint에 넣지 말 것 — 빌드가 DS Status Bar를 자동 삽입
- **Status Bar를 텍스트/프레임으로 직접 그리거나 blueprint 노드로 넣지 말 것.**
- `batch_build_screen`은 blueprint root.children에 status bar 노드가 **없으면 DS "Status Bar" 인스턴스를 루트 첫 자식으로 자동 삽입**한다. blueprint에 "Status Bar" 같은 노드를 넣으면 빌드가 그걸 그대로 써서 직접 그린 status bar가 박힌다(= 버그).
- **규칙: blueprint root.children에 status bar를 절대 포함하지 않는다.** 빌드가 알아서 DS 인스턴스를 넣는다.
- **로고**: 🔴 NavBar 는 이제 DS 'Tool Bar' 인스턴스(절대 규칙 0-W) — **Type=Home variant 에 로고가 내장**되어 있어 Logo Placeholder 가 필요 없다. (`_customNavBar` raw frame 인 경우에만 기존 방식: `"Logo Placeholder"` 프레임(80×32)을 넣으면 `cmd_build`가 DS 로고 인스턴스로 자동 교체(Step G). 텍스트로 로고를 그리지 말 것.)
- **빌드 후 검증**: 루트 첫 자식이 INSTANCE `"Status Bar"`인지 확인.
- 참고: "Styles" 페이지(`276:1882`)에 마스터 인스턴스가 있다 — Status Bar `279:4758`, 로고 `279:4757`. 자동 삽입이 안 되는 특수 상황에서만 `clone_node`(인스턴스는 clone해도 인스턴스 유지) 후 `insert_child`로 수동 삽입.

### 2-H. ⚠️ 큰 면적 brand fill — 🔻 2026-06-12 advisory 강등 (룰 2계층 ② 참조: 의도된 컬러 히어로 허용, WARN만)
- **"추천 스테이지 섹션같이 버튼이 아니면서 면적이 큰 frame에 brand color를 채우지마!"**
- 이전 룰 폐기 — "Recommend Brand Card = brand-solid hero" 패턴 (`bg-brand-solid` 보라색 큰 카드) 사용자 분노.
- **새 표준**: 큰 카드 = `bg-primary` + `border-secondary` 1px. brand 는 **작은 액센트**(텍스트, 버튼 label, 작은 dot)만.
- **사용자 reference 패턴** (17380:48334 분석):
  - Recommend Brand Card: `bg-primary` 흰 + border (이전 brand-solid)
  - Eyebrow / Headline: `text-primary` 다크 / `fg-secondary` (이전 fg-white)
  - **숫자 hero** "1,300,000": `text-brand-primary` 보라 (강조)
  - **CTA Primary** "참여하기": `bg-primary` + label brand
  - Detail Card: `bg-secondary` 회색 (위계 역전 — 흰 hero 안 회색 inset)
  - CTA Secondary: `fill=none` + label `text-tertiary`
- **시스템 강제 (3단 박힘):**
  1. `_enforce_no_large_brand_fill(blueprint)` — blueprint 단계: `$token(bg-brand-*)` + (cornerRadius≥12 ∧ children≥2 ∨ children≥3) frame 자동 `bg-primary` + border 교체
  2. `_strip_large_brand_fills(root_id)` — 빌드 트리 단계: brand RGB heuristic + 면적 ≥ 100×60 frame 검출 + 교정
  3. `cmd_post_fix` 끝에서 매 실행 자동 — 회귀 차단 (`_auto_fix_invisible_text` 가 내부 흰 텍스트 다크로 연쇄 fix)
- **실측 검증**: brand card fill을 일부러 깨뜨린 후 post-fix → 1건 frame + 8건 텍스트 자동 회복 로그 확인.

### 2. ⚠️ 색상 — 절제된 단일 액센트 + 폴리시 (2026-05-23 갱신)
- **브랜드 컬러는 앱의 단일 일관 액센트** — 주 액션(CTA)·active 탭/네비·핵심 수치·중요 링크/아이콘 등 **의도된 여러 지점**에 일관되게 사용한다. 회사가 거부한 건 "여러 색 난무"이지 브랜드 컬러 자체가 아니다. 단, 모든 카드·태그·통계에 무분별하게 깔지는 말 것.
- **피드백(상태) 컬러는 소량·차분하게** — 미납·완료·주의 등 **진짜 상태 정보**에 한해 `success`/`warning`/`error` 계열을 절제된 톤으로 소량 사용 가능. 장식·태그·통계 전반에 색을 까는 건 금지.
- **폴리시 필수 (와이어프레임 탈피)** — 평평한 그레이 박스만 나열하면 와이어프레임처럼 보인다. **카드 그림자/elevation, 흰 카드 ↔ 연한 그레이 면의 도형-배경 대비, 강한 타이포 위계(히어로 수치는 크게·Bold)**로 "디자인된" 느낌을 만든다.
- **베이스는 뉴트럴 그레이** — `bg-/fg-/border-` 그레이 계열 중심이되, 완전 무채색 평면은 금지.
- **Why**: 회사가 "브랜드/피드백 컬러 난무"를 거부 → 절제. 그러나 완전 그레이톤 + 버튼 1개는 "와이어프레임 같다"고 재피드백 (2026-05-23). 적정선 = 절제된 단일 액센트 + 상태 컬러 소량 + 입체감 폴리시.

### 2-J. ⚠️ Aqua 컬러 사용 자제 (2026-06-05 정책 재반전)
> 🔴 사용자 명시 (2026-06-05): *"전에 아쿠아 컬러 사용하라고 했었는데 이젠 아쿠아 컬러 사용을
> 자제하도록 규칙과 코드 수정해."* → 2026-06-02 의 **"Aqua 보조 액센트 권장"을 폐기**한다.
> 이제 **Aqua 컬러 사용을 자제**한다.
>
> ⚠️ **정책 이력 (3번 반전):** 2026-05-05 "aqua 쓰지마"(차단) → 2026-06-02 "Aqua 보조 액센트
> 권장"(반전) → **2026-06-05 "Aqua 자제"(재반전, 현재)**.
>
> - **주 액센트 = 브랜드 퍼플** (그대로): 주 액션(CTA)·active 탭/네비·핵심 hero 수치·진행바.
> - **상태색 = 진짜 상태에만** 소량: success(완료/곧 수령)·warning(미납/D-day)·error(연체).
> - **Aqua 는 자제** — 꼭 필요한 특수 케이스가 아니면 쓰지 않는다. 단조로움이 우려되면 Aqua
>   대신 **중립(`bg-secondary`/`bg-tertiary`/`text-secondary`)** 으로 카드·섹션을 차별화하거나
>   **brand tint(`bg-brand-secondary`/`text-brand-primary`)** 를 절제 사용한다. 🔴 **인접 섹션
>   시각 언어 차별화(0-N)는 색이 아니라 레이아웃·구조로도 한다** — 굳이 Aqua 같은 별도 색을
>   끌어오지 말 것.
> - **"여러 색 난무" 금지** 는 그대로.
>
> **시스템 강제 (코드 박힘):**
> 1. `scripts/design_rules/R26_second_accent.py` (rule_id `R26-aqua-restraint`) — **L2 lint
>    advisory**: Aqua 토큰이 화면에 쓰이면 WARN("Aqua 자제 — 중립/brand tint 로 대체"). 차단은
>    안 함(자제이지 완전 금지는 아님).
> 2. `figma_mcp_client.py _enforce_color_restraint` — 빌드 로그 `[색상]` 에 Aqua N곳 집계 +
>    N>0 이면 자제 권고 출력. (구: Aqua=0 단조 경고 → **폐기**.)
> 3. `figma_mcp_client.py _normalize_aqua_token` — **유지**. Aqua 를 정말 써야 할 특수 케이스
>    에서 올바른 색으로 해석·바인딩하기 위함(`utility-blue`=파랑 오염 방지). Aqua 토큰 자체가
>    죽은 건 아니다 — 자제할 뿐.
> 4. `scripts/design_rules/schema.py` — `aqua` 명시 토큰의 primitive-prefix ban 예외도 유지.
>
> **빌드 후 검증:** 빌드 로그 `[색상]` 에 Aqua 가 **0곳이거나 최소**인지 + 스크린샷에 청록색이
> 거의 없는지(브랜드 퍼플 + 상태색 + 중립 위주) 확인.

### 2-K. 🔴 다크 면 기본값 금지 — 색 축은 화면 간에도 로테이션 (2026-07-10 사용자 룰)

> 사용자 관찰: *"(모델을 fable 로 바꾼 뒤) 어두운 컬러를 아주 많이 쓴다. opus 4.8 일 땐
> 브랜드 컬러 중심으로 밸런스 있게 썼다."* — 실측: 연속 2개 시안(imin_signup_home_20260709,
> imin_stage_joined_20260710)이 모두 다크 네이비(`bg-primary-solid`) 면을 히어로/앵커로 사용.
>
> **Why:** novelty 게이트는 *같은 화면의 직전 빌드*와만 비교하므로, 화면을 넘나드는 모델의
> 스타일 버릇(다크 면 선호)은 통과된다. 다크 면이 기본값이 되면 "100번 생성하면 다 똑같다"
> 문제의 재현이다. 룰 환경(2-H·13·2-J 가 브랜드/유채색 *면*을 제한)이 다크를 유일한 '대담한
> 면'으로 남긴 구조적 원인도 있으므로 의식적 로테이션으로 보정한다.
>
> **룰 (스타일 계층 — 작성자 판단 지침, 코드 강제 없음):**
> 1. **기본 밸런스 = 뉴트럴 베이스(흰 카드+보더) + 브랜드 퍼플 *액센트***(CTA·active 탭·핵심
>    수치·링크·'나의 것'). 브랜드 *면* 자제(규칙 13)는 그대로 유지 — 액센트로 밸런스를 만든다.
> 2. **다크 면(`bg-primary-solid` 등)은 로테이션의 한 카드일 뿐 기본값 금지.**
>    `_designDirection.color` 를 정할 때 같은 화면의 직전 빌드뿐 아니라 **최근 생성한 다른
>    화면들의 색 축과도 겹치지 않는지** 자문한다 — 직전 화면(들)이 다크 축이었으면 다른 축으로.
> 3. **레퍼런스 선택 편향 점검** — 후보 중 다크 히어로만 골라 근거 삼는 것 자체가 버릇의
>    발현이다. 색 축이 다른 후보를 의식적으로 섞어 학습한다.
> 4. 시스템 강제(cross-screen novelty)는 도입하지 않는다 — 취향은 룰이 아니라 *선택*으로
>    반영한다는 사용자 결정 (2026-07-10 "권장안으로").

### 2-L. 🔴 승인본 메트릭 = 기준선 — fable 성향 셀프체크 (2026-07-13 사용자 룰)

> 사용자 관찰: *"지난달 Opus 4.8 로 생성한 디자인이 레이아웃·배치·크기·컬러 모두 방금(fable)
> 생성한 것보다 훨씬 낫다"* + *"fable 5 의 특성이 아주 강하게 반영되고 있다"* — 이후
> *"매번 opus 문법으로 생성하라고 해야 하나?"* → 룰로 상시화.
>
> **실측 근거 (imin_stage_recommend — Opus 승인본 20260609 vs fable 20260713b):**
> 본문 16px↔14px / 히어로 16 Bold+인용바(헤드 ~75px)↔24 Bold 2줄(156px) / 순번 셀
> 40×34(패딩 8)↔35×20 붕괴(패딩 0) / 칩 44h↔40h / 회색 면 2곳↔4곳 중첩.
>
> **룰 (스타일 계층 — 작성자 판단 지침, 2-K 와 동일하게 코드 강제 없음):**
> 1. **같은 화면의 사용자 승인본이 있으면 그 스타일 메트릭이 기준선이다** — 타이포 스케일
>    분포·패딩/여백 리듬·컨테이너 문법(예: Status Box 회색 박스 안 흰 셀)·figure-ground(흰
>    페이지 + 회색 면 소수)를 **±20% 이내로 승계**한다. 벗어나려면 사유를 `_concept.diffs` 에
>    명시. 빌드 전 `get_nodes_info` 로 승인본 메트릭 표를 뽑아 대조한다.
> 2. **발산(S24~S26)의 대상은 와이어다 — 승인본이 아니다.** 승인본에서 구조를 갈아엎는 것은
>    창의가 아니라 품질 후퇴다 (0-G-2 의 실질 의미).
>    ⚠️ **역방향 주의 (2026-07-14 사용자: "와이어프레임이랑 아주 똑같다! 이러면 맡길 이유가 없지"):**
>    메트릭 승계는 와이어 배치 트레이싱의 면죄부가 아니다. 콘텐츠 1:1 + 메트릭 승계 위에서
>    **정보 구조·그룹핑·위계는 반드시 재설계**한다(섹션 통합/카드 그룹핑/히어로 승격 등 구조 레벨 —
>    점선→솔리드, 이모지 제외 같은 코스메틱 차이는 발산이 아니다). 세 원칙은 양립한다.
> 3. **fable 성향 셀프체크 (blueprint 확정 직전 4항):**
>    ① 다크 면을 앵커로 썼나 (→ 2-K)  ② 타이포 극대비인가 (헤드 24+ 인데 본문 전부 14- —
>    승인 스케일은 16 베이스+12 디테일의 1.3배 간격)  ③ 밀도를 올렸나 (컨트롤 크기·패딩을
>    레퍼런스보다 축소 — 칩 44h·셀 34h 가 기준)  ④ 컨셉 명명("콘솔"·"3표면" 등)에 구조를
>    끼워맞췄나 — 하나라도 YES 면 승인본 메트릭과 대조 후 완화한다.
> 4. **고정 높이 셀은 height 단독 의존 금지** — 상하 패딩으로 높이를 만든다 (enforcer 가
>    FIXED 를 풀어도 콘텐츠가 높이를 지탱, 규칙 20 과 동일 철학. 20260713b 셀 붕괴의 교훈).
> 5. 메모리 참조: `fable-ui-traits`(성향 프로필 7항), `approved-baseline-not-divergence-target`.

### 2-B. ⚠️ 카드 표면 — 🔻 2026-06-12 기본값으로 강등 (룰 2계층 ② 참조: 그레이 면 flip 폐지, 보더는 흰-on-흰 시인성만 자동)
- **루트 위 최상위 카드의 표면 = `$token(bg-primary)` fill + 보더 1px** — `bg-secondary`(회색)로 채우지 말 것. 흰 카드를 보더로 정의한다.
- 🔴 **보더 색 = 뒤(배경) fill 에 따라 결정 (2026-06-02 사용자 룰):**
  - **뒤 배경이 `bg-primary`(흰색)면 보더는 `$token(border-primary)`** — 흰 배경 위 흰 카드는
    연한 `border-secondary` 로는 경계가 거의 안 보여, **더 진한 `border-primary`(#d2d6db)** 로 정의한다.
  - 뒤 배경이 `bg-secondary`/`bg-tertiary` 등 비-흰색이면 보더는 `$token(border-secondary)`.
  - 사용자 명시: *"뒤에 fill color가 bg-primary일때 바로 위 frame의 border color는 border-primary를 사용할 것!"*
- 카드 안의 인셋·서브카드는 대상 아님 (필요 시 `bg-secondary`/`bg-tertiary` 유지). 브랜드 컬러 카드(`bg-brand-solid` 등)도 그대로 둔다.
- **예외 — 맨 아래 Footer (2026-06-05 사용자 룰: 배경색 없음)**: Footer는 **배경색 없음**(`$token(bg-primary)` = 루트와 블렌딩, 회색 띠 X) + **보더 없음**(그림자도 없음). 사용자 명시 *"footer의 bg color는 없는게 나을거 같다."* 강제: `_enforce_card_surface` 의 footer 분기가 footer fill 을 `bg-primary` 로 설정(과거 bg-secondary 회색 띠 폐기).
- **시스템 강제 (자동):** `_enforce_white_card_border_live`(post-fix)가 walk 하며 **각 카드의 뒤
  배경 fill 을 추적** — bg-primary 위면 border-primary, 그 외면 border-secondary 로 stroke 강제 +
  DS 변수 바인딩. 기존에 border-secondary 가 박힌 흰-배경 카드도 border-primary 로 업그레이드(idempotent).
  blueprint 에서 어떻게 쓰든 빌드가 바로잡는다.
- 🔵 **`_keepSurface` 마커 — 의도된 보더리스 그레이 표면 opt-out (2026-06-12 사용자 피드백):**
  사용자가 v2 홈을 *"고리타분 / 와이어와 똑같음 — 카카오페이를 최대한 참고"* 라고 피드백 →
  카카오페이/토스 톤(보더 제로, bg-secondary 보더리스 면으로 영역 구분)이 필요한 화면에서는
  카드 노드에 **`"_keepSurface": true`** 를 박으면 `_enforce_card_surface` 의 그레이→흰카드+보더
  교정을 건너뛴다 (`_keepSizing` 과 동일한 intent-존중 철학). 기본값은 여전히 2-B(흰 카드+보더) —
  마커는 author 가 보더리스 면을 *의도*했을 때만. 적용 예: `imin_signup_home_v5` 의 현황 스트립·
  한도 콜아웃·출석/초대 그룹.

### 2-B-3. 🔴 흰 카드 elevation = DS `Shadows/shadow-basic` 자동 바인딩 (2026-06-18 사용자: "표준으로 박아줘, 빌드마다 자동")
- 사용자 명시: 흰 면+보더 카드에 shadow-basic 효과를 표준으로, **빌드마다 자동** 적용.
- **시스템 강제 (코드 박힘, 자동):** `_apply_card_shadow_live`(cmd_post_fix **맨 끝**, drop-shadow strip *뒤*라
  살아남음) — 흰 fill(bg-primary) + 보이는 보더 + width≥80 + (cornerRadius 8~99 둥근 카드 **또는**
  `_cardShadow` 마커) 인 FRAME 에 DS **`Shadows/shadow-basic`** effect style 을 `set_effect_style_id`
  (`S:{key},{id}`)로 바인딩. 키는 `_load_effect_style_map()` → **`ds/EFFECT_STYLE_MAP.json`**(sync-effect-styles
  추출본) fallback. DS 인스턴스·stepper-btn(원형 999/작은 폭)·skip 마커는 제외. 멱등.
- **제외 (그림자 없음):** 노드에 `"_noShadow": true` 또는 `"_placeholderAllowed"`(CMS 배너 placeholder 등 —
  *자체로 두드러져 그림자 불필요*, 2026-06-18 사용자) → skip.
- **강제 (자동감지 못하는 카드):** 개별 코너 radius(월렛 바처럼 topLeftRadius 만 둥근)는 get_nodes_info 가
  cornerRadius 를 None 으로 줘서 자동감지 안 됨 → 노드에 `"_cardShadow": true` 로 강제.
- ⚠️ **이전 "drop-shadow 절대 금지"(2-E/[[feedback_no_drop_shadow]])는 *raw 임의 그림자*만 금지** —
  DS `Shadows/shadow-basic` 카드 elevation 은 이 표준이 적용한다(strip 뒤에 재바인딩). 테스트 `test_card_shadow.py`.
- 🔴 **effect style 키 추출:** 작업 파일은 DS 를 라이브러리로 *참조*만 해 `getLocalEffectStylesAsync()` 가
  0건 → 키 없음. DS 파일(Imin Design System)에 plugin 연결 후 `python3 scripts/figma_mcp_client.py
  sync-effect-styles` 1회 실행 → `ds/EFFECT_STYLE_MAP.json` 생성·커밋(TEXT_STYLE_MAP·VARIABLE_KEY_MAP 과 동일 패턴).

### 2-B-2. ⚠️ 브랜드 틴트 '면' = bg-brand-primary — 🔻 2026-06-12 advisory 강등 (명시 fill 존중, live 교정 no-op)
- 사용자 명시: *"이런건 컬러를 `bg-brand-primary` 를 사용게 시각적으로 맞아."* (강조된 '오늘'
  스케줄 블록 등 브랜드 틴트 면을 가리키며)
- **브랜드 틴트를 '면'(자식을 담는 블록/카드 표면)으로 쓸 때는 `$token(bg-brand-primary)`(#f4ecff,
  연한 라벤더)** 를 쓴다. **`bg-brand-secondary`(#e6d4ff)·`bg-brand-secondary-hover`(#cfaeff) 는 더
  진해 면 표면에 쓰면 시각적으로 무겁다 → 면에는 금지.** secondary 계열은 작은 액센트/상태(badge·
  dot·hover 등)에만.
- 적용 예: '오늘' 입금/지급 강조 블록, '차근차근 모을게요' 같은 틴트 카드 표면 → 모두 bg-brand-primary.
- **시스템 강제 (자동, 2중):**
  1. `_enforce_brand_tint_surface_primary(blueprint)` (cmd_build pre-process, no-large-brand-fill 직후) —
     **children 을 가진 frame** 의 fill 이 `$token(bg-brand-secondary[-hover])`/`bg-brand-primary_alt`
     면 `$token(bg-brand-primary)` 로 교정.
  2. `_enforce_brand_tint_surface_primary_live(root_id)` (cmd_post_fix, white-card-border *직전*) —
     라이브 트리에서 children 가진 FRAME 의 fill 이 #e6d4ff/#cfaeff 면 #f4ecff(bg-brand-primary)로
     교정 + 토큰 바인딩. DS 인스턴스·내부(`;`) 노드 제외.
- **빌드 후 검증:** 빌드 로그에 `[규칙] 브랜드 틴트 면 N건 → bg-brand-primary` 또는
  `[brand-tint-surface-live] ✓` 라인 확인. 틴트 블록/카드가 진한 보라(secondary)가 아니라 연한
  라벤더(primary)인지 스크린샷 확인.

### 2-C. ⚠️ 타이포 위계 — 크기·굵기로 시각 리듬 (2026-05-23 룰 / 2026-06-12 DS 스케일 정합)
- 🔴 **fontSize 는 반드시 DS 텍스트 스타일 스케일 값만 쓴다: `12 / 14 / 16 / 20 / 24 / 32 / 40 / 48`**
  (2026-06-12 회귀 교정 — 이전 가이드의 17~19/22~26/28~36 같은 off-scale 값은 DS 에 스타일이
  없어 **텍스트 스타일 바인딩이 불가능**했다. 타이틀 3개가 전부 미바인딩된 뿌리.)
- **컬러가 절제될수록 시각 위계는 폰트 크기·굵기로 강화한다.** 표준 type scale:
  - **HERO** (카드 안 핵심 금액·수치) — `24px Bold` (DS `Heading xs`) 또는 `32px Bold` (DS `Heading sm`)
  - **TITLE** (화면 타이틀) — `24px Bold` (DS `Heading xs`)
  - **SECTION** (섹션 헤더) — `16px Bold` (DS `Body md/Bold`) ~ `20px Bold` (DS `Body xl/Bold`)
    — 사용자 수정 사례(2026-06-12)는 섹션 타이틀 16 Bold 선호
  - **BODY (기본)** — `16px Medium/SemiBold` (DS `Body md`) ← 🔴 **기본 텍스트는 16**
  - **보조 (라벨·캡션·부제)** — `14px` (DS **`Body sm`**) ← 🔴 **간혹 쓰는 보조 크기**
  - **미세 (푸터·법적 고지·정말 작아야 하는 fine print)** — `12px` (DS `Body xs`) ← 🔴 **정말 작게 표현해야 할 때만**
- **시스템 강제 (2026-06-12):** `_apply_ds_text_styles` 의 snap 스케일은 하드코딩이 아니라
  `ds/TEXT_STYLE_MAP.json` 의 **실제 사이즈 집합에서 derive** (`_ds_text_size_scale`). ±3px 안
  스타일이 없으면 **`[text-style] ⚠️ DS 스타일 미매칭` WARN** 으로 노드 이름·크기를 출력한다 —
  빌드 로그에 이 라인이 보이면 blueprint fontSize 를 위 스케일로 수정할 것.
- 🔴 **보조 텍스트는 DS `Body sm`(14) 스타일 (2026-06-05 사용자 룰):** 현황 라벨("총 스테이지 수
  86,696개"), 안내/재참여 문구("함께 모은 목돈, 다시 모아볼까요?"), 한도 디테일("한도 … 이용 중
  잔여 …"), 리스트 부제("출석 체크하고 포인트 받아요") 같은 보조 텍스트는 **`Body sm`(14px)** 이
  적절하다. (기본 본문=`Body md` 16, 미세=`Body xs` 12.)
- 🔴 **타이틀 아래 디스크립션 텍스트는 `Body sm`(14) ~ `Body xs`(12) (2026-06-05 사용자 룰):**
  사용자 명시 *"타이틀 아래 디스크립션 텍스트들은 sm, xs 정도로 쓰면 된다."* 섹션/카드 타이틀 바로
  아래 부제·설명("목돈을 이만큼 모았어요", "매월 얼마나 모을까요?", "어떤 방법으로 시작할까요?",
  리스트 부제 등)은 **16(Body md)으로 키우지 말고 `Body sm`(14) 또는 `Body xs`(12)** 로 둔다.
  타이틀(16~18)보다 작아야 위계가 산다 — 디스크립션을 16으로 올리면 타이틀과 동급이 돼 단조로움.
  - ⚠️ `ds/TEXT_STYLE_MAP.json` 이 stale 하면 Pretendard `Body sm`(14) 키가 빠져 있어(파일의 옛
    'Text sm' 키가 라이브 DS 에선 `Body xs`/12 로 import 됨) **Body sm 을 바인딩할 수 없다** →
    플러그인을 DS 파일('Imin Design System')에 연결 후 `sync-text-styles` 로 재추출해야 Body sm
    키가 맵에 들어온다(절대 규칙 0-S 참조). 재싱크 후엔 enforcer 의 (14,bucket) 조회가 Body sm 을
    바인딩한다.
- 같은 카드 안에 **최소 3단계 이상 차이**를 둔다 — HERO 금액은 본문(BODY)의 2배 안팎이어야 리듬이 산다.
- 🔴 **크기 하한 정책 (2026-06-05 사용자 룰): 기본 16 / 보조 14 / 12 는 정말 작은 경우(푸터·미세 문구)만.**
  사용자: *"기본이 16이고 아래 14를 간혹 쓰고 12는 정말 작게 표현해야 되는 경우일때만. 12pt 텍스트가
  너무 많이 쓰이고 있어."* → **일반 텍스트에 12pt 남용 금지.** 12/13pt 라벨은 14 로 올린다. 11/10pt 는
  쓰지 않는다(푸터 fine print 도 최소 12).
- **시스템 강제 (자동, 2중):**
  1. `_enforce_min_text_size(blueprint)` (cmd_build pre-process, font weight 정규화 직후) — 일반 텍스트
     fontSize < 14 → 14, 푸터(조상 이름 'footer') 안 미세 문구 < 12 → 12 로 상향. 장식 기호(●/>/−/+ 등
     단일문자·비문자)·제목·hero 는 제외. text-style 매핑 *전* 에 올려 올바른 DS 스타일 버킷이 선택됨.
  2. `_enforce_min_text_size_live(root_id)` (cmd_post_fix, 브랜드 틴트 면 직전) — 라이브 백스톱.
     get_nodes_info(batch)는 styled 텍스트 fontSize 를 None 으로 주므로 **TEXT 노드별 get_node_info 로
     실제 fontSize 를 읽어** 하한 미만이면 `set_font_size` 로 상향. DS 인스턴스 내부(';') 제외.
- ⛔ **2026-06-18 폐기:** 구 `_enforce_text_hierarchy`(카드 안 통화 hero 금액을 30px Bold 로 *자동 승격*)는 삭제(no-op). 타이포 위계는 이제 **전적으로 작성자(blueprint fontSize)가 결정** — 와이어를 창의적으로 변형(크기·위계 자유)하는 것과 충돌해 사용자 결정으로 제거. hero 수치를 크게 쓰고 싶으면 blueprint 에서 직접 DS 스케일(24/32/40/48 등)로 명시한다. (DS 스케일 준수=2-C·접근성 하한=min-text-size 만 정합성 차원에서 유지.)

### 2-D. ⚠️ Modal 화면 패턴 — 상단 X만, Footer·Tab Bar·상단 탭 없음 (2026-05-24 룰)
- **Full modal** (홈 위로 슬라이드업되는 단일 화면, 예: 거래 스케줄 상세) 은:
  - **상단 헤더 = X(닫기) 버튼만** — 로고·알림·채팅·검색 등 nav 아이콘 없음. X 는 우측 상단(NavBar `primaryAxisAlignItems: MAX`).
  - **Footer 없음 · Tab Bar 없음 · 상단 Tab 메뉴(거래현황/누적거래 등) 없음** — 모달은 단일 컨텍스트.
  - 루트 높이는 콘텐츠에 HUG (불필요한 빈 공간 금지).
- Blueprint root 에 `"_screenType": "modal"` 명시 → `cmd_build`의 `_enforce_modal_pattern` 이 자동 강제: Footer / Tab Bar / 상단 탭(`Tab Row`/`Top Tab`/`Section Tab` 포함) / non-X nav 아이콘(`Logo`/`bell`/`chat` 등) 을 빌드 전에 제거하고 NavBar 를 우측 정렬한다.
- 🔴 **모달은 unified imin_home 베이스를 쓰지 말 것 — 와이어에 있는 것만 처음부터 custom blueprint 로.** 홈 대시보드 섹션(Screen Hero/Top Alert/Recommend/Lounge/Attendance/Mode Tabs/Tab Bar/FAB/Footer)을 끌어오면 **R58 (`design_rules/R58_modal_no_home_sections.py`) 가 build 를 차단**한다 (2026-05-28 사용자 분노). 와이어에 진짜 있는 드문 경우만 `_modalAllowSections:[...]` 로 허용.
- 🔴 **루트 높이 = HUG 필수** — 모달 root 가 FIXED(852)면 하단 CTA 가 잘린다. `layoutSizingVertical: "HUG"` 로 콘텐츠 전체 + CTA 가 보이게.
- 모달이 아닌 일반 화면은 기존대로 (NavBar 풀세트 + Tab Bar + Footer).

### 2-G. ⚠️ 하단 CTA = DS Button 컴포넌트 인스턴스 우선 (2026-05-24 룰)
- **하단 CTA 버튼(Bottom Action Bar 의 Primary CTA / Submit Button / 참여하기 등) 은 무조건 DS `Action Button` 컴포넌트 인스턴스로 만든다.** raw frame 으로 그리지 말 것.
- DS Button 으로 표현이 안 되는 특수 케이스(이중 버튼, 그라데이션 CTA 등)에 한해 직접 그릴 수 있음 — 그 외는 항상 instance.
- **사용할 키 (scripts/design_rules/ds_catalog.py):**
  - `Action Button md Primary` (`ed0032bcf28f03da97e4b3006f54d30a0fbe5914`) — 기본 CTA
  - `Action Button md Secondary` / `Tertiary` / `Outline` / `Ghost` — 위계별
  - `Action Button sm` (`a8a4d7eb7874c469ab89105cc342fad85a3d28ce`) — 보조 CTA
- **🔴 사이즈 — 기본 화면의 하단 고정/보이는 CTA 버튼은 `Size: 2xl` 이 기본 (2026-08-04 사용자 룰 — 2026-05-28 'lg 기본' 개정. "버튼 사이즈가 너무 작다. 기본 화면들에서 cta버튼의 크기는 2xl").** 비활성은 `State: Disabled`.
  - **코드 강제:** blueprint 의 `properties:{Size:2xl}` 는 빌드 때 무시되므로, `_enforce_ds_button_sizing` (post-fix) 가 **VERTICAL 부모의 전폭 CTA 의 Size variant 를 2xl 로 자동 강제** → `set_instance_properties`. 매 빌드 자동 적용.
- **라벨:** Action Button 라벨은 nested TEXT("Button CTA") 라 `properties.label` 로 **안 바뀐다**. `set_text_content` 또는 inject 의 `_instanceText` / label_map 로 override. ⚠️ Size 등 **variant 변경 후엔 라벨 재확인** (variant swap 이 override 를 리셋할 수 있음).
- **시스템 강제 (기존):** R23 inject 의 `detect_button_shape` 가 raw button frame 을 자동 swap. catalog 미스 시 build ERROR.
- Blueprint 작성 시: `{"type":"instance","componentKey":"ed0032bcf28f03da97e4b3006f54d30a0fbe5914","_instanceText":"참여하기","properties":{"Size":"lg","State":"Disabled"}}` 패턴.
- 🔴 **instanceProperties(variant flip) 자동 적용 — 수동 flip 영구 제거 (2026-06-04):**
  `batch_build_screen` 의 `create_component_instance` 는 blueprint 의 `instanceProperties`/
  `_instanceVariants`(Hierarchy=Primary, Color=Warning, Size=lg 등)를 **적용하지 않는다**(인스턴스만 생성).
  그래서 'Action Button md Secondary' 키로 import 후 Hierarchy=Primary 로 flip 하려던 CTA 가
  매 빌드 Secondary(연보라)로 남아 **매번 수동 flip** 하던 회귀가 있었다. → `_collect_instance_variant_paths`
  + `_enforce_ds_instance_variants`(post-fix, ds-button-sizing **직전** 실행)가 경로 매칭으로
  `set_instance_properties` 자동 적용. blueprint 인스턴스에 `"instanceProperties":{"Hierarchy":"Primary",...}`
  박으면 빌드 후 자동 flip(로그 `[ds-instance-variant] ✓`). [[ds-action-button-primary-key-broken]] 우회 자동화.

> 🔴 **2-G-2. ⚠️ 하단 액션바 버튼 높이 통일 — 제일 큰 것에 맞춤 (2026-06-02 사용자 룰)**
>
> 사용자 명시: *"버튼의 높이가 왜 다르지? 제일 큰거와 같아야 되. 이건 수정하고 규칙 강화하고 코드에 박아."*
>
> **하단 액션바(Bottom Action Bar / Action Bar / CTA Bar) 안의 모든 버튼·아이콘 박스는 높이가
> 같아야 한다 — 그 중 제일 큰 것의 높이로 통일.** (북마크·채팅 아이콘 박스가 DS CTA 버튼보다
> 낮게 찌부러지는 회귀 차단.)
>
> **회귀 원인:** 아이콘 박스(VERTICAL HUG)는 콘텐츠 높이(아이콘 ~22 / 아이콘+라벨 ~37)로
> 붕괴하는데 옆 DS CTA 버튼은 ~44~56 라 높이 제각각.
>
> **시스템 강제 (코드 박힘, 자동):** `_enforce_action_bar_equal_height(root_id)` (cmd_post_fix,
> **size-invariant 이후**에 실행해 최종 권한 — size-invariant 의 icon-box 정사각화가 한쪽만
> 키우는 충돌 방지). 액션바 직계 버튼/박스 중 최대 높이 H 계산 → 낮은 것들을 vertical FIXED +
> height=H 로 통일. ⚠️ Bottom **Tab Bar** 는 `_enforce_tab_bar_children_fill_live` 가 따로 처리(제외).
>
> 🔴 **함정 (2026-06-04 회귀): `resize_node` 는 폭·높이 둘 다 FIXED 로 박는다.** height 통일
> 하려고 전폭 CTA 버튼에 `resize_node` 를 호출하면 **가로 FILL 이 깨져 폭이 고정 → "참여하기"
> 라벨이 잘린다**(이미지에 "참"만 보임). 그래서 이 룰은 CTA(액션바 최대폭 자식 / INSTANCE /
> 이름에 btn·button·cta·submit·참여)에 대해선 height 조정 후 **무조건 `horizontal=FILL` 재단언**
> 한다. ⚠️ '원래 가로 모드 보존' 방식은 NG — 직전 패스에서 이미 FIXED 가 된 버튼의 FIXED 를
> 그대로 보존하는 버그가 있었다. 전폭 CTA 는 항상 FILL 로 강제.
>
> 🔴 **target = CTA 버튼 높이 기준 (2026-06-04 재정의):** 처음엔 'max 높이'를 target 으로
> 썼는데, size-invariant 가 아이콘 박스(단일자식)를 정사각(56)으로 키우면 박스(56) > CTA(44) 가
> 되어 역전 → 사용자 원래 의도("작은 아이콘 박스를 **CTA 높이에 맞춰라**")와 어긋났다. 이제
> **target = CTA 높이**, 아이콘 박스가 거기 맞추고 **CTA 자신은 높이 안 건드림**(DS 버튼은
> 억지로 키우면 안 붙음). CTA 없으면 max 폴백.

> 🔴 **2-G-3. ⚠️ 상단 NavBar 우측 액션 = 아이콘 버튼 (텍스트는 특수 케이스만, 2026-06-04 사용자 룰)**
>
> 사용자 명시: *"상단 네비게이션바 우측에 일반적으로 아이콘 버튼이 위치하는데 지금처럼 텍스트
> 버튼이 들어가면 안되. 아주 특수한 경우에만 텍스트 버튼을 사용할거야."*
>
> NavBar 우측의 액션 라벨(공유/완료/편집/저장/닫기/취소/다음/더보기/검색/알림 등)은 **텍스트가
> 아니라 아이콘 버튼**. **아주 특수한 경우**만 텍스트 — 매핑에 없는 라벨이거나 노드에
> `"_navTextAllowed": true` 마커가 있으면 텍스트 유지.
>
> **시스템 강제 (코드 박힘):** `scripts/design_rules/R62_navbar_icon_action.py`
> - L2 lint: NavBar 안 액션 라벨 TEXT 발견 시 WARN.
> - L3 inject: 알려진 액션 라벨(`_ACTION_ICON` 맵: 공유→share-07, 완료/저장→check, 편집→edit-02,
>   닫기/취소→x-close, 다음→arrow-right, 더보기→dots-vertical, 검색→search-lg …)에 **정확히 일치**
>   하는 TEXT 를 ICON 노드로 교체 → build 가 svg_icon 생성. **제목(매핑에 없음)은 안전하게 유지.**
> - L5 verify: 빌드 후에도 액션 라벨 텍스트가 남으면 WARN.
> - blueprint 작성 시 NavBar 우측에 "공유" 같은 액션은 처음부터 `{"type":"icon","iconName":"share-07"}`
>   로 써도 되고, 텍스트로 써도 R62 가 자동 교체한다. 새 액션 라벨은 `_ACTION_ICON` 맵에 추가.

> 🔴 **2-G-4. ⚠️ 연속된 전폭 CTA 는 위계 차등 — 덜 중요한 것은 Outline/Tertiary (2026-06-05 사용자 룰)**
>
> 사용자 명시: *"CTA 버튼이 위 아래 연속적으로 있을땐 좀 더 덜 중요한 버튼의 위계를 tertiary 나
> outline 으로 설정하도록 규칙 추가하고 코드에 박아."*
>
> 세로로 인접한 전폭 DS Action Button **Primary** 인스턴스가 2개 이상이면 한 화면에 같은 강조색
> CTA 가 위계 없이 경쟁한다(예: 월렛 "목돈 출금하기" 바로 아래 납입 "지금 납입하기" 둘 다 보라).
> → **화면 맥락상 더 중요한 액션 1개만 Primary 로 두고 나머지를 `Outline`(실패 시 Tertiary→
> Secondary 폴백)으로 자동 다운그레이드**한다.
>
> 🔴 **어느 게 더 중요한가 = 맥락 판단 (2026-06-05 사용자: "화면상에서 맥락을 고려해 더 중요한
> 액션은 primary 로"):** 코드가 의미를 완벽히 알 순 없으므로 **3단 우선순위**로 keeper(=Primary
> 유지) 를 정한다:
> 1. **blueprint `_ctaKeepPrimary: true` 마커 (최우선·원칙)** — 🔴 Claude 가 blueprint 작성 시
>    화면 맥락(어느 액션이 더 긴급·의무·핵심인가)을 판단해 더 중요한 CTA 에 직접 박는다. 예:
>    D-1 납입(의무·놓치면 미납/i-CSS 하락) > 월렛 출금(선택) → 납입에 마커.
> 2. **라벨 의미 휴리스틱** — 마커 없으면 라벨로 추론: '주 액션' 동사(납입/결제/제출/참여/신청/
>    확인/시작/완료/동의/송금/주문/가입…)가 '보조'(출금/취소/나중에/더보기/공유/저장/닫기…)보다
>    우선. 그룹 일부만 주 액션이면 그것을 Primary 유지.
> 3. **맨 아래 폴백** — 둘 다 판단 불가(모두 주 액션 / 모두 중립)일 때만 맨 아래(엄지 영역) 유지.
>
> **시스템 강제 (코드 박힘, 자동):** `figma_mcp_client._enforce_consecutive_cta_hierarchy(root_id, bp)`
> — cmd_post_fix chain 의 **multicol-fill *뒤*** 에 실행(button-sizing 직후엔 set_layout_sizing(FILL)
> 리렌더 전이라 전폭 width 가 stale → 못 잡음. 모든 width/sizing 강제가 끝난 뒤라야 신뢰성 있음).
> 전폭 = absoluteBoundingBox width ≥ 250. '연속' = 두 전폭 Primary CTA 사이 세로 간격 < 320px
> (카드 1개 경계 정도). 멀리 떨어진(스크롤상 다른 맥락) CTA·캐로셀 카드 안 CTA(폭 < 250) 는 제외.
> 라벨은 인스턴스의 `Label#…` prop 에서 읽는다.
>
> **빌드 후 검증:** 빌드 로그에 `[cta-hierarchy] '<name>' Primary → Outline` 라인이 보이면 자동
> 적용 성공. 스크린샷에서 **맥락상 더 중요한 CTA 가 채움(Primary), 덜 중요한 것이 테두리(Outline)**
> 인지 확인. 🔴 **새 화면 작성 시 연속 전폭 CTA 가 생기면 Claude 가 반드시 더 중요한 쪽에
> `_ctaKeepPrimary` 를 명시**한다(휴리스틱·맨아래 폴백에 의존하지 말 것).

> 🔴 **2-G-5. ⚠️ 수평 연속 동일 성격 CTA = Tertiary (FAB 있는 화면, 2026-06-05 사용자 룰)**
>
> 사용자 명시: *"fab 버튼도 있는 화면에서 수평으로 연속된 버튼 같은 경우는 성격까지 같다면
> 버튼 위계를 tertiary 로 설정되게 규칙 추가하고 코드에 박아."*
>
> 캐로셀 등에서 **가로로 나열된 DS Action Button 이 2개 이상 + 라벨(성격)이 동일**하면(예:
> 추천 카드 2장의 "참여하기" × 2) 위계 경쟁이 무의미하고, FAB(brand 주 액션)가 이미 화면의
> brand 강조점이라 **brand 과다**가 된다 → 그 CTA 들을 전부 **Tertiary**(폴백 Outline→Secondary)로
> 자동 다운그레이드한다. **FAB 가 있는 화면에만** 적용(brand 강조점이 이미 있다는 전제).
>
> **세로 규칙(2-G-4)과 구분:** 2-G-4 는 전폭(width≥250) 세로 연속 CTA 의 위계 차등(주 액션 1개만
> Primary). 2-G-5 는 캐로셀 카드 안 **수평 반복 동일 라벨** CTA(폭<250 라 2-G-4 대상 아님)를 전부
> Tertiary. 두 규칙은 대상이 갈려 충돌 없음.
>
> **시스템 강제 (코드 박힘, 자동):** `figma_mcp_client._enforce_horizontal_repeated_cta_tertiary(root_id)`
> — cmd_post_fix chain 의 `_enforce_consecutive_cta_hierarchy`(세로) 직후. 같은 라벨(`Label#` prop)
> CTA 들의 top 편차 < 40px(같은 행) + x 가 서로 다름 → 수평 반복으로 보고 Tertiary flip. FAB(이름에
> 'fab') 없는 화면은 skip.
>
> **빌드 후 검증:** 빌드 로그 `[cta-horiz-tertiary] '<name>' (<라벨>) → Tertiary` 라인 확인.
> 스크린샷에서 캐로셀 반복 CTA 가 채움(Primary)이 아니라 약한 위계(Tertiary)이고 FAB 만 brand
> 강조점인지 확인.

### 2-I. ⚠️ 폼 컨트롤(체크박스/토글/라디오/인풋)은 DS 컴포넌트 인스턴스 — raw frame 금지 (2026-05-28 사용자 분노)
- **체크박스를 raw 원형/사각 frame + check 아이콘으로 그리지 말 것.** DS 컴포넌트 인스턴스 사용:
  - `Checkbox md` (`bbd5c20958464e51295e73c3c90ef7d54c0b0b69`, 20×20, unchecked) / `Checkbox md checked` (`73691ec35c62c70735d61722347dfd995b32c5ec`)
  - 토글/라디오/인풋/슬라이더/드롭다운도 동일 — `_VERIFIED_AUTOSWAP_ROLES` 의 DS 컴포넌트로.
- Blueprint: `{"type":"instance","componentKey":"bbd5c20958464e51295e73c3c90ef7d54c0b0b69"}` 패턴.
- R23 의 `detect_checkbox_shape` 는 현재 key UNVERIFIED → WARN only 라 자동 swap 안 됨 — **작성 시 직접 instance 로 쓸 것** (raw frame 으로 그리면 사용자 분노).
- 🔴 **텍스트 인풋 = DS 'Input field' 인스턴스 (2026-08-05 사용자 실측 패턴 — 쿠폰등록_DS 인풋을 직접 교체하며 확정):**
  - key: `074f2839b4ce11d761931642b0305f277f811563` (ds_catalog 'Input field')
  - variants: **Size=md, Type=Default, Destructive=False**, 미입력 상태는 **State=Placeholder**
  - placeholder 문구는 내부 TEXT override(`set_text_content`) · 가로 `FILL`
  - **라벨(위)과 helper text(아래 ⓘ+안내)는 인스턴스 밖 raw 로 유지** — Input field 인스턴스는 입력 박스만 담당
  - 변환(리바인딩) 작업에서도 raw 밑줄/박스형 인풋을 만나면 이 인스턴스로 교체할 것

### 2-F. ⚠️ 루트 minHeight=852 + 하단 바 bottom-pin (2026-05-24 룰)
- 루트 프레임 **min height = 852** (iPhone 16 뷰포트). 콘텐츠가 늘어나면 그에 따라 같이 늘어남.
- 콘텐츠 합이 852 보다 짧을 때, 화면에 고정된 하단 바(**Bottom Action Bar / Tab Bar / CTA Bar / FAB**) 는 **루트 하단(y = 852 - bar.height)에 bottom-align** — 콘텐츠 끝에 붙어 떠 있지 않게 한다.
- **시스템 강제:** `cmd_post_fix` 의 `_enforce_root_min_height` (scripts/figma_mcp_client.py, 2026-05-24) — 루트 높이 < 852 시 852 로 늘리고, 이름에 `tab bar`/`tabbar`/`bottom action bar`/`action bar`/`cta bar`/`fab` 포함된 자식을 ABSOLUTE + bottom constraint MAX 로 새 루트 하단에 재배치. 콘텐츠가 852 보다 길면 손대지 않음 (콘텐츠 끝이 곧 바의 위치).

### 2-E-5. ⚠️ 행 셀 그룹 세로 사이징 통일 — baseline 어긋남 차단 (2026-06-02 사용자)
- **사례**: 회차 셀렉터 "Round Cell 1~13" 중 **2자리(10~13)만 빌드가 FIXED h=36 으로 키워**(1~9 는 HUG h=23), 더 높은 셀 안 숫자가 ~6px 아래로 내려가 정렬이 틀어짐. ⚠️ **blueprint 는 13개 전부 HUG 로 올발랐다 — 빌드 단계가 일부 셀만 키운 회귀**(그래서 blueprint 만 고쳐선 못 막음 → post-fix 가드 필수).
- **시스템 강제** — `_normalize_row_cell_vertical_sizing_live(root_id)` (`cmd_post_fix` chain):
  1. HORIZONTAL parent 의 직계 FRAME 자식 중, 이름 끝 숫자를 뗀 **prefix 가 같은 셀 그룹**(예 'Round Cell')이 3개+ 인 경우 감지
  2. 그 그룹의 `layoutSizingVertical` 이 섞였거나 height 가 2px 초과로 다르면 → **다수 사이징으로 통일**(다수가 FIXED 인데 height 들쭉날쭉이면 HUG 로 — 텍스트 셀은 HUG 가 정답)
  3. idempotent — 일관되면 no-op
- **회귀 신호**: 숫자/날짜 셀 행에서 일부 셀(보통 2자리)의 텍스트만 위/아래로 어긋남, 언더라인이 두 높이로 끊김
- 🔴 **2026-06-02 원형 셀 찌부 회귀 + 근본 버그 fix (사용자 "왜 순번 블록들이 찌부되어있지?"):**
  - **증상**: 원형 순번 셀(cornerRadius 999, 32×32)이 세로 HUG 로 붕괴해 **h=14 타원(pill)** 이 됨.
    한 행에서 셀 개수 다르면(1~9 행 vs 10~13 행) 타원 폭도 달라 보임.
  - **뿌리 1 — size-invariant 가드 무력화**: `_enforce_fixed_size_invariants_final`(원형→정사각 복원
    최종 가드)이 `node.get("width")` 를 읽었는데, **`get_nodes_info` 는 width/height 를 top-level 이
    아니라 `absoluteBoundingBox` 에만 담아 반환** → 항상 `None` → 가드가 **통째로 0건** 동작.
    → `_node_wh(n)` 헬퍼 신설(absoluteBoundingBox 폴백)로 수정 → 이제 정상 복원.
  - **뿌리 2 — HUG 룰이 원형 셀까지 붕괴**: `_enforce_horizontal_row_hug_v_live`(HORIZONTAL + 자식
    전부 TEXT → HUG)가 원형 셀을 HUG 로 만듦. `_qualifies` 에 **원형(cornerRadius≥w/2) · 작은
    정사각(폭≤60, |w−h|≤8) 셀 예외** 추가 — FIXED 정사각 유지.
  - blueprint 의 round_cell 은 FIXED 32×32 로 작성하면 됨(post-fix 가드가 보장).
- 🔴 **2026-06-04 참여자 아바타 원형 붕괴(가로만 좁아짐) — size-invariant min-width 버그:**
  - **증상**: 참여자 썸네일 아바타(원형 36×36)가 가로만 FIXED→**HUG 로 붕괴해 폭=아이콘폭(16px)**,
    세로 30 그대로 → 세로로 긴 좁은 pill. (셀이 가로로 줄어든 케이스 — 위 round 셀은 세로 붕괴.)
  - **뿌리**: `_enforce_fixed_size_invariants_final._is_circle_iconbox` 가 `20 <= w` 를 요구해,
    **한 축이 16px(<20)로 붕괴한 원형을 감지 못 함** → 복원 누락. → `max(w,h)` 기준으로 범위
    체크하고 `cornerRadius>=100`(999 류) 이면 붕괴해도 원형으로 인식하도록 수정 → max(w,h) 정사각 복원.
  - **참여자/멤버 아바타는 랜덤 이미지 사용** (사용자 OK): blueprint 아바타 frame 에
    `"imageQuery":"portrait,face,person"` 박으면 `apply_image_queries` 가 loremflickr 랜덤 사진을
    `set_image_fill` + placeholder 아이콘 제거. `clipsContent:true` + cornerRadius 999 로 원형 클립.
- 🔴 **2026-06-04 얇은 pill/드래그 핸들/dot 이 거대 원으로 폭주 — size-invariant min 가드:**
  - **증상**: 바텀시트 드래그 핸들(40×4)·월 셀 dot(5×5)이 빌드 후 셀을 가득 채우는 **거대한
    원**이 됨. 핸들=40×40 원, dot=75×75 원.
  - **뿌리**: 장식 요소가 cornerRadius 999 인데 FILL enforcer 가 한 축을 늘리면(핸들→풀폭,
    dot→셀폭) `_enforce_fixed_size_invariants_final._is_circle_iconbox` 가 `max(w,h)` 정사각
    복원 대상으로 잡아 거대 원으로 만든다. → 순수 함수 `_is_circle_square_target(w,h,cr,childType)`
    에 **`min(w,h) >= 12` 가드** 추가: 얇은 pill/핸들/dot(min ≤ 5) 제외, 진짜 붕괴 원형
    아바타(min ~16)는 보존. 테스트 `scripts/tests/test_circle_square_target.py` 10케이스.
  - **blueprint 팁**: 작은 dot 인디케이터는 frame(원형) 대신 **text bullet "●"** 로 — 프레임
    enforcer 의 FILL/정사각화에 면역. 드래그 핸들은 `layoutSizingHorizontal/Vertical:"FIXED"`.

> 🔴 **2026-06-04 — `isTabBar` 가 'nav' 든 컨트롤 프레임을 하단 탭바로 오인 → 흰 fill+보더 강제:**
> `enhanceBlueprint`(figma-mcp-embedded.ts)의 `isTabBar` 가 이름에 **'nav'/'bottom'** 만 들어가도
> (자식 3~6 + 텍스트) 하단 탭바로 보고 **흰 fill(1,1,1) + top border(0.95,0.96,0.96)** 를 강제했다.
> → 'Year Nav'(연도 네비)·상단 'NavBar' 가 카드처럼 흰 박스+보더로 깨짐(사용자 분노). 절대규칙
> 0-O(상단 NavBar 룰)와 **다른 별개 버그**. 수정: `isTabLike` 를 하단 탭바 전용 표현만 매칭
> (`tab`/`탭`/`bottom nav`/`bottom tab`/`하단`)으로 좁힘 — 바 `nav`/`bottom` 제외. ⚠️ TS 변경이라
> `npm run build` + 브리지 재시작 후 적용. 컨트롤/네비 행은 의도치 않은 fill/stroke 를 받지 않는다.

### 2-E-4. ⚠️ Bottom Tab Bar 자식 FILL + 라벨 wrap 차단 (2026-05-28 사용자 분노)
- **사례**: Bottom Tab Bar 5개 자식 (Tab 홈/커뮤니티/스테이지/라운지/나) 이 HUG horizontal 로 박혀, tab-label TEXT 가 width=24 (아이콘 width 따라가서) 좁아져 "커뮤/니티", "스테/이지", "라운/지" 같이 두 줄 wrap. R13.3 inject 후에도 회귀 가능.
- **시스템 강제** — `_enforce_tab_bar_children_fill_live(root_id)` (`cmd_post_fix` chain):
  1. 이름에 'tab bar' / 'tabbar' / 'bottom tab' / 'bottom nav' 포함 HORIZONTAL parent + 자식 3+ frame 감지
  2. parent → layoutMode=HORIZONTAL + primaryAxisAlignItems=MIN + counterAxisAlignItems=CENTER + itemSpacing=0
  3. 각 tab 자식 frame → layoutSizingHorizontal=FILL (5등분 균등)
  4. tab 자식 안 TEXT (tab-label) → textAutoResize=HEIGHT + textAlignHorizontal=CENTER + layoutSizingHorizontal=FILL
- **회귀 신호**: Tab Bar 라벨이 두 줄로 wrap 되거나 width 가 24px 정도로 좁아짐

### 2-E-3. ⚠️ 작은 cell (width ≤ 60) 안 TEXT — 중앙 정렬 + 모서리 잘림 차단 (2026-05-28 사용자 명시)
- **사례**: Month Cell Jan Active (44×44) 안 "Jan/1" 흰 텍스트가 좌측 정렬되어 cell 가장자리에 박힘. 다른 month cells "Oct/Nov/Dec/Feb/Mar/Apr" 도 cornerRadius=20(원형) + 텍스트 width=cell width 가득 → 좌우 둥근 모서리에 의해 "Jct/Vov/Jec" 처럼 잘림.
- **룰 (3단)**:
  1. **작은 cell 안 TEXT 는 textAlignHorizontal/Vertical=CENTER 강제** — width ≤ 60 frame 안 TEXT 자식은 무조건 중앙. blueprint 에 명시 안 했어도 post-fix 가 강제
  2. **작은 cell 의 cornerRadius 가 width/3 이상 + 텍스트 가득 시 cornerRadius 축소** — 원형 cell 안 텍스트 가득은 좌우 잘림 → cornerRadius = max(8, width/5) (rounded square 로 변경)
  3. **3-col label/value grid (Summary Grid 등) — 균등 분포 + 컬럼 안 텍스트 중앙 정렬 강제** — HORIZONTAL parent 안 라벨/값 VERTICAL stack col ≥ 2 패턴 감지 시: parent layoutMode=HORIZONTAL + primaryAxisAlignItems=MIN + counterAxisAlignItems=CENTER, 각 col → FILL horizontal + VERTICAL + counterAxisAlignItems=CENTER, col 안 TEXT 자식 textAlign=CENTER. 컬럼이 카드 width 균등 분배 + 텍스트 컬럼 중앙
- **시스템 강제 (cmd_post_fix 자동)**:
  - `_center_text_in_small_cells_live(root_id)` — 작은 cell 안 TEXT 중앙 정렬
  - `_fix_text_clip_in_small_round_cells(root_id)` — 원형 cell 잘림 차단
  - `_fix_space_between_col_baseline(root_id)` — SPACE_BETWEEN col baseline MIN 통일
- **회귀 신호**: cell 안 텍스트가 좌측·우측에 박혀있음, 셀 모서리에서 글자가 잘림, 3-col grid 라벨이 다른 y 위치

### 2-E-2. ⚠️ Rounded card (cornerRadius ≥ 8) 는 clipsContent=true 유지 (2026-05-28 사용자 명시)
- **R45 가 모든 비-carousel frame 의 clipsContent=false 를 강제하던 부작용**: 라운지 카드처럼 cornerRadius=16인 카드 안 image/색 영역(예: 보라 Lounge Image 120px)이 카드 라운드 모서리 밖으로 튀어나와 **상단이 각져 보이는 버그**.
- **룰**: `cornerRadius ≥ 8` (또는 individual `top*Radius` 중 하나라도 ≥ 8) frame 은 `clipsContent=true` 유지. R45 의 clip-false 강제 대상에서 제외.
- **시스템 강제 (2단)**:
  1. `_disable_section_clipping` (R45) 의 `is_rounded_card()` 가드 — cornerRadius ≥ 8 frame skip
  2. `_enforce_rounded_card_clip_live(root_id)` 가 R45 직후 chain — rounded card 의 clipsContent=true 강제 (generator/manual fix 가 false 박아도 복구)
- shadow 는 어차피 `_strip_all_drop_shadows` 가 다 제거하므로 R42(shadow clearance)와 충돌 없음.
- 회귀 신호: 카드 안 보라/이미지 영역의 **상단** 모서리가 직각으로 보임 (카드 모서리는 둥근데 내부만 각짐).

### 2-E. ⛔ Section Divider 자동 삽입 폐기 (2026-05-27 사용자 명시)
- **"frame에 border를 추가하라니깐 엉뚱하게 섹션 사이에 선을 넣고있냐!!!"** — 섹션 사이에 1px divider 라인 자동 삽입 금지. 이전(2026-05-24) 룰 폐기.
- 정보 그룹 경계는 **카드 자체의 border** 로 표현한다 — `_enforce_white_card_border`(fill=`bg-primary` frame 에 `border-secondary` 1px 자동) + 카드별 stroke 토큰 바인딩이 담당.
- **시스템 강제:** `_enforce_section_dividers` 는 폐기 (no-op + 입력 divider 노드 자동 제거). `cmd_post_fix` 끝에 `_strip_section_dividers` 가 빌드 트리의 모든 "Section Divider" 노드 자동 삭제 — 회귀 차단.
- Blueprint 에 명시적으로 "Section Divider" 노드 작성하지 말 것. drop-shadow 도 함께 금지 ([[feedback_no_drop_shadow]] 참조).

### 3. Tab Bar 아이템은 반드시 FILL 균등 분배
- Tab Bar 내 모든 아이템: `layoutSizingHorizontal: "FILL"`, `layoutSizingVertical: "FILL"`
- HUG/FIXED 혼용 금지 — 아이템 간격이 불균등해짐
- 빌드 후 반드시 Tab Bar 아이템 사이징 검증할 것

### 5-B. ⚠️ 상단 모드 탭 = underline tabs (🔴 2026-06-12 Segmented_control 에서 전환)
- 🔴 **2026-06-12 개편 (절대 규칙 0-J/0-V):** 상단 모드 탭(거래현황/누적거래, 추천/전체 등 콘텐츠
  전환 탭)도 **underline tabs 가 기본** — Segmented_control(알약 토글)이 아니다. `_segLabels`(non-forced)
  로 작성돼도 R60 `_inject` 가 빌드 직전 **underline tabs styled frame 으로 자동 변환**한다.
- 🔴 **DS v7 "Horizontal tabs"(129dd87…/dda7a104…) 폐기**(모바일 드롭다운 붕괴)는 그대로 유효.
- **Segmented_control 은 컴팩트 on/off 토글에만** (`_forceSegmented:true`). 키: Style=hug
  `47a01673a46dc3bc9bfd62948c10e5fa9f2e5e78` / Style=fill `2ee9d12d4c904650ab496b9bcdf874a648e73ceb`
  (set `143ee3e3…` import 불가). `_configure_segmented_control` 가 prop(Show Segment/Label#/Active) 자동 설정.
- **생성기**: `unified_blueprint.py _gen_mode_tabs` 가 `_segLabels` 로 emit 해도 R60 이 underline 으로 변환.
- 회귀 신호: 상단 모드 탭이 **알약(pill) Segmented** 로 보임(밑줄 tabs 가 아님) / "전체/전체" / DS v7 키.
  상세 → 메모리 [[segmented-control-prop-labels]], [[tabs-underline-default]].

### 6. Underline Tab Active/Inactive 높이 일치 + Individual Stroke
- Underline 스타일 탭에서 Active에는 Underline Bar(2px)가 있어 Inactive보다 높아짐
- **Tab Inactive는 `layoutSizingVertical: "FILL"`** 설정 — Tab Row(HORIZONTAL) 내에서 Active 높이에 맞춰 자동 확장
- 텍스트 세로 정렬이 틀어지면 안 됨 — 빌드 후 높이 일치 검증 필수
- **Tab Row 스트로크는 individual stroke: bottom only** — 4면 전체가 아닌 하단만 1px 보더
  - `set_stroke_color(nodeId, r, g, b, a, strokeWeight=1, strokeTopWeight=0, strokeBottomWeight=1, strokeLeftWeight=0, strokeRightWeight=0)`
  - `strokeAlign: "INSIDE"` 권장

### 7. Tab Bar 아이템 — vertical FILL + 텍스트 CENTER 정렬
- Tab Bar 내 모든 아이템: `layoutSizingVertical: "FILL"` (아이콘+텍스트 세로 정렬 일치)
- 모든 Tab Label 텍스트: `textAlignHorizontal: "CENTER"`, `layoutSizingHorizontal: "FILL"`
- HUG 텍스트 + FILL 아이템 혼용 시 아이콘과 텍스트 정렬이 어긋남

### 8. ⚠️ 모든 섹션/카드/리스트는 반드시 FILL 가로 사이징 (절대 HUG 금지)
- **이 규칙은 가장 자주 위반된다. 반드시 지켜야 한다.**
- Blueprint에서 모든 `FRAME` 타입 자식 노드에 `"layoutSizingHorizontal": "FILL"` 명시
- 특히 **섹션 프레임, 카드 프레임, 리스트 아이템 프레임** — HUG로 두면 가로 너비가 텍스트 길이에 따라 들쭉날쭉
- 텍스트 노드(`type: "text"`)만 HUG 가능 — FRAME은 HUG 금지
- **빌드 후 검증**: `get_node_info`로 모든 섹션/카드의 `layoutSizingHorizontal` 확인, HUG인 것 발견 시 즉시 FILL로 수정
- **Blueprint JSON 규칙**: root 직계 자식과 그 자식들은 모두 `layoutSizingHorizontal: "FILL"` 필수 (아이콘 등 고정 크기 요소 제외)

> 🔵 **8-B. `_keepSizing` 마커 — author 가 의도한 HUG/FIXED 를 FILL enforcer 로부터 보호 (2026-06-10, intent 존중)**
>
> FILL 강제·vertical-hug 등 post-fix enforcer 가 author 가 *명시한* HUG/FIXED 를 망치는 회귀가 있다
> (예: SPACE_BETWEEN 행의 우측 칩이 HUG→FILL 로 늘어나 좌우가 붙음 / FIXED 정사각 원이 가로 FILL 로
> 타원). **그 사이징이 의도적이면 노드에 `"_keepSizing": true`** 를 박는다 — 빌드 후 **E.7.7(모든
> enforcer 뒤)** 에서 `_enforce_keep_sizing_live` 가 선언한 `layoutSizingHorizontal/Vertical`(+ 양축
> FIXED 면 width/height 정확 치수)을 **최종 재단언**해 author 의도가 마지막 권한을 갖는다.
> - 사용 예: `fr("Giver Info", layoutSizingHorizontal="HUG", _keepSizing=True, …)` (SPACE_BETWEEN 우측 칩),
>   `fr("One Circle", width=220, height=220, layoutSizingHorizontal="FIXED", layoutSizingVertical="FIXED", _keepSizing=True, …)` (정원 보호).
> - ⚠️ 남용 금지 — 섹션/카드/리스트는 여전히 FILL(규칙 8)이 기본. `_keepSizing` 은 **HUG/FIXED 가 정답인
>   소수 노드**(우측 정렬 칩·고정 정사각·아이콘 박스 등)에만.
> - 강제: `_collect_keep_sizing(bp)` + `_enforce_keep_sizing_live(root, map)` (Step E.7.7). DS INSTANCE
>   내부(`;`)는 제외(규칙 0-K). 테스트 `scripts/tests/test_keep_sizing.py`.

### 9. ⚠️ Tab Bar와 FAB — 루트 프레임 하단에 배치 (콘텐츠 아래)
- **이 규칙도 매번 누락된다. 빌드 후 반드시 적용해야 한다.**
- **batch_build_screen은 `layoutPositioning: "ABSOLUTE"`를 적용하지 않는다** → 빌드 후 반드시 별도 `set_layout_positioning` 호출
- **배치 원칙**: Tab Bar는 **콘텐츠 하단에 밀착**(빈 흰 띠/데드밴드 금지), FAB는 **콘텐츠/Tab Bar 위로 떠서** 우측 하단에 위치한다. FAB는 floating 버튼이므로 마지막 섹션과 겹쳐도 정상이다.
- **위치 계산** (`post-fix` `_fix_layout_and_positions`가 자동 적용):
  1. 마지막 콘텐츠 요소의 bottom (y + height) = `content_bottom`
  2. Tab Bar: `y = content_bottom` (콘텐츠에 밀착 — 사이에 빈 공간 두지 말 것), `x = 0`
  3. **FAB (2026-05-27 사용자 룰)**: icon-only 56×56 원형
     - `x = root_width - 56 - 20` (우측 20px)
     - `y = (Tab Bar_y or content_bottom) - 56 - 20` (Tab Bar 위 20px gap; Tab Bar 없으면 콘텐츠 마지막 요소 위 20px gap)
  4. Root height: `Tab Bar_y + 73`
- ⚠️ **데드밴드 금지**: 예전엔 `FAB y = content_bottom + 24`, `Tab Bar y = FAB_y + 60`으로 둬서 콘텐츠와 Tab Bar 사이에 ~76px 빈 흰 띠가 생겼다 — 이제 Tab Bar가 콘텐츠에 밀착하고 FAB가 그 위로 뜬다.
- Tab Bar: `set_layout_positioning(positioning: "ABSOLUTE")` → `move_node(x: 0, y: 계산값)`
- FAB: `set_layout_positioning(positioning: "ABSOLUTE")` → `move_node(x: 317, y: 계산값)` (393−56−20=317)
- **FAB 크기 (2026-05-27 사용자 룰)**: **icon-only 56×56 원형**, `cornerRadius: 28`. 라벨 텍스트 금지 — 아이콘만. 라벨이 필요한 케이스는 별도 pill variant 사용 (drop-down 메뉴 / 라벨 hint 등).
- **🔴 FAB 아이콘 (2026-05-27 사용자 강력 명시)**: **이모티콘 절대 사용 금지** (💰 🔍 ❤️ ⭐ 등). 반드시 DS icon component 인스턴스. DS instance 색 override 실패 시 fallback: Pretendard Bold ASCII 텍스트 ("+", "→" 등) — emoji 폰트 사용 금지.
- **🔴 FAB 아이콘 컬러 (2026-05-28 사용자 강력 명시)**: **무조건 `$token(fg-light)`** (`#ffffff`). brand-solid 보라 위 흰 아이콘이 정석. `fg-white`(alias — silent skip 위험) / `fg-primary_on-brand` / 검정 / raw RGB 모두 금지. **시스템 강제 3단:**
  1. blueprint inject: `R57_fab_icon_fg_light.py` 가 FAB 자손 icon/vector 의 `iconColor`/`fill`/`stroke`/`strokeColor` 를 자동으로 `$token(fg-light)` 교정
  2. cmd_post_fix 끝: `_enforce_fab_icon_color_live(root_id)` 가 라이브 트리 FAB 자손 VECTOR/ICON 의 `fills/0`·`strokes/0` 을 fg-light 로 강제 + 바인딩
  3. 두 곳 모두 idempotent — 새 세션 회귀 차단
- **🔴 FAB 위치 (2026-05-27 사용자 강력 명시)**: Tab Bar 또는 마지막 bottom 요소 **위 20px** + 우측 20px. Tab Bar 위치 변경 시 FAB 같이 옮겨야 함 — `python3 scripts/figma_mcp_client.py post-fix <rootId>` 재실행 시 자동 동기화.
- **FAB 컬러**: PRD에 특정 색상이 지정되어 있으면 해당 색상 사용 (config에서 fill 오버라이드). 미지정 시 브랜드 컬러 `$token(bg-brand-solid)` 사용 — FAB는 화면에서 가장 중요한 버튼이므로 브랜드 컬러가 기본
- **빌드 후 검증**: Tab Bar가 콘텐츠 하단에 밀착했는지, FAB가 우측 20px / Tab Bar 위 20px 위치에 있는지 확인

### 10. ⚠️ 히어로 배너는 반드시 가로 캐로셀 구조
- **이 규칙도 매번 VERTICAL 스택으로 잘못 생성된다.**
- 히어로 섹션(VERTICAL, paddingLeft/Right=0) 안에 **"Banner Carousel" 래퍼 프레임(HORIZONTAL)** 필수:
  ```
  Hero Section (VERTICAL, FILL, paddingTop=20, paddingLeft=0, paddingRight=0, clipsContent=true)
    └─ Banner Carousel (HORIZONTAL, clipsContent: true, FILL x FIXED 162, paddingLeft=20, itemSpacing=12)
    │   ├─ Banner Card 1 (FIXED 353×162)
    │   ├─ Banner Card 2 (FIXED 353×162)
    │   └─ Banner Card 3 (FIXED 353×162)
    └─ Indicator (HORIZONTAL, HUG)
        ├─ Dot 1 (active)
        ├─ Dot 2
        └─ Dot 3
  ```
- **Hero Section `paddingTop: 20`, `paddingLeft/Right: 0`** — 상단 패딩 20px 필수, 좌우 패딩은 Carousel의 `paddingLeft: 20`으로 대신 적용
- Banner Carousel에 **`clipsContent: true`** 필수 — `set_auto_layout`의 `clipsContent` 파라미터로 설정
- **`itemSpacing: 12`** — Banner 2가 우측에 약 8px peek 보여 스와이프 가능 힌트 제공
- **Blueprint 작성 시**: 캐로셀 래퍼 노드를 명시적으로 포함하고, `clipsContent: true` 설정
- 배너 카드는 FIXED 사이징 (FILL로 하면 캐로셀 내에서 줄어듦)
- 🔴 **인디케이터(dot)는 DS `Pagination dot group` 컴포넌트 인스턴스 (2026-06-05 사용자 룰):**
  캐로셀/배너 인디케이터는 raw bullet("●")·dot frame 으로 그리지 말고 **Imin DS `Pagination dot group`**
  인스턴스를 쓴다. 사용자 명시 *"imin DS에 Pagination dot group component가 있어서 그걸 쓰면 돼."*
  - 기본 키 (Style=Dot, Framed=False): **lg** `2ac006ab01ff82ad9b74c16d4cf6c17609a02d79` /
    md `347badbada16ce6814540e82246101d2dc65a295` (catalog `COMPONENT_KEYS["Pagination dot group"]`).
  - blueprint: `{"name":"Indicator","type":"instance","componentKey":"2ac006ab…","layoutSizingHorizontal":"HUG"}`.
  - 🔴 **인디케이터 위 gap = 아래 padding (대칭, 2026-06-05 사용자 룰):** 인디케이터가 마지막 자식인
    프레임(Hero 등)은 인디케이터 위 itemSpacing(gap)과 프레임 paddingBottom 을 **동일**하게 — 위아래
    비대칭이면 불안정해 보임(사용자 명시). 강제: `_enforce_indicator_symmetric_gap`(cmd_post_fix) 가
    Pagination 인디케이터를 마지막 자식으로 둔 VERTICAL 프레임의 paddingBottom = itemSpacing 으로 통일.
  - **시스템 강제:** 홈 생성기(`gen_*home*.py`)의 캐로셀 Indicator 를 이 인스턴스로 **직접 작성**(explicit)
    + `ds_catalog.COMPONENT_KEYS["Pagination dot group"]` 에 키 등록. 새 blueprint 작성 시 캐로셀
    인디케이터는 반드시 이 인스턴스로 쓸 것. (스케줄 dot 등 **캐로셀이 아닌** 작은 dot 은 인디케이터가
    아니므로 text bullet 유지 — 캐로셀 인디케이터만 이 컴포넌트.)

### 11. ⚠️ 카드 내 레이블/버튼 텍스트는 반드시 가시적으로
- 카드 내 텍스트가 배경색과 비슷하면 안 보임
- 텍스트 컬러: `$token(fg-primary)` 또는 `$token(fg-secondary)` 사용 (어두운 색)
- 카드 배경이 밝은 색이면 텍스트는 Bold + 어두운 색 필수
- **빌드 후 검증**: 스크린샷에서 모든 레이블/버튼 텍스트가 눈에 보이는지 확인
- 🔴 **`fg-quaternary`(#f9fafb)·`text-quaternary`(#d2d6db)는 거의 흰색** — 흰 배경 위 텍스트/아이콘에 **절대 사용 금지**(안 보임). 비활성 탭·보조 텍스트 등 "흐린 회색"이 필요하면 `fg-secondary`/`text-secondary`(#687079) 또는 `fg-tertiary`/`text-tertiary`(#b1b6be)를 쓸 것.

### 11-B. 🔴 텍스트 색 = 중요도 위계 / CTA 유도 caption은 text-secondary (2026-06-08 사용자 룰)
- 사용자 명시: *"'함께 모은 목돈, 다시 모아볼까요?' 같은 텍스트는 중요도에서 최상은 아니거든.
  그러면 컬러를 secondary 를 써야 하지 않겠어?"*
- **텍스트 색은 중요도 위계를 따른다:** `text-primary`(진한)는 **최상위 중요도**(hero 수치·핵심 타이틀)에만.
  **CTA 를 유도하는 권유·안내 문구**("다시 모아볼까요?", "지금 시작해 보세요" 등 버튼 위 caption)나
  부제·설명은 **`text-secondary`**(연한 회색). (참고: 2-C 의 크기 위계 + 본 색 위계를 함께 적용.)
- **시스템 강제 (코드 박힘):** `_enforce_cta_caption_secondary(blueprint)` (cmd_build pre-process,
  text-hierarchy 직후) — 컨테이너 자식 중 **CTA(라벨 있는 액션 버튼 instance / button 이름 frame)의
  바로 앞 형제 TEXT** 가 `fontColor=text-primary` + `fontSize ≤ 16`(hero/title 제외) + weight ≠ Bold
  (강조 의도 제외) 이면 `text-secondary` 로 교정(로그 `[규칙] CTA 유도 caption N건 → text-secondary`).
  의도적 primary 유지는 노드에 `"_keepTextColor": true` 로 opt-out. 테스트 `test_cta_caption_secondary.py`.
- **작성법:** 버튼 위 권유 문구는 처음부터 `text-secondary` 로 쓸 것(enforcer 가 백스톱).

### 12. 섹션 간 간격 — 배경색 동일 + divider 없으면 gap 0
- 인접한 섹션의 배경색이 동일(둘 다 투명/white)이고 사이에 divider가 없으면 **gap 0px** — 섹션 내부 padding이 여백 역할
- 배경색이 다르거나(컬러 → white 등) 사이에 divider가 있으면 gap 유지
- 🔴 **섹션 bg 색 경계 = 아래 섹션 상단 padding 증가 (2026-06-05 사용자 룰):** 인접 섹션의 배경색이
  다를 때(예: 그레이 밴드 → 흰 섹션) **아래 섹션의 paddingTop 을 그 섹션의 좌우 padding 값과 동일하게(대칭)** 맞춘다 — 과하게 늘리지
  말 것. 사용자 명시 *"섹션간 bg color가 다를때 아래 frame의 상단 padding값을 늘려야한다 → 상단
  padding은 좌우 패딩값과 똑같으면 된다."* **시스템 강제 (코드 박힘):** `_enforce_section_bg_gap_padding(root_id)`
  (cmd_post_fix, brand-tint 직후) — 루트 직계 섹션을 위→아래로 훑어 위 섹션과 보이는 SOLID 배경색이
  다르면: **채워진 밴드(자체 bg fill)면 상/하 padding=24(`_BAND_VPAD`=spacing-3xl)**, 빈/흰 섹션이면
  **paddingTop=paddingLeft**(대칭) 로 설정. 같은 색/무배경 경계·고정 바(NavBar/Tab Bar/Wallet)·pl=0 섹션 제외.
- 🔴 **채워진 풀폭 밴드 섹션 = 상/하 padding 24(spacing-3xl) + 토큰 바인딩 (2026-06-05 사용자 룰):**
  자체 bg fill 을 가진 풀폭 밴드(시작유도·추천 등)는 상단=좌우(20)가 아니라 **상/하 24(대칭)**. 사용자:
  *"위아래 패딩값 24로 맞추고 토큰 바인딩도 해."* 24 는 post-fix `_bind_spacing_tokens_live` 가
  **spacing-3xl 토큰으로 자동 바인딩**(절대값 아님). 위 enforcer 의 '밴드' 분기가 강제 → 재빌드에도 유지.

### 13. 섹션 강조 — 🔻 2026-06-18 색 강제 전면 삭제 (밴드 여부·색 모두 작성자 자율)
- 🔴 사용자 명시(2026-06-18): *"중요 섹션 frame fill color 를 bg-secondary 로 고정하는 건 삭제하고,
  자율적으로 판단해서 넣거나 primary 를 쓰거나 하는 걸로. 섹션 안 블록을 꼭 secondary 로 채울 필요는 없어."*
- **이전 룰(폐기):** 중요 섹션(목돈만들기·스테이지 현황·추천)을 **풀폭 bg-secondary 밴드로 강제** +
  **밴드 내부 sub-card 를 bg-primary 로 흰색화** + 미적용 시 lint. → 2026-06-18 **전부 삭제.**
- **새 규칙 (자율):**
  - **섹션을 강조할지, 어떤 색을 줄지(bg-primary / bg-secondary / brand-tint / 무fill 등)는 전적으로
    작성자가 판단**한다. bg-secondary 로 고정하지 않는다.
  - **밴드 내부 블록도 특정 색(secondary)으로 채울 필요 없다** — 내부 색도 자율. 빌드가 더 이상 내부
    sub-card 를 흰색화하지 않는다(작성자 fill 존중).
  - 강조 수단은 색 밴드 외에도 자유: 컬러 히어로 카드·타이포 위계·여백·그룹화 등. 디자인 방향(S25)에
    따라 매번 다르게.
  - 🔴 **회색(bg-secondary) 도배 지양 + bg-brand-primary 자제 (2026-06-18 사용자):**
    "여전히 secondary 쓰고 있어 너무 칙칙해졌다" + "**bg-brand-primary 는 왠만해선 안 쓰는 게 좋아**".
    → 강조를 **surface 색**으로 만들지 말 것. ① 여러 섹션을 `bg-secondary`(회색)로 도배 = 칙칙(금지).
    ② `bg-brand-primary`(라벤더 틴트) 면 = 자제(왠만하면 안 씀). **기본은 흰 면(bg-primary) + 보더로
    카드를 정의**하고, 강조는 **타이포 위계·여백·그룹화 + 브랜드 퍼플 *액센트*(텍스트·CTA·아이콘·작은
    dot)**로 만든다. 회색은 보조 영역에만 절제 사용. (2-B-2 의 brand-tint 면도 이 자제 방침을 따른다.)
- **`_band` 마커 = '풀폭 구조'만:** 노드에 `"_band": true` 를 박으면 그 섹션은 **풀폭(FILL) + 상/하·좌우
  padding fill-in**(미지정 시만)으로 표준화된다. **fill·보더·내부 색은 건드리지 않는다(자율).** 즉
  `_band` 는 "content 좌우 padding 밖으로 빼서 풀폭으로 둔다"는 *레이아웃* 마커일 뿐, 색 마커가 아니다.
  풀폭 색면을 원하면 그 노드에 `fill` 을 직접 명시한다(예 `bg-secondary`, `bg-brand-primary` 등).
- **시스템 (`_enforce_section_band`, cmd_build pre-process):** `_band` → `layoutSizingHorizontal=FILL`
  + padding fill-in 만. 색·내부 블록·보더 미관여. lint(밴드 nudge) 폐기. 로그
  `[규칙] _band 섹션 풀폭 구조 표준화 N건 (… 색·내부 블록 fill 은 author 자율 — 강제 안 함)`.
  ⚠️ 풀폭이 되려면 좌우 padding 있는 프레임 안에 두면 안 됨(content 가로 padding 0 또는 root 직계).
- **13-B (🔻 2026-06-12 기본값 강등 — 명시 gap 존중·WARN, 미지정만 20 채움). 홈 Content(섹션 스택) gap = `spacing-2xl`(20) (2026-06-08 사용자: "content gap이 32로
  spacing-4xl 로 설정되있는데, spacing-2xl 이여야 해 … 코드에 박아"):** 메인·모든 탭바 홈 화면의 섹션
  스택(`Content`/`Content Mid` 등) 프레임 itemSpacing 은 32(spacing-4xl)가 과하므로 **20(spacing-2xl)**
  로 통일한다(섹션 안 padding·밴드 상하 24 가 여백 담당, 섹션 간 gap 은 20).
  **시스템 강제 (코드 박힘):** `_enforce_home_content_gap(blueprint)` (cmd_build pre-process, section-band
  직후) — `_is_home_blueprint` 화면의 VERTICAL `Content`/`Content Mid`/`Content Top`/`Content Bottom`
  프레임 itemSpacing 을 20 으로 교정(로그 `[규칙13-B]`). post-fix 의 spacing 바인더가 20→spacing-2xl
  토큰 자동 바인딩. 의도적 다른 간격은 노드에 `"_keepContentGap": true` 로 opt-out. 테스트
  `test_section_band.py`. blueprint/생성기의 Content gap 은 20 으로 쓸 것.

### 14. ⚠️ 스테이지 카드 — 아이콘/이미지 삽입 금지
- Stage Card 안에 아이콘, 이미지를 **절대 넣지 말 것**
- Stage Card 구성: 태그(포인트/기프티콘) + 금액 텍스트 + 이율/기간 정보 + 북마크 — **이것만**
- 아이콘/이미지를 넣으면 카드가 복잡해지고 PRD 의도에서 벗어남

### 14-B. 🔴 스테퍼 그룹(기간/월 입금 등 `− 값 +`)은 세로 2-row 스택 (2026-06-08 사용자 룰)
- 사용자 명시: *"회차와 금액을 1 row에 넣었는데 2 row로 하는건 어떠니?"* — 추천 스테이지의
  `기간`·`월 입금` 같은 스테퍼 묶음을 **가로 2-up(2-col)로 두지 말고 세로 2-row로 스택**한다.
- **Why:** 가로 2-up 이면 각 스테퍼 control 폭이 ~126px 로 좁아 값 박스가 ~50px 밖에 안 돼,
  큰 값("110만원"·최대 "160만원")이 `−`/`+` 와 **겹치거나 2줄로 줄바꿈**된다. 세로 2-row 로
  스택하면 각 control 이 전폭(~313px)이 되어 값이 원래 크기로 한 줄에 들어간다.
- **작성법 (blueprint/생성기):** 스테퍼 그룹 프레임 = `layoutMode VERTICAL`(gap 10) + 세로 HUG /
  각 스테퍼 = 가로 FILL·세로 HUG / control = `HORIZONTAL` `primaryAxisAlignItems=MIN` gap 8 /
  값 텍스트 = 가로 **FILL** + 가운데 정렬 (값 FILL + `−` 좌 / `+` 우 = 겹침 불가). 값 크기는
  유지(절대 줄이지 말 것 — 폭은 2-row 가 해결). 생성기 `gen_signup_home_v4.py`·
  `gen_active_home_v3.py`·`gen_done_home_v3.py` 의 `stepper()`/`Steppers` 에 반영됨.
- **시스템 강제 (코드 박힘, 자동):** `figma_mcp_client._enforce_stepper_two_row_live(root_id)`
  (cmd_post_fix, indicator-gap 직후) — 직계 frame 자식 2개 이상이 각각 `control`(직계 TEXT 에
  '−'·'+' 둘 다 가진 HORIZONTAL frame)을 품은 '스테퍼 그룹'을 **이름 무관 구조로 감지**해,
  그룹을 VERTICAL 스택 + 각 스테퍼 FILL/HUG + control primary=MIN + 값 FILL 로 강제. blueprint 가
  실수로 2-up 으로 작성돼도 빌드가 자동 교정. DS 인스턴스·내부(';') 제외.
- **빌드 후 검증:** 빌드 로그에 `[stepper-2row] ✓ 스테퍼 그룹 N건 세로 2-row 스택` 라인 확인.
  스크린샷에서 `기간`/`월 입금` 스테퍼가 세로로 쌓이고 큰 값도 한 줄에 들어가는지 확인.

### 18. ⚠️ 루트 프레임 높이 = 전체 콘텐츠 높이 (852px로 줄이지 말 것)
- **post-fix가 설정한 루트 높이를 임의로 줄이지 말 것**
- 852px(iPhone 16 뷰포트)는 **프로토타입 전용** — 디자인 프레임 크기가 아님
- 루트 프레임은 **모든 콘텐츠(+ CTA Bar/Tab Bar)가 다 보이는 높이**여야 함
- CTA Bar/Tab Bar를 ABSOLUTE로 배치할 때도 루트 높이는 콘텐츠 전체를 포함해야 함
- 루트를 852px로 줄이면 하단 섹션이 잘려서 안 보임 → **절대 금지**

### 19. ⚠️ 스크린샷 QA — PRD 모든 섹션 보이는지 확인 필수
- 스크린샷 촬영 후 **PRD에 명시된 모든 섹션이 화면에 보이는지** 1:1 대조
- "스크롤 영역이라 정상"으로 넘기지 말 것 — 디자인 프레임에 전체 콘텐츠가 보여야 완료
- 하나라도 안 보이면 **완료 선언 금지** — 원인 파악 후 수정
- 체크 순서: PRD 섹션 목록 나열 → 스크린샷에서 각 섹션 존재 확인 → 누락 시 수정

### 19-B. 세로 패딩 대칭 — 🔻 2026-06-15 advisory 강등 (큰 비대칭은 디자인 도구로 존중)
- 원래(2026-06-05): *"특별한 이유 없는 비대칭을 하지 못하도록"* → pt==pb 강제.
- 🔴 **2026-06-15 강등 (사용자 룰: 콘텐츠 영역 간격을 창의적으로):** 비대칭 세로 패딩은 **리듬·
  강조의 디자인 도구**일 수 있어 더는 일괄 강제하지 않는다. 룰 2계층 ② 의 fill-in-only 철학.
  - **미세 차이(≤4px)** = 무의식적 오타로 보고 max 로 fill-in 교정(가독성 보존).
  - **큰 비대칭(>4px)** = 의도로 보고 **존중**(`[스타일-기본값]` advisory WARN 만, 변경 없음).
    의도가 명확하면 `"_asymPad": true` 로 WARN 도 침묵.
- **시스템:** `_enforce_symmetric_vpad(blueprint)` (cmd_build pre-process) — VERTICAL + 자식 2개
  이상 컨테이너. 이름이 chrome/특수면 제외, DS 인스턴스 제외. 가로 pl/pr 은 미관여.
- **빌드 후 검증:** 의도된 비대칭은 유지되는지 확인. 빌드 로그 `[규칙] 세로 패딩 미세 비대칭(≤4px)
  교정 N건` / 큰 비대칭은 `[스타일-기본값] … author 의도 존중`.

### 20. ⚠️ CTA/Button 프레임 — autoLayout에 paddingTop/Bottom 필수
- CTA Button, Submit Button 등 **텍스트를 포함한 버튼 프레임**에 `autoLayout` padding 필수
- `height: 52`만 지정하고 padding을 빼면, HUG 사이징에서 높이가 텍스트(~20px)로 축소됨
- **올바른 패턴**: `autoLayout: { ..., paddingTop: 16, paddingBottom: 16 }` → HUG여도 16+20+16 = 52px
- `height`에 의존하지 말고 **padding으로 높이를 확보**하는 것이 안전
- `validate_blueprint`의 R5 규칙이 자동 검증

### 21. ⚠️ 숫자/짧은 텍스트는 아이콘으로 변환되면 안 됨 — 빌드 후 QA로 검증
- `enhanceBlueprint`의 이모지→아이콘 자동변환은 **숫자만 있는 텍스트**(스테퍼 값 `"5"`,
  카운트, 배지 숫자 등)를 이모지로 오인해 `star-01` 아이콘으로 바꾸는 버그가 있었다.
  - 원인: 정규식 `\p{Emoji}` 는 숫자 `0-9`·`#`·`*` 도 매칭한다.
  - 수정: `isEmojiOnlyText`에 `글자/숫자(\p{L}\p{N})가 하나라도 있으면 이모지 아님` 가드 추가.
- **빌드 후 QA 강제** — `cmd_build` Step E.6 `_qa_blueprint_integrity()`:
  원본 blueprint와 빌드 트리를 1:1 대조해 **blueprint가 `type:"text"`인데 빌드 결과가
  TEXT가 아닌 노드**를 잡아낸다. 위반 시 같은 부모의 TEXT 형제를 복제·텍스트 교체로 자동 교정.
- blueprint 작성 시 스테퍼 값·카운트·배지 숫자는 반드시 `type:"text"`로 명시할 것.

### 22. ⚠️ 빌드 후 QA — 대비(가시성) + 레이아웃 자동 검사
- `cmd_build` Step E.7 `_qa_visual_checks()` — 사람 눈에 의존하지 않고 빌드 트리를 분석:
  - **대비 검사**: 텍스트/아이콘 색을 배경과 WCAG 상대휘도로 비교, 대비 비율 `< 1.8`이면
    경고 (안 보이는 텍스트/아이콘 차단 — 예: `fg-quaternary` on white). `fg-tertiary`(~1.98)는 통과.
  - **레이아웃 검사**: 마지막 콘텐츠와 Tab Bar 사이 데드밴드(빈 띠 24px↑), 콘텐츠가
    Tab Bar 뒤로 가려짐, Tab Bar 잘림/루트 하단 빈 공간을 감지.
- 빌드 로그의 `[QA] ⚠️ 시각 검사` 라인을 반드시 확인하고, 잡힌 항목을 수정할 것.
- ※ 측정 가능한 항목만 자동화된다 — "디자인이 PRD 의도에 맞나"는 여전히 사람이 확인.

> 🔵 **22-B. 레이아웃 스멜 검사 (2026-06-10) — 스크린샷 보기 *전*에 회귀 패턴 자동 노출**
>
> `cmd_build` 의 **E.7.7 끝**(모든 레이아웃 재단언 후 = 최종 상태)에서 `_qa_layout_smells()` 가
> 결정적으로(서브에이전트·LLM 없이) 자주 손으로 고치던 회귀 3종을 감지:
> 1. **SPACE_BETWEEN 행에 콘텐츠 든 FILL 자식** → 분배 깨짐(한쪽 뭉침). (선물 Giver Info 회귀)
> 2. **짧은 텍스트(≤6자, 명시 \n 없음)가 2줄+ wrap** → 폭 collapse. ("후기 공유"→"후/기", 탭 라벨)
> 3. **프레임 폭 <4px 붕괴** → 2-col FILL collapse.
> (원형→타원은 size-invariant/`_keepSizing` 이 이미 막고, 검출 시 버튼 pill 오탐이 커서 제외 — 고정밀 유지.)
>
> **빌드 로그 `[smell] ⚠️ 레이아웃 스멜 N건` 라인이 보이면 그 노드를 스크린샷에서 우선 확인**하고
> 수정한다(메시지에 수정법까지 안내 — 예 "HUG + _keepSizing 권장"). `[smell] OK` 면 그 3종은 없음.
> 코드: `_detect_layout_smells`(순수, 테스트 `test_layout_smells.py` 10건) + `_qa_layout_smells`(라이브).
> 정상 화면 5종에서 오탐 0 확인. ※ 이건 self-verify(0-F) 대체가 아니라 *보조* — 스크린샷 확인은 여전히 필수.

---

## 빌드 후 자동 후처리 (post-fix)

> `build` 명령 완료 시 자동으로 `post-fix`가 실행된다. 별도 실행도 가능:
> ```bash
> python3 scripts/figma_mcp_client.py post-fix <rootNodeId>
> ```

**post-fix가 자동 수정하는 항목:**
```
1. FILL 검증/수정: 모든 FRAME 자식 → FILL (FAB/Tab Bar 제외, SPACE_BETWEEN 마지막 HUG 자식 보존)
   - _walk: 재귀적 FILL 수정 (parent_layout_mode 빈 문자열이면 skip 안 함)
   - 안전장치: 재귀적 FILL 강제 (depth 4까지, VERTICAL 부모의 모든 FRAME 자식)
2. 섹션 간격: 배경색 동일 + divider 없는 인접 섹션 → gap 0
3. Tab Bar/FAB: ABSOLUTE 배치 + 루트 하단 위치 + FAB width 복원 (HUG)
4. Tab Bar item FILL 통일 + Tab Row individual stroke (bottom-only)
5. zero-width 텍스트: width=0 TEXT → textAutoResize="WIDTH_AND_HEIGHT" + FILL (Banner Card 내부 텍스트는 FIXED 160px)
6. DS Effect Style (Shadows/*) 자동 바인딩: frame.effects 가 raw 값으로 박혀 있어도
   첫 DROP_SHADOW fingerprint(offset.y, radius) → Shadows/shadow-{xs,sm,md,lg,xl,2xl}
   가장 가까운 DS effect style 에 `set_effect_style_id` 로 바인딩.
   인스턴스 내부 노드(`I…;…`) 와 이미 styles.effect 가 채워진 노드는 skip.
   - 수동 재바인딩: `python3 scripts/figma_mcp_client.py bind-effect-styles <rootNodeId>`
7. padding/gap → "3. Spacing"/spacing-* 시맨틱 DS 변수 자동 바인딩 (2026-05-28 "절대값 말고
   spacing- 토큰 박아" / 🔴 2026-05-29 "primitive(Spacing/) 쓰면 안돼. 3. Spacing 의 spacing- 토큰으로"):
   `_bind_spacing_tokens_live`가 post-fix 가장 마지막(모든 레이아웃 강제 후)에 라이브 트리의
   auto-layout paddingLeft/Right/Top/Bottom · itemSpacing · counterAxisSpacing 최종 값을 읽어,
   디자인 스케일에 **정확히 일치하는 값만** "3. Spacing" 컬렉션의 시맨틱 토큰에 바인딩한다.
   🔴 **primitive 스케일(`Spacing/5 (20px)` 등) 절대 금지** — 반드시 `spacing-*`:
   0=`spacing-none` 2=`spacing-xxs` 4=`spacing-xs` 6=`spacing-sm` 8=`spacing-md` 12=`spacing-lg`
   16=`spacing-xl` 20=`spacing-2xl` 24=`spacing-3xl` 32=`spacing-4xl` 40=`spacing-5xl` 48=`spacing-6xl`...
   `_load_spacing_map`이 figmaPath 소문자 `spacing-` 시작 토큰만 사용(primitive `Spacing/` 제외).
   토큰 value == 현재 값이라 시각 변화 0. DS 인스턴스 + 인스턴스 내부 노드(`I…;…`)는 제외.
   스케일 밖 값(10/14/18/22/28 등)은 토큰이 없어 리터럴 유지 — 임의 snap 금지(레이아웃 보존).
   → blueprint 의 padding/gap 은 스케일 값(0/2/4/6/8/12/16/20/24/32/40/48...)으로 쓰면 전부 바인딩됨.
7-b. 🔴 cornerRadius → `radius-*` DS 변수 자동 바인딩 (2026-06-04 사용자 "radius값 왜 토큰
   바인딩 안해? radius- 로 시작하는 토큰 있다"): `_bind_radius_tokens_live`가 spacing 바인더
   직후 실행 — 라이브 트리의 cornerRadius(균일)와 **개별 코너**(시트 top 16/bottom 0; blueprint
   값으로, get_nodes_info 가 개별 코너를 None 으로 줘서)를 스케일 일치 `radius-*` 토큰에 바인딩.
   스케일: 0=`radius-none` 4=`radius-xxs` 6=`radius-xs` 8=`radius-sm` 10=`radius-md` 12=`radius-lg`
   14=`radius-xl` 16=`radius-2xl` 20=`radius-3xl` 24=`radius-4xl` 28=`radius-5xl` 32=`radius-6xl`,
   **완전 둥근(≥100, 999/9999 류)=`radius-full`**(Figma 가 절반-사이즈 clamp → 동일). figmaPath
   소문자 `radius-` 시작 토큰만. 토큰 value==현재 radius 라 시각 변화 0. DS 인스턴스·내부(`I…;…`)
   제외. 스케일 밖(7/13/18 등)은 리터럴 유지. 4코너 각각 `topLeftRadius`…로 바인딩(plugin
   `rectangleCornerRadii`). 테스트 `test_radius_token_binding.py`.
7-c. 🔴 SVG 아이콘 VECTOR 색 → `fg-*` DS 변수 자동 바인딩 (2026-06-09 사용자 "아이콘 frame 안
   vector 의 stroke color 바인딩이 안 됨 → svg 삽입 시 가장 가까운 컬러로 바인딩하는 프로세스
   추가"): `_bind_icon_color_tokens_live`가 radius 바인더 직후 실행 — `code.js` 의 `colorizeVectors`
   가 아이콘(svg_icon) 색을 **리터럴 RGB 로 박아**(예 #2c3744) 변수에 안 묶이던 회귀를 라이브에서
   교정. 대상 = VECTOR/LINE/STAR/POLYGON/BOOLEAN_OPERATION 노드의 stroke/fill. **`Colors/Foreground/
   fg-*` 전경 팔레트(16개)에서 가장 가까운(L1) 색을 찾아** `set_bound_variables`로 바인딩.
   🔴 **stroke 아이콘 vs fill 아이콘 구분 (2026-06-09 사용자 "월렛 아이콘은 stroke 아이콘이야"):**
   Untitled UI 아이콘은 stroke 기반이고 내부는 투명이어야 한다. **VECTOR 에 visible stroke 가 있으면
   = stroke 아이콘 → stroke 만 fg-* 에 바인딩하고, fill(있으면 SVG 가 남긴 spurious 흰 내부)은
   `set_fill_color(clear)` 로 제거**(배경이 비치게). **stroke 없이 fill 만 있으면 = fill 아이콘 →
   fill 을 바인딩.** (이전엔 fills·strokes 둘 다 바인딩해서 월렛 같은 stroke 아이콘의 spurious 흰
   fill 을 fg-light 에 바인딩해 정당화해버리던 버그 → 수정.)
   매칭: #2c3744→`fg-primary`, #7700ff→`fg-brand-primary`, #ffffff→`fg-light`, #b1b6be→
   `fg-tertiary` 등(토큰 value≈현재 색이라 시각 변화 0). **거리 > 0.30(L1) 인 색은 리터럴 유지**(임의
   스냅 금지 — aqua #009eaa 등 비-전경색은 안 바뀜). 이미 바인딩된 paint·DS INSTANCE·내부(`;`)는
   skip(규칙 0-K 컴포넌트 색 보호). `'-alt'`/`'_hover'` fg 변형은 팔레트에서 제외. 멱등. 빌드 소스
   `code.js colorizeVectors` 도 stroke 있으면 fill=[] 로 비워 새 빌드부터 spurious fill 이 안 생김
   (⚠️ 플러그인 재실행 후 활성; post-fix 가 그 전에도 보정). 테스트 `test_icon_color_binding.py`.
7-d. 🔴 아이콘 프레임의 '보이지 않는 잔존 fill' 정리 (2026-06-09 사용자 "프레임 fill 에 바인딩되고
   visibility off 되어있어 → 정리 패스 추가"): `_strip_icon_frame_hidden_fills_live`가 7-c 직후 실행 —
   svg_icon 프레임(작은 정사각 + 자식이 vector 계열, VECTOR ≥1)에 남은 **visibility off fill**(실제
   색은 내부 VECTOR stroke 가 담당하므로 무의미)을 `set_fill_color(clear:true)`로 제거(plugin 이
   `node.fills = []`). **보이지 않는(visible=false) fill 만** 지워 시각 변화 0 — 보이는 fill(의도된 배경)
   은 손대지 않음. DS INSTANCE·내부(`;`) 제외. 빌드 때 `_collect_bindings`가 svg_icon 의 `iconColor`를
   **프레임 fills/0 에 바인딩하지 않도록**(is_icon_node skip) 막아 새 빌드는 애초에 이 잔존 fill 바인딩이
   안 생긴다. ⚠️ `clear`는 `code.js setFillColor` 에 추가된 plugin 기능이라 **플러그인 재실행 후 활성**.
   테스트 `test_icon_color_binding.py`(`_is_svg_icon_frame`).
8. 2-col FILL 붕괴 자동 복구 (2026-06-04 사용자 "코드에 박아"): `_enforce_multicol_fill_live`가
   모든 sizing 강제 *뒤*에 실행 — HORIZONTAL row 의 FILL 컬럼이 **1px 로 붕괴**하고 형제가
   전폭(FIXED)을 먹는 batch_build_screen 버그([[two-col-fill-card-collapse]])를 라이브에서 교정.
   직계 frame 자식 중 width ≤ 3px(붕괴 신호)가 보이면, 작은 고정 요소(아이콘/버튼 ≤56px FIXED)를
   제외한 모든 컬럼 자식을 `set_layout_sizing(FILL)` 로 균등 복원. 붕괴 없으면 no-op.
   회귀 사례: 추천 스테이지 '기간/월 입금' 2-col 스테퍼에서 기간이 1px 로 사라짐 → 자동 복원.
9. 텍스트 박스 상하 여백 복원 (2026-06-04 사용자 "프레임 안 텍스트 위아래 딱 붙으면 안 된다"):
   `_enforce_text_box_padding_live`가 multicol-fill *뒤*에 실행 — batch_build 가 HORIZONTAL row
   안 **FILL 박스의 세로 패딩을 0 으로** 떨어뜨려(stat 박스 '완료한 스테이지/3,000개' 가 패딩 0 →
   텍스트가 박스 모서리에 밀착) 발생하는 회귀를 교정. 대상: **VERTICAL FRAME + 보이는 SOLID fill
   + cornerRadius≥6 + 직계 TEXT≥2** 인데 세로 패딩 < 12 또는 itemSpacing < 6 → paddingTop/Bottom
   = max(현재,14), itemSpacing = max(현재,6) 로 복원. 투명 텍스트 그룹(fill 없음/cornerRadius 0)·
   DS 인스턴스 내부는 제외. 판별: `_text_box_needs_padding` (회귀 테스트 `test_text_box_padding.py`).
10. ⭐ blueprint 명시 FIXED 폭/padding 최종 복원 — **AUTO_FIX 이후** (2026-06-04 "내 스케줄" 회귀 뿌리):
   🔴 **순서가 핵심**: `design_rules:AUTO_FIX`(Step E.7.5)가 **cmd_post_fix 보다 *나중*에** 돌면서
   author 레이아웃을 다시 덮어쓴다. 그래서 cmd_post_fix 안에서 폭/padding 을 고쳐도 무력화됐다.
   → **Step E.7.7**(`cmd_build`, AUTO_FIX + size-invariant *이후*, 모든 단계 맨 끝)에서
   `_enforce_fixed_widths`(blueprint `layoutSizingHorizontal:"FIXED"`+width)·`_enforce_blueprint_padding`
   (blueprint autoLayout padding)을 **무조건 재단언**해 최종 권한을 갖는다. (get_nodes_info 의 padding
   직렬화가 None/stale 이라 '바뀐 것만' 판정이 카드를 놓쳐 → 멱등 재단언.)
   회귀 사례: 2-line Date Cell 이 FILL 로 늘어남(56→161) / Sched 카드 paddingLeft 0(본문 우측 밀림).
11. col-baseline 오매칭 차단 (2026-06-04): `_fix_space_between_col_baseline`(3-col stat grid 중앙정렬)이
   '내 스케줄' 같은 **리스트 행**(작은 날짜셀 56 + 넓은 본문 267)을 grid 로 오인해 본문을 FILL+가운데
   정렬시키던 회귀. → 컬럼 폭이 크게 불균등(max>2.2×min)하거나 작은 셀(≤72px)이 섞이면 list row 로
   보고 skip. (진짜 균등 3-col 요약만 중앙정렬.)
12. padding `... or 0` None 버그 (2026-06-04): get_nodes_info 가 paddingLeft 등을 **None 으로 누락**
   직렬화 → `node.get("paddingLeft") or 0` = 0 으로 실제 16 패딩을 파괴(paddingLeft 만 0 회귀).
   → padding 재설정 enforcer 들(col-baseline·`_restore_content_section_padding`)은 **숫자로 확인된
   필드만 set_auto_layout 에 전달, 모르는 필드는 생략**(code.js 가 기존값 보존). multicol-fill 의
   작은요소 제외도 sizingH 플래그 대신 **폭(≤64px) 기준**으로 판별(플래그 직렬화 불안정 대응).
[규칙] 루트 프레임 배경 = bg-primary 강제 (절대 규칙 0 — 리터럴 + DS 변수 바인딩)
```

**cmd_build 루트 auto-layout 보호:**
```
- batch_build_screen 완료 후, 루트가 이미 VERTICAL이면 set_auto_layout 재호출 금지
- layoutMode 재설정 시 Figma가 자식 layoutSizingHorizontal을 HUG로 리셋하는 버그 방지
- 루트가 VERTICAL 아닐 때만 set_auto_layout 호출 (최초 설정용)
```

**post-fix가 수정하지 않는 항목 (수동 확인 필요):**
```
1. 캐로셀 구조: HORIZONTAL 래퍼 + clipsContent (Blueprint에서 올바르게 설정해야 함)
2. 텍스트 가시성: 색상 대비 (스크린샷으로 확인)
```


---

## 트러블슈팅 (빌드 이슈 대응 — 코드에 박힌 자동 동작의 배경)

## ⚠️ 텍스트 스타일(set_text_style_id) 적용 — 라이브러리 fallback (2026-06-01)
- **증상**: 빌드 후 variables(색/spacing)는 바인딩됐는데 **텍스트 스타일만 하나도 적용 안 됨**. 빌드 로그에 `[text-style] DS text style 인덱스 비어있음 — 건너뜀`.
- **원인**: `get_styles`(code.js)는 `getLocalTextStylesAsync`로 **로컬 스타일만** 조회. 작업 파일은 DS(`Imin Design System`)를 **라이브러리로 참조만** 하고 로컬 text style이 0개 → 인덱스 빔. Figma는 변수와 달리 **라이브러리 스타일 목록 API가 없음**.
- **해법 (이미 코드에 박힘 — 자동 동작)**: `_load_text_style_map`이 로컬 0건이면 `ds/TEXT_STYLE_MAP.json`(사전 추출본)을 fallback으로 사용. `set_text_style_id`는 `S:{key},` 형식이면 `importStyleByKeyAsync`로 라이브러리 스타일을 import해 적용하므로 **로컬 없어도 동작**.
- **`ds/TEXT_STYLE_MAP.json`이 없거나 stale하면**: plugin을 **DS 파일(Imin Design System)에 연결**한 뒤 `python3 scripts/figma_mcp_client.py sync-text-styles` 1회 실행 → 추출·저장 후 커밋. (variables의 `TOKEN_MAP.json`과 동일 패턴)
- **⚠️ Carmen sans 등 비-UI 폰트 제외 (필수)**: DS text style에 **Carmen sans**(영문 전용, UI 폰트 아님)가 섞여 있고, `ExtraBold`가 weight bucket `bold`로 분류돼 `(24,bold)`·`(16,bold)` 인덱스에서 Pretendard Bold를 덮어쓴다. 그러면 Pretendard 텍스트에 Carmen sans style이 매칭돼 plugin이 그 폰트 로드로 **22초+ hang → 미적용**. `_is_pretendard_text_style`이 **Pretendard 패밀리만 매칭**(Carmen 제외)하도록 막아둠. 사용자 명시: "Carmen sans는 UI 폰트가 아니다 — 제외."
- **재빌드 없이 기존 화면에 적용**: `python3 scripts/figma_mcp_client.py apply-text-styles <rootNodeId>`
- **참고**: `cmd_build`의 `batch_build_screen`이 client 300초 timeout으로 죽으면 그 뒤의 text style 단계(Step E.5.5)에 도달 못 함 → 이땐 `apply-text-styles`로 보완.

## ⚠️ batch_build_screen timeout 시 후속 단계 자동 복구 (2026-06-01) — 모든 회귀의 공통 뿌리
- **증상**: 빌드는 됐는데 **색 변수 바인딩·text style·post-fix 가 전부 안 됨** (화면 색/배치는 리터럴로 박혀 정상처럼 보이나 DS 변수 연결·스타일 없음).
- **원인**: `batch_build_screen` 은 plugin 이 노드 생성을 끝내도 응답을 못 보내 **client 300초 timeout** 이 잦다. 예전엔 이 예외로 `cmd_build` 가 중단되어 Step D~H(색 바인딩 E.5 / text style E.5.5 / post-fix)가 전부 스킵됐다. 이 세션의 3개 회귀(text style 미적용·색 바인딩 누락·post-fix 미실행)가 **모두 이 하나의 뿌리**.
- **해법 (코드에 박힘 — 자동)**: `cmd_build` 가 `batch_build_screen` 을 try/except 로 감싸고, timeout/예외 시 `_recover_built_root_id(blueprint.name)` 로 plugin 이 끝낸 root 를 `get_document_info` 폴링으로 찾아 `root_id` 를 복구한 뒤 **후속 단계를 그대로 잇는다**. `original_blueprint`(token 보존 deep copy)는 batch_build 전에 떠 있어 색 바인딩이 정상 동작.
- **수동 복구가 필요한 옛 빌드**: `auto-bind <rootId> <blueprint.json>`(색 변수) + `apply-text-styles <rootId>`(text style) + `post-fix <rootId>`.



> 🔴 **8-C — 라이브 조립 오토레이아웃 의무 (2026-08-24 사용자 지적: "어느순간 일반 프레임을 많이 쓰고 있다")**
>
> **원인 3가지 (재발 구조):** ① `create_frame` 의 layoutMode 파라미터가 조용히 무시돼 오토레이아웃이
> 항상 후적용 3연타(마찰) ② 캡처 실측 (x,y) 를 그대로 박는 좌표 복사 관성 ③ verify 에 레이아웃
> 게이트 부재로 조용히 축적.
>
> **의무:** 라이브 조립(MCP 직접 생성)의 콘텐츠 컨테이너(카드/행/리스트/섹션)는 예외 없이
> 오토레이아웃. 실측 좌표는 반드시 padding/gap 으로 번역한다. plain frame 허용 = 화면 루트(393폭)와
> 오버레이 전용 컨테이너(자식 전부 ABSOLUTE)뿐.
>
> **시스템 강제:** ① `ds_convert_lib.new_auto_frame(call, parent, name, layout, gap, pad, ...)` —
> create→set_auto_layout→sizing 원자화 헬퍼(생성은 이걸로) ② verify `plain-frame-suspect` —
> layoutMode NONE + 흐름형 자식 ≥2 FRAME 은 FAIL. plain→오토레이아웃 무손실 전환 레시피: 자식
> 절대좌표 사전 실측 → 비균등 gap 은 투명 래퍼 행으로 균등화 → 전환 후 절대좌표 assert.
