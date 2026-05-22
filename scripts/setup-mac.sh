#!/usr/bin/env bash
# Figma Design Agent — macOS 최초 환경 설정 (디자인 생성 준비)
#
# Git에서 레포를 클론한 macOS 사용자가 디자인 생성을 시작하기 전,
# 필요한 모든 의존성을 설치/검증한다. 멱등(idempotent) — 여러 번 실행해도 안전하며
# 이미 설치된 항목은 건너뛴다.
#
# 처리 항목:
#   1. Homebrew                       — Mac 패키지 매니저 (없으면 비대화식 설치)
#   2. Python 3                       — figma_mcp_client.py 실행용 (시스템/Homebrew 자동 선택)
#   3. Python 패키지: requests, Pillow (--install-rembg 시 rembg 추가)
#   4. Node.js 18+ (Homebrew)         — Vite 6는 Node 18+ 필수
#   5. npm 의존성 (--legacy-peer-deps, .npmrc에 설정됨)
#   6. sharp 네이티브 모듈 (darwin-arm64 / darwin-x64 플랫폼 패키지)
#   7. 프로젝트 빌드 (npm run build → out/)
#
# 사용법:
#   bash scripts/setup-mac.sh              # 기본 설치
#   bash scripts/setup-mac.sh --install-rembg  # rembg(배경 제거) 포함
#   npm run setup:mac                      # npm이 이미 있으면 이걸로도 가능

set -euo pipefail

INSTALL_REMBG=0
for arg in "$@"; do
  case "$arg" in
    --install-rembg|-r) INSTALL_REMBG=1 ;;
  esac
done

# ── 색상 ──────────────────────────────────────────────────
if [[ -t 1 ]]; then
  CYAN=$'\033[0;36m'; GREEN=$'\033[0;32m'; GRAY=$'\033[0;37m'
  YELLOW=$'\033[0;33m'; NC=$'\033[0m'
else
  CYAN=""; GREEN=""; GRAY=""; YELLOW=""; NC=""
fi

step()  { printf "\n${CYAN}=== %s ===${NC}\n" "$1"; }
ok()    { printf "  ${GREEN}[OK]${NC}   %s\n" "$1"; }
info()  { printf "  ${GRAY}[..]${NC}   %s\n" "$1"; }
warn()  { printf "  ${YELLOW}[WARN]${NC} %s\n" "$1"; }

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

printf "\n${CYAN}###############################################${NC}\n"
printf "${CYAN}#  Figma Design Agent - macOS 환경 설정        #${NC}\n"
printf "${CYAN}###############################################${NC}\n"

arch="$(uname -m)"
if [[ "$arch" == "arm64" ]]; then
  brew_prefix="/opt/homebrew"
  sharp_cpu="arm64"
else
  brew_prefix="/usr/local"
  sharp_cpu="x64"
fi

# ── 1. Homebrew ───────────────────────────────────────────
step '1/7 Homebrew 확인/설치'
if ! command -v brew >/dev/null 2>&1; then
  if [[ -x "$brew_prefix/bin/brew" ]]; then
    eval "$("$brew_prefix/bin/brew" shellenv)"
  fi
fi

if ! command -v brew >/dev/null 2>&1; then
  info 'Homebrew 미설치 — 비대화식 설치 시도 중 (관리자 비밀번호 입력이 필요할 수 있음)...'
  # 공식 설치 스크립트. NONINTERACTIVE=1은 prompt를 건너뛰지만, sudo 비밀번호는 필요할 수 있음.
  if NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"; then
    eval "$("$brew_prefix/bin/brew" shellenv)"
  else
    warn 'Homebrew 자동 설치 실패.'
    echo ''
    echo '아래 명령으로 직접 설치한 뒤 이 스크립트를 다시 실행하세요:'
    echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    echo ''
    exit 1
  fi
fi
ok "Homebrew: $(brew --version | head -n1)"

# ── 2. Python 3 ───────────────────────────────────────────
step '2/7 Python 3 확인/설치'
PYTHON=""
# Homebrew Python 우선 (시스템 Python은 PEP 668 제약이 있음)
for cand in python3.12 python3.11 python3.13 python3; do
  if path="$(command -v "$cand" 2>/dev/null)"; then
    case "$path" in
      *"$brew_prefix"*) PYTHON="$path"; break ;;
    esac
  fi
