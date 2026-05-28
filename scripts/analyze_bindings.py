# -*- coding: utf-8 -*-
import json, sys

path = r'C:\Users\user\.claude\projects\C--imin-figma-design-agent\d1c8a590-9153-4a7d-ae3b-fa4f126eca0e\tool-results\mcp-figma-tools-get_nodes_info-1779378752391.txt'
data = json.load(open(path, encoding='utf-8'))

unbound = []   # list of dicts
bound = []     # list of dicts
no_bg = []     # frames with empty fills
tree_lines = []

def rgb(c):
    if c is None:
        return "n/a"
    r = round(c.get('r', 0) * 255)
    g = round(c.get('g', 0) * 255)
    b = round(c.get('b', 0) * 255)
    a = c.get('a', 1)
    return "rgb(%d,%d,%d) a=%s" % (r, g, b, a)

def first_solid(arr):
    if not arr:
        return None
    for f in arr:
        if f.get('type') == 'SOLID' and f.get('visible', True) != False:
            return f
    return None

def check(node, depth, parent_id):
    nid = node.get('id')
    name = node.get('name')
    ntype = node.get('type')
    tree_lines.append("%s%s  [%s]  %s  (parent: %s)" % ('  ' * depth, nid, ntype, name, parent_id))

    issues = []
    okparts = []

    # ---- FILL ----
    fills = node.get('fills')
    fillsolid = first_solid(fills) if isinstance(fills, list) else None
    if isinstance(fills, list) and len(fills) == 0:
        # empty fills
        if ntype == 'TEXT':
            issues.append(('fill', 'TEXT has NO fill', 'n/a'))
        else:
            no_bg.append((nid, name, ntype))
    elif fillsolid is not None:
        bv = fillsolid.get('boundVariables', {})
        if bv and bv.get('color'):
            okparts.append('fill')
        else:
            issues.append(('fill', 'SOLID fill not bound', rgb(fillsolid.get('color'))))
    # image fill / gradient fill -> not a token concern; skip

    # ---- BACKGROUND (legacy) ----
    bg = node.get('background')
    if isinstance(bg, list) and bg:
        bgsolid = first_solid(bg)
        if bgsolid is not None:
            bv = bgsolid.get('boundVariables', {})
            if bv and bv.get('color'):
                okparts.append('background')
            else:
                issues.append(('background', 'SOLID background not bound', rgb(bgsolid.get('color'))))

    # ---- STROKE ----
    strokes = node.get('strokes')
    if isinstance(strokes, list) and strokes:
        ssolid = first_solid(strokes)
        if ssolid is not None:
            bv = ssolid.get('boundVariables', {})
            if bv and bv.get('color'):
                okparts.append('stroke')
            else:
                issues.append(('stroke', 'SOLID stroke not bound', rgb(ssolid.get('color'))))

    if issues:
        unbound.append({'id': nid, 'name': name, 'type': ntype, 'issues': issues})
    elif okparts:
        bound.append({'id': nid, 'name': name, 'type': ntype, 'ok': okparts})

    for ch in node.get('children', []) or []:
        check(ch, depth + 1, nid)

for entry in data:
    doc = entry.get('document')
    if doc:
        check(doc, 0, 'ROOT')

print("==== TREE STRUCTURE ====")
for l in tree_lines:
    print(l)

print()
print("==== UNBOUND NODES (count=%d) ====" % len(unbound))
for u in unbound:
    for (what, desc, color) in u['issues']:
        print("UNBOUND | %s | %s | %s | %s | %s | %s" % (u['id'], u['name'], u['type'], what, desc, color))

print()
print("==== BOUND NODES (count=%d) ====" % len(bound))
for b in bound:
    print("BOUND | %s | %s | %s | %s" % (b['id'], b['name'], b['type'], '+'.join(b['ok'])))

print()
print("==== FRAMES WITH NO BACKGROUND (empty fills) (count=%d) ====" % len(no_bg))
for n in no_bg:
    print("NO-BG | %s | %s | %s" % n)

print()
print("==== TOTALS ==== nodes=%d unbound=%d bound=%d no_bg=%d" % (len(tree_lines), len(unbound), len(bound), len(no_bg)))
