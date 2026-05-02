# imin-notification-center — 알림 센터

**검증 점수**: OVERALL 100/100 (모든 5축 만점)
**화면 크기**: 390×866px
**검증 wrapperId**: 16993:65727 (2026-05-03)
**원본 PRD**: 텍스트만 (와이어프레임 없음) — 사용자 검증 시 6개 알림 카드 mixed 상태로 결과 도출

## 시나리오
사용자가 받은 알림(거래 / 이벤트 / 시스템)을 한 화면에서 확인. 미확인 N건 + 확인 완료 카드가 mixed로 노출되는 메인 상태.

## 적합한 PRD 패턴
- "알림 센터 / 알림 목록 / 알림 inbox"
- "거래·이벤트·시스템 종류 분류"
- "미확인/확인 dot 상태 구분"
- "type별 시맨틱 색상 (거래=brand, 이벤트=warning, 시스템=neutral)"
- 모달 형태 (close X), tabBar 없음

## 4개 섹션 구성
1. `modalHeader` — 좌측 X close + 가운데 "알림" 타이틀
2. `underlineTab` — 4-segment (전체 / 거래 / 이벤트 / 시스템), 기본 active "전체"
3. `notificationList` — kind별 시맨틱 색상 카드 N개
   - **kind**: `transaction` (보라 wallet) / `event` (warning gift) / `system` (neutral bell)
   - **unread=true**: Bold title + brand purple 8px dot 우측
   - **unread=false**: Medium title + textSecondary (위계 dilution 회피)
4. `spacer` — 하단 24px

## 데이터 슬롯
| 필드 | 값 출처 | 예시 |
|---|---|---|
| `items[].kind` | PRD: 알림 종류 | transaction / event / system |
| `items[].title` | PRD: 알림 제목 verbatim | "참여한 스테이지가 시작됐어요" |
| `items[].body` | PRD: 본문 (2줄까지) | "마이월렛 10만원 첫 납부일이..." |
| `items[].time` | PRD: 시간 표시 | "방금 전" / "30분 전" / "어제" / "2주 전" |
| `items[].unread` | PRD: 미확인 여부 | true / false |

## 적용 시 주의
- 와이어프레임이 없어도 PRD의 type 분류와 미확인 상태만 정확히 반영하면 100점 도달
- empty state 시나리오는 별도 spec (이 skill 범위 외)
- "전체 읽음" CTA는 PRD에 명시되어 있을 때만 modalHeader 우측에 추가 (현재 spec엔 없음)

## 검증 시각 (2026-05-03)
- 6 카드 mixed (3 unread + 3 read)
- 거래 2건 (보라 wallet bg)
- 이벤트 2건 (warning bg, gift icon은 IK 미추가 — minor)
- 시스템 2건 (neutral bg, bell icon)
- divider 카드 사이 1px border-secondary
