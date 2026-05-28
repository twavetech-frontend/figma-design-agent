#!/usr/bin/env python3
"""스테이지 추천 목록 화면 — v2 폴리시드 (레이아웃 재구성 + 액센트 컬러).

와이어프레임을 그대로 옮기지 않고: 금액을 히어로로, 회차바/통계 미니카드/
컬러 태그·랭크 pill로 위계와 색을 강화. 1위 카드는 brand 보더+그림자로 강조.
"""
import json

tab_bar = json.load(open('/tmp/v32_tabbar.json'))

WHITE = {'r': 1, 'g': 1, 'b': 1, 'a': 1}


def txt(name, chars, size, weight, color, **kw):
    n = {'name': name, 'type': 'text', 'characters': chars, 'fontSize': size,
         'fontWeight': weight, 'fontColor': color}
    n.update(kw)
    return n


def pill(name, label, bg, fg, size=12, weight=700):
    return {
        'name': name, 'type': 'frame', 'layoutSizingHorizontal': 'HUG',
        'fill': bg, 'cornerRadius': 999,
        'autoLayout': {'layoutMode': 'HORIZONTAL', 'paddingLeft': 10, 'paddingRight': 10,
                       'paddingTop': 5, 'paddingBottom': 5,
                       'counterAxisAlignItems': 'CENTER'},
        'children': [txt(name + '-t', label, size, weight, fg)],
    }


# ── 1. 상단 탭 네비 ──────────────────────────────────────────────
top_nav = {
    'name': 'Top Tab Nav', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
    'fill': '$token(bg-primary)',
    'autoLayout': {'layoutMode': 'HORIZONTAL', 'paddingLeft': 20, 'paddingRight': 20,
                   'paddingTop': 10, 'paddingBottom': 10,
                   'primaryAxisAlignItems': 'SPACE_BETWEEN',
                   'counterAxisAlignItems': 'CENTER'},
    'children': [
        {'name': 'Nav Tabs', 'type': 'frame', 'layoutSizingHorizontal': 'HUG',
         'autoLayout': {'layoutMode': 'HORIZONTAL', 'itemSpacing': 16,
                        'counterAxisAlignItems': 'CENTER'},
         'children': [
             {'name': 'Tab 추천 (Active)', 'type': 'frame', 'layoutSizingHorizontal': 'HUG',
              'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 6, 'paddingTop': 4,
                             'counterAxisAlignItems': 'CENTER'},
              'children': [
                  txt('label', '추천', 22, 800, '$token(fg-primary)'),
                  {'name': 'Underline', 'type': 'frame', 'width': 28, 'height': 3,
                   'layoutSizingHorizontal': 'FILL', 'cornerRadius': 2,
                   'fill': '$token(bg-brand-solid)'},
              ]},
             {'name': 'Tab 전체', 'type': 'frame', 'layoutSizingHorizontal': 'HUG',
              'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 6, 'paddingTop': 4,
                             'counterAxisAlignItems': 'CENTER'},
              'children': [txt('label', '전체', 22, 700, '$token(fg-tertiary)')]},
         ]},
        {'name': 'icon-search', 'type': 'icon', 'iconName': 'search-lg',
         'size': 24, 'iconColor': '$token(fg-primary)'},
    ],
}

# ── 2. 모으기 셀렉터 (연한 brand 박스로 카드화) ──────────────────
selector = {
    'name': 'Selector Section', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
    'fill': '$token(bg-primary)',
    'autoLayout': {'layoutMode': 'VERTICAL', 'paddingLeft': 20, 'paddingRight': 20,
                   'paddingTop': 6, 'paddingBottom': 10},
    'children': [{
        'name': 'Selector Box', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
        'fill': '$token(bg-brand-primary)', 'cornerRadius': 14,
        'autoLayout': {'layoutMode': 'HORIZONTAL', 'paddingLeft': 16, 'paddingRight': 14,
                       'paddingTop': 13, 'paddingBottom': 13,
                       'primaryAxisAlignItems': 'SPACE_BETWEEN',
                       'counterAxisAlignItems': 'CENTER'},
        'children': [
            {'name': 'Sel Texts', 'type': 'frame', 'layoutSizingHorizontal': 'HUG',
             'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 2},
             'children': [
                 txt('sel-eyebrow', '모으기 목표', 11, 600, '$token(fg-brand-primary)'),
                 txt('sel-label', '한 달에 약 100만원 · 13개월', 17, 800,
                     '$token(fg-primary)'),
             ]},
            {'name': 'icon-chevron', 'type': 'icon', 'iconName': 'chevron-down',
             'size': 22, 'iconColor': '$token(fg-brand-primary)'},
        ],
    }],
}

