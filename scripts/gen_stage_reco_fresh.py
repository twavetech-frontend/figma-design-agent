#!/usr/bin/env python3
"""스테이지 추천 목록 — 2026-05-18 신규 분석 빌드.

와이어프레임을 새로 분석: '받아요' 문장은 날짜 컨텍스트 + 32px 히어로 금액으로,
회차 스텝퍼는 현재 회차 위 dark 툴팁 + 단계 채움 셀로, 통계는 회색 미니스트립,
추가혜택은 카드 하단 풀블리드 light-brand 밴드로 재구성.
필터칩은 와이어프레임대로 outline 스타일(active=brand 보더). 1위 카드는 brand 강조.
"""
import json

tab_bar = json.load(open('/tmp/v32_tabbar.json'))

WHITE = {'r': 1, 'g': 1, 'b': 1, 'a': 1}
DARK = {'r': 0.13, 'g': 0.13, 'b': 0.15, 'a': 1}


def txt(name, chars, size, weight, color, **kw):
    n = {'name': name, 'type': 'text', 'characters': chars, 'fontSize': size,
         'fontWeight': weight, 'fontColor': color}
    n.update(kw)
    return n


def pill(name, label, bg, fg, size=11, weight=700, radius=999, stroke=None):
    p = {
        'name': name, 'type': 'frame', 'layoutSizingHorizontal': 'HUG',
        'fill': bg, 'cornerRadius': radius,
        'autoLayout': {'layoutMode': 'HORIZONTAL', 'paddingLeft': 10, 'paddingRight': 10,
                       'paddingTop': 5, 'paddingBottom': 5,
                       'counterAxisAlignItems': 'CENTER'},
        'children': [txt(name + '-t', label, size, weight, fg)],
    }
    if stroke:
        p['stroke'] = stroke
        p['strokeWeight'] = 1
    return p


# ── 1. 상단 탭 네비 (추천 / 전체 + 검색) ─────────────────────────
def nav_tab(label, active):
    children = [txt('label', label, 23, 800 if active else 700,
                    '$token(fg-primary)' if active else '$token(fg-tertiary)')]
    if active:
        children.append({'name': 'Underline', 'type': 'frame', 'width': 24, 'height': 3,
                         'layoutSizingHorizontal': 'FILL', 'cornerRadius': 2,
                         'fill': '$token(bg-brand-solid)'})
    return {'name': f'Nav {label}', 'type': 'frame', 'layoutSizingHorizontal': 'HUG',
            'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 7, 'paddingTop': 2,
                           'counterAxisAlignItems': 'CENTER'},
            'children': children}


top_nav = {
    'name': 'Top Tab Nav', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
    'fill': '$token(bg-primary)',
    'autoLayout': {'layoutMode': 'HORIZONTAL', 'paddingLeft': 20, 'paddingRight': 20,
                   'paddingTop': 12, 'paddingBottom': 12,
                   'primaryAxisAlignItems': 'SPACE_BETWEEN',
                   'counterAxisAlignItems': 'CENTER'},
    'children': [
        {'name': 'Nav Tabs', 'type': 'frame', 'layoutSizingHorizontal': 'HUG',
         'autoLayout': {'layoutMode': 'HORIZONTAL', 'itemSpacing': 18,
                        'counterAxisAlignItems': 'CENTER'},
         'children': [nav_tab('추천', True), nav_tab('전체', False)]},
        {'name': 'icon-search', 'type': 'icon', 'iconName': 'search-lg',
         'size': 24, 'iconColor': '$token(fg-primary)'},
    ],
}

# ── 2. 모으기 목표 셀렉터 (와이어프레임대로 underline 인라인) ──────
goal_selector = {
    'name': 'Goal Selector', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
    'fill': '$token(bg-primary)',
    'autoLayout': {'layoutMode': 'VERTICAL', 'paddingLeft': 20, 'paddingRight': 20,
                   'paddingTop': 4, 'paddingBottom': 14, 'itemSpacing': 9},
    'children': [
        {'name': 'Goal Row', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
         'autoLayout': {'layoutMode': 'HORIZONTAL', 'itemSpacing': 6,
                        'primaryAxisAlignItems': 'SPACE_BETWEEN',
                        'counterAxisAlignItems': 'CENTER'},
         'children': [
             {'name': 'Goal Texts', 'type': 'frame', 'layoutSizingHorizontal': 'HUG',
              'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 1},
              'children': [
                  txt('goal-eyebrow', '모으기 목표', 11, 600, '$token(fg-brand-primary)'),
                  txt('goal-label', '한 달에 약 100만원 · 13개월 모으기', 18, 800,
                      '$token(fg-primary)'),
              ]},
             {'name': 'icon-chevron-down', 'type': 'icon', 'iconName': 'chevron-down',
              'size': 22, 'iconColor': '$token(fg-primary)'},
         ]},
        {'name': 'Goal Underline', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
         'height': 2, 'fill': '$token(fg-primary)'},
    ],
}

