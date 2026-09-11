"""clone_variant — 경로 해석·계획 수립 오프라인 테스트 (MCP 왕복 없음, 2026-09-11).
fixture = 05_stagedetail_1_1_1 (overlay) 4366:128696 트리(depth 4 prune)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..'))
sys.path.insert(0, os.path.join(HERE, '..', 'design_rules'))
import clone_variant as CV  # noqa: E402
import ds_catalog as C      # noqa: E402

FX = os.path.join(HERE, 'fixtures', 'clone_variant_stagedetail.json')
TREE = json.load(open(FX, encoding='utf-8'))

SPEC = {
    "source": "4366:128696", "name": "스테이지상세_참여전_빠른시작_DS", "viewport": 852,
    "delete": ["SB band (teal)", "초기화", "게시글", "stagedetail/arambubble/speech_bubble",
               "Member list/Member row[1]/Gift Pill", "Member list/Member row[2]/ic_crown"],
    "texts": [
        {"path": "Pink Header/stagedetail/top/TEXT[0]", "text": "빠른시작합시다."},
        {"path": "Member list/Member row[1]/TEXT[0]", "text": "벨벨", "styleFrom": "Member list/Member row[0]/TEXT[0]"},
        {"path": "Member list/Member row[2]/TEXT[0]", "text": "메리아리"},
    ],
    "pinBottom": ["stagedetail/arambubble"],
    "stageMembers": "auto",
}


def test_resolve_indexed_and_text_paths():
    n = CV.resolve_path(TREE, "Member list/Member row[1]/Gift Pill")
    assert n['name'] == 'Gift Pill' and n['id'] == '4366:128765'
    t = CV.resolve_path(TREE, "Pink Header/stagedetail/top/TEXT[0]")
    assert t['type'] == 'TEXT' and t['id'] == '4366:128720'
    assert CV.resolve_path(TREE, "4366:128809")['name'].startswith('스테이지가 시작되면')


def test_missing_path_raises_with_context():
    try:
        CV.resolve_path(TREE, "Member list/Member row[9]/TEXT[0]")
    except KeyError as e:
        assert 'Member row[9]' in str(e)
    else:
        raise AssertionError('KeyError 기대')


def test_plan_stage_color_auto_from_total_deposit_count():
    plan = CV.build_plan(SPEC, TREE)
    assert plan['stage']['members'] == 13
    assert plan['stage']['style']['name'].endswith('13 - pink')
    # 대상: Status Bar + Pink Header + 순번 + Num circle×8 = 11, 인스턴스 내부(';') 제외
    assert len(plan['stage']['targets']) == 11
    assert all(';' not in t for t in plan['stage']['targets'])


def test_plan_texts_delete_pin():
    plan = CV.build_plan(SPEC, TREE)
    assert [d['name'] for d in plan['delete']] == ['SB band (teal)', '초기화', '게시글', 'speech_bubble', 'Gift Pill', 'ic_crown']
    t2 = [t for t in plan['texts'] if t['text'] == '벨벨'][0]
    assert t2['styleFromId'] == '4366:128760' and t2['parentId'] == '4366:128761' and t2['index'] == 1
    assert t2['old'] == '월 103,304 원'
    pin = plan['pinBottom'][0]
    assert pin['id'] == '4366:128930' and pin['y'] == 852 - 112


def test_stage_members_inference_and_unknown_count():
    assert C.infer_stage_members(['총 입금', '13회']) == 13
    assert C.infer_stage_members(['9명 스테이지']) == 9
    assert C.infer_stage_members(['총 입금 12회']) is None   # 정의 밖 인원수 → 날조 금지
    assert C.stage_color_style(7)['hex'] == '#9095f9'
    assert C.stage_color_style(6) is None


def test_plan_without_stage_when_not_inferable():
    spec = dict(SPEC, stageMembers=None)
    assert CV.build_plan(spec, TREE)['stage'] is None