# ── 3. 필터 칩 ───────────────────────────────────────────────────
CHIPS = [('🚀 빠른 시작', True), ('⚡ 빨리 받기', False), ('💰 이자 받기', False),
         ('💎 중도 수령', False), ('📈 수익률 순', False)]


def chip(label, active):
    return {
        'name': f'Chip {label}', 'type': 'frame', 'layoutSizingHorizontal': 'HUG',
        'fill': '$token(bg-brand-solid)' if active else '$token(bg-secondary)',
        'cornerRadius': 999,
        'autoLayout': {'layoutMode': 'HORIZONTAL', 'paddingLeft': 14, 'paddingRight': 14,
                       'paddingTop': 9, 'paddingBottom': 9,
                       'counterAxisAlignItems': 'CENTER'},
        'children': [txt('chip-label', label, 13, 700,
                         WHITE if active else '$token(fg-secondary)')],
    }


filter_chips = {
    'name': 'Filter Chips', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
    'clipsContent': True, 'fill': '$token(bg-primary)',
    'autoLayout': {'layoutMode': 'HORIZONTAL', 'paddingLeft': 20, 'paddingRight': 20,
                   'paddingTop': 8, 'paddingBottom': 12, 'itemSpacing': 8},
    'children': [chip(l, a) for l, a in CHIPS],
}

# ── 4. 개수 / 정렬 행 ────────────────────────────────────────────
count_sort = {
    'name': 'Count Sort Row', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
    'fill': '$token(bg-primary)',
    'autoLayout': {'layoutMode': 'HORIZONTAL', 'paddingLeft': 20, 'paddingRight': 20,
                   'paddingTop': 4, 'paddingBottom': 10,
                   'primaryAxisAlignItems': 'SPACE_BETWEEN',
                   'counterAxisAlignItems': 'CENTER'},
    'children': [
        {'name': 'Count Wrap', 'type': 'frame', 'layoutSizingHorizontal': 'HUG',
         'autoLayout': {'layoutMode': 'HORIZONTAL', 'itemSpacing': 4,
                        'counterAxisAlignItems': 'CENTER'},
         'children': [
             txt('count-num', '1,284', 15, 800, '$token(fg-brand-primary)'),
             txt('count-unit', '개의 추천', 14, 600, '$token(fg-secondary)'),
         ]},
        {'name': 'Sort', 'type': 'frame', 'layoutSizingHorizontal': 'HUG',
         'autoLayout': {'layoutMode': 'HORIZONTAL', 'itemSpacing': 2,
                        'counterAxisAlignItems': 'CENTER'},
         'children': [
             txt('sort-label', '혜택 많은 순', 13, 600, '$token(fg-tertiary)'),
             {'name': 'icon-sort-chevron', 'type': 'icon', 'iconName': 'chevron-down',
              'size': 16, 'iconColor': '$token(fg-tertiary)'},
         ]},
    ],
}


# ── 5. 추천 카드 ────────────────────────────────────────────────
def round_bar(passed):
    cells = []
    for i in range(1, 14):
        on = i <= passed
        cur = i == passed
        cells.append({
            'name': f'cell-{i}', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
            'height': 26, 'layoutSizingVertical': 'FIXED',
            'fill': ('$token(bg-brand-solid)' if cur else
                     '$token(bg-brand-secondary)' if on else '$token(bg-secondary)'),
            'autoLayout': {'layoutMode': 'HORIZONTAL', 'primaryAxisAlignItems': 'CENTER',
                           'counterAxisAlignItems': 'CENTER'},
            'children': [txt(f'n-{i}', str(i), 10, 700,
                             WHITE if on else '$token(fg-tertiary)')],
        })
    return {
        'name': 'Round Bar', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
        'fill': '$token(bg-secondary)', 'cornerRadius': 8, 'clipsContent': True,
        '_repetitionAllowed': '회차 진행 바 — 1~13회차 세그먼트는 필수 UI',
        'autoLayout': {'layoutMode': 'HORIZONTAL', 'itemSpacing': 2,
                       'paddingTop': 2, 'paddingBottom': 2,
                       'paddingLeft': 2, 'paddingRight': 2},
        'children': cells,
    }


