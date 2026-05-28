#!/usr/bin/env python3
"""내 스케줄 화면 — 2026-05-18 신규 분석 빌드.

와이어프레임을 새로 분석: 3개 통계는 시맨틱 컬러로 차등(완료=그린/남은=브랜드),
스케줄 리스트는 상태별 차등화 — 완료=그린 / 연체=레드 보더+레드 배지 /
오늘=브랜드 보더+브랜드 배지 / 예정=워닝 배지. 날짜 배지는 상태색을 담는 앵커.
하단 탭바 없음(서브 화면 — 와이어프레임에 없음).
"""
import json

WHITE = {'r': 1, 'g': 1, 'b': 1, 'a': 1}
CLEAR = {'r': 0, 'g': 0, 'b': 0, 'a': 0}


def txt(name, chars, size, weight, color, **kw):
    n = {'name': name, 'type': 'text', 'characters': chars, 'fontSize': size,
         'fontWeight': weight, 'fontColor': color}
    n.update(kw)
    return n


def icon(name, icon_name, size, color):
    return {'name': name, 'type': 'icon', 'iconName': icon_name,
            'size': size, 'iconColor': color}


def circle_btn(name, icon_name, diam, bg, icon_color, icon_size):
    return {
        'name': name, 'type': 'frame', 'layoutSizingHorizontal': 'FIXED',
        'layoutSizingVertical': 'FIXED', 'width': diam, 'height': diam,
        'cornerRadius': diam // 2, 'fill': bg,
        'autoLayout': {'layoutMode': 'HORIZONTAL', 'primaryAxisAlignItems': 'CENTER',
                       'counterAxisAlignItems': 'CENTER'},
        'children': [icon(name + '-i', icon_name, icon_size, icon_color)],
    }


def pill(name, label, bg, fg, size=11, weight=600):
    return {
        'name': name, 'type': 'frame', 'layoutSizingHorizontal': 'HUG',
        'layoutSizingVertical': 'HUG', 'fill': bg, 'cornerRadius': 999,
        'autoLayout': {'layoutMode': 'HORIZONTAL', 'paddingLeft': 9, 'paddingRight': 9,
                       'paddingTop': 4, 'paddingBottom': 4,
                       'counterAxisAlignItems': 'CENTER'},
        'children': [txt(name + '-t', label, size, weight, fg)],
    }


# ── 1. 상단 앱바 (뒤로 + 중앙 타이틀) ────────────────────────────
top_bar = {
    'name': 'Top App Bar', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
    'fill': '$token(bg-primary)',
    'autoLayout': {'layoutMode': 'HORIZONTAL', 'paddingLeft': 12, 'paddingRight': 12,
                   'paddingTop': 8, 'paddingBottom': 8,
                   'counterAxisAlignItems': 'CENTER'},
    'children': [
        circle_btn('Back Btn', 'chevron-left', 36, '$token(bg-primary)',
                   '$token(fg-primary)', 20),
        txt('app-title', '내 스케줄', 18, 800, '$token(fg-primary)',
            layoutSizingHorizontal='FILL', textAlignHorizontal='CENTER'),
        {'name': 'Bar Spacer', 'type': 'frame', 'layoutSizingHorizontal': 'FIXED',
         'layoutSizingVertical': 'FIXED', 'width': 36, 'height': 36, 'fill': CLEAR,
         'autoLayout': {'layoutMode': 'HORIZONTAL'}},
    ],
}

# ── 2. 월 선택 카드 ──────────────────────────────────────────────
month_card = {
    'name': 'Month Section', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
    'fill': '$token(bg-primary)',
    'autoLayout': {'layoutMode': 'VERTICAL', 'paddingLeft': 16, 'paddingRight': 16,
                   'paddingTop': 8, 'paddingBottom': 0},
    'children': [{
        'name': 'Month Card', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
        'fill': '$token(bg-primary)', 'cornerRadius': 18,
        'effects': [{'type': 'DROP_SHADOW', 'color': {'r': 0.1, 'g': 0.1, 'b': 0.2, 'a': 0.06},
                     'offset': {'x': 0, 'y': 2}, 'radius': 10, 'spread': 0}],
        'autoLayout': {'layoutMode': 'HORIZONTAL', 'paddingLeft': 14, 'paddingRight': 14,
                       'paddingTop': 14, 'paddingBottom': 14,
                       'primaryAxisAlignItems': 'SPACE_BETWEEN',
                       'counterAxisAlignItems': 'CENTER'},
        'children': [
            circle_btn('Month Prev', 'chevron-left', 40, '$token(bg-secondary)',
                       '$token(fg-tertiary)', 20),
            {'name': 'Month Label', 'type': 'frame', 'layoutSizingHorizontal': 'HUG',
             'autoLayout': {'layoutMode': 'HORIZONTAL', 'itemSpacing': 4,
                            'counterAxisAlignItems': 'CENTER'},
             'children': [
                 txt('month-t', '26년 1월', 19, 800, '$token(fg-primary)'),
                 icon('month-chevron', 'chevron-down', 20, '$token(fg-primary)'),
             ]},
            circle_btn('Month Next', 'chevron-right', 40, '$token(bg-secondary)',
                       '$token(fg-tertiary)', 20),
        ],
    }],
}


