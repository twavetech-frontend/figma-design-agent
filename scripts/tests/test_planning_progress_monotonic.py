# -*- coding: utf-8 -*-
"""기획 통독 진행바 monotonic 회귀 테스트 (2026-06-08 사용자: "플러그인이 16/36 에서 멈춰있었다").

회귀: 비동기 Read 커버리지 훅 subprocess 가 순서 보장 없이 'reading' 알림을 보내, ack(done)
이후 늦게 도착한 stale 'reading'(예: 첫 청크 16/36)이 플러그인 진행바를 중간 상태로 되돌려
갇혔다. 송신 측 가드: 이미 통독 ack(.read.json) 됐으면 부분 Read 라도 'reading' 대신 'done'.
(수신 측 ui.html 은 done 후 reading/syncing 무시 — 별도 monotonic 가드, JS 라 여기선 미검증.)
"""
import importlib.util
import json
import os
import sys
import tempfile

_HOOK = os.path.join(os.path.dirname(__file__), "..", "hooks", "planning_read_hook.py")
_spec = importlib.util.spec_from_file_location("planning_read_hook", _HOOK)
h = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(h)


def _setup(tmp):
    """임시 digest + meta + ack 환경으로 훅 모듈 경로를 재바인딩."""
    digest = os.path.join(tmp, "_planning_digest.txt")
    lines = ["## UC-%02d 섹션\n" % i for i in range(1, 37)]
    # 36개 섹션 헤더 + 본문 채워 총 줄 수 늘리기
    body = "".join(lines) + "본문\n" * 200 + "통독 확인 토큰: abc123def456\n"
    with open(digest, "w", encoding="utf-8") as f:
        f.write(body)
    with open(digest + ".meta.json", "w", encoding="utf-8") as f:
        json.dump({"hash": "h1", "count": 36, "read_token": "abc123def456"}, f)
    h._DIGEST = digest
    h._META = digest + ".meta.json"
    h._ACK = digest + ".read.json"
    h._GATE_DIR = os.path.join(tmp, ".gate")
    os.makedirs(h._GATE_DIR, exist_ok=True)


def test_partial_read_sends_done_when_already_acked():
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp)
        # 이미 통독 ack 됨
        with open(h._ACK, "w", encoding="utf-8") as f:
            json.dump({"read_token": "abc123def456", "hash": "h1", "count": 36}, f)
        sent = []
        h._notify_plugin = lambda status, **d: sent.append((status, d))
        # 부분 Read(첫 청크, 16/36 수준) — ack 됐으니 done 이어야
        h._handle_post_read({
            "session_id": "s1",
            "tool_input": {"file_path": h._DIGEST, "offset": 1, "limit": 20},
            "tool_response": "showing lines 1-20 of 600 total",
        })
        assert sent, "알림이 전송되어야 한다"
        assert sent[-1][0] == "done", "ack 후엔 부분 Read 라도 reading 이 아니라 done"


def test_partial_read_sends_reading_when_not_acked():
    with tempfile.TemporaryDirectory() as tmp:
        _setup(tmp)
        # ack 없음(.read.json 미존재) — 부분 Read 는 reading(진행률) 이어야
        assert not os.path.exists(h._ACK)
        sent = []
        h._notify_plugin = lambda status, **d: sent.append((status, d))
        h._handle_post_read({
            "session_id": "s2",
            "tool_input": {"file_path": h._DIGEST, "offset": 1, "limit": 20},
            "tool_response": "showing lines 1-20 of 600 total",
        })
        # 부분이라 reading (단, 우연히 complete 판정 안 나도록 작은 범위)
        assert sent and sent[-1][0] == "reading", "ack 전 부분 Read 는 reading 진행률"
