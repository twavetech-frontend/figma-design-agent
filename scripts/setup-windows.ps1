#Requires -Version 5.1
<#
.SYNOPSIS
  Figma Design Agent — Windows 최초 환경 설정 (디자인 생성 준비)

.DESCRIPTION
  Git에서 레포를 클론한 Windows 사용자가 디자인 생성을 시작하기 전,
  필요한 모든 의존성을 설치/검증한다. 멱등(idempotent) — 여러 번 실행해도 안전하며
  이미 설치된 항목은 건너뛴다.

  처리 항목:
    1. Python 3.12 (winget)          — figma_mcp_client.py 실행용
    2. Python 패키지: requests, Pillow
    3. PYTHONUTF8=1 사용자 환경변수  — 한글 출력 cp949 UnicodeEncodeError 방지
    4. Node.js LTS (winget)          — Vite 6는 Node 18+ 필수
    5. npm 의존성 (--legacy-peer-deps, .npmrc에 설정됨)
    6. sharp 네이티브 모듈 (win32-x64 플랫폼 패키지)
    7. 프로젝트 빌드 (npm run build → out/)

.EXAMPLE
  npm run setup:windows
  powershell -ExecutionPolicy Bypass -File scripts/setup-windows.ps1
#>
param()

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot

function Write-Step($m) { Write-Host "`n=== $m ===" -ForegroundColor Cyan }
function Write-Ok($m)   { Write-Host "  [OK]   $m" -ForegroundColor Green }
function Write-Info($m) { Write-Host "  [..]   $m" -ForegroundColor Gray }
function Write-Warn2($m){ Write-Host "  [WARN] $m" -ForegroundColor Yellow }

# winget 설치 후 같은 세션에서 새 명령을 찾도록 PATH를 갱신
function Update-SessionPath {
  $machine = [Environment]::GetEnvironmentVariable('Path', 'Machine')
  $user    = [Environment]::GetEnvironmentVariable('Path', 'User')
  $env:Path = "$machine;$user"
}

# 실제 Python 탐색 — PATH의 python3/python은 Microsoft Store 별칭 stub이므로
# Programs\Python 과 Program Files\Python* 만 탐색한다.
function Find-RealPython {
  $dirs = @()
  $dirs += Get-ChildItem "$env:LOCALAPPDATA\Programs\Python" -Directory -ErrorAction SilentlyContinue
  $dirs += Get-ChildItem 'C:\Program Files\Python*' -Directory -ErrorAction SilentlyContinue
  foreach ($d in $dirs) {
    $exe = Join-Path $d.FullName 'python.exe'
    if (Test-Path $exe) {
      try {
        $v = & $exe --version 2>&1
        if ("$v" -match 'Python 3\.') { return $exe }
      } catch {}
    }
  }
  return $null
}

function Assert-Winget {
  if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw 'winget을 찾을 수 없습니다. Microsoft Store에서 "앱 설치 관리자"(App Installer)를 설치한 뒤 다시 실행하세요.'
  }
}

function Invoke-Npm($argList) {
  & npm @argList
  if ($LASTEXITCODE -ne 0) {
    throw ('npm ' + ($argList -join ' ') + " 실패 (exit $LASTEXITCODE)")
  }
}

Write-Host ''
Write-Host '###############################################' -ForegroundColor Cyan
Write-Host '#  Figma Design Agent - Windows 환경 설정      #' -ForegroundColor Cyan
Write-Host '###############################################' -ForegroundColor Cyan

# ── 1. Python ─────────────────────────────────────────────
Write-Step '1/7 Python 3.x 확인/설치'
$python = Find-RealPython
if (-not $python) {
  Assert-Winget
  Write-Info 'Python 미설치 — winget으로 Python 3.12 설치 중...'
  winget install --id Python.Python.3.12 -e --accept-source-agreements --accept-package-agreements --silent --scope user | Out-Null
  Update-SessionPath
  $python = Find-RealPython
  if (-not $python) { throw 'Python 설치 후에도 찾을 수 없습니다. https://python.org 에서 수동 설치하세요.' }
}
Write-Ok "Python: $python  ($(& $python --version 2>&1))"

