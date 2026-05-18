#!/usr/bin/env python3
"""v32 블루프린트를 선택 노드(17015:73114)의 '홈 > 거래 스케줄 화면' PRD에 맞게 변환.

imin_home과 8섹션 유사하나 1.6이 '거래 스케줄 캘린더'(신규 custom 섹션),
헤더에 X 닫기 버튼 추가.
"""
import copy
import json

src = json.load(open('scripts/blueprint_imin_home_v32.json'))


def find(node, name):
    if node.get('name') == name:
        return node
    for c in node.get('children', []):
        r = find(c, name)
        if r:
            return r
    return None


def set_text(node, name, value):
    n = find(node, name)
    if n is None:
        raise SystemExit(f'!! text node not found: {name}')
    n['characters' if 'characters' in n else 'text'] = value


bp = copy.deepcopy(src)
bp['rootName'] = 'home_schedule'
bp['name'] = 'home_schedule'
bp['discoverySource'] = 'selected-node:17015:73114 (home > schedule PRD)'

# --- 불필요 섹션 제거 (RULE 0) ---
drop = {'Missed Alert Wrap', 'Credit Section', 'Schedule Section', 'Stage List Section'}
bp['children'] = [c for c in bp['children'] if c.get('name') not in drop]

# --- Attendance Event Section → Attendance Section (Event Banner 제거) ---
att = find(bp, 'Attendance Event Section')
att['name'] = 'Attendance Section'
att['children'] = [c for c in att['children'] if c.get('name') != 'Event Banner Wrap']

# --- 1.1 NavBar: X 닫기 버튼 추가 ---
nav_right = find(bp, 'Nav Right')
nav_right['children'].append({
    'name': 'icon-x', 'type': 'icon', 'iconName': 'x-close',
    'size': 24, 'iconColor': '$token(fg-primary)',
})

# --- 1.2 거래 현황 / 누적 거래 탭 ---
seg = find(bp, 'Segmented Tabs')
seg['children'][0]['name'] = 'Tab 거래현황 (Active)'
seg['children'][1]['name'] = 'Tab 누적거래'
set_text(seg['children'][0], 'label', '거래 현황')
set_text(seg['children'][1], 'label', '누적 거래')

# --- 1.3 Summary 카드 — 신규 사용자 zero state ---
summ = find(bp, 'Summary Section')
set_text(summ, 'bigTitle', '진행중인 0건의 스테이지 내역')
set_text(summ, 'val', '+ 0원')
due = find(summ, 'Row Due')
due['children'][0]['characters' if 'characters' in due['children'][0] else 'text'] = '빌린 금액'
due['children'][1]['characters' if 'characters' in due['children'][1] else 'text'] = '- 0원'

# --- 1.4 출석 배너 ---
att_s = find(bp, 'Attendance Section')
set_text(att_s, 'title', '연속 0일째 출석 체크 중')
set_text(att_s, 'subtitle', '매일매일 출첵하면 특별한 혜택이!')

# --- 1.5 추천 스테이지 eyebrow ---
set_text(find(bp, 'Recommend Section'), 'Eyebrow', '민지님을 위한 추천 스테이지')

# --- 1.7 라운지 ---
set_text(find(bp, 'Lounge Section'), 'Wallet', '예치금(포인트): 312,490원(100p)')

# --- 1.8 Tab Bar — 홈/라운지/스테이지/커뮤니티/전체 ---
tb = find(bp, 'Tab Bar')
tabs = {c['name']: c for c in tb['children']}
tb['children'] = [tabs['Tab Home'], tabs['Tab Lounge'], tabs['Tab Stage'],
                  tabs['Tab Community'], tabs['Tab Me']]
labels = {'Tab Home': '홈', 'Tab Lounge': '라운지', 'Tab Stage': '스테이지',
          'Tab Community': '커뮤니티', 'Tab Me': '전체'}
for tname, lab in labels.items():
    for c in tabs[tname].get('children', []):
        if c.get('type') == 'text':
            c['characters' if 'characters' in c else 'text'] = lab

