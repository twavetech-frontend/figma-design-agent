# 브리지 서버를 Windows 작업 스케줄러에 로그온 시 자동 시작으로 등록 (2026-07-14).
# 사용: npm run bridge:install:win   (해제: npm run bridge:uninstall:win)
# 주의: schtasks 는 launchd 의 KeepAlive 같은 자동 재시작이 없다 — 죽으면 재로그온 또는
#       schtasks /Run /TN imin-figma-bridge 로 수동 재기동.
$ErrorActionPreference = "Stop"

$Repo = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Bridge = Join-Path $Repo "out\bridge\index.js"
if (-not (Test-Path $Bridge)) {
    Write-Host "[FAIL] out\bridge\index.js 없음 - 'npm run build' 먼저 실행하세요." -ForegroundColor Red
    exit 1
}

$Node = (Get-Command node -ErrorAction SilentlyContinue).Source
if (-not $Node) { $Node = "C:\Program Files\nodejs\node.exe" }
if (-not (Test-Path $Node)) {
    Write-Host "[FAIL] node.exe 를 찾을 수 없습니다 - setup-windows.ps1 먼저 실행하세요." -ForegroundColor Red
    exit 1
}

$TaskName = "imin-figma-bridge"
$Action = "`"$Node`" `"$Bridge`""

schtasks /Delete /TN $TaskName /F 2>$null | Out-Null
schtasks /Create /TN $TaskName /TR $Action /SC ONLOGON /RL LIMITED /F | Out-Null
schtasks /Run /TN $TaskName | Out-Null

Start-Sleep -Seconds 5
$listening = Test-NetConnection -ComputerName 127.0.0.1 -Port 8767 -WarningAction SilentlyContinue
if ($listening.TcpTestSucceeded) {
    Write-Host "[OK] 브리지 데몬 등록 완료 - WS 8767 기동 확인 (작업: $TaskName)" -ForegroundColor Green
} else {
    Write-Host "[WARN] 등록은 됐으나 포트 기동 미확인 - schtasks /Run /TN $TaskName 재시도" -ForegroundColor Yellow
}
