# 비주얼 스타일 레퍼런스 컬렉션

> 이 프로젝트에서 생성되는 모든 GUI의 공식 비주얼 기준이 되는 레퍼런스 시안 목록.
> 새 레퍼런스 추가 시 **반드시 이 인덱스에 행을 추가**하고, 기여한 템플릿/규칙을 매핑해야 한다.
> 추가 워크플로우는 [`CLAUDE.md` § 레퍼런스 추가 워크플로우](../../CLAUDE.md#레퍼런스-추가-워크플로우) 참조.

---

## 레퍼런스 목록

| # | 레퍼런스 | 경로 | 추가일 | 기여한 Blueprint 템플릿 | 기여한 VS 규칙 |
|---|---------|------|--------|-----------------------|--------------|
| 1 | 아임인 홈 화면 (거래 현황 탭) | [`imin-home/`](imin-home/) | 2026-04-21 | `SummaryCard2Col`, `AlertCard`, `SectionHeader`, `HorizontalCardScroll`, `ProgressCard`, `AttendanceStrip` + `blueprint.json` (15 섹션, 복제 재사용 권장) | VS1~VS8 (큰 숫자 강조, 상태 컬러 3원색 세트, Pill 배지 스펙, 아이콘 배지 원형, 가로 스크롤 섹션, 섹션 헤더 3요소, Premium CTA 카드, 진행률 바) |
| 1b | 아임인 홈 화면 (누적 거래 탭) | [`imin-home-cumulative/`](imin-home-cumulative/) | 2026-04-22 | `RankingCard4Col` (아바타+메달오버레이+레벨 bar) + `FooterLegal` — 나머지 섹션은 imin-home `blueprint.json` 재사용 예시 | VS31 Stroke INSIDE, VS32 가로 스크롤 Peek |
| 2 | 아임인 진행중 스테이지 내역 모달 | [`imin-stage-modal/`](imin-stage-modal/) | 2026-04-21 | `ModalHeader`, `SummaryCardLinkRows`, `MonthScrollerCalendar`, `StatsStrip3Col`, `TransactionTimelineItem` + `blueprint.json` | VS9~VS14 (Modal Header X-close, 금액 링크 스타일, 월 캘린더 active ring, D-day 날짜 배지, 타임라인 with progress, Flat Stats Strip) |
| 3 | 아임인 스테이지 탭 (추천 피드) | [`imin-stage-tab/`](imin-stage-tab/) | 2026-04-21 | `CategoryChipScroller`, `SegmentedTabControl`, `StepperFilterCard`, `SliderFilterCard`, `FilterChipTriggers`, `BottomSheetFilter`, `AvatarScroller`, `StageCardTimeline`, `LegalFooter` + FAB 원형 variant 보강 | VS15~VS23 (Outline Chip 필터, Segmented Tab, Stepper 행, Slider 행, 필터 칩 트리거, Bottom Sheet, 아바타 스크롤, 스테이지 카드 multi-layout, Legal Footer) |
| 4 | 아임인 스테이지 상세 (참여자 탭 + 참여 바텀시트) | [`imin-stage-detail/`](imin-stage-detail/) | 2026-04-21 | `BackOnlyHeader`, `StageDetailSummaryCard`, `ParticipantTimelineRow`, `EmptyStatePlaceholder`, `RoundSelectorGrid`, `DecisionBottomSheet` + `SegmentedTabControl`/`BottomSheetFilter` 보강 | VS24~VS30 (Back-only Header, Asymmetric 3-col Summary, Timeline 참여자 Row, TimelineNode variant, Empty State, N-cell 선택 그리드, Decision BottomSheet) + VS16/VS20 보강 |

---

## 레퍼런스별 상세

### 1. 아임인 홈 화면
- **원본**: Figma Make standalone HTML export (`_ _ _standalone_.html`, 8.4MB)
- **포함 컴포넌트** (15종):
  - Phone Shell (iPhone 15/16 390×844, dynamic island, status bar, home indicator)
  - App Header (imin 로고 + eye/bell/message-square 버튼)
  - Home Tabs (Underline 스타일, 거래 현황 / 누적 거래)
  - Missed Alert (P0 알림)
  - Summary Card (2-col 그리드 금액 요약)
  - Schedule Section (Horizontal Timeline ↔ List Timeline 스왑)
  - Limit Section (진행률 + 신용점수 nudge)
  - Stage Recommender (Premium CTA, 슬라이더/스테퍼 포함 — 블루프린트 템플릿 제외)
  - Current Stages (220px 가로 스크롤 카드)
  - Onboarding Nudge (계좌 연결 유도)
  - Attendance Strip (연속 출석 + 7일 체크)
  - Event Banner (그라데이션 + 태그 pill + 도트 인디케이터)
  - Lounge Section (150px 가로 스크롤 상품 카드)
  - Cumulative View (누적 실적 + 플랫폼 현황 + 다크 액센트 카드)
  - Bottom Nav (5탭 + badge)
- **비고**: `StageRecommender` 같은 인터랙티브 카드(슬라이더+스테퍼 내장)는 Blueprint 템플릿으로 일반화하지 않음 — 개별 화면별로 `sections-2.jsx` 원본 참조하여 구현

### 2. 아임인 진행중 스테이지 내역 모달
- **원본**: 이미지 스크린샷 (`screenshot.png`) — 코드/번들 없음, 이미지 분석 기반 아카이브
- **화면 성격**: 풀스크린 모달 — "내 스테이지 4건" 상세 요약 + 월별 거래 스케줄 + 납입 타임라인 리스트
- **포함 컴포넌트** (5종):
  - Modal Header (우측 X-close only, 좌측 빈 공간)
  - Summary Card with Link Rows (타이틀 + 체크/스파클 아이콘 + "모은/빌린 금액" 링크 row)
  - Month Scroller Calendar (7개 월 가로 배치, Jan=active 원형 강조, 좌우 chevron, 하단 "납입 ▼" 필터)
  - Stats Strip 3-Col (월 납입액 / 납입 완료액 / 남은 납입액 — flat 3-col 띠)
  - Transaction Timeline Items × N (좌측 D-day 배지 + 중앙 타이틀+금액+progress bar + 우측 outline pill/상태 텍스트)
- **상태별 컬러 매핑**:
  | 상태 | Progress Bar | Right Action |
  |-----|-------------|-------------|
  | 미납 (D+n) | error-secondary (빨강) | Outline pill "납입 하기" |
  | 오늘 (D-day) | brand-solid | — 상황별 |
  | 완료 | success-secondary (초록) full | text "납입 완료" |
  | 예정 (D-n) | quaternary track only | Outline pill "선납 하기" |
- **비고**: 이미지 기반이라 정확한 interaction(드롭다운 동작, 스크롤 컨테이너 등)은 추측 기반 — 실제 구현 시 디자이너 확인 필요

### 3. 아임인 스테이지 탭 (추천 피드)
- **원본**: Figma Make standalone HTML export (`template.html`) + 추출한 3개 sections jsx
  - `sections-1.jsx`, `sections-2.jsx` — imin-home과 동일한 컴포넌트 라이브러리 (재사용)
  - `sections-3.jsx` — 스테이지 탭 전용 신규 컴포넌트
- **화면 성격**: 스테이지 추천 피드 탭 — 카테고리 필터 + 파라미터 조정 + 카드 리스트 + 최하단 푸터
- **수정 이력**:
  - 초기 디자인: 5-탭 outline chip 카테고리 필터 (추천/직접/신규/인기/마감임박)
  - **v2 수정** (`screenshot-top-v2.png`): 2-탭 Segmented Control로 변경 (추천/직접) — `SegmentedTabControl` 템플릿 / VS16 규칙으로 반영
- **포함 컴포넌트**:
  - **상단 고정**: AppHeader (재사용) + Segmented Tab Control (v2) 또는 Category Chip Scroller (v1)
  - **필터 (Tweak에 따라 3가지 스타일)**:
    - Stepper 스타일 (기본): ± 버튼 3행 카드
    - Slider 스타일: native range slider 3행
    - Sheet Trigger 스타일: 칩 트리거 → Bottom Sheet Filter 호출
  - **Maker Avatars**: 52sq 원형 아바타 가로 스크롤 + dashed 추가 버튼 + crown badge overlay
  - **Stage Card 리스트**: 3가지 레이아웃 variant (Timeline Bar / Ring Gauge / Number Hero) + 공통 금액 요약 + 혜택 배지 band
  - **CreateStageFAB**: 원형 52sq + 3px 흰 border + brand-solid (기존 pill FAB와 다른 variant)
  - **Bottom Nav**: stages 탭 active 상태
  - **Legal Footer**: 3-col 약관 + 사업자 정보
- **Tweak 변수** (Figma Make 특성 — 디자이너가 스위치할 수 있는 옵션):
  - `filterStyle`: stepper / slider / sheet
  - `cardLayout`: timeline / ring / number
  - `cardCount`: 보여줄 카드 수
  - `showMakers`: 아바타 섹션 on/off
- **비고**: `SliderFilter`, `SheetTriggers`, `FilterSheet`, `StageCard` 3-layout variant는 모두 블루프린트에 반영. Tweak 기반 조건부 렌더링은 Figma에선 "variant property"로 구현 가능

### 4. 아임인 스테이지 상세 (참여자 탭 + 참여 바텀시트)
- **원본**: Figma Make standalone HTML export (`template.html`) + `sections-1.jsx` (imin-home 재사용 라이브러리) + `sections-2.jsx` (상세 전용) + `inline-0.jsx` (상위 조립)
- **화면 성격**: 스테이지 상세 페이지 — 요약 카드 + 4-탭(참여자/이율/진행/채팅) + 참여자 타임라인 리스트 + (탭 시) 참여 시뮬레이션 바텀시트
- **포함 컴포넌트**:
  - **BackOnlyHeader**: 뒤로가기(chevron-left 24) 만 — 타이틀 없음
  - **StageDetailSummaryCard**: 타이틀(16 ExtraBold) + 시작 라벨 baseline 정렬 + 3-col 비대칭 grid (총 납입수 1fr / 약정금 1.4fr / 인원 1fr)
  - **StageDetailTabs** (2-style 선택):
    - pill (기본): 4-segment gray track + 흰 pill active (VS16 4-tab variant)
    - underline: DS Underline Tabs (기존 rule 14 적용)
  - **ParticipantTimelineRow**: 좌측 rail(width 36 + 세로선 + 원형 노드) + 우측 카드. emphasize=true면 brand-solid 카드 + brand shadow
  - **TimelineNode 3-variant**: number / avatar(invite=gradient 이니셜 or plan=credit-card 아이콘) / stage(dot)
  - **EmptyStatePlaceholder**: 아이콘 원 64sq + 타이틀 + 서브 (이율/진행/채팅 탭)
  - **JoinSimSheet (DecisionBottomSheet)**: 참여 가능 회차 탭 시 열림
    - Grabber + 우측 상단 X (drag handle만으로는 닫기 동선 부족 → 복합 시트)
    - 헤더 설명 (월 금액 × 기간)
    - **RoundSelectorGrid**: 13-cell 가로 바 + 선택 회차 아래 삼각 pointer
    - 안내 텍스트 (4회차 납입 후 목돈 수령)
    - 금액 상세 section (목돈 / 총 이자 — 이자는 수령 회차에 따라 + success 또는 − error)
    - 선물/수수료 배지 row
    - CTA Section (참여하기 full-width 버튼, brand shadow)
- **Tweak 변수**:
  - `tabStyle`: pill / underline
  - `timelineVisual`: number / avatar / stage
  - `rowDensity`: normal / tight
- **실시간 계산 로직** (참고용 — 블루프린트 외):
  - `payout = monthly × totalRounds` (약정금 고정)
  - `interest = monthly × totalRounds × 0.006 × (midpoint - selectedRound)` — 빠른 회차 = 대출(이자 −), 늦은 회차 = 예금(이자 +)
  - `gift = selectedRound === 1 ? 500 : 0` — 1회차 선택 시에만 포인트
- **주요 설계 의도**: drag handle + X 조합은 복합 시트의 닫기 동선 명확화. 실시간 값 계산은 사용자가 회차 탭할 때마다 하단 금액 갱신하여 **결정의 결과를 미리 체험** 가능