# ── 3. 필터 칩 (outline 스타일 — 와이어프레임 충실) ───────────────
CHIPS = [('🚀 빠른 시작', True), ('⚡ 빨리 받기', False), ('💰 이자 받기', False),
         ('💎 중도 수령', False), ('📈 수익률 순', False)]


def chip(label, active):
    return {
        'name': f'Chip {label}', 'type': 'frame', 'layoutSizingHorizontal': 'HUG',
        'fill': '$token(bg-brand-primary)' if active else '$token(bg-primary)',
        'cornerRadius': 999,
        'stroke': '$token(fg-brand-primary)' if active else '$token(border-secondary)',
        'strokeWeight': 1.5 if active else 1,
        'autoLayout': {'layoutMode': 'HORIZONTAL', 'paddingLeft': 14, 'paddingRight': 14,
                       'paddingTop': 9, 'paddingBottom': 9,
                       'counterAxisAlignItems': 'CENTER'},
        'children': [txt('chip-label', label, 13, 700,
                         '$token(fg-brand-primary)' if active
                         else '$token(fg-secondary)')],
    }


filter_chips = {
    'name': 'Filter Chips', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
    'clipsContent': True, 'fill': '$token(bg-primary)',
    'autoLayout': {'layoutMode': 'HORIZONTAL', 'paddingLeft': 20, 'paddingRight': 20,
                   'paddingTop': 4, 'paddingBottom': 14, 'itemSpacing': 8},
    'children': [chip(l, a) for l, a in CHIPS],
}

