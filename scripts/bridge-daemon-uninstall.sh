#!/usr/bin/env bash
# 브리지 launchd 데몬 등록 해제. 사용: npm run bridge:uninstall
set -euo pipefail
LABEL="com.imin.figma-bridge"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
if [ -f "$PLIST" ]; then
  launchctl unload -w "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "[OK] 브리지 데몬 해제 완료 ($LABEL)"
else
  echo "[OK] 등록된 데몬 없음 — 할 일 없음"
fi
