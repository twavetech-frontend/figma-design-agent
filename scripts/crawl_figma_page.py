#!/usr/bin/env python3
"""활성 페이지 크롤러 → index_figma_page.py 입력 XML (2026-09-04 영구화).

공식 Figma MCP get_metadata 가 세션에 없을 때의 대체 경로 (memory: page-index-crawler-fallback).
브리지 도구를 in-process(fc.call_tool)로 호출:
  - PAGE / SECTION / 거대 FRAME(폭 > max_w) → get_node_info children 재귀
  - 화면급 FRAME(min_w~max_w) → get_node_tree(maxDepth 14) 로 전체 트리 (0.2~0.3s)
출력: <tag id name x y width height> 들여쓰기 XML (TEXT 는 characters 를 name 으로)

사용:
  python3 scripts/crawl_figma_page.py --out scripts/_figma_page_v216.xml [--page 0:1]
  python3 scripts/index_figma_page.py scripts/_figma_page_v216.xml --tag v216
"""
import json
import os
import sys
import time
from xml.sax.saxutils import quoteattr

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import figma_mcp_client as fc  # noqa: E402

CALL_TIMEOUT = float(os.environ.get("CRAWL_CALL_TIMEOUT", "25"))


RECONNECT_WAIT = float(os.environ.get("CRAWL_RECONNECT_WAIT", "90"))
FAILS = []  # (tool, nodeId, reason) — 조용히 삼키지 않고 끝에 요약 + exit 1


def call(name, args, timeout=None, _retry=True):
    """fc.call_tool 과 동일하되 per-call timeout (기본 25s). 실패/타임아웃 시 None.
    (2026-09-04: 거대 화면 1개의 get_node_tree 가 300s 를 물고 크롤 전체를 죽인 회귀 방지)
    🔴 2026-09-04 회귀 수정: MCP error 응답(특히 플러그인 순간 단절 'Not connected to Figma
    plugin')을 로그 없이 None 으로 삼켜 섹션 12개가 통째로 빠진 채 '성공'(95/921 화면)으로
    보고됐다. 이제 에러를 출력·집계하고, 플러그인 단절이면 재접속을 기다렸다가 재시도한다."""
    payload = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
               "params": {"name": name, "arguments": args}}
    headers = {"Content-Type": "application/json"}
    sid = fc.get_session_id()
    if sid:
        headers["mcp-session-id"] = sid
    try:
        resp = fc._http.post(fc.MCP_URL, json=payload, headers=headers, timeout=timeout or CALL_TIMEOUT)
        data = resp.json()
    except Exception as e:  # timeout 포함
        print(f"  ⚠ {name} {args.get('nodeId')} 실패: {type(e).__name__}", flush=True)
        FAILS.append((name, args.get("nodeId"), type(e).__name__))
        return None
    err = data.get("error")
    content = (data.get("result") or {}).get("content")
    # 도구 에러는 result.isError + content 텍스트로 오기도 한다
    if not err and (data.get("result") or {}).get("isError"):
        err = _txt(content)
    if err:
        msg = err.get("message") if isinstance(err, dict) else str(err)
        # 🔴 2026-09-11: 단절 순간 이미 날아가 있던 콜은 "Plugin disconnected" 로 돌아온다
        #    ("Not connected" 만 잡으면 그 1건이 재시도 없이 실패 집계 → 크롤 불완전 오판)
        if _retry and ("Not connected" in msg or "Plugin disconnected" in msg
                       or "Must join a channel" in msg):
            if _wait_plugin_reconnect():
                return call(name, args, timeout, _retry=False)
        print(f"  ⚠ {name} {args.get('nodeId')} MCP error: {msg[:120]}", flush=True)
        FAILS.append((name, args.get("nodeId"), msg[:120]))
        return None
    return content


def _wait_plugin_reconnect():
    """플러그인 단절(1001 등) 시 RECONNECT_WAIT 초까지 get_document_info 폴링으로 재접속 대기."""
    print(f"  ⏳ 플러그인 단절 감지 — 최대 {int(RECONNECT_WAIT)}s 재접속 대기…", flush=True)
    t0 = time.time()
    while time.time() - t0 < RECONNECT_WAIT:
        time.sleep(2)
        n_before = len(FAILS)
        r = call("get_document_info", {}, timeout=10, _retry=False)
        del FAILS[n_before:]
        if r is not None:
            print(f"  ✓ 플러그인 재접속 ({round(time.time() - t0)}s)", flush=True)
            return True
    print("  ✗ 플러그인 재접속 실패 — 남은 노드는 건너뜀", flush=True)
    return False


