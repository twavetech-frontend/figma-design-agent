#!/bin/bash
# sync-tokens-from-github.sh
#
# GitHub (twavetech-frontend/design-system)에서 최신 토큰을 가져와
# ds/DESIGN_TOKENS.md, ds/TOKEN_MAP.json을 재생성합니다.
#
# 사용법:
#   bash scripts/sync-tokens-from-github.sh
#
# 디자인 생성 전에 반드시 실행하여 최신 토큰을 보장합니다.

set -e

REPO_RAW="https://raw.githubusercontent.com/twavetech-frontend/design-system/main"
TMP_DIR="/tmp/ds-sync-$$"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT_DIR="$PROJECT_ROOT/ds"

echo "Fetching latest tokens from GitHub..."
mkdir -p "$TMP_DIR"

# 1. tokens.json + sync-to-agent.js 가져오기
curl -sL "$REPO_RAW/tokens.json" -o "$TMP_DIR/tokens.json"
curl -sL "$REPO_RAW/sync-to-agent.js" -o "$TMP_DIR/sync-to-agent.js"

# 검증
if [ ! -s "$TMP_DIR/tokens.json" ]; then
  echo "ERROR: Failed to fetch tokens.json"
  rm -rf "$TMP_DIR"
  exit 1
fi

if [ ! -s "$TMP_DIR/sync-to-agent.js" ]; then
  echo "ERROR: Failed to fetch sync-to-agent.js"
  rm -rf "$TMP_DIR"
  exit 1
fi

TOKEN_COUNT=$(python3 -c "import json; d=json.load(open('$TMP_DIR/tokens.json')); print(sum(1 for k in d if not k.startswith('\$')))" 2>/dev/null || echo "?")
echo "Downloaded tokens.json ($TOKEN_COUNT token sets)"

# 2a. ⚠️ sync-to-agent.js Dark-mode 제외 필터 버그 패치
#  업스트림 필터 `includes('dark mode')` 는 실제 set 키 "1. Color modes/Dark"
#  (소문자 "color modes/dark") 를 못 걸러 Dark set 이 Light 를 override 한다.
#  → 색상 토큰 285개가 DARK 값으로 덤프되는 회귀. "color modes/dark" 로 교정.
#  업스트림(design-system/sync-to-agent.js)이 고쳐지면 grep 가드로 자동 무효화.
if grep -q "includes('dark mode')" "$TMP_DIR/sync-to-agent.js"; then
  sed -i.bak "s#includes('dark mode')#includes('color modes/dark')#" "$TMP_DIR/sync-to-agent.js"
  rm -f "$TMP_DIR/sync-to-agent.js.bak"
  echo "Patched sync-to-agent.js — Dark-mode 제외 필터 교정 (Light 모드 강제)"
fi

# 2b. sync-to-agent.js 실행 → DESIGN_TOKENS.md + TOKEN_MAP.json 생성
echo "Generating DESIGN_TOKENS.md and TOKEN_MAP.json..."
cd "$TMP_DIR"
node sync-to-agent.js --out "$OUT_DIR"

# 3. 정리
rm -rf "$TMP_DIR"

# 4. 검증 — bg-primary 가 LIGHT 값인지 확인 (DARK 모드 회귀 감지)
BG_PRIMARY=$(python3 -c "import json; print(json.load(open('$OUT_DIR/TOKEN_MAP.json'))['--colors-background-bgPrimary']['value'])" 2>/dev/null || echo "?")
if [ "$BG_PRIMARY" = "#000000" ]; then
  echo "ERROR: TOKEN_MAP.json bg-primary=#000000 — DARK 모드 회귀! Dark-mode 패치 실패."
  exit 1
fi

echo ""
echo "Sync complete! Files updated:"
echo "  $OUT_DIR/DESIGN_TOKENS.md"
echo "  $OUT_DIR/TOKEN_MAP.json"
echo "  검증 통과: bg-primary=$BG_PRIMARY (LIGHT 모드)"
