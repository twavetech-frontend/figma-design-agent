#!/usr/bin/env python3
"""신용점수 조회 동의 화면 — 2026-05-19 신규 분석 빌드.

와이어프레임을 새로 분석: 평면 회색 점수 카드 → 짙은 brand 히어로 카드로 승격,
4개 본문 문단(텍스트 벽) → 키워드 brand-bold + 설명 grey 의 스캔 가능한 3-row
정보 카드로 재구성. 문의 정보는 하단 저대비 노트로 분리. 모달 스텝 화면 —
하단 탭바 없음, X 닫기 + 하단 '다음' CTA.
"""
import json

WHITE = {'r': 1, 'g': 1, 'b': 1, 'a': 1}
ALPHA_W_STRONG = {'r': 1, 'g': 1, 'b': 1, 'a': 0.16}
ALPHA_W_SOFT = {'r': 1, 'g': 1, 'b': 1, 'a': 0.13}
ALPHA_W_TEXT = {'r': 1, 'g': 1, 'b': 1, 'a': 0.55}
ALPHA_W_LABEL = {'r': 1, 'g': 1, 'b': 1, 'a': 0.82}


def txt(name, chars, size, weight, color, **kw):
    n = {'name': name, 'type': 'text', 'characters': chars, 'fontSize': size,
         'fontWeight': weight, 'fontColor': color}
    n.update(kw)
    return n


def icon(name, icon_name, size, color):
    return {'name': name, 'type': 'icon', 'iconName': icon_name,
            'size': size, 'iconColor': color}


# ── 1. 상단 바 (X 닫기) ──────────────────────────────────────────
top_bar = {
    'name': 'Top Bar', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
    'autoLayout': {'layoutMode': 'HORIZONTAL', 'paddingLeft': 20, 'paddingRight': 20,
                   'paddingTop': 10, 'paddingBottom': 6,
                   'primaryAxisAlignItems': 'MAX', 'counterAxisAlignItems': 'CENTER'},
    'children': [icon('icon-close', 'x-close', 26, '$token(fg-primary)')],
}

# ── 2. 타이틀 ────────────────────────────────────────────────────
title_section = {
    'name': 'Title Section', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
    'autoLayout': {'layoutMode': 'VERTICAL', 'paddingLeft': 24, 'paddingRight': 24,
                   'paddingTop': 14, 'paddingBottom': 0},
    'children': [
        txt('title', '스테이지 참여에<br>꼭 필요해요.', 24, 800, '$token(fg-primary)',
            layoutSizingHorizontal='FILL', lineHeight=32),
    ],
}

# ── 3. 신용점수 카드 (짙은 brand 히어로) ─────────────────────────
def digit_cell(idx):
    return {
        'name': f'Digit {idx}', 'type': 'frame', 'layoutSizingHorizontal': 'FIXED',
        'layoutSizingVertical': 'FIXED', 'width': 40, 'height': 46,
        'cornerRadius': 9, 'fill': ALPHA_W_SOFT,
        'autoLayout': {'layoutMode': 'HORIZONTAL', 'primaryAxisAlignItems': 'CENTER',
                       'counterAxisAlignItems': 'CENTER'},
        'children': [txt(f'q{idx}', '?', 19, 800, ALPHA_W_TEXT)],
    }


score_card = {
    'name': 'Score Card Section', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
    'autoLayout': {'layoutMode': 'VERTICAL', 'paddingLeft': 20, 'paddingRight': 20,
                   'paddingTop': 20, 'paddingBottom': 0},
    'children': [{
        'name': 'Score Card', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
        'fill': '$token(bg-brand-section)', 'cornerRadius': 20,
        'effects': [{'type': 'DROP_SHADOW',
                     'color': {'r': 0.27, 'g': 0.15, 'b': 0.5, 'a': 0.22},
                     'offset': {'x': 0, 'y': 8}, 'radius': 20, 'spread': 0}],
        'autoLayout': {'layoutMode': 'VERTICAL', 'paddingLeft': 24, 'paddingRight': 24,
                       'paddingTop': 24, 'paddingBottom': 24, 'itemSpacing': 44},
        'children': [
            # 상단: 조회 액션
            {'name': 'Card Action', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
             'autoLayout': {'layoutMode': 'HORIZONTAL',
                            'primaryAxisAlignItems': 'SPACE_BETWEEN',
                            'counterAxisAlignItems': 'CENTER'},
             'children': [
                 txt('action-label', '신용점수 조회', 19, 800, WHITE),
                 {'name': 'Action Arrow', 'type': 'frame',
                  'layoutSizingHorizontal': 'FIXED', 'layoutSizingVertical': 'FIXED',
                  'width': 38, 'height': 38, 'cornerRadius': 19, 'fill': ALPHA_W_STRONG,
                  'autoLayout': {'layoutMode': 'HORIZONTAL',
                                 'primaryAxisAlignItems': 'CENTER',
                                 'counterAxisAlignItems': 'CENTER'},
                  'children': [icon('arrow-i', 'chevron-right', 20, WHITE)]},
             ]},
            # 하단: 점수 표시
            {'name': 'Score Row', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
             'autoLayout': {'layoutMode': 'HORIZONTAL', 'itemSpacing': 10,
                            'counterAxisAlignItems': 'CENTER'},
             'children': [
                 txt('score-label', '신용점수', 17, 700, ALPHA_W_LABEL,
                     layoutSizingHorizontal='HUG'),
                 {'name': 'Digit Row', 'type': 'frame', 'layoutSizingHorizontal': 'HUG',
                  'autoLayout': {'layoutMode': 'HORIZONTAL', 'itemSpacing': 6,
                                 'counterAxisAlignItems': 'CENTER'},
                  'children': [digit_cell(i) for i in range(1, 5)]},
                 txt('score-unit', '점', 17, 700, WHITE, layoutSizingHorizontal='HUG'),
             ]},
        ],
    }],
}

