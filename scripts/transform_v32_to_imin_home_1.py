#!/usr/bin/env python3
"""v32 블루프린트를 선택 노드(17015:73113)의 imin_home_1 PRD/와이어프레임에 맞게 변환."""
import json, copy

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
    if 'characters' in n:
        n['characters'] = value
    else:
        n['text'] = value


bp = copy.deepcopy(src)
bp['rootName'] = 'imin_home_1'
bp['name'] = 'imin_home_1'
bp['discoverySource'] = 'selected-node:17015:73113 (imin_home_1 PRD)'

# --- 1) 불필요 섹션 제거 (RULE 0: 와이어프레임에 없는 섹션) ---
drop = {'Missed Alert Wrap', 'Credit Section'}
bp['children'] = [c for c in bp['children'] if c.get('name') not in drop]

# --- 2) Attendance Event Section → Attendance Section (Event Banner 제거) ---
att = find(bp, 'Attendance Event Section')
att['name'] = 'Attendance Section'
att['children'] = [c for c in att['children'] if c.get('name') != 'Event Banner Wrap']

# --- 3) 섹션 순서 재배치 (와이어프레임 기준) ---
order = ['NavBar', 'Segmented Tabs Wrap', 'Summary Section', 'Schedule Section',
         'Attendance Section', 'Recommend Section', 'Stage List Section',
         'Lounge Section', 'Footer Section', 'Tab Bar']
by_name = {c['name']: c for c in bp['children']}
missing = [n for n in order if n not in by_name]
assert not missing, f'missing sections: {missing}'
assert len(by_name) == len(order), f'extra sections: {set(by_name)-set(order)}'
bp['children'] = [by_name[n] for n in order]

# --- 4) 콘텐츠를 PRD에 맞춤 ---
# 4.1 거래 현황 / 누적 거래 탭
seg = find(bp, 'Segmented Tabs')
set_text(seg, 'label', '거래 현황')          # 첫 자식
seg['children'][0]['name'] = 'Tab 거래현황 (Active)'
seg['children'][1]['name'] = 'Tab 누적거래'
seg['children'][1]['children'][0]['characters' if 'characters' in seg['children'][1]['children'][0] else 'text'] = '누적 거래'

# 4.2 Summary 카드 — 신규 사용자 zero state
summ = find(bp, 'Summary Section')
set_text(summ, 'bigTitle', '진행중인 0건의 스테이지 내역')
set_text(summ, 'val', '+ 0원')               # Row Collected
# Row Due 라벨/값
due = find(summ, 'Row Due')
due['children'][0]['characters' if 'characters' in due['children'][0] else 'text'] = '빌린 금액'
due['children'][1]['characters' if 'characters' in due['children'][1] else 'text'] = '- 0원'

# 4.3 출석 배너
att_s = find(bp, 'Attendance Section')
set_text(att_s, 'title', '연속 0일째 출석 체크 중')
set_text(att_s, 'subtitle', '매일매일 출첵하면 특별한 혜택이!')

# 4.4 추천 스테이지 — eyebrow를 PRD 유도 문구로
rec = find(bp, 'Recommend Section')
set_text(rec, 'Eyebrow', '얼마까지 모을 수 있는지 확인해보세요')

# 4.5 라운지 — 예치금(포인트)
lng = find(bp, 'Lounge Section')
set_text(lng, 'Wallet', '예치금(포인트): 312,490원(100p)')

# 4.6 Tab Bar — 홈/라운지/스테이지/커뮤니티/전체
tb = find(bp, 'Tab Bar')
tabs = {c['name']: c for c in tb['children']}
tb['children'] = [tabs['Tab Home'], tabs['Tab Lounge'], tabs['Tab Stage'],
                  tabs['Tab Community'], tabs['Tab Me']]
set_text(tabs['Tab Me'], 'tab-me-label', '전체')


def relabel(tab, lab):
    for c in tab.get('children', []):
        if c.get('type') == 'text':
            c['characters' if 'characters' in c else 'text'] = lab


relabel(tabs['Tab Home'], '홈')
relabel(tabs['Tab Lounge'], '라운지')
relabel(tabs['Tab Stage'], '스테이지')
relabel(tabs['Tab Community'], '커뮤니티')
relabel(tabs['Tab Me'], '전체')

# --- 5) references[] (S20/S21) ---
bp['references'] = [
    {
        "section": "전체 레이아웃 / 세그먼트 탭 / 요약 카드 / 푸터",
        "ref": "in-file 16941:51284",
        "extract": "imin_home 캐노니컬: 흰 pill on 회색 track 세그먼트 탭, brand 위 알파-화이트 sub-component, Footer legal 텍스트 블록",
        "_searchLog": {
            "queries": ["imin home canonical 거래 현황", "홈 잔액 요약 카드"],
            "candidates": ["in-file 16941:51284", "in-file 17015:73113",
                           "uibowl/toss/cm7k1isty000yjy0cucjybjl6.png"],
            "chosen": "in-file 16941:51284",
            "copyNotes": "세그먼트 높이 40 track radius 20 active white pill radius 16; 요약 카드 brand-solid 배경 위 36px Bold 흰 금액; Footer 이용약관·개인정보처리방침·사업자등록번호 12px fg-tertiary 좌측 정렬. v32 검증 빌드 구조 그대로 차용, PRD 17015:73113 와이어프레임 섹션 순서 반영."
        }
    },
    {
        "section": "추천 스테이지 카드 / 출석 배너 / 라운지 리스트",
        "ref": "uibowl/kakaopay/cmgno0mt2000zjy04ks467n95.png",
        "extract": "추천 카드 썸네일+제목+혜택 + 노란 pill, 회색 섹션 구분 배경, 리스트 아이템 좌측 썸네일+2줄 텍스트+우측 가격",
        "_searchLog": {
            "queries": ["적금 상품 추천 카드 보라", "포인트 상품 가로 카드", "출석 체크 배너"],
            "candidates": ["uibowl/kakaopay/cmgno0mt2000zjy04ks467n95.png",
                           "uibowl/kakaopay/cm8zjuej30001kz0d9fq3tl76.png",
                           "uibowl/kakaopay/cmgnmig7d0003l804mvcop25n.png"],
            "chosen": "uibowl/kakaopay/cmgno0mt2000zjy04ks467n95.png",
            "copyNotes": "카드 행 좌측 56px 썸네일 + 중앙 2줄 텍스트(회색 라벨/굵은 제목) + 우측 노란 둥근 pill + chevron; 섹션 사이 8px 회색 divider band, 섹션 타이틀 18px Bold, 출석 배너는 좌 아이콘+2줄텍스트 우 버튼."
        }
    }
]

json.dump(bp, open('scripts/blueprint_imin_home_1_v33.json', 'w'),
          ensure_ascii=False, indent=2)
print('written: scripts/blueprint_imin_home_1_v33.json')
print('sections:', [c['name'] for c in bp['children']])
