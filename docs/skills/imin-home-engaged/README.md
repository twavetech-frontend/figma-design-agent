# imin-home-engaged — 참여중 유저 홈

**검증 점수**: OVERALL 94/100 (antiSlop 100 / typography 80 / spacing 100 / contrast 82 / hierarchy 100)
**화면 크기**: 390×1780px
**검증 wrapperId**: 16993:62000 (2026-05-03)

## 시나리오
1개 이상 스테이지에 참여 중인 사용자의 메인 홈. 거래 현황 + 납입/지급 일정 + 한도 사용률 + 추천 hero + 참여 카드 + 출석 + 이벤트 + 라운지가 모두 포함된 full home.

## 적합한 PRD 패턴
- "거래 현황을 한눈에 보여달라"
- "이번 달 납입 일정이 노출되어야"
- "참여중 스테이지 카드를 가로 스크롤로"
- "한도 사용률 + 신용점수 연동 CTA"
- "미납 발생 시 P0 경고 배너 최상단"

## 13개 섹션 구성
1. `appHeader` (logo + bell + message)
2. `underlineTab` (거래 현황 active / 누적 거래)
3. `alertBanner` (error) — **데이터 슬롯**: 미납 건수 / 날짜 / 경고 메시지
4. `summaryCardLinkRows` — **슬롯**: 진행 건수, 모은/빌린 금액
5. `monthScrollerCalendar` — **슬롯**: 이번 달 일정 5~7일
6. `creditUsageCard` — **슬롯**: 한도 사용액, 사용률, 신용점수 CTA 텍스트
7. `sectionHeader` (추천)
8. `recommendHero` — **슬롯**: 사용자명, 예상 수령액, 슬라이더/스테퍼 값, CTA
9. `sectionHeader` (참여 중인 스테이지)
10. `stageCardScroll` — **슬롯**: 카드 N개의 status/이율/금액/회차
11. `alertBanner` (warning) — **슬롯**: 계좌 연결 등 secondary CTA
12. `attendanceWeek` — **슬롯**: 연속 출석일, 보상 안내, 7일 상태
13. `eventBannerCarousel` — **슬롯**: banners 배열
14. `productHotDeal` — **슬롯**: pointBalance, products N개
15. `sectionHeader` (누적 거래 현황)
16. `statsStrip3Col` — **슬롯**: 누적 수령액/납입액/평균 수익
17. `footerLegal` — **슬롯**: 사업자정보 (보통 고정)

## Overlays
- `tabBar` (홈 active)
- `fab` (wallet)

## 사용법
```
1. 이 spec.json을 복사
2. 위 "데이터 슬롯" 항목을 PRD/와이어프레임 값으로 치환
3. positionRelativeTo를 사용자 와이어프레임 노드 ID로 설정
4. build_from_spec(spec) 호출
5. critique 점수 ≥ 80 확인 후 사용자 보고
```