def _txt(r):
    if isinstance(r, list):
        return "".join(x.get("text", "") for x in r if isinstance(x, dict))
    if isinstance(r, dict):
        return json.dumps(r, ensure_ascii=False)
    return str(r)


def _node(r):
    try:
        d = json.loads(_txt(r))
    except Exception:
        return None
    if isinstance(d, dict) and isinstance(d.get("node"), dict):
        d = d["node"]
    return d if isinstance(d, dict) else None


def _line(n, depth):
    tag = str(n.get("type", "node")).lower()
    name = n.get("characters") if n.get("type") == "TEXT" and n.get("characters") else n.get("name", "")
    name = str(name).replace("\n", " ")[:120]
    attrs = [f"id={quoteattr(str(n.get('id', '')))}", f"name={quoteattr(name)}"]
    for k in ("x", "y", "width", "height"):
        v = n.get(k)
        if isinstance(v, (int, float)):
            attrs.append(f'{k}="{round(v, 1)}"')
    return "  " * depth + f"<{tag} {' '.join(attrs)}>"


def _walk_tree(n, depth, out):
    out.append(_line(n, depth))
    for c in n.get("children") or []:
        _walk_tree(c, depth + 1, out)


def crawl(page_id="0:1", min_w=360, max_w=430, log=print):
    out, stats = [], {"info": 0, "tree": 0, "screens": 0, "empty_tree": 0}
    t0 = time.time()

    def rec(node_id, depth, stub=None):
        n = _node(call("get_node_info", {"nodeId": node_id}))
        stats["info"] += 1
        if not n:
            stats["failed"] = stats.get("failed", 0) + 1
            if stub is not None:
                out.append(_line(stub, depth).replace(">", ' crawl="failed">', 1))
            return
        out.append(_line(n, depth))
        for c in n.get("children") or []:
            ctype, w = c.get("type"), c.get("width") or 0
            if ctype in ("SECTION", "PAGE") or (ctype in ("FRAME", "GROUP", "COMPONENT", "INSTANCE") and w > max_w):
                rec(c["id"], depth + 1, stub=c)
            elif ctype in ("FRAME", "COMPONENT", "INSTANCE", "GROUP") and min_w <= w <= max_w:
                t = _node(call("get_node_tree", {"nodeId": c["id"], "maxDepth": 14}))
                stats["tree"] += 1
                if t is None:
                    # 타임아웃/실패 → 얕은 get_node_info 재귀(depth 2)로 대체
                    stats["fallback"] = stats.get("fallback", 0) + 1
                    _shallow(c["id"], depth + 1, 2)
                    continue
                if t and t.get("children"):
                    # 위치는 부모 기준 좌표를 유지(get_node_tree 가 좌표를 안 주는 경우 보강)
                    for k in ("x", "y", "width", "height"):
                        t.setdefault(k, c.get(k))
                    _walk_tree(t, depth + 1, out)
                    stats["screens"] += 1
                else:
                    stats["empty_tree"] += 1
                    out.append(_line(c, depth + 1))
            else:
                out.append(_line(c, depth + 1))
            if (stats["info"] + stats["tree"]) % 100 == 0:
                log(f"  … calls={stats['info'] + stats['tree']} screens={stats['screens']} {round(time.time() - t0)}s", flush=True)

    def _shallow(node_id, depth, remain):
        n = _node(call("get_node_info", {"nodeId": node_id}))
        stats["info"] += 1
        if not n:
            return
        out.append(_line(n, depth))
        for c in n.get("children") or []:
            if remain > 1 and c.get("children") is not None and c.get("type") in ("FRAME", "GROUP", "INSTANCE", "COMPONENT", "SECTION"):
                _shallow(c["id"], depth + 1, remain - 1)
            else:
                out.append(_line(c, depth + 1))

    rec(page_id, 0)
    stats["elapsed_s"] = round(time.time() - t0, 1)
    return "\n".join(out) + "\n", stats


def main():
    args = sys.argv[1:]
    if "-h" in args or "--help" in args:
        print(__doc__)
        return 0
    page = args[args.index("--page") + 1] if "--page" in args else "0:1"
    outp = args[args.index("--out") + 1] if "--out" in args else os.path.join(HERE, "_figma_page.xml")
    xml, stats = crawl(page)
    stats["failed"] = len(FAILS)
    with open(outp, "w", encoding="utf-8") as f:
        f.write(xml)
    print(f"✓ XML → {outp}  {json.dumps(stats)}")
    if FAILS:
        print(f"✗ 크롤 불완전 — 실패 {len(FAILS)}건 (섹션/화면이 통째로 빠졌을 수 있음). "
              f"플러그인 연결 확인 후 재실행할 것. 예: {FAILS[:3]}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
