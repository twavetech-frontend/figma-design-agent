#!/usr/bin/env bash
# UserPromptSubmit hook: 디자인 생성 의도 감지 시
#  1. npm run bridge 자동 시작 (idempotent)
#  2. 세션 첫 발화 시 get_selection + DS 페이지 prefetch 지시 컨텍스트 주입
set -u

input=$(cat)
prompt=$(printf '%s' "$input" | python3 -c "import sys,json
try: print(json.load(sys.stdin).get('prompt',''))
except: pass" 2>/dev/null)
session_id=$(printf '%s' "$input" | python3 -c "import sys,json
try: print(json.load(sys.stdin).get('session_id',''))
except: pass" 2>/dev/null)

[ -z "$prompt" ] && exit 0

# 트리거: "디자인" + (생성|만들|그릴)
if ! printf '%s' "$prompt" | grep -q "디자인"; then exit 0; fi
if ! printf '%s' "$prompt" | grep -qE "생성|만들|그릴"; then exit 0; fi

# 1. Bridge auto-start (idempotent)
if lsof -ti:8767 >/dev/null 2>&1; then
  bridge_msg="🌉 figma bridge 이미 실행 중 (port 8767)"
else
  cd /Users/julee/imin/figma-design-agent || exit 0
  nohup npm run bridge > /tmp/figma-bridge.log 2>&1 &
  disown
  bridge_msg="🌉 figma bridge 시작됨 (log: /tmp/figma-bridge.log)"
fi

# 2. Session-scoped: prefetch context는 첫 발화 1회만 주입
marker="/tmp/claude-design-init-${session_id:-default}"
if [ -f "$marker" ]; then
  # 재발화: bridge 상태만
  printf '%s' "$bridge_msg" | python3 -c "
import sys,json
print(json.dumps({'systemMessage': sys.stdin.read(), 'suppressOutput': True}, ensure_ascii=False))
"
  exit 0
fi
touch "$marker"

# 3. 첫 발화: bridge 상태 + get_selection + DS prefetch 지시 주입
BRIDGE_MSG="$bridge_msg" python3 <<'PY'
import os, json
ctx = """[디자인 생성 자동 초기화 — 세션 첫 발화 1회 한정]
사용자가 디자인 생성 의도를 표현했다. 응답을 시작하기 전에 다음 작업을 **단일 메시지에서 병렬로** 즉시 실행하여 컨텍스트를 미리 준비할 것:

1. mcp__figma-tools__get_selection — 와이어프레임/노드 선택 여부 확인 (있으면 분석 시작점)
2. WebFetch — 아래 DS 컴포넌트 페이지 29개 병렬 prefetch (15분 캐시, 실제 디자인 시 즉시 재사용)

DS URL 베이스: https://twavetech-frontend.github.io/design-system-docs
경로:
- /components/badges, /components/tags, /components/inputs, /components/toggles
- /components/sliders, /components/tabs, /components/dropdowns, /components/selects
- /components/checkboxes, /components/radio-group, /components/segmented-control
- /components/avatars, /components/tooltip, /components/date-pickers, /components/table
- /components/pagination, /components/modal, /components/alerts
- /components/loading-indicators, /components/progress-indicators, /components/charts
- /components/link
- /components/buttons/action-button, /components/buttons/destructive-button
- /components/buttons/close-button, /components/buttons/utility-button
- /components/buttons/social-button, /components/buttons/app-store-button
- /components/buttons/group

각 WebFetch의 prompt는 짧게: "List variants, sizes, props, color tokens." 정도로 통일.
병렬 호출이 끝나면 사용자에게 클러리피케이션 질문(어떤 화면? 스타일? 배치 위치?) 또는 후속 작업으로 자연스럽게 이어가라."""
out = {
  "systemMessage": os.environ.get("BRIDGE_MSG","") + " · DS prefetch + get_selection 자동 트리거",
  "suppressOutput": True,
  "hookSpecificOutput": {
    "hookEventName": "UserPromptSubmit",
    "additionalContext": ctx
  }
}
print(json.dumps(out, ensure_ascii=False))
PY
exit 0
