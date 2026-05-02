# Skills Index — imin Figma Design Patterns

이 디렉토리는 **검증된 ScreenSpec 템플릿** 모음입니다. 비디자이너 사용자가 PRD/와이어프레임을 던질 때 agent가 처음부터 ScreenSpec을 짜기 전에 **여기서 가장 가까운 시나리오를 먼저 찾아** 그 템플릿의 데이터 슬롯만 채우는 방식으로 작업하면 더 빠르고 결정적인 결과가 나옵니다.

각 skill 폴더에는:
- `spec.json` — 검증된 ScreenSpec 템플릿 (placeholder 데이터)
- `README.md` — 시나리오 설명 + 데이터 슬롯 + critique 점수 기준

## 📋 등록된 6개 Skill (2026-05-03 기준)

| Skill | 시나리오 | 화면 크기 | 검증 점수 | 적합한 PRD 패턴 |
|---|---|---|---|---|
| [`imin-home-engaged`](imin-home-engaged/) | 참여중 유저 홈 (full home, 거래 현황 + 캘린더 + 한도 + 추천) | 390×1780 | 94/100 | 기존 사용자 메인 화면, 거래·일정 관리 중심 |
| [`imin-home-newbie`](imin-home-newbie/) | 신규 유저 홈 (추천 hero 최상단, 거래 현황 없음) | 390×1612 | 97/100 | 첫 진입 사용자, 가입 유도 + 플랫폼 통계 |
| [`imin-home-empty`](imin-home-empty/) | 0건 empty state 홈 (full home 구조, 모든 데이터 0) | 390×1612 | 97/100 | 가입했지만 미참여 유저, 빈 상태 안내 + 추천 hero + 빈 카드 placeholder |
| [`imin-stage-detail-modal`](imin-stage-detail-modal/) | 스테이지 상세 모달 | 390×1310 | 97/100 | 카드 탭 → 상세 진입, 단일 스테이지 진행 현황 |
| [`imin-schedule-modal`](imin-schedule-modal/) | 거래 스케줄 모달 (close 모달, empty state 포함) | 390×1880 | 99/100 | 거래 일정 상세, 캘린더 + 일별 거래 |
| [`imin-notification-center`](imin-notification-center/) | 알림 센터 (4-tab + kind별 시맨틱 카드) | 390×866 | **100/100** | 알림 inbox, 거래·이벤트·시스템 분류, 미확인/확인 mixed |

## 🎯 사용 흐름

```
사용자: "이 PRD로 figma 디자인 만들어줘"
agent:
  1. PRD Read
  2. 위 INDEX 검토 → 가장 가까운 skill 1개 선택
     ─ "참여중 + 거래 일정" → imin-home-engaged
     ─ "신규 + 가입 유도" → imin-home-newbie
     ─ "0건 + empty" → imin-home-empty
     ─ "단일 스테이지 상세" → imin-stage-detail-modal
     ─ "스케줄 / 캘린더 모달" → imin-schedule-modal
     ─ 매칭 없음 → 처음부터 spec 작성
  3. skill의 spec.json 복사 → PRD 데이터로 슬롯 치환
  4. build_from_spec 호출
  5. 자동 critique 점수 보고
```

## ➕ 새 Skill 추가하는 법

새 PRD/와이어프레임으로 빌드해서 critique 점수 90+ 달성하면 그 spec을 `docs/skills/<scenario-name>/spec.json`에 저장 + README 작성. INDEX 업데이트.

**Skill 자격 기준**:
- critique OVERALL ≥ 90
- 기존 skill과 명확히 구별되는 시나리오
- 데이터 슬롯이 명확히 정의됨 (어떤 필드가 PRD-specific인지)
