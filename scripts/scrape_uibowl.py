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


def fetch_apps(app_name: str) -> list:
    """Fetch all snapshots of an app (uibowl.io may have multiple per scrape date).

    Returns the full list — typically 1-4 snapshots per app, each carrying
    its own pattern set of images. We aggregate across all snapshots.
    """
    url = (
        "https://uibowl.io/api/v2/apps/search?"
        f"keyword={urllib.parse.quote(app_name)}"
        "&exact=true&componentCodes=[]&type=MOBILE"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    if not data.get("ok"):
        raise SystemExit(f"API not OK: {data}")
    apps = data.get("data") or []
    if not apps:
        raise SystemExit(f"No app found for keyword '{app_name}'")
    return apps


def download_image(url: str, dest: Path) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        return True
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
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
    print(f"[scrape] snapshots: {len(apps)}")
    for a in apps:
        print(f"  - {a.get('id')} scrapped={a.get('scrapped_date')} "
              f"patterns={len(a.get('patterns') or [])}")

    # Flatten across all snapshots
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