# ── 3. 요약 카드 (탭 + 통계 + 버튼 + 안내) ───────────────────────
def seg_tab(label, active):
    bar_color = '$token(bg-brand-solid)' if active else '$token(border-secondary)'
    text_color = '$token(fg-brand-primary)' if active else '$token(fg-tertiary)'
    return {
        'name': f'Tab {label}', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
        'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 10, 'paddingTop': 14,
                       'counterAxisAlignItems': 'CENTER'},
        'children': [
            txt('tab-t', label, 15, 700 if active else 500, text_color,
                textAlignHorizontal='CENTER'),
            {'name': 'Tab Underline', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
             'height': 2, 'layoutSizingVertical': 'FIXED', 'fill': bar_color},
        ],
    }


def stat_col(label, value, value_color):
    return {
        'name': f'Stat {label}', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
        'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 6,
                       'counterAxisAlignItems': 'CENTER'},
        'children': [
            txt('stat-l', label, 12, 500, '$token(fg-tertiary)',
                textAlignHorizontal='CENTER'),
            txt('stat-v', value, 17, 800, value_color, textAlignHorizontal='CENTER'),
        ],
    }


def action_btn(name, icon_name, label):
    return {
        'name': name, 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
        'fill': '$token(bg-primary)', 'cornerRadius': 12,
        'stroke': '$token(border-secondary)', 'strokeWeight': 1,
        'autoLayout': {'layoutMode': 'HORIZONTAL', 'paddingTop': 13, 'paddingBottom': 13,
                       'paddingLeft': 10, 'paddingRight': 10, 'itemSpacing': 6,
                       'primaryAxisAlignItems': 'CENTER', 'counterAxisAlignItems': 'CENTER'},
        'children': [
            icon(name + '-i', icon_name, 18, '$token(fg-brand-primary)'),
            txt(name + '-t', label, 13, 600, '$token(fg-primary)'),
        ],
    }


summary_card = {
    'name': 'Summary Section', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
    'fill': '$token(bg-primary)',
    'autoLayout': {'layoutMode': 'VERTICAL', 'paddingLeft': 16, 'paddingRight': 16,
                   'paddingTop': 12, 'paddingBottom': 0},
    'children': [{
        'name': 'Summary Card', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
        'fill': '$token(bg-primary)', 'cornerRadius': 18, 'clipsContent': True,
        'effects': [{'type': 'DROP_SHADOW', 'color': {'r': 0.1, 'g': 0.1, 'b': 0.2, 'a': 0.06},
                     'offset': {'x': 0, 'y': 2}, 'radius': 10, 'spread': 0}],
        'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 0},
        'children': [
            # 탭
            {'name': 'Tab Row', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
             'autoLayout': {'layoutMode': 'HORIZONTAL', 'itemSpacing': 0},
             'children': [seg_tab('납입', True), seg_tab('수령', False)]},
            # 통계 3열
            {'name': 'Stat Row', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
             'autoLayout': {'layoutMode': 'HORIZONTAL', 'paddingLeft': 12,
                            'paddingRight': 12, 'paddingTop': 20, 'paddingBottom': 18,
                            'itemSpacing': 8},
             'children': [
                 stat_col('월 납입 총액', '500,000원', '$token(fg-primary)'),
                 stat_col('납입 완료', '500,000원', '$token(fg-success-primary)'),
                 stat_col('남은 납입액', '500,000원', '$token(fg-brand-primary)'),
             ]},
            # 액션 버튼 2개
            {'name': 'Action Row', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
             'autoLayout': {'layoutMode': 'HORIZONTAL', 'paddingLeft': 16,
                            'paddingRight': 16, 'paddingBottom': 16, 'itemSpacing': 8},
             'children': [
                 action_btn('Btn 납입반영', 'refresh-cw-01', '납입반영 내역'),
                 action_btn('Btn 가상계좌', 'credit-card-01', '가상계좌 납입 내역'),
             ]},
            # 입금반영 안내 (확장 행)
            {'name': 'Notice Row', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
             'fill': '$token(bg-secondary)',
             'autoLayout': {'layoutMode': 'HORIZONTAL', 'paddingLeft': 18,
                            'paddingRight': 16, 'paddingTop': 15, 'paddingBottom': 15,
                            'primaryAxisAlignItems': 'SPACE_BETWEEN',
                            'counterAxisAlignItems': 'CENTER'},
             'children': [
                 txt('notice-t', '입금반영 안내', 14, 600, '$token(fg-secondary)',
                     layoutSizingHorizontal='HUG'),
                 icon('notice-chevron', 'chevron-down', 20, '$token(fg-tertiary)'),
             ]},
        ],
    }],
}