# ── 4. 안내 정보 카드 (텍스트 벽 → 스캔 가능한 3-row) ────────────
INFO = [
    ('KCB 신용점수 630점 이상', '아임인 스테이지에 참여할 수 있는 조건이에요.'),
    ('신용점수에 따라 스테이지 한도 결정', '조회된 점수에 맞춰 참여 한도가 자동 산정돼요.'),
    ('신용점수에 전혀 영향 없어요',
     '개인정보 보호법에 따라 정보가 안전하게 보호되니 안심하세요.'),
]


def info_row(keyword, desc):
    return {
        'name': f'Info Row {keyword[:6]}', 'type': 'frame',
        'layoutSizingHorizontal': 'FILL',
        'autoLayout': {'layoutMode': 'HORIZONTAL', 'itemSpacing': 12,
                       'counterAxisAlignItems': 'MIN'},
        'children': [
            {'name': 'Info Dot Wrap', 'type': 'frame', 'layoutSizingHorizontal': 'FIXED',
             'layoutSizingVertical': 'FIXED', 'width': 20, 'height': 24,
             'autoLayout': {'layoutMode': 'HORIZONTAL', 'primaryAxisAlignItems': 'CENTER',
                            'counterAxisAlignItems': 'CENTER'},
             'children': [
                 {'name': 'Info Dot', 'type': 'frame', 'layoutSizingHorizontal': 'FIXED',
                  'layoutSizingVertical': 'FIXED', 'width': 7, 'height': 7,
                  'cornerRadius': 999, 'fill': '$token(bg-brand-solid)',
                  'autoLayout': {'layoutMode': 'HORIZONTAL'}},
             ]},
            {'name': 'Info Texts', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
             'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 4},
             'children': [
                 txt('info-kw', keyword, 15, 700, '$token(fg-brand-primary)',
                     layoutSizingHorizontal='FILL', lineHeight=21),
                 txt('info-desc', desc, 13, 400, '$token(fg-secondary)',
                     layoutSizingHorizontal='FILL', lineHeight=19),
             ]},
        ],
    }


info_section = {
    'name': 'Info Section', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
    'autoLayout': {'layoutMode': 'VERTICAL', 'paddingLeft': 20, 'paddingRight': 20,
                   'paddingTop': 20, 'paddingBottom': 0},
    'children': [{
        'name': 'Info Card', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
        'fill': '$token(bg-brand-primary)', 'cornerRadius': 16,
        'autoLayout': {'layoutMode': 'VERTICAL', 'paddingLeft': 20, 'paddingRight': 20,
                       'paddingTop': 20, 'paddingBottom': 20, 'itemSpacing': 18},
        'children': [info_row(k, d) for k, d in INFO],
    }],
}

# ── 5. 문의 안내 노트 ────────────────────────────────────────────
contact_note = {
    'name': 'Contact Note', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
    'autoLayout': {'layoutMode': 'HORIZONTAL', 'paddingLeft': 24, 'paddingRight': 24,
                   'paddingTop': 14, 'paddingBottom': 0, 'itemSpacing': 6,
                   'counterAxisAlignItems': 'CENTER'},
    'children': [
        icon('icon-help', 'help-circle', 15, '$token(fg-tertiary)'),
        txt('contact-t', '신용 조회 문의 · KCB 고객센터 02-708-1000', 12, 500,
            '$token(fg-tertiary)', layoutSizingHorizontal='FILL'),
    ],
}