# ===================================================================
# 신규 섹션 1: Calc Prompt (한도 확인 유도 배너)
# ===================================================================
calc_prompt = {
    'name': 'Calc Prompt Section', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
    'fill': '$token(bg-primary)',
    'autoLayout': {'layoutMode': 'VERTICAL', 'paddingTop': 8, 'paddingBottom': 8,
                   'paddingLeft': 16, 'paddingRight': 16},
    'children': [{
        'name': 'Calc Prompt Banner', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
        'fill': '$token(bg-secondary)', 'cornerRadius': 16,
        'autoLayout': {'layoutMode': 'HORIZONTAL', 'paddingTop': 14, 'paddingBottom': 14,
                       'paddingLeft': 16, 'paddingRight': 16, 'itemSpacing': 14,
                       'counterAxisAlignItems': 'CENTER'},
        'children': [
            {'name': 'Calc Ring', 'type': 'frame', 'width': 36, 'height': 36,
             'cornerRadius': 18, 'fill': {'r': 1, 'g': 1, 'b': 1, 'a': 1},
             'stroke': '$token(fg-brand-primary)', 'strokeWeight': 2,
             'autoLayout': {'layoutMode': 'HORIZONTAL', 'primaryAxisAlignItems': 'CENTER',
                            'counterAxisAlignItems': 'CENTER'},
             'children': [{'name': 'Calc Ring Q', 'type': 'text', 'characters': '?',
                           'fontSize': 16, 'fontWeight': 700,
                           'fontColor': '$token(text-brand-primary)'}]},
            {'name': 'Calc Prompt Label', 'type': 'text', 'layoutSizingHorizontal': 'HUG',
             'characters': '스테이지 이용을 위해 한도를 확인해주세요.',
             'fontSize': 14, 'fontWeight': 500, 'fontColor': '$token(text-secondary)'},
        ],
    }],
}

# ===================================================================
# 신규 섹션 2: Calendar Section (거래 스케줄 캘린더)
# ===================================================================
MONTHS = [('Oct', '10'), ('Nov', '11'), ('Dec', '12'), ('Jan', '1'),
          ('Feb', '2'), ('Mar', '3'), ('Apr', '4')]


def month_item(abbr, num, active):
    children = [{'name': 'm-abbr', 'type': 'text', 'characters': abbr,
                 'fontSize': 11, 'fontWeight': 500,
                 'fontColor': '$token(text-brand-primary)' if active else '$token(text-tertiary)'}]
    if active:
        children.append({
            'name': 'm-num-circle', 'type': 'frame', 'width': 28, 'height': 28,
            'cornerRadius': 14, 'fill': '$token(bg-brand-solid)',
            'autoLayout': {'layoutMode': 'HORIZONTAL', 'primaryAxisAlignItems': 'CENTER',
                           'counterAxisAlignItems': 'CENTER'},
            'children': [{'name': 'm-num', 'type': 'text', 'characters': num,
                          'fontSize': 14, 'fontWeight': 700,
                          'fontColor': '$token(text-white)'}]})
        children.append({'name': 'm-today', 'type': 'text', 'characters': '이번달',
                          'fontSize': 10, 'fontWeight': 500,
                          'fontColor': '$token(text-brand-primary)'})
    else:
        children.append({'name': 'm-num', 'type': 'text', 'characters': num,
                          'fontSize': 14, 'fontWeight': 600,
                          'fontColor': '$token(text-secondary)'})
    return {'name': f'Month {abbr}', 'type': 'frame', 'layoutSizingHorizontal': 'HUG',
            'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 4,
                           'counterAxisAlignItems': 'CENTER'},
            'children': children}


def stat_col(label, value):
    return {'name': f'Stat {label}', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
            'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 4},
            'children': [
                {'name': 's-label', 'type': 'text', 'characters': label,
                 'fontSize': 12, 'fontWeight': 500, 'fontColor': '$token(text-tertiary)'},
                {'name': 's-value', 'type': 'text', 'characters': value,
                 'fontSize': 15, 'fontWeight': 700, 'fontColor': '$token(text-primary)'},
            ]}