# ── 2. Python 패키지 ──────────────────────────────────────
Write-Step '2/7 Python 패키지 설치 (requests, Pillow)'
& $python -m pip install --upgrade pip --quiet --disable-pip-version-check
& $python -m pip install --upgrade requests Pillow --quiet --disable-pip-version-check
Write-Ok 'requests, Pillow 설치/갱신 완료'

# ── 3. PYTHONUTF8 ─────────────────────────────────────────
Write-Step '3/7 PYTHONUTF8 환경변수'
if ([Environment]::GetEnvironmentVariable('PYTHONUTF8', 'User') -ne '1') {
  [Environment]::SetEnvironmentVariable('PYTHONUTF8', '1', 'User')
  Write-Ok 'PYTHONUTF8=1 사용자 환경변수 등록 (한글 출력 cp949 오류 방지)'
} else {
  Write-Ok 'PYTHONUTF8=1 이미 설정됨'
}
$env:PYTHONUTF8 = '1'

# ── 4. Node.js ────────────────────────────────────────────
Write-Step '4/7 Node.js 18+ 확인/설치'
$nodeMajor = 0
$nv = ''
try {
  $nv = (& node --version) 2>$null
  if ($nv -match 'v(\d+)\.') { $nodeMajor = [int]$Matches[1] }
} catch {}
if ($nodeMajor -ge 18) {
  Write-Ok "Node $nv"
} else {
  Assert-Winget
  if ($nodeMajor -gt 0) { Write-Warn2 "Node $nv — 너무 오래됨 (Vite 6는 Node 18+ 필요)" }
  else { Write-Info 'Node 미설치' }
  Write-Info 'winget으로 Node.js LTS 설치 중...'
  winget install --id OpenJS.NodeJS.LTS -e --accept-source-agreements --accept-package-agreements --silent | Out-Null
  Update-SessionPath
  $nv = (& node --version) 2>$null
  Write-Ok "Node $nv 설치 완료"
}

# ── 5~7. npm install / sharp / build ──────────────────────
Push-Location $repoRoot
try {
  Write-Step '5/7 npm 의존성 설치'
  Invoke-Npm @('install', '--legacy-peer-deps', '--no-fund', '--no-audit')
  Write-Ok 'npm install 완료'

  Write-Step '6/7 sharp 네이티브 모듈 (win32-x64 플랫폼 패키지)'
  if (-not (Test-Path (Join-Path $repoRoot 'node_modules\@img'))) {
    Write-Info '플랫폼 패키지 누락 — 명시적으로 재설치 중...'
    Invoke-Npm @('install', '--include=optional', '--os=win32', '--cpu=x64', '--legacy-peer-deps', '--no-fund', '--no-audit', 'sharp')
  }
  & node -e "require('sharp'); console.log('  sharp', require('sharp').versions.sharp, 'OK')"
  if ($LASTEXITCODE -ne 0) { throw 'sharp 네이티브 모듈 로드 실패' }
  Write-Ok 'sharp 정상 로드'

  Write-Step '7/7 프로젝트 빌드'
  Invoke-Npm @('run', 'build')
  Write-Ok '빌드 완료 → out/'
} finally {
  Pop-Location
}

# ── 완료 ──────────────────────────────────────────────────
Write-Host ''
Write-Host '###############################################' -ForegroundColor Green
Write-Host '#  환경 설정 완료                              #' -ForegroundColor Green
Write-Host '###############################################' -ForegroundColor Green
Write-Host ''
Write-Host '다음 단계:' -ForegroundColor Cyan
Write-Host '  1. 브리지 서버 기동:   npm run bridge'
Write-Host '  2. Figma 데스크톱 앱에서 플러그인 실행 (ws://localhost:8767 자동 연결)'
Write-Host '  3. 디자인 생성 시작'
Write-Host ''
Write-Host "Python 경로: $python" -ForegroundColor Gray
Write-Host '  figma_mcp_client.py 호출 시 이 전체 경로를 사용하세요.' -ForegroundColor Gray
Write-Host '  (PATH의 python3/python 은 Microsoft Store 별칭이라 동작하지 않음)' -ForegroundColor Gray
Write-Host ''