# ── 6. 하단 그룹 (동의 + CTA) ────────────────────────────────────
bottom_group = {
    'name': 'Bottom Group', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
    'autoLayout': {'layoutMode': 'VERTICAL', 'paddingLeft': 20, 'paddingRight': 20,
                   'paddingTop': 28, 'paddingBottom': 16, 'itemSpacing': 14},
    'children': [
        {'name': 'Consent Row', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
         'fill': '$token(bg-secondary)', 'cornerRadius': 12,
         'autoLayout': {'layoutMode': 'HORIZONTAL', 'paddingLeft': 14, 'paddingRight': 14,
                        'paddingTop': 14, 'paddingBottom': 14, 'itemSpacing': 10,
                        'primaryAxisAlignItems': 'SPACE_BETWEEN',
                        'counterAxisAlignItems': 'CENTER'},
         'children': [
             {'name': 'Consent Left', 'type': 'frame', 'layoutSizingHorizontal': 'HUG',
              'autoLayout': {'layoutMode': 'HORIZONTAL', 'itemSpacing': 9,
                             'counterAxisAlignItems': 'CENTER'},
              'children': [
                  icon('consent-check', 'check-circle', 22, '$token(fg-brand-primary)'),
                  txt('consent-t', '[필수] 개인(신용)정보 수집·이용·제공 동의', 13, 600,
                      '$token(fg-primary)'),
              ]},
             icon('consent-chevron', 'chevron-right', 18, '$token(fg-tertiary)'),
         ]},
        {'name': 'CTA Button', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
         'fill': '$token(bg-brand-solid)', 'cornerRadius': 14,
         'autoLayout': {'layoutMode': 'HORIZONTAL', 'paddingTop': 17, 'paddingBottom': 17,
                        'primaryAxisAlignItems': 'CENTER',
                        'counterAxisAlignItems': 'CENTER'},
         'children': [txt('cta-t', '다음', 16, 800, WHITE)]},
    ],
}

bp = {
    'rootName': 'credit_score_check_2026_0519',
    'name': 'credit_score_check_2026_0519',
    'type': 'frame', 'width': 393, 'height': 1000,
    'fill': '$token(bg-primary)',
    'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 0},
    'discoverySource': 'user-provided wireframe (신용점수 조회 동의) — 2026-05-19 신규 분석',
    'children': [top_bar, title_section, score_card, info_section, contact_note,
                 bottom_group],
    'references': [
        {
            'section': '동의/안내 화면 — 타이틀 + 정보 구조 + 하단 CTA',
            'ref': 'uibowl/kakaopay/cmgnmw6qu0003l904wzbwqthc.png',
            'extract': '필수 동의 설명 화면의 타이틀 + 라벨링된 정보 블록 + 하단 풀폭 CTA',
            '_searchLog': {
                'queries': ['신용점수 조회 카드 점수', '약관 동의 정보수집 다음 버튼 온보딩',
                            '안내 설명 정보 동의 모달 시작'],
                'candidates': ['uibowl/kakaopay/cmgnmw6qu0003l904wzbwqthc.png',
                               'uibowl/toss/cm7k1x52u0094l50cmcwjgn5a.png',
                               'uibowl/heydealer/cmliqezi000y8js04hoh57kks.png'],
                'chosen': 'uibowl/kakaopay/cmgnmw6qu0003l904wzbwqthc.png',
                'copyNotes': 'kakaopay 상세설명서: (필수) 타이틀 + 본문 + 라벨링된 정보 그리드 + 하단 풀폭 CTA(동의하기). 차용: 타이틀→정보블록→하단 CTA 구조. 폴리시(와이어 1:1 탈피): 평면 회색 점수카드를 짙은 brand 히어로 카드로 승격(alpha-white 점수칸), 4개 본문 텍스트 벽을 키워드 brand-bold + grey 설명의 3-row 정보카드로 재구성, 문의는 하단 저대비 노트로 분리.',
            },
        },
        {
            'section': '하단 풀폭 CTA + 모달 스텝 레이아웃',
            'ref': 'uibowl/toss/cm7k1x52u0094l50cmcwjgn5a.png',
            'extract': '타이틀 + 콘텐츠 + 하단 고정 풀폭 brand CTA 의 온보딩 스텝 레이아웃',
            '_searchLog': {
                'queries': ['온보딩 스텝 하단 CTA', '모달 시작 화면 다음 버튼'],
                'candidates': ['uibowl/toss/cm7k1x52u0094l50cmcwjgn5a.png',
                               'uibowl/kakaopay/cmgnmw6qu0003l904wzbwqthc.png',
                               'uibowl/heydealer/cmliqezi000y8js04hoh57kks.png'],
                'chosen': 'uibowl/toss/cm7k1x52u0094l50cmcwjgn5a.png',
                'copyNotes': 'toss 대출한도 계산기 온보딩: 상단 타이틀 + 콘텐츠 + 하단 풀폭 brand CTA. 차용: 하단 풀폭 CTA + 모달 스텝 구조(상단 X 닫기, 바텀 탭바 없음).',
            },
        },
    ],
}

out = 'scripts/blueprint_credit_score_2026_0519.json'
json.dump(bp, open(out, 'w'), ensure_ascii=False, indent=2)
print('written:', out)