# ── 4. 리스트 헤더 ───────────────────────────────────────────────
list_header = {
    'name': 'List Header', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
    'fill': '$token(bg-primary)',
    'autoLayout': {'layoutMode': 'HORIZONTAL', 'paddingLeft': 20, 'paddingRight': 20,
                   'paddingTop': 22, 'paddingBottom': 10,
                   'primaryAxisAlignItems': 'SPACE_BETWEEN',
                   'counterAxisAlignItems': 'CENTER'},
    'children': [
        txt('lh-title', '2026년 1월', 17, 800, '$token(fg-primary)',
            layoutSizingHorizontal='HUG'),
        pill('Count Pill', '총 4건', '$token(bg-primary)', '$token(fg-tertiary)',
             size=12, weight=600),
    ],
}


# ── 5. 스케줄 카드 ───────────────────────────────────────────────
def date_badge(top_label, date_str, bg, fg, top_color=None):
    children = []
    if top_label:
        children.append(txt('badge-top', top_label, 10, 700, top_color or fg,
                            textAlignHorizontal='CENTER'))
    children.append(txt('badge-date', date_str, 15, 800, fg,
                        textAlignHorizontal='CENTER'))
    return {
        'name': 'Date Anchor', 'type': 'frame', 'layoutSizingHorizontal': 'FIXED',
        'layoutSizingVertical': 'FIXED', 'width': 56, 'height': 56,
        'cornerRadius': 14, 'fill': bg,
        'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 1,
                       'primaryAxisAlignItems': 'CENTER',
                       'counterAxisAlignItems': 'CENTER'},
        'children': children,
    }


def schedule_card(badge, title, amount, rounds, status_label, status_color,
                   accent_stroke=None):
    return {
        'name': f'Schedule Card {title}', 'type': 'frame',
        'layoutSizingHorizontal': 'FILL', 'fill': '$token(bg-primary)',
        'cornerRadius': 14,
        'stroke': accent_stroke or '$token(border-secondary)',
        'strokeWeight': 1.5 if accent_stroke else 1,
        'effects': [{'type': 'DROP_SHADOW',
                     'color': {'r': 0.1, 'g': 0.1, 'b': 0.2, 'a': 0.05},
                     'offset': {'x': 0, 'y': 2}, 'radius': 8, 'spread': 0}],
        'autoLayout': {'layoutMode': 'HORIZONTAL', 'paddingLeft': 14, 'paddingRight': 16,
                       'paddingTop': 14, 'paddingBottom': 14, 'itemSpacing': 14,
                       'counterAxisAlignItems': 'CENTER'},
        'children': [
            badge,
            {'name': 'Card Mid', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
             'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 5},
             'children': [
                 txt('sc-title', title, 13, 500, '$token(fg-tertiary)'),
                 txt('sc-amount', amount, 20, 800, '$token(fg-primary)'),
                 pill('Rounds Pill', rounds, '$token(bg-secondary)',
                      '$token(fg-tertiary)', size=11, weight=600),
             ]},
            txt('sc-status', status_label, 14, 700, status_color,
                layoutSizingHorizontal='HUG', textAlignHorizontal='RIGHT'),
        ],
    }


