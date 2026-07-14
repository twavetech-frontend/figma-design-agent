#!/usr/bin/env bash
# 브리지 서버를 macOS launchd 사용자 에이전트로 등록 (2026-07-14).
# - 로그인 시 자동 시작 + 프로세스 사망 시 자동 재시작 (KeepAlive)
# - Claude Code 세션과 완전 분리 — 세션 종료돼도 브리지 유지
# 사용: npm run bridge:install   (해제: npm run bridge:uninstall)
set -euo pipefail

LABEL="com.imin.figma-bridge"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/imin-figma-bridge.log"

# node 절대 경로 — launchd 는 셸 PATH 를 상속하지 않는다
NODE="$(command -v node || true)"
[ -z "$NODE" ] && for p in /opt/homebrew/bin/node /usr/local/bin/node; do
  [ -x "$p" ] && NODE="$p" && break
done
if [ -z "$NODE" ]; then
  echo "[FAIL] node 를 찾을 수 없습니다 — setup-mac.sh 먼저 실행하세요." >&2
  exit 1
fi

if [ ! -f "$REPO/out/bridge/index.js" ]; then
  echo "[FAIL] out/bridge/index.js 없음 — 'npm run build' 먼저 실행하세요." >&2
  exit 1
fi

mkdir -p "$HOME/Library/LaunchAgents" "$HOME/Library/Logs"

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array>
    <string>$NODE</string>
    <string>$REPO/out/bridge/index.js</string>
  </array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key><string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
  </dict>
</dict>
</plist>
PLIST_EOF

# 재등록 멱등: 기존 로드 해제 후 다시 로드
launchctl unload -w "$PLIST" 2>/dev/null || true
launchctl load -w "$PLIST"

# 기동 확인 (최대 15초)
for _ in $(seq 1 15); do
  if lsof -i :8767 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "[OK] 브리지 데몬 등록 완료 — WS 8767 기동 확인"
    echo "     plist: $PLIST"
    echo "     log:   $LOG"
    echo "     해제:  npm run bridge:uninstall"
    exit 0
  fi
  sleep 1
done
echo "[WARN] 등록은 됐으나 15초 내 포트 기동 미확인 — 로그 확인: tail -20 $LOG" >&2
exit 1