def stat_card(label, value, value_color):
    return {
        'name': f'Stat {label}', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
        'fill': '$token(bg-secondary)', 'cornerRadius': 12,
        'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 4, 'paddingTop': 12,
                       'paddingBottom': 12, 'paddingLeft': 14, 'paddingRight': 14},
        'children': [
            txt('st-label', label, 11, 600, '$token(fg-tertiary)'),
            txt('st-value', value, 15, 800, value_color),
        ],
    }


def reco_card(idx, rank_label, rank_bg, rank_fg, tag_label, tag_bg, tag_fg,
              when, amount, passed, monthly, interest, interest_pos, highlight):
    shadow = {'type': 'DROP_SHADOW',
              'color': {'r': 0.27, 'g': 0.15, 'b': 0.5, 'a': 0.16 if highlight else 0.07},
              'offset': {'x': 0, 'y': 6 if highlight else 3},
              'radius': 22 if highlight else 14, 'spread': 0}
    interest_color = '$token(fg-success-primary)' if interest_pos else '$token(fg-primary)'
    return {
        'name': f'Reco Card {idx}', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
        'fill': '$token(bg-primary)', 'cornerRadius': 20,
        'stroke': '$token(bg-brand-solid)' if highlight else '$token(border-secondary)',
        'strokeWeight': 1.5 if highlight else 1,
        'effects': [shadow],
        'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 16, 'paddingTop': 18,
                       'paddingBottom': 18, 'paddingLeft': 18, 'paddingRight': 18},
        'children': [
            # 헤더: 랭크 pill + 컬러 태그
            {'name': 'Card Header', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
             'autoLayout': {'layoutMode': 'HORIZONTAL',
                            'primaryAxisAlignItems': 'SPACE_BETWEEN',
                            'counterAxisAlignItems': 'CENTER'},
             'children': [
                 pill('Rank Pill', rank_label, rank_bg, rank_fg),
                 pill('Tag Pill', tag_label, tag_bg, tag_fg, size=11),
             ]},
            # 금액 히어로
            {'name': 'Amount Block', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
             'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 2},
             'children': [
                 txt('when', when, 13, 600, '$token(fg-tertiary)'),
                 {'name': 'Amount Row', 'type': 'frame', 'layoutSizingHorizontal': 'HUG',
                  'autoLayout': {'layoutMode': 'HORIZONTAL', 'itemSpacing': 3,
                                 'counterAxisAlignItems': 'CENTER'},
                  'children': [
                      txt('amt', amount, 29, 800, '$token(fg-brand-primary)'),
                      txt('amt-unit', '원', 18, 700, '$token(fg-primary)'),
                      txt('amt-tail', '수령', 15, 600, '$token(fg-secondary)'),
                  ]},
             ]},
            # 회차 진행
            {'name': 'Bar Block', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
             'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 7},
             'children': [
                 {'name': 'Bar Head', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
                  'autoLayout': {'layoutMode': 'HORIZONTAL',
                                 'primaryAxisAlignItems': 'SPACE_BETWEEN',
                                 'counterAxisAlignItems': 'CENTER'},
                  'children': [
                      txt('bar-label', '회차 진행', 12, 600, '$token(fg-tertiary)',
                          layoutSizingHorizontal='HUG'),
                      txt('bar-prog', f'{passed}회차 수령 · 총 13회차', 12, 700,
                          '$token(fg-brand-primary)', layoutSizingHorizontal='HUG'),
                  ]},
                 round_bar(passed),
             ]},
            # 통계 미니카드 2개
            {'name': 'Stat Row', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
             'autoLayout': {'layoutMode': 'HORIZONTAL', 'itemSpacing': 8},
             'children': [
                 stat_card('매월 납입액', monthly, '$token(fg-primary)'),
                 stat_card('총 이자 비용', interest, interest_color),
             ]},
            # 추가 혜택 컬러 칩
            {'name': 'Benefit Row', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
             'autoLayout': {'layoutMode': 'HORIZONTAL', 'itemSpacing': 8,
                            'counterAxisAlignItems': 'CENTER'},
             'children': [
                 txt('benefit-label', '추가 혜택', 12, 600, '$token(fg-tertiary)',
                     layoutSizingHorizontal='HUG'),
                 pill('Point Chip', 'P 50,000P', '$token(bg-brand-primary)',
                      '$token(fg-brand-primary)', size=12),
                 pill('Voucher Chip', '🎫 10만원', '$token(bg-warning-secondary)',
                      '$token(fg-warning-primary)', size=12),
             ]},
        ],
    }


