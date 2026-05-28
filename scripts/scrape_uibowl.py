#!/usr/bin/env python3
"""Scrape uibowl.io for an app's full screen catalog.

Direct API approach (no headless browser needed):
  GET /api/v2/apps/search?keyword=<APP>&exact=true&componentCodes=[]&type=MOBILE
  → returns app + nested patterns + images

Usage:
  python3 scripts/scrape_uibowl.py 토스
  python3 scripts/scrape_uibowl.py 토스 references/uibowl/toss

Output structure:
  <outputDir>/
    index.json     — array of {imgId, patternName, patternCode, patternCodeName,
                                imageUrl, localPath, app}
    <imgId>.png    — image files
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


def _auth_headers() -> dict:
    """Build request headers; if UIBOWL_SESSION env var is set, include
    the auth cookie that unlocks the full catalog (≫ unauthenticated preview).
    """
    h = {"User-Agent": "Mozilla/5.0"}
    token = os.environ.get("UIBOWL_SESSION")
    if token:
        h["Cookie"] = f"__Secure-next-auth.session-token={token}"
    return h


def fetch_apps(app_name: str) -> list:
    """Fetch all snapshots of an app via /apps/search."""
    url = (
        "https://uibowl.io/api/v2/apps/search?"
        f"keyword={urllib.parse.quote(app_name)}"
        "&exact=true&componentCodes=[]&type=MOBILE"
    )
    req = urllib.request.Request(url, headers=_auth_headers())
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    if not data.get("ok"):
        raise SystemExit(f"API not OK: {data}")
    apps = data.get("data") or []
    if not apps:
        raise SystemExit(f"No app found for keyword '{app_name}'")
    return apps


def fetch_pattern_codes(app_name: str) -> list:
    """Get all pattern codes (categories) the app has, with counts."""
    url = (
        "https://uibowl.io/api/v2/codes?"
        f"type=PAT&exact=true&appType=MOBILE&"
        f"appName={urllib.parse.quote(app_name)}"
    )
    req = urllib.request.Request(url, headers=_auth_headers())
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode())
        return data.get("data") or []
    except Exception as e:
        print(f"[scrape] codes fetch failed: {e}")
        return []


def fetch_patterns_by_code(pattern_code: int, limit: int = 50) -> list:
    """Fetch patterns (each with images) filtered by a specific pattern code."""
    qs = (
        f"sortField=createdAt&categoryCodes=%5B%5D&componentCodes=%5B%5D&"
        f"patternCodes=%5B{pattern_code}%5D&limit={limit}&offset=0&"
        f"single=false&type=MOBILE"
    )
    url = f"https://uibowl.io/api/v2/apps/patterns?{qs}"
    req = urllib.request.Request(url, headers=_auth_headers())
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode())
        return data.get("data") or []
    except Exception as e:
        print(f"  [pattern {pattern_code}] fetch failed: {e}")
        return []


def download_image(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    # Some uibowl image paths contain spaces or other unsafe chars — quote
    # the path component while leaving scheme/host alone.
    parts = urllib.parse.urlsplit(url)
    safe_path = urllib.parse.quote(parts.path)
    safe_url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, safe_path,
                                        parts.query, parts.fragment))
    req = urllib.request.Request(safe_url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            dest.write_bytes(r.read())
        return True
    except Exception as e:
        print(f"  [dl FAIL] {url} → {e}", file=sys.stderr)
        if dest.exists():
            dest.unlink()
        return False


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    app_name = sys.argv[1]
    out_dir = Path(sys.argv[2] if len(sys.argv) > 2
                   else f"references/uibowl/{app_name}")
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"[scrape] target: {app_name}")
    print(f"[scrape] output: {out_dir}")

    apps = fetch_apps(app_name)
    app_ids = {a.get("id") for a in apps if a.get("id")}
    print(f"[scrape] snapshots: {len(apps)}")
    for a in apps:
        print(f"  - {a.get('id')} scrapped={a.get('scrapped_date')} "
              f"patterns={len(a.get('patterns') or [])}")

    # Stage 1: collect from /apps/search snapshots (preview patterns)
    records = []
    for app in apps:
        patterns = app.get("patterns") or []
        for pat in patterns:
            for img in (pat.get("images") or []):
                records.append({
                    "imgId": img.get("id"),
                    "imageUrl": img.get("url"),
                    "patternName": pat.get("patternName") or "",
                    "patternCode": pat.get("patternCode"),
                    "patternCodeName": pat.get("patternCodeName") or "",
                    "description": img.get("description") or "",
                    "sort": img.get("sort"),
                    "createdAt": img.get("createdAt"),
                    "appId": app.get("id"),
                    "appName": app.get("name"),
                    "scrapedDate": app.get("scrapped_date"),
                    "categoryName": app.get("categoryName"),
                })

    # Stage 2: for each pattern code the app has, hit /apps/patterns and
    # filter by appId — yields the full catalog beyond the search preview.
    codes = fetch_pattern_codes(app_name)
    print(f"[scrape] pattern codes: {len(codes)} "
          f"(total count={sum(c.get('count',0) for c in codes)})")
    for code_entry in codes:
        code = code_entry.get("code")
        cname = code_entry.get("name", "")
        cnt = code_entry.get("count", 0)
        if not code or cnt == 0:
            continue
        # Fetch patterns by this code; results may include other apps too,
        # so filter by app id
        patterns = fetch_patterns_by_code(code, limit=max(20, cnt * 4))
        added = 0
        for pat in patterns:
            pat_app_id = (pat.get("app") or {}).get("id")
            if pat_app_id not in app_ids:
                continue
            for img in (pat.get("images") or []):
                records.append({
                    "imgId": img.get("id"),
                    "imageUrl": img.get("url"),
                    "patternName": pat.get("patternName") or "",
                    "patternCode": pat.get("patternCode"),
                    "patternCodeName": pat.get("patternCodeName") or "",
                    "description": img.get("description") or "",
                    "sort": img.get("sort"),
                    "createdAt": img.get("createdAt"),
                    "appId": pat_app_id,
                    "appName": (pat.get("app") or {}).get("name") or app_name,
                    "categoryName": (pat.get("app") or {}).get("categoryName"),
                })
                added += 1
        print(f"  [code {code} {cname}] +{added} (count metadata: {cnt})")

    # Dedupe by imgId
    seen = set()
    deduped = []
    for r in records:
        if r["imgId"] in seen:
            continue
        seen.add(r["imgId"])
        deduped.append(r)
    records = deduped
    print(f"[scrape] images (deduped): {len(records)}")

    # Download in parallel
    def _do(rec):
        url = rec["imageUrl"]
        if not url:
            return rec, False
        ext = (Path(urllib.parse.urlparse(url).path).suffix or ".png").lower()
        safe = "".join(c if c.isalnum() or c in "_-" else "_"
                       for c in (rec["imgId"] or ""))
        local = out_dir / f"{safe}{ext}"
        ok = download_image(url, local)
        if ok:
            rec["localPath"] = str(local.relative_to(out_dir.parent.parent))
        return rec, ok

    downloaded = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = [ex.submit(_do, r) for r in records]
        for f in as_completed(futures):
            rec, ok = f.result()
            if ok:
                downloaded += 1
                if downloaded % 20 == 0:
                    print(f"  [dl] {downloaded}/{len(records)}")
    print(f"[scrape] downloaded: {downloaded}/{len(records)}")

    primary = apps[0] if apps else {}
    index_path = out_dir / "index.json"
    index_path.write_text(json.dumps({
        "appName": primary.get("name"),
        "appId": primary.get("id"),
        "categoryName": primary.get("categoryName"),
        "iconImg": primary.get("iconImg"),
        "MAU": primary.get("MAU"),
        "snapshots": [{"id": a.get("id"), "scrapped_date": a.get("scrapped_date")}
                      for a in apps],
        "scrapedAt": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "count": downloaded,
        "records": [r for r in records if r.get("localPath")],
    }, indent=2, ensure_ascii=False))
    print(f"[scrape] index: {index_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
