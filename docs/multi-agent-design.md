# 멀티에이전트 디자인 모드

> 전체 프로토콜: [`src/multi-agent-design-SKILL.md`](../src/multi-agent-design-SKILL.md)
> QA 체크리스트: [`src/QA_CHECKLIST.md`](../src/QA_CHECKLIST.md)

## 발동 조건 (2개 이상 충족 시)
- 화면 섹션 **3개 이상**
- 아이콘 삽입 **5개 이상**
- DS 변수 바인딩 대상 **20개 노드 이상**

## 에이전트 구성
| Agent | 역할 | 실행 Wave |
|-------|------|-----------|
| Orchestrator | 계획 수립, 루트 프레임 생성, Fix 루프 | 전체 |
| **Agent A** (구조빌드) | 섹션 프레임, 컴포넌트 인스턴스, 텍스트 | Wave 1 |
| **Agent C** (DS토큰) | Text Style + Typography + Radius + Color 변수 바인딩 | Wave 2 ‖ |
| **Agent D** (아이콘) | ds-1-icons.json → clone_node → insert_child | Wave 2 ‖ |
| **QA Agent** | CLAUDE.md 10개 항목 체크, fixInstructions 생성 | Wave 3 |

## 실행 순서
```
Orchestrator: 플랜 수립 + 루트 프레임
   ↓
[Task(Agent A)]                     ← Wave 1
   ↓ 동시 실행
[Task(Agent C)] ‖ [Task(Agent D)]   ← Wave 2
   ↓
[Task(QA Agent)]                    ← QA
   ↓ 실패 시 Fix (최대 2회)
완료
```

## 핵심 규칙
- **Task 병렬 호출**: Wave 2에서 두 Task를 **단일 메시지**에 동시 포함
- **채널 공유**: 모든 Agent가 `join_channel(channel)` 후 동일 Figma 문서 접근
- **Output JSON**: 각 Agent는 반드시 구조화된 JSON으로 응답 (nodeId 포함)
- **Fix 루프**: QA 실패 시 Orchestrator가 직접 수정, 최대 2회 반복