schedule_list = {
    'name': 'Schedule List', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
    'fill': '$token(bg-primary)',
    'autoLayout': {'layoutMode': 'VERTICAL', 'paddingLeft': 16, 'paddingRight': 16,
                   'paddingTop': 0, 'paddingBottom': 28, 'itemSpacing': 10},
    'children': [
        schedule_card(
            date_badge(None, '1/2', '$token(bg-success-secondary)',
                       '$token(fg-success-primary)'),
            '소액 저축 습관 만들기', '100,000원', '2/5회차',
            '납입 완료', '$token(fg-success-primary)'),
        schedule_card(
            date_badge(None, '1/3', '$token(bg-error-secondary)',
                       '$token(fg-error-primary)'),
            '나는 나비', '100,000원', '2/5회차',
            '연체 중', '$token(fg-error-primary)',
            accent_stroke='$token(fg-error-primary)'),
        schedule_card(
            date_badge('오늘', '1/13', '$token(bg-brand-solid)', WHITE, top_color=WHITE),
            '하하하하하', '100,000원', '5/5회차',
            '납입 전', '$token(fg-secondary)',
            accent_stroke='$token(bg-brand-solid)'),
        schedule_card(
            date_badge('D-16', '1/16', '$token(bg-warning-secondary)',
                       '$token(fg-warning-primary)'),
            '여행가자!', '100,000원', '5/5회차',
            '납입 전', '$token(fg-secondary)'),
    ],
}

bp = {
    'rootName': 'my_schedule_2026_0518',
    'name': 'my_schedule_2026_0518',
    'type': 'frame', 'width': 393, 'height': 1180,
    'fill': '$token(bg-primary)',
    'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 0},
    'discoverySource': 'user-provided wireframe (내 스케줄) — 2026-05-18 신규 분석',
    'children': [top_bar, month_card, summary_card, list_header, schedule_list],
    'references': [
        {
            'section': '언더라인 탭 + 통계 + 스케줄 리스트',
            'ref': 'uibowl/kakaopay/cm8zjuicz005rkz0dl9eo78b5.png',
            'extract': '카드 안 언더라인 탭, 라벨-값 통계, 좌측 앵커 + 콘텐츠 + 우측 상태 리스트',
            '_searchLog': {
                'queries': ['납입 스케줄 내역 리스트 상태', '월 선택 캘린더 납입 현황 통계',
                            '적금 자동이체 연체 상태 리스트 카드'],
                'candidates': ['uibowl/kakaopay/cm8zjuicz005rkz0dl9eo78b5.png',
                               'uibowl/toss/dxmi8x1hgahxeflr3yzubcgh.png',
                               'uibowl/heydealer/cmlipz9610005l704d90kr3ij.png'],
                'chosen': 'uibowl/kakaopay/cm8zjuicz005rkz0dl9eo78b5.png',
                'copyNotes': 'kakaopay 통계 화면: 언더라인 탭(시장/뉴스) + 좌측 번호 앵커 + 콘텐츠 + 우측 정렬 값 리스트. 차용: 카드 내 언더라인 탭, 좌측 배지 앵커 리스트. 폴리시(와이어 1:1 탈피): 3개 통계를 시맨틱 컬러로 차등(완료=success 그린/남은=brand), 스케줄 카드를 상태별 차등화 — 연체=error 보더+레드 배지, 오늘=brand 보더+brand-solid 배지, 예정=warning 배지로 시각 위계 부여.',
            },
        },
        {
            'section': '상단 앱바 (뒤로 + 중앙 타이틀)',
            'ref': 'uibowl/toss/dxmi8x1hgahxeflr3yzubcgh.png',
            'extract': '원형 back 버튼 + 중앙 정렬 타이틀의 미니멀 상단 앱바',
            '_searchLog': {
                'queries': ['상세 내역 상단 앱바', '뒤로가기 중앙 타이틀 헤더'],
                'candidates': ['uibowl/toss/dxmi8x1hgahxeflr3yzubcgh.png',
                               'uibowl/kakaopay/cm8zjuicz005rkz0dl9eo78b5.png',
                               'uibowl/heydealer/cmliq4qbs0013lb04vj4a8y5x.png'],
                'chosen': 'uibowl/toss/dxmi8x1hgahxeflr3yzubcgh.png',
                'copyNotes': 'toss 상세 내역 화면 상단: back 아이콘 + 중앙 정렬 타이틀 + 우측 균형 spacer. 그대로 차용해 좌-중-우 3분할 앱바 구성, 하단 탭바는 서브 화면이므로 미포함.',
            },
        },
    ],
}

out = 'scripts/blueprint_my_schedule_2026_0518b.json'
json.dump(bp, open(out, 'w'), ensure_ascii=False, indent=2)
print('written:', out)
