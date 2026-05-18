#!/usr/bin/env python3
"""이미 빌드된 화면의 TEXT 노드 fill 바인딩을 fg-* → text-* 로 재바인딩.

post-fix sweep은 이미 바인딩된 fill을 건너뛰므로, 정책 변경(2026-05-18) 후
기존 화면을 갱신하려면 이 스크립트로 강제 재바인딩한다.
사용: python3 scripts/rebind_text_to_text_tokens.py <rootNodeId>
"""
import json
import re
import sys

import figma_mcp_client as fmc

FG_TO_TEXT = fmc._FG_TO_TEXT_SUFFIX


def main(root_id):
    fmc.ensure_session()
    rv = fmc.call_tool("get_local_variables", {})
    var_by_id = {v["id"]: v for v in json.loads(rv[0]["text"]).get("variables", [])}
    # text-* 토큰 이름 → 변수 id (figmaPath 또는 name 끝 세그먼트로 매칭)
    text_tok_id = {}
    for v in var_by_id.values():
        last = (v.get("name") or "").rsplit("/", 1)[-1]
        if last.startswith("text-"):
            text_tok_id[last] = v["id"]

    rt = fmc.call_tool("get_nodes_info", {"nodeIds": [root_id]})
    tree = json.loads(rt[0]["text"])[0].get("document") or {}

    to_bind = []
    skipped_no_text_var = []

    def walk(n):
        nid = n.get("id") or ""
        if nid.startswith("I"):
            return  # 인스턴스 내부는 건드리지 않음
        if n.get("type") == "TEXT":
            fills = n.get("fills") or []
            if fills and isinstance(fills[0], dict):
                bv = fills[0].get("boundVariables") or {}
                cb = bv.get("color") if isinstance(bv, dict) else None
                if isinstance(cb, dict) and cb.get("id"):
                    vid = cb["id"]
                    vname = (var_by_id.get(vid) or {}).get("name", "")
                    last = vname.rsplit("/", 1)[-1]
                    mapped = FG_TO_TEXT.get(last)
                    if mapped:
                        if mapped in text_tok_id:
                            to_bind.append({
                                "nodeId": nid,
                                "bindings": {"fills/0": "Colors/Text/" + mapped},
                            })
                        else:
                            skipped_no_text_var.append((nid, last, mapped))
        for c in n.get("children") or []:
            walk(c)

    walk(tree)
    print(f"재바인딩 대상 TEXT 노드: {len(to_bind)}건")
    if skipped_no_text_var:
        print(f"⚠️ text- 변수 없음 {len(skipped_no_text_var)}건: {skipped_no_text_var[:5]}")

    succeeded = 0
    for i in range(0, len(to_bind), 50):
        batch = to_bind[i:i + 50]
        r = fmc.call_tool("batch_bind_variables", {"items": batch})
        try:
            d = json.loads(r[0]["text"])
            succeeded += d.get("succeeded", 0)
        except Exception:
            pass
    print(f"✅ 재바인딩 완료: {succeeded}/{len(to_bind)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "17302:27839")
