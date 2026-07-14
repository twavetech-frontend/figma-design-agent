# 브리지 작업 스케줄러 등록 해제. 사용: npm run bridge:uninstall:win
$ErrorActionPreference = "SilentlyContinue"
schtasks /End /TN "imin-figma-bridge" 2>$null | Out-Null
schtasks /Delete /TN "imin-figma-bridge" /F 2>$null | Out-Null
Write-Host "[OK] 브리지 데몬 해제 완료 (imin-figma-bridge)" -ForegroundColor Green
