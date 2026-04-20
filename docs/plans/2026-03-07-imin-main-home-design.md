# imin 메인 홈 화면 디자인

## 개요
아임인(imin) 앱의 메인 홈 화면. 스테이지 참여 유도 + 매일 혜택으로 리텐션 강화.

## 화면 구조 (393x1500+)

### 1. Status Bar (54px) - clone 1:3448
### 2. NavBar (56px) - HORIZONTAL, SPACE_BETWEEN
- 좌: "imin" 로고 (ExtraBold, brand color)
- 우: bell + message-chat 아이콘

### 3. Transaction Ribbon (36px) - brand-section bg
- 중앙: "누적 거래 3,191,399건" (white text, Medium 12px)

### 4. Hero Banner (padding 20, Banner Card 200px)
- 프로모션 카드 (친구 초대 수익, 화장품 프로모션 등)
- Gemini 이미지 생성 (isHero=true)
- 하단 인디케이터 (1/5 dots)

### 5. 추천! 스테이지 섹션
- Header: "추천! 스테이지" (Bold) + "전체보기 >" 링크
- 탭: "빠른 시작" (active) | "많은 혜택"
- 가로 스크롤 카드 (width ~160px, 2.5개 노출)
  - 월 납입금, 목표 금액, 이율(%), 추가 혜택 태그
  - 우하단 북마크 아이콘

### 6. 놓칠 수 없는 즐거움 섹션
- Header: "놓칠 수 없는 즐거움" (Bold)
- 2-column 그리드: 랜덤박스, 기프트샵
- Gemini 3D 아이콘 (50x50 노드, 150x150 이미지)

### 7. 매일매일 혜택받기 섹션
- Header: "매일매일 혜택받기" (Bold)
- 리스트 아이템 (아이콘 + 제목 + 설명 + chevron-right)
  - 친구 구조대
  - 출석체크
  - 포인트 충전소

### 8. 목돈 계산기 배너
- "스테이지 목돈 계산기" CTA 배너
- Gemini 3D calculator 이미지

### 9. FAB (ABSOLUTE)
- brand bg + wallet 아이콘 + "마이 월렛"
- y = TabBar.y - 56 - 16

### 10. Tab Bar (ABSOLUTE, 74px)
- 홈(active), 커뮤니티, 스테이지, 라운지, 나

## 디자인 결정
- 스테이지 카드: 가로 스크롤
- 누적 거래 건수: NavBar 아래 리본
- 색상: DS v1 토큰 100%
- 폰트: Pretendard, weight 위계 적용
- 이미지: Gemini 3D soft matte