# ── 4. 개수 / 정렬 행 ────────────────────────────────────────────
count_sort = {
    'name': 'Count Sort Row', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
    'fill': '$token(bg-primary)',
    'autoLayout': {'layoutMode': 'HORIZONTAL', 'paddingLeft': 20, 'paddingRight': 20,
                   'paddingTop': 2, 'paddingBottom': 10,
                   'primaryAxisAlignItems': 'SPACE_BETWEEN',
                   'counterAxisAlignItems': 'CENTER'},
    'children': [
        {'name': 'Count Wrap', 'type': 'frame', 'layoutSizingHorizontal': 'HUG',
         'autoLayout': {'layoutMode': 'HORIZONTAL', 'itemSpacing': 3,
                        'counterAxisAlignItems': 'CENTER'},
         'children': [
             txt('count-num', '1,284', 15, 800, '$token(fg-brand-primary)'),
             txt('count-unit', '개의 추천 스테이지', 14, 600, '$token(fg-secondary)'),
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
def step_bar(received):
    cells = []
    for i in range(1, 14):
        passed = i <= received
        cur = i == received
        cells.append({
            'name': f'step-{i}', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
            'height': 28, 'layoutSizingVertical': 'FIXED', 'cornerRadius': 5,
            'fill': ('$token(bg-brand-solid)' if cur else
                     '$token(bg-brand-secondary)' if passed else '$token(bg-secondary)'),
            'autoLayout': {'layoutMode': 'HORIZONTAL', 'primaryAxisAlignItems': 'CENTER',
                           'counterAxisAlignItems': 'CENTER'},
            'children': [txt(f'sn-{i}', str(i), 10, 700,
                             WHITE if passed else '$token(fg-tertiary)')],
        })
    return {
        'name': 'Step Cells', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
        '_repetitionAllowed': '회차 진행 셀 — 1~13회차 세그먼트는 필수 UI',
        'autoLayout': {'layoutMode': 'HORIZONTAL', 'itemSpacing': 3},
        'children': cells,
    }


def stat_col(label, value, value_color, align='MIN'):
    return {
        'name': f'Stat {label}', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
        'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 3,
                       'counterAxisAlignItems': align},
        'children': [
            txt('stl', label, 11, 600, '$token(fg-tertiary)'),
            txt('stv', value, 15, 800, value_color),
        ],
    }


def reco_card(idx, rank_label, tag_label, tag_bg, tag_fg,
              when, amount, received, monthly, interest, interest_zero, highlight):
    body_children = [
        # 랭크 헤더 (메달 이모지 + 라벨 — 스왑 위험 없는 텍스트)
        {'name': 'Rank Header', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
         'autoLayout': {'layoutMode': 'HORIZONTAL',
                        'primaryAxisAlignItems': 'SPACE_BETWEEN',
                        'counterAxisAlignItems': 'CENTER'},
         'children': [
             txt('rank-label', rank_label, 14, 800, '$token(fg-brand-primary)',
                 layoutSizingHorizontal='HUG'),
             pill('Tag Pill', tag_label, tag_bg, tag_fg, size=11),
         ]},
        # 금액 히어로
        {'name': 'Amount Block', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
         'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 3},
         'children': [
             txt('when', when, 13, 600, '$token(fg-tertiary)'),
             {'name': 'Amount Row', 'type': 'frame', 'layoutSizingHorizontal': 'HUG',
              'autoLayout': {'layoutMode': 'HORIZONTAL', 'itemSpacing': 3,
                             'counterAxisAlignItems': 'BASELINE'},
              'children': [
                  txt('amt', amount, 32, 800, '$token(fg-brand-primary)'),
                  txt('amt-unit', '원', 19, 700, '$token(fg-primary)'),
                  txt('amt-tail', '받아요', 15, 600, '$token(fg-secondary)'),
              ]},
         ]},
        # 회차 스텝퍼 (현재 회차 위 dark 툴팁)
        {'name': 'Stepper Block', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
         'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 8},
         'children': [
             {'name': 'Stepper Head', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
              'autoLayout': {'layoutMode': 'HORIZONTAL',
                             'primaryAxisAlignItems': 'SPACE_BETWEEN',
                             'counterAxisAlignItems': 'CENTER'},
              'children': [
                  pill('Round Tooltip', f'{received}회차 수령 완료', DARK, WHITE,
                       size=11, weight=700, radius=8),
                  txt('total-rounds', '총 13회차', 12, 600, '$token(fg-tertiary)',
                      layoutSizingHorizontal='HUG'),
              ]},
             step_bar(received),
         ]},
        # 통계 미니 스트립
        {'name': 'Stat Strip', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
         'fill': '$token(bg-secondary)', 'cornerRadius': 12,
         'autoLayout': {'layoutMode': 'HORIZONTAL', 'paddingLeft': 16, 'paddingRight': 16,
                        'paddingTop': 13, 'paddingBottom': 13, 'itemSpacing': 12},
         'children': [
             stat_col('매월 납입액', monthly, '$token(fg-primary)', 'MIN'),
             stat_col('총 이자 비용', interest,
                      '$token(fg-success-primary)' if interest_zero
                      else '$token(fg-primary)', 'MAX'),
         ]},
        # 추가 혜택 — 카드 하단 inset light-brand 밴드
        {'name': 'Benefit Band', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
         'layoutSizingVertical': 'HUG', 'fill': '$token(bg-brand-primary)',
         'cornerRadius': 12,
         'autoLayout': {'layoutMode': 'HORIZONTAL', 'paddingLeft': 14, 'paddingRight': 14,
                        'paddingTop': 11, 'paddingBottom': 11, 'itemSpacing': 8,
                        'primaryAxisAlignItems': 'SPACE_BETWEEN',
                        'counterAxisAlignItems': 'CENTER'},
         'children': [
             txt('benefit-label', '추가 혜택', 12, 700, '$token(fg-brand-primary)',
                 layoutSizingHorizontal='HUG'),
             {'name': 'Benefit Chips', 'type': 'frame', 'layoutSizingHorizontal': 'HUG',
              'layoutSizingVertical': 'HUG',
              'autoLayout': {'layoutMode': 'HORIZONTAL', 'itemSpacing': 6,
                             'counterAxisAlignItems': 'CENTER'},
              'children': [
                  pill('Point Chip', 'P 50,000P', '$token(bg-primary)',
                       '$token(fg-brand-primary)', size=12, radius=999),
                  pill('Voucher Chip', '🎫 10만원권', '$token(bg-warning-secondary)',
                       '$token(fg-warning-primary)', size=12, radius=999),
              ]},
         ]},
    ]
    shadow = {'type': 'DROP_SHADOW',
              'color': {'r': 0.27, 'g': 0.15, 'b': 0.5, 'a': 0.18 if highlight else 0.06},
              'offset': {'x': 0, 'y': 6 if highlight else 3},
              'radius': 24 if highlight else 12, 'spread': 0}
    return {
        'name': f'Reco Card {idx}', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
        'layoutSizingVertical': 'HUG',
        'fill': '$token(bg-primary)', 'cornerRadius': 20,
        'stroke': '$token(bg-brand-solid)' if highlight else '$token(border-secondary)',
        'strokeWeight': 1.5 if highlight else 1,
        'effects': [shadow],
        'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 14,
                       'paddingLeft': 18, 'paddingRight': 18,
                       'paddingTop': 18, 'paddingBottom': 18},
        'children': body_children,
    }


card_list = {
    'name': 'Card List', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
    'fill': '$token(bg-primary)',
    'autoLayout': {'layoutMode': 'VERTICAL', 'paddingLeft': 20, 'paddingRight': 20,
                   'paddingTop': 4, 'paddingBottom': 24, 'itemSpacing': 16},
    'children': [
        reco_card(1, '🥇 추천 1위',
                  '최다 혜택', '$token(bg-warning-secondary)',
                  '$token(fg-warning-primary)',
                  '2025년 12월 25일 수령 예정', '20,529,600', 1,
                  '1,725,376원', '1,900,288원', False, True),
        reco_card(2, '🥈 추천 2위',
                  '이자 0원', '$token(bg-success-secondary)',
                  '$token(fg-success-primary)',
                  '2027년 6월 25일 수령 예정', '20,800,000', 7,
                  '1,600,000원', '0원', True, False),
        reco_card(3, '🥉 추천 3위',
                  '빠른 수령', '$token(bg-brand-primary)', '$token(fg-brand-primary)',
                  '2025년 11월 25일 수령 예정', '10,400,000', 3,
                  '850,000원', '320,000원', False, False),
    ],
}

bp = {
    'rootName': 'stage_reco_2026_0518',
    'name': 'stage_reco_2026_0518',
    'type': 'frame', 'width': 393, 'height': 2000,
    'fill': '$token(bg-primary)',
    'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 0},
    'discoverySource': 'user-provided wireframe (스테이지 추천 목록) — 2026-05-18 신규 분석',
    'children': [top_nav, goal_selector, filter_chips, count_sort, card_list, tab_bar],
    'references': [
        {
            'section': '언더라인 탭 + 필터칩 + 랭크 추천 리스트',
            'ref': 'uibowl/kakaopay/cm8zjuel10005kz0dir0fyqwv.png',
            'extract': '상단 언더라인 탭, 가로 필터, 번호 랭크 + 콘텐츠 + 혜택 pill 리스트 구조',
            '_searchLog': {
                'queries': ['추천 상품 카드 리스트 필터', '적금 만기 수령 회차 진행 스텝',
                            '정렬 필터 칩 가로 스크롤 outline'],
                'candidates': ['uibowl/kakaopay/cm8zjuel10005kz0dir0fyqwv.png',
                               'uibowl/kakaopay/cm8zjuenp000bkz0dtfzb0yfv.png',
                               'uibowl/heydealer/cmliqih8n001kle04hjpiq8k4.png'],
                'chosen': 'uibowl/kakaopay/cm8zjuel10005kz0dir0fyqwv.png',
                'copyNotes': 'kakaopay 카드추천: 상단 언더라인 탭(내역/카드추천), 번호 랭크 + 콘텐츠 + 우측 혜택 pill 리스트. 차용: 번호 랭크 뱃지 + 우측 컬러 태그 pill. 폴리시: 와이어프레임 인라인 받아요 문장을 32px 히어로 금액으로 승격, 회차 스텝퍼는 현재회차 dark 툴팁 + brand 단계채움, 추가혜택은 카드 하단 풀블리드 light-brand 밴드로 분리.',
            },
        },
        {
            'section': '바텀 탭 바 / 회차 스텝퍼',
            'ref': 'in-file 16941:51284',
            'extract': 'imin DS 바텀 탭 5개, 세그먼트형 회차 인디케이터',
            '_searchLog': {
                'queries': ['imin bottom tab bar', '회차 세그먼트 진행 스텝'],
                'candidates': ['in-file 16941:51284',
                               'uibowl/kakaopay/cm8zjuel10005kz0dir0fyqwv.png',
                               'uibowl/heydealer/cmliqih8n001kle04hjpiq8k4.png'],
                'chosen': 'in-file 16941:51284',
                'copyNotes': 'v32 검증 빌드 Tab Bar 5탭(스테이지 active) 차용. 회차 스텝퍼는 지난 회차 brand-secondary, 현재 회차 brand-solid 흰 숫자, 남은 회차 회색으로 단계 표현.',
            },
        },
    ],
}

out = 'scripts/blueprint_stage_reco_2026_0518b.json'
json.dump(bp, open(out, 'w'), ensure_ascii=False, indent=2)
print('written:', out)
