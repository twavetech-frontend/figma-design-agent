# imin-home-empty — 0건 empty state 홈

**검증 점수**: OVERALL 97/100 (antiSlop 100 / typography 92 / spacing 100 / contrast 90 / hierarchy 100)
**화면 크기**: 390×1612px
**검증 wrapperId**: 16993:64029 (2026-05-03)
**원본 와이어프레임**: 사용자가 추가한 `imin_home_1` (16993:63432)

## 시나리오
가입했지만 아직 스테이지 미참여 상태인 사용자. 거래 현황의 모든 수치가 0이고, 참여 카드가 비어있는 empty state. 추천 hero로 첫 참여를 유도.

## 적합한 PRD 패턴
- "신규 가입 직후 사용자 홈"
- "진행중 0건 스테이지 표시"
- "참여 중인 스테이지 / 찜한 스테이지 탭 전환"
- "예치금 312,490원(100p) 같은 포인트 잔액 표시"
- description에 인증사용자/클린사용자 같은 *조건부 뱃지* 룰 언급

## 12개 섹션 구성
1. `appHeader` — imin + bell + message
2. `underlineTab` — 거래 현황 / 누적 거래
3. `summaryCardLinkRows` — **슬롯**: 진행 건수, 모은/빌린 +0원, 인증/클린사용자 hint
   - titleIcons: `["checkCircle", "sparkle"]` (인증 + 클린 메타)
4. `attendanceWeek` — **슬롯**: 연속 0일, 보상 텍스트, 7일 future
5. `sectionHeader` — 추천 스테이지 + 목표 trailing
6. `recommendHero` — **슬롯**: 1회차 / 1,300만원 / 슬라이더/스테퍼 / 토글 텍스트
7. `segmentedTab` — 참여 중인 스테이지 / 찜한 스테이지
8. `stageCardScroll` — **슬롯**: empty state 메시지 카드 2개
   - status: inProgress / scheduled로 구분 (실데이터 들어오면 카드 추가)
9. `productHotDeal` — **슬롯**: 라운지 + 포인트 잔액 + 상품 카드
10. `footerLegal` — 사업자정보
11. `tabBar` (overlay)
12. `fab` (overlay)

## 데이터 슬롯 가이드
| 위치 | 필드 | 값 출처 |
|---|---|---|
| summaryCardLinkRows | 진행중 N건 | PRD: 사용자 참여 건수 (이 skill에서는 0) |
| recommendHero | amount | PRD: 목표 모금액 (1,300만원 디폴트) |
| recommendHero | slider | PRD: 회차 1~13 중 선택값 |
| stageCardScroll | empty 메시지 | "참여 중인 스테이지가 없어요" / "찜한 스테이지가 없어요" |
| productHotDeal | pointBalance | PRD: 사용자 보유 포인트 ("312,490원(100p)") |

## 적용 시 주의
- 모든 거래 수치 0이지만 `valueTone="positive"` (모은) / `"negative"` (빌린)을 유지해서 색상 의미 단위 보존
- empty state 메시지는 alertBanner(info) 또는 stageCardScroll의 statusLabel에 자연어로 표현
