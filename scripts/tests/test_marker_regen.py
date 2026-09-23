"""marker_regen — 후보 영역·옛 마커 귀속·병합 오프라인 테스트 (MCP 없음, 2026-09-23)."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
import marker_regen as MR  # noqa: E402


def frame(id_, name, y, h, children=None, type_='FRAME', visible=True):
    return {'id': id_, 'name': name, 'type': type_, 'y': y, 'height': h, 'visible': visible, 'children': children or []}


TREE = frame('root', 'imin_x', 0, 852, [
    frame('sb', 'Status Bar', 0, 62, type_='INSTANCE'),
    frame('dim', 'Dim Overlay', 62, 100),
    frame('sheet', 'Modal Sheet', 162, 690, [
        frame('intro', 'Notice Intro', 0, 156, [{'id': 't1', 'type': 'TEXT', 'characters': '이용약관과 운영정책이\n개정될 예정이에요'}]),
        frame('rule', 'Row Rule', 156, 1),
        frame('block', 'Change Block', 180, 236),
        frame('note', 'Deemed Consent Note', 430, 40),
        frame('acts', 'Sheet Actions', 480, 128, [frame('cta', 'Agree CTA', 0, 56, [{'id': 't2', 'type': 'TEXT', 'characters': '확인했어요'}], type_='INSTANCE')]),
    ]),
])


def test_candidate_areas_unwraps_sheet_and_skips_bars_and_rules():
    areas = MR.candidate_areas(TREE)
    assert [a['name'] for a in areas] == ['Notice Intro', 'Change Block', 'Deemed Consent Note', 'Sheet Actions']
    assert areas[0]['y'] == 162 and areas[1]['y'] == 342     # 랩(Modal Sheet y162) 오프셋 합산


def test_legacy_alignment_survives_uniform_shift_and_leaves_far_markers_unmatched():
    areas = MR.candidate_areas(TREE)                          # y: intro 162, block 342, note 592, acts 642
    # 시트가 122px 밀린 옛 마커 4개 → 순서 정렬로 제 영역 복귀
    assert MR.align_legacy([284, 464, 714, 764], areas) == ['intro', 'block', 'note', 'acts']
    # 마커 3개(중간 영역 하나 없음) → 가까운 셋만 짝, note 는 비어 있음
    assert MR.align_legacy([162, 342, 642], areas) == ['intro', 'block', 'acts']
    # 아주 먼 마커(y 1500)는 짝 없이 남는다
    assert MR.align_legacy([162, 1500], areas) == ['intro', None]


def test_marker_name_roundtrip_multi():
    assert MR.parse_marker(MR.marker_name(3, '4802:1')) == (3, ['4802:1'])
    assert MR.parse_marker(MR.marker_name(2, ['a', 'b'])) == (2, ['a', 'b'])
    assert MR.parse_marker('Description') == (None, [])


def test_merge_keeps_adds_draft_and_removes_and_reorders():
    areas = MR.candidate_areas(TREE)
    existing = [
        {'n': 1, 'sections': ['intro'], 'text': '헤더\n[기능]\n· a'},
        {'n': 2, 'sections': ['gone'], 'text': '삭제된 영역'},
        {'n': 3, 'sections': ['acts'], 'text': '액션\n[기능]\n· b'},
    ]
    rows, rep = MR.merge(existing, areas)
    assert [r['sections'][0] for r in rows] == ['intro', 'block', 'note', 'acts']   # 현재 y 순 + 새 영역 2개 삽입
    assert [r['status'] for r in rows] == ['kept', 'added', 'added', 'kept']
    assert rep['removed'][0]['sections'] == ['gone'] and len(rep['added']) == 2
    assert rows[1]['text'].startswith('Change Block 영역 (초안 — 작성 필요)\n[기능]')


def test_merge_fold_absorbs_uncovered_areas_into_previous_row():
    areas = MR.candidate_areas(TREE)
    existing = [{'n': 1, 'sections': ['intro'], 'text': 't1'}, {'n': 2, 'sections': ['acts'], 'text': 't2'}]
    rows, rep = MR.merge(existing, areas, fold=True)
    assert [r['sections'] for r in rows] == [['intro', 'block', 'note'], ['acts']]
    assert rep['added'] == [] and [f['name'] for f in rep['folded']] == ['Change Block', 'Deemed Consent Note']
    # 다음 regen 에선 커버된 영역이라 초안이 생기지 않는다
    rows2, rep2 = MR.merge([{'n': 1, 'sections': ['intro', 'block', 'note'], 'text': 't1'}, {'n': 2, 'sections': ['acts'], 'text': 't2'}], areas)
    assert rep2['added'] == [] and len(rows2) == 2


def test_draft_row_lists_texts_and_buttons_without_inventing():
    areas = MR.candidate_areas(TREE)
    acts = [a for a in areas if a['id'] == 'acts'][0]
    d = MR.draft_row(acts)
    assert "버튼 '확인했어요': {동작: 확인 필요}" in d and '[예외처리]' in d
