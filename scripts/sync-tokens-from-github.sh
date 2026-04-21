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

# 2. sync-to-agent.js 실행 → DESIGN_TOKENS.md + TOKEN_MAP.json 생성
echo "Generating DESIGN_TOKENS.md and TOKEN_MAP.json..."
cd "$TMP_DIR"
node sync-to-agent.js --out "$OUT_DIR"

# 3. 정리
rm -rf "$TMP_DIR"

echo ""
echo "Sync complete! Files updated:"
echo "  $OUT_DIR/DESIGN_TOKENS.md"
echo "  $OUT_DIR/TOKEN_MAP.json"