calendar = {
    'name': 'Calendar Section', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
    'fill': '$token(bg-primary)',
    'autoLayout': {'layoutMode': 'VERTICAL', 'paddingTop': 8, 'paddingBottom': 16,
                   'paddingLeft': 16, 'paddingRight': 16},
    'children': [{
        'name': 'Calendar Card', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
        'fill': '$token(bg-secondary)', 'cornerRadius': 16,
        'autoLayout': {'layoutMode': 'VERTICAL', 'paddingTop': 20, 'paddingBottom': 20,
                       'paddingLeft': 18, 'paddingRight': 18, 'itemSpacing': 16},
        'children': [
            # 타이틀
            {'name': 'Calendar Title', 'type': 'text', 'layoutSizingHorizontal': 'FILL',
             'characters': '거래 스케줄', 'fontSize': 16, 'fontWeight': 700,
             'fontColor': '$token(text-primary)', 'textAlignHorizontal': 'CENTER'},
            # 월 네비게이션 (◀ 월탭들 ▶)
            {'name': 'Month Nav Row', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
             'autoLayout': {'layoutMode': 'HORIZONTAL', 'itemSpacing': 4,
                            'counterAxisAlignItems': 'CENTER'},
             'children': [
                 {'name': 'cal-prev', 'type': 'icon', 'iconName': 'chevron-left',
                  'size': 20, 'iconColor': '$token(fg-tertiary)'},
                 {'name': 'Month Tabs', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
                  '_repetitionAllowed': '월 선택기 — Oct~Apr 7개월 탭은 캘린더 필수 UI',
                  'autoLayout': {'layoutMode': 'HORIZONTAL',
                                 'primaryAxisAlignItems': 'SPACE_BETWEEN',
                                 'counterAxisAlignItems': 'CENTER'},
                  'children': [month_item(a, n, a == 'Jan') for a, n in MONTHS]},
                 {'name': 'cal-next', 'type': 'icon', 'iconName': 'chevron-right',
                  'size': 20, 'iconColor': '$token(fg-tertiary)'},
             ]},
            # 필터 ("납입 ▾")
            {'name': 'Filter Row', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
             'autoLayout': {'layoutMode': 'HORIZONTAL', 'primaryAxisAlignItems': 'MAX',
                            'counterAxisAlignItems': 'CENTER'},
             'children': [{
                 'name': 'Filter Chip', 'type': 'frame', 'layoutSizingHorizontal': 'HUG',
                 'fill': '$token(bg-primary)', 'cornerRadius': 8,
                 'stroke': '$token(border-secondary)', 'strokeWeight': 1,
                 'autoLayout': {'layoutMode': 'HORIZONTAL', 'itemSpacing': 4,
                                'paddingTop': 6, 'paddingBottom': 6,
                                'paddingLeft': 12, 'paddingRight': 10,
                                'counterAxisAlignItems': 'CENTER'},
                 'children': [
                     {'name': 'f-label', 'type': 'text', 'characters': '납입',
                      'fontSize': 12, 'fontWeight': 500,
                      'fontColor': '$token(text-secondary)'},
                     {'name': 'f-chevron', 'type': 'icon', 'iconName': 'chevron-down',
                      'size': 14, 'iconColor': '$token(fg-tertiary)'},
                 ]}]},
            # 통계 밴드 (월 납입액 / 납입 완료액 / 남은 납입액)
            {'name': 'Stats Band', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
             'fill': '$token(bg-primary)', 'cornerRadius': 12,
             'autoLayout': {'layoutMode': 'HORIZONTAL', 'itemSpacing': 8,
                            'paddingTop': 14, 'paddingBottom': 14,
                            'paddingLeft': 16, 'paddingRight': 16},
             'children': [stat_col('월 납입액', '0원'), stat_col('납입 완료액', '0원'),
                          stat_col('남은 납입액', '0원')]},
            # 월 요약 (2026년 1월 / 총 0건)
            {'name': 'Month Summary Row', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
             'autoLayout': {'layoutMode': 'HORIZONTAL',
                            'primaryAxisAlignItems': 'SPACE_BETWEEN',
                            'counterAxisAlignItems': 'CENTER'},
             'children': [
                 {'name': 'cal-month', 'type': 'text', 'characters': '2026년 1월',
                  'fontSize': 14, 'fontWeight': 700, 'fontColor': '$token(text-primary)'},
                 {'name': 'cal-count', 'type': 'text', 'characters': '총 0건',
                  'fontSize': 14, 'fontWeight': 500, 'fontColor': '$token(text-tertiary)'},
             ]},
            # 빈 상태
            {'name': 'Calendar Empty', 'type': 'frame', 'layoutSizingHorizontal': 'FILL',
             'autoLayout': {'layoutMode': 'VERTICAL', 'itemSpacing': 6,
                            'paddingTop': 24, 'paddingBottom': 24,
                            'counterAxisAlignItems': 'CENTER'},
             'children': [
                 {'name': 'empty-title', 'type': 'text', 'characters': '납입할 금액이 없습니다.',
                  'fontSize': 15, 'fontWeight': 700, 'fontColor': '$token(text-secondary)',
                  'textAlignHorizontal': 'CENTER'},
                 {'name': 'empty-sub', 'type': 'text',
                  'characters': '아임인과 함께 목돈 모으기를 시작해보세요.',
                  'fontSize': 13, 'fontWeight': 500,
                  'fontColor': '$token(text-brand-primary)',
                  'textAlignHorizontal': 'CENTER'},
             ]},
        ],
    }],
}

