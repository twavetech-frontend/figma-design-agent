#!/usr/bin/env python3
"""오래된 디자인 빌드 산출물 자동 정리 — 생성 7일 경과 시 삭제.

왜: blueprint·빌드 산출물(frontend spec json, QA 스크린샷, 레퍼런스 썸네일)이
무한 누적돼 레포/디스크가 비대해진다. '디자인 생성 준비'(setup-mac.sh /
setup-windows.ps1) 의 **마지막 프로세스**로 자동 호출돼 7일 지난 것을 비운다.

기준: 파일 mtime. blueprint·산출물은 생성 후 수정하지 않으므로 mtime ≈ 생성일
      (생성일을 그대로 보장하는 크로스플랫폼 API 가 없어 mtime 으로 근사).

보존(절대 삭제 안 함):
  - 소스 템플릿: blueprint_templates.json, blueprint_unified_imin_home.json
  - 소스/입력: gen_*.py · spec_*.json · wireframe_content_*.json · archetype_specs/
    (애초에 아래 TARGETS 패턴에 안 잡힘)

사용:
  python3 scripts/cleanup_old_blueprints.py            # 7일 경과분 삭제
  python3 scripts/cleanup_old_blueprints.py --dry-run  # 삭제 예정만 출력
  TTL_DAYS=14 python3 scripts/cleanup_old_blueprints.py # TTL 환경변수 override
"""
import glob
import os
import shutil
import sys
import time

TTL_DAYS = int(os.environ.get("TTL_DAYS", "7"))
TTL_SEC = TTL_DAYS * 86400
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 패턴에 잡혀도 절대 삭제하지 않는 소스 파일
KEEP = {
    "blueprint_templates.json",
    "blueprint_unified_imin_home.json",
}

# 7일 경과 시 삭제 대상 (재생성 가능한 산출물)
TARGETS = [
    "scripts/blueprint_*.json",   # 디자인 blueprint (gen 스크립트/와이어에서 재생성)
    "json/*.json",                # 빌드 frontend spec 산출물
    "scripts/ref_thumbnails/*",   # 레퍼런스 썸네일 (ref_search 재생성)
    "scripts/qa_screenshots/*",   # QA 스크린샷 (빌드 self-verify 재생성)
]


def _size(path):
    if os.path.isdir(path):
        return sum(os.path.getsize(os.path.join(d, f))
                   for d, _, fs in os.walk(path) for f in fs)
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _remove(path):
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)
    else:
        try:
            os.remove(path)
        except OSError:
            pass


def main(dry_run=False):
    now = time.time()
    deleted = freed = 0
    for pattern in TARGETS:
        for path in glob.glob(os.path.join(ROOT, pattern)):
            base = os.path.basename(path)
            if base in KEEP:
                continue
            # PRD 입력 파일은 json/ 에 섞여 있어도 절대 삭제 안 함 (사용자 소스)
            if "PRD" in base.upper():
                continue
            try:
                age = now - os.path.getmtime(path)
            except OSError:
                continue
            if age < TTL_SEC:
                continue
            size = _size(path)
            rel = os.path.relpath(path, ROOT)
            if dry_run:
                print(f"  [dry-run] {int(age // 86400)}일 경과  {rel}")
            else:
                _remove(path)
                print(f"  [삭제] {int(age // 86400)}일 경과  {rel}")
            deleted += 1
            freed += size
    head = "삭제 예정" if dry_run else "정리 완료"
    print(f"🧹 오래된 산출물 {head}: {deleted}건 / {freed // 1024}KB "
          f"(생성 {TTL_DAYS}일 경과 blueprint·json·QA·썸네일)")
    return deleted


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