done
# Homebrew Python 없으면 시스템 python3로 폴백
if [[ -z "$PYTHON" ]] && command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
fi

if [[ -z "$PYTHON" ]] || ! "$PYTHON" --version 2>&1 | grep -qE 'Python 3\.(9|1[0-9])'; then
  info 'Python 3.12 설치 중 (brew install python@3.12)...'
  brew install python@3.12 >/dev/null
  PYTHON="$brew_prefix/opt/python@3.12/bin/python3.12"
fi
ok "Python: $PYTHON ($("$PYTHON" --version 2>&1))"

# ── 3. Python 패키지 ──────────────────────────────────────
step '3/7 Python 패키지 설치 (requests, Pillow)'
pip_install() {
  # PEP 668(externally-managed-environment) 대응:
  # --break-system-packages 우선, 실패 시 --user 폴백
  if ! "$PYTHON" -m pip install --upgrade --quiet --disable-pip-version-check \
       --break-system-packages "$@" 2>/dev/null; then
    "$PYTHON" -m pip install --upgrade --quiet --disable-pip-version-check --user "$@"
  fi
}
pip_install pip
pip_install requests Pillow
ok 'requests, Pillow 설치/갱신 완료'

if [[ "$INSTALL_REMBG" == "1" ]]; then
  info 'rembg 설치 중 (수 분 소요, 용량 큼)...'
  if pip_install rembg onnxruntime; then
    ok 'rembg 설치 완료'
  else
    warn 'rembg 설치 실패 — 로컬 아이콘 배경제거만 영향 (디자인 빌드는 정상)'
  fi
else
  info 'rembg 생략 (필요 시 --install-rembg 옵션으로 재실행)'
fi

# ── 4. Node.js ────────────────────────────────────────────
step '4/7 Node.js 18+ 확인/설치'
node_major=0
node_ver=""
if command -v node >/dev/null 2>&1; then
  node_ver="$(node --version)"
  node_major="$(printf '%s' "$node_ver" | sed -nE 's/^v([0-9]+)\..*/\1/p')"
  node_major="${node_major:-0}"
fi

if [[ "$node_major" -ge 18 ]]; then
  ok "Node $node_ver"
else
  if [[ "$node_major" -gt 0 ]]; then
    warn "Node $node_ver — 너무 오래됨 (Vite 6는 Node 18+ 필요)"
  else
    info 'Node 미설치'
  fi
  info 'Homebrew로 Node.js LTS 설치 중...'
  brew install node >/dev/null
  ok "Node $(node --version) 설치 완료"
fi

# ── 5~7. npm install / sharp / build ──────────────────────
cd "$repo_root"

step '5/7 npm 의존성 설치'
npm install --legacy-peer-deps --no-fund --no-audit
ok 'npm install 완료'

step "6/7 sharp 네이티브 모듈 (darwin-${sharp_cpu} 플랫폼 패키지)"
if [[ ! -d "node_modules/@img" ]]; then
  info '플랫폼 패키지 누락 — 명시적으로 재설치 중...'
  npm install --include=optional --os=darwin --cpu="$sharp_cpu" \
    --legacy-peer-deps --no-fund --no-audit sharp
fi
node -e "require('sharp'); console.log('  sharp', require('sharp').versions.sharp, 'OK')"
ok 'sharp 정상 로드'

step '7/7 프로젝트 빌드'
npm run build
ok '빌드 완료 → out/'

# ── 완료 ──────────────────────────────────────────────────
echo ''
printf "${GREEN}###############################################${NC}\n"
printf "${GREEN}#  환경 설정 완료                              #${NC}\n"
printf "${GREEN}###############################################${NC}\n"
echo ''
echo '다음 단계:'
echo '  1. 브리지 서버 기동:   npm run bridge'
echo '  2. Figma 데스크톱 앱에서 플러그인 실행 (ws://localhost:8767 자동 연결)'
echo '  3. 디자인 생성 시작'
echo ''
printf "${GRAY}Python 경로: %s${NC}\n" "$PYTHON"
printf "${GRAY}  figma_mcp_client.py 호출 시 이 전체 경로를 사용하세요.${NC}\n"
echo ''