# --- 섹션 순서 재배치 + 신규 섹션 삽입 ---
order = ['NavBar', 'Segmented Tabs Wrap', 'Summary Section', 'Attendance Section',
         'Recommend Section', 'Lounge Section', 'Footer Section', 'Tab Bar']
by_name = {c['name']: c for c in bp['children']}
missing = [n for n in order if n not in by_name]
assert not missing, f'missing: {missing}'
new_children = [
    by_name['NavBar'], by_name['Segmented Tabs Wrap'], by_name['Summary Section'],
    by_name['Attendance Section'], calc_prompt, by_name['Recommend Section'],
    calendar, by_name['Lounge Section'], by_name['Footer Section'], by_name['Tab Bar'],
]
bp['children'] = new_children

# --- references[] (S20/S21) ---
bp['references'] = [
    {
        'section': '전체 레이아웃 / 세그먼트 탭 / 요약 카드 / 푸터',
        'ref': 'in-file 16941:51284',
        'extract': 'imin_home 캐노니컬: 흰 pill on 회색 track 세그먼트 탭, brand 위 알파-화이트 sub, Footer legal 블록',
        '_searchLog': {
            'queries': ['imin home canonical', '홈 거래 현황 요약'],
            'candidates': ['in-file 16941:51284', 'in-file 17015:73114',
                           'uibowl/toss/cm7k1isty000yjy0cucjybjl6.png'],
            'chosen': 'in-file 16941:51284',
            'copyNotes': '세그먼트 높이 40 track radius 20 active white pill radius 16; 요약 카드 brand 배경 위 흰 금액; Footer 12px fg-tertiary 좌측 정렬. v32 검증 빌드 구조 차용, PRD 17015:73114 와이어프레임 섹션 순서 반영.',
        },
    },
    {
        'section': '거래 스케줄 캘린더 (월 탭 + 통계 밴드 + 빈 상태)',
        'ref': 'uibowl/toss/cm7k1isty000yjy0cucjybjl6.png',
        'extract': '월 탭 가로 스크롤 + 선택 월 원형 강조, 회색 통계 밴드 3컬럼, 중앙 정렬 빈 상태 안내 + 브랜드 링크',
        '_searchLog': {
            'queries': ['납입 일정 캘린더 월 탭', '거래 내역 빈 상태', '월별 스케줄 캘린더'],
            'candidates': ['uibowl/toss/cm7k1isty000yjy0cucjybjl6.png',
                           'uibowl/kakaopay/cmgnmig7d0003l804mvcop25n.png',
                           'uibowl/toss/cm7k1isub0010jy0c6atzxh5a.mp4'],
            'chosen': 'uibowl/toss/cm7k1isty000yjy0cucjybjl6.png',
            'copyNotes': '월 탭 행: 약어(11px 회색) 위, 숫자(14px) 아래, 선택 월은 28px brand 원 + 흰 숫자 + 이번달 라벨. 통계는 옅은 카드 밴드 안 3컬럼(라벨 12 회색 / 값 15 굵게). 빈 상태는 24px 상하 패딩 중앙 정렬, 굵은 안내 + 브랜드 링크.',
        },
    },
]

out = 'scripts/blueprint_home_schedule_v1.json'
json.dump(bp, open(out, 'w'), ensure_ascii=False, indent=2)
print('written:', out)
print('sections:', [c['name'] for c in bp['children']])
