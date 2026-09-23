#!/usr/bin/env python3
"""flow_arrow_catalog.py — flow 화살표 종류 카탈로그 (규칙 0-FLOW-2, 2026-09-23 사용자 룰).

사용자: *"Flow 를 그릴 때 올바른 arrow 사용에 대한 규칙 및 코드가 있어야 한다. 하나씩 선택하고 용도를 말해 주면
그에 대한 사용 규칙 및 코드를 작성."* — `my tool box` 의 커넥터 템플릿마다 **용도(type)** 를 등록해 두고,
`flow` spec 의 edge 에 `type` 을 주면 그 용도의 템플릿만 복제해서 쓴다(모양·굵기·색·캡·점선은 템플릿이 정답,
코드가 스타일을 만들지 않는다).

카탈로그: scripts/flow_arrow_catalog.json
{
  "toolbox": "4802:104148",
  "arrows": {
    "<type>": {"templateId": "4802:104153", "purpose": "…", "when": ["…"], "notWhen": ["…"],
               "style": {"strokeWeight": 4, "color": "#757575", "dash": null, "lineType": "ELBOWED",
                         "startCap": "CIRCLE_FILLED", "endCap": "ARROW_EQUILATERAL"},   # 등록 시 실측 스냅샷(문서용)
               "defaults": {"lineType": "ELBOWED", "fromMagnet": "RIGHT", "toMagnet": "LEFT"},
               "labelHint": "…"}
  },
  "default": "<type>"        # edge.type 생략 시
}

CLI:
  python3 scripts/figma_mcp_client.py arrow-register <type> --purpose "…" [--when "a;b"] [--not-when "c"]
        [--label-hint "…"] [--node <connectorId>] [--default]      # --node 생략 시 Figma 선택 노드
  python3 scripts/figma_mcp_client.py arrow-list
등록 시 선택된 커넥터의 스타일(굵기·색·점선·캡·라인타입)을 스냅샷으로 저장하고, 툴박스 밖 노드면 경고한다.
"""
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

CATALOG_PATH = os.path.join(_HERE, 'flow_arrow_catalog.json')


def load():
    if not os.path.exists(CATALOG_PATH):
        return {'toolbox': None, 'arrows': {}, 'default': None}
    return json.load(open(CATALOG_PATH, encoding='utf-8'))


def save(cat):
    json.dump(cat, open(CATALOG_PATH, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)


def _hex(c):
    if not c:
        return None
    return '#%02x%02x%02x' % (round(c.get('r', 0) * 255), round(c.get('g', 0) * 255), round(c.get('b', 0) * 255))


def style_snapshot(info):
    """get_node_info(CONNECTOR) → 문서용 스타일 스냅샷."""
    st = (info.get('strokes') or [{}])[0]
    return {'strokeWeight': info.get('strokeWeight'), 'color': _hex(st.get('color')), 'opacity': st.get('opacity'),
            'dash': info.get('dashPattern'), 'lineType': info.get('connectorLineType'),
            'startCap': info.get('connectorStartStrokeCap'), 'endCap': info.get('connectorEndStrokeCap')}


def template_for(cat, arrow_type):
    """edge.type → (templateId, entry). 미등록이면 KeyError(등록된 type 목록 포함)."""
    arrows = cat.get('arrows') or {}
    t = arrow_type or cat.get('default')
    if not t or t not in arrows:
        raise KeyError(f"화살표 type '{arrow_type}' 미등록 — 등록된 type: {sorted(arrows)} (arrow-register 로 추가)")
    return arrows[t]['templateId'], arrows[t]


def register(cat, key, template_id, purpose, when=(), not_when=(), label_hint=None, style=None, defaults=None, make_default=False):
    if not key or not purpose:
        raise ValueError('type 키와 purpose 는 필수')
    entry = {'templateId': template_id, 'purpose': purpose, 'when': list(when), 'notWhen': list(not_when),
             'style': style or {}, 'defaults': defaults or {'lineType': 'ELBOWED', 'fromMagnet': 'RIGHT', 'toMagnet': 'LEFT'},
             'labelHint': label_hint or ''}
    cat.setdefault('arrows', {})[key] = entry
    if make_default or not cat.get('default'):
        cat['default'] = key
    return entry


def describe(cat):
    lines = [f"flow 화살표 카탈로그 — {len(cat.get('arrows') or {})}종 (기본: {cat.get('default')}, 툴박스 {cat.get('toolbox')})"]
    for k, e in (cat.get('arrows') or {}).items():
        s = e.get('style') or {}
        lines.append(f"  {k:14s} {e['templateId']:14s} {e['purpose']}")
        lines.append(f"  {'':14s} 스타일 {s.get('strokeWeight')}px {s.get('color')} dash={s.get('dash')} {s.get('lineType')} {s.get('startCap')}→{s.get('endCap')}")
        if e.get('when'):
            lines.append(f"  {'':14s} 쓸 때: " + ' / '.join(e['when']))
        if e.get('notWhen'):
            lines.append(f"  {'':14s} 쓰지 말 때: " + ' / '.join(e['notWhen']))
        if e.get('labelHint'):
            lines.append(f"  {'':14s} 라벨: {e['labelHint']}")
    return '\n'.join(lines)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ('-h', '--help'):
        print(__doc__)
        return 1
    cat = load()
    if argv[0] == 'list':
        print(describe(cat))
        return 0
    if argv[0] != 'register':
        print(__doc__)
        return 1
    args = argv[1:]
    key = next((a for a in args if not a.startswith('--')), None)

    def opt(name, default=None):
        if name in args:
            i = args.index(name)
            return args[i + 1] if i + 1 < len(args) else default
        return default
    import figma_mcp_client as fc

    def call(t, a):
        return fc.parse_content(fc.call_tool(t, a)).get('json') or {}
    fc.ensure_session()
    nid = opt('--node')
    if not nid:
        sel = call('get_selection', {})
        nodes = sel.get('nodes') or sel.get('selection') or []
        if len(nodes) != 1 or nodes[0].get('type') != 'CONNECTOR':
            print(f'커넥터 1개를 선택하세요 (현재 {[(n.get("type"), n.get("name")) for n in nodes]})')
            return 1
        nid = nodes[0]['id']
    info = call('get_node_info', {'nodeId': nid})
    if info.get('type') != 'CONNECTOR':
        print(f'{nid} 는 CONNECTOR 가 아님 ({info.get("type")})')
        return 1
    if cat.get('toolbox') is None:
        import flow_connect as FC
        cat['toolbox'] = FC.find_toolbox(call)
    if cat.get('toolbox') and info.get('parentId') != cat['toolbox']:
        print(f"⚠️ {nid} 의 부모({info.get('parentId')})가 툴박스({cat['toolbox']})가 아님 — 템플릿은 'my tool box' 안에 있어야 복제 원본이 보존됨")
    when = [x.strip() for x in (opt('--when') or '').split(';') if x.strip()]
    not_when = [x.strip() for x in (opt('--not-when') or '').split(';') if x.strip()]
    entry = register(cat, key, nid, opt('--purpose'), when, not_when, opt('--label-hint'), style_snapshot(info), make_default='--default' in args)
    save(cat)
    print(f"✓ 등록 {key} ← {nid}: {entry['purpose']}")
    print(describe(cat))
    return 0


if __name__ == '__main__':
    sys.exit(main())