card_list = {
    'name': 'Card List', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
    'fill': '$token(bg-primary)',
    'autoLayout': {'layoutMode': 'VERTICAL', 'paddingLeft': 20, 'paddingRight': 20,
                   'paddingTop': 6, 'paddingBottom': 22, 'itemSpacing': 16},
    'children': [
        reco_card(1, '👑 추천 1위', '$token(bg-brand-solid)', WHITE,
                  '최다 혜택', '$token(bg-warning-secondary)', '$token(fg-warning-primary)',
                  '2025년 12월 25일 수령 예정', '20,529,600', 1,
                  '1,725,376원', '1,900,288원', False, True),
        reco_card(2, '추천 2위', '$token(bg-brand-primary)', '$token(fg-brand-primary)',
                  '이자 0원', '$token(bg-success-secondary)', '$token(fg-success-primary)',
                  '2027년 6월 25일 수령 예정', '20,800,000', 7,
                  '1,600,000원', '0원', True, False),
        reco_card(3, '추천 3위', '$token(bg-secondary)', '$token(fg-secondary)',
                  '빠른 수령', '$token(bg-brand-primary)', '$token(fg-brand-primary)',
                  '2025년 11월 25일 수령 예정', '10,400,000', 3,
                  '850,000원', '320,000원', False, False),
    ],
}

bp = {
    'rootName': 'stage_recommend_v2',
    'name': 'stage_recommend_v2',
    'type': 'frame', 'width': 393, 'height': 1900,
    'fill': '$token(bg-primary)',
    'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 0},
    'discoverySource': 'user-provided wireframe (스테이지 추천 목록) — v2 폴리시드',
    'children': [top_nav, selector, filter_chips, count_sort, card_list, tab_bar],
    'references': [
        {
            'section': '필터 칩 / 추천 카드 리스트 / 정렬 행',
            'ref': 'uibowl/kakaopay/cmgno0mt2000zjy04ks467n95.png',
            'extract': '언더라인 탭 + 라운드 필터칩 + 카드 리스트, 카드에 컬러 태그/랭크 강조',
            '_searchLog': {
                'queries': ['추천 상품 리스트 필터칩', '적금 상품 카드 회차 진행',
                            '정렬 필터 칩 가로스크롤'],
                'candidates': ['uibowl/kakaopay/cmgno0mt2000zjy04ks467n95.png',
                               'uibowl/heydealer/cmliqih6y001gle04i462r1ac.png',
                               'uibowl/toss/cm7k1x59x009sl50c665tyf46.png'],
                'chosen': 'uibowl/kakaopay/cmgno0mt2000zjy04ks467n95.png',
                'copyNotes': '와이어프레임 1:1 대신 폴리시: 금액을 29px 히어로 숫자로, 회차바는 brand-solid/secondary 단계 채움, 통계는 회색 미니카드 2분할, 랭크 pill+컬러 태그(오렌지/그린/브랜드), 1위 카드는 brand 보더+그림자 강조.',
            },
        },
        {
            'section': '바텀 탭 / 회차 진행 바',
            'ref': 'in-file 16941:51284',
            'extract': 'imin DS 바텀 탭바 5개, 세그먼트형 회차 인디케이터',
            '_searchLog': {
                'queries': ['imin bottom tab bar', '회차 세그먼트 진행 바'],
                'candidates': ['in-file 16941:51284',
                               'uibowl/kakaopay/cmgno0mt2000zjy04ks467n95.png',
                               'uibowl/toss/cm7k1x5aa009ul50ccc4iwhtl.png'],
                'chosen': 'in-file 16941:51284',
                'copyNotes': 'v32 검증 빌드 Tab Bar 5탭 차용(스테이지 active). 회차바는 지난 회차 brand-secondary, 현재 회차 brand-solid, 남은 회차 회색.',
            },
        },
    ],
}

out = 'scripts/blueprint_stage_recommend_v2.json'
json.dump(bp, open(out, 'w'), ensure_ascii=False, indent=2)
print('written:', out)
