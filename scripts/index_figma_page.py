#!/usr/bin/env python3
"""Figma 페이지 메타데이터 XML → 화면/에셋/텍스트 인덱스 (2026-09-02 사용자 지시).

배경: "디자인 생성 준비" 때 플러그인이 실행된 파일의 페이지 전체를 스캔해 특징을
저장해 두면, 변환 요청 시 기존 DS본/벡터 에셋 탐색이 즉시 된다 (친구초대_랭킹_DS 를
못 찾아 crop 메달을 쓴 사고의 재발 방지 — capture-1to1 메모리 4항 참조).

입력: Figma MCP `get_metadata(fileKey, nodeId=<pageId>)` 결과 텍스트 파일
      (tool-results 의 JSON array [{type,text}] 또는 순수 XML 텍스트 모두 허용)
출력: scripts/_figma_index_<tag>.json
  { "screens":  [{id, name, section, x, y, w, h}],   # 화면급 FRAME (기본 w 360~430)
    "sections": [{id, name, depth}],
    "assets":   [{id, name, kind, screen}],           # ico_*/img_*/btn_*/card_* 등
    "texts":    [{id, chars, screen}] }               # 텍스트 노드 이름(=내용 요약)

사용:
  python3 scripts/index_figma_page.py <xml파일> [--tag v216] [--min-w 360] [--max-w 430]
검색:
  python3 scripts/index_figma_page.py --grep 랭킹 [--tag v216]
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ASSET_PREFIXES = ("ico_", "ic_", "img_", "btn_", "card_", "logo_")
TAG_RE = re.compile(
    r'^(\s*)<([a-z-]+)\s+id="([^"]+)"\s+name="([^"]*)"'
    r'(?:[^>]*?x="(-?[\d.]+)")?(?:[^>]*?y="(-?[\d.]+)")?'
    r'(?:[^>]*?width="([\d.]+)")?(?:[^>]*?height="([\d.]+)")?'
)


def load_xml_text(path):
    raw = open(path, encoding="utf-8").read()
    if raw.lstrip().startswith("["):
        try:
            return "".join(x.get("text", "") for x in json.loads(raw))
        except Exception:
            pass
    return raw


def build_index(xml_text, min_w=360, max_w=430):
    screens, sections, assets, texts = [], [], [], []
    section_stack = []  # (indent, name)
    screen_stack = []   # (indent, name)
    for line in xml_text.splitlines():
        m = TAG_RE.match(line)
        if not m:
            continue
        indent, tag, nid, name, x, y, w, h = m.groups()
        ind = len(indent)
        while section_stack and section_stack[-1][0] >= ind:
            section_stack.pop()
        while screen_stack and screen_stack[-1][0] >= ind:
            screen_stack.pop()
        cur_section = " > ".join(s[1] for s in section_stack) or None
        cur_screen = screen_stack[-1][1] if screen_stack else None
        wf = float(w) if w else None
        if tag == "section":
            sections.append({"id": nid, "name": name, "depth": len(section_stack)})
            section_stack.append((ind, name))
        elif tag in ("frame", "instance", "component") and wf and min_w <= wf <= max_w and not screen_stack:
            screens.append({"id": nid, "name": name, "section": cur_section,
                            "x": float(x or 0), "y": float(y or 0), "w": wf, "h": float(h or 0)})
            screen_stack.append((ind, name))
        elif tag == "text":
            texts.append({"id": nid, "chars": name, "screen": cur_screen})
        lname = name.lower()
        if lname.startswith(ASSET_PREFIXES):
            assets.append({"id": nid, "name": name, "kind": tag, "screen": cur_screen})
    return {"screens": screens, "sections": sections, "assets": assets, "texts": texts}


def index_path(tag):
    return os.path.join(HERE, f"_figma_index_{tag}.json")


def cmd_grep(tag, query):
    p = index_path(tag)
    if not os.path.exists(p):
        print(f"인덱스 없음: {p} — 먼저 XML 로 인덱스를 생성할 것")
        return 1
    idx = json.load(open(p, encoding="utf-8"))
    q = query.lower()
    for kind in ("screens", "sections", "assets"):
        for it in idx[kind]:
            if q in (it.get("name") or "").lower():
                print(f"[{kind[:-1]}] {it['id']} {it['name']!r}"
                      + (f" (section: {it.get('section')})" if it.get("section") else ""))
    seen_screens = set()
    for it in idx["texts"]:
        if q in (it.get("chars") or "").lower():
            key = it.get("screen") or it["id"]
            if key in seen_screens:
                continue
            seen_screens.add(key)
            print(f"[text] {it['id']} {it['chars']!r} (screen: {it.get('screen')})")
    return 0


def main():
    args = sys.argv[1:]
    tag = "default"
    if "--tag" in args:
        i = args.index("--tag")
        tag = args[i + 1]
        del args[i:i + 2]
    if args and args[0] == "--grep":
        sys.exit(cmd_grep(tag, " ".join(args[1:])))
    if not args:
        print(__doc__)
        sys.exit(1)
    min_w, max_w = 360, 430
    if "--min-w" in args:
        i = args.index("--min-w"); min_w = float(args[i + 1]); del args[i:i + 2]
    if "--max-w" in args:
        i = args.index("--max-w"); max_w = float(args[i + 1]); del args[i:i + 2]
    xml = load_xml_text(args[0])
    idx = build_index(xml, min_w, max_w)
    out = index_path(tag)
    json.dump(idx, open(out, "w", encoding="utf-8"), ensure_ascii=False)
    print(f"✓ {out} — 화면 {len(idx['screens'])} / 섹션 {len(idx['sections'])} / "
          f"에셋 {len(idx['assets'])} / 텍스트 {len(idx['texts'])}")


if __name__ == "__main__":
    main()
