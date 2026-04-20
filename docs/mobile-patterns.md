# Mobile Design Patterns

## Mobile Detail Screen 패턴

- **핵심 수치 = Inline Horizontal Stat 1행** — 약정금/이율/인원/기간 등 4개 이내 수치는 카드 그리드(2×2) 대신 **한 줄 가로 배치**로 세로 공간 절약. 카드형은 데스크톱/태블릿 전용
- **부제목 필수** — 화면 타이틀 아래 한 줄 설명 텍스트로 맥락 전달 (예: "매월 30만원씩 12개월간 진행하는 스테이지입니다")
- **긴급 알림 배너** — 잔여석, 마감임박 등 FOMO 요소를 경고 배너로 표시 (예: "잔여 4석 | 빠른 참여를 권장합니다")
- **"보기"와 "행동" 섹션 분리** — 참여현황(상태 확인)과 순번선택(사용자 행동)을 별도 섹션으로 분리. 혼합 금지
- **호스트/작성자 프로필 = 탭 가능 카드** — 아바타+이름+뱃지+chevron-right로 내비게이션 어포던스 제공
- **태그에 아이콘 포함** — 텍스트만 있는 태그보다 아이콘+텍스트 조합이 가독성과 스캔성 향상
- **iOS Status Bar 포함 필수 (최우선 규칙)** — 모바일 프레임 생성 시 Status Bar를 직접 만들지 말고, **반드시 icons 페이지의 `Status bar` 인스턴스(노드 ID: `1:3448`)를 `clone_node`로 복제**해서 사용할 것. 절차: `clone_node(1:3448, rootId)` → `insert_child(index=0)` → `set_layout_sizing(horizontal: FILL)` → `resize_node(393, 54)`. Blueprint JSON에 Status Bar 자식 노드를 직접 정의하지 말 것 — 빌드 후 clone으로 삽입
- **섹션 구분 = 여백 우선** — 두꺼운 Divider(8px 배경색) 대신 **여백(16~24px)**과 섹션 타이틀로 구분. Divider는 같은 섹션 내 항목 간 얇은 선(1px)만 사용
- **CTA 버튼에 아이콘 장식** — 주요 행동 버튼에 아이콘을 추가하면 시각적 강조 효과
- **정보 밀도 최적화** — 모바일은 스크롤 최소화가 핵심. 불필요한 패딩/카드 여백을 줄이고 한 화면에 최대한 많은 정보 노출
- **순번/좌석 선택 UI** — 그리드 형태(3~4열)의 원형/라운드 버튼으로 표시. 상태는 3종류: 확정(filled), 선택됨(brand color), 선택 가능(outline). 반드시 범례(Legend) 포함

## Julee App Pattern Reference (ds/JULEE_APP_PATTERNS.md)
- **레이아웃·컴포넌트·인터랙션 패턴만 참고** — 화면 구조, 카드 레이아웃, 탐색 흐름, 제스처 등 UX 패턴 적용 가능
- **색상 패턴은 완전 무시** — 외부 색상 팔레트, 배경색, 텍스트 색, 브랜드 컬러는 참고하지 않음. 색상은 항상 DS v1 토큰 전용

## Mobile Screen Size
- 모바일 디자인은 **iPhone 16** 기준: **393 × 852** px
- **상단 Status Bar 62px 확보 필수** — y=0~62 구간은 항상 비워둘 것. 콘텐츠는 **y=74** (62 + 12px 패딩)부터 시작
- 모든 모바일 디자인 생성 시 이 사이즈를 기본으로 사용
- TabBar 높이: 74px → TabBar y = 852 - 74 = **778**
- FAB 위치: TabBar 위 16px → FAB y = 778 - 56 - 16 = **706**, x = 393 - 56 - 20 = **317**

## Constraints & Scroll Behavior (프로토타입 필수 설정)
- **NavBar**: Scroll behavior → Position: **Fixed (stay in place)**, Overflow: **No scrolling**
- **TabBar**: Constraints: **Left, Bottom** / Scroll behavior → Position: **Fixed (stay in place)**, Overflow: **No scrolling**
- **FAB**: Constraints: **Right, Bottom**
- NavBar와 TabBar는 스크롤 시 화면에 고정, FAB는 우하단에 고정
