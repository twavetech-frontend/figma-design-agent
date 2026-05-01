# Semantic Token Binding Sweep Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 빌드 직후 `_bind_semantic_tokens` post-fix 6단계를 추가해 raw 컬러/간격/radius/typography/shadow 값을 `ds/TOKEN_MAP.json`의 semantic 토큰에 자동 바인딩한다.

**Architecture:** `scripts/figma_mcp_client.py`에 모듈 함수 추가 (별도 파일 분리 X — 기존 `_fix_*` post-fix 함수와 동일 패턴 유지). `_load_token_index`로 역인덱스 4종 빌드, 4개 매처(`_match_color/number/textstyle/shadow`)로 임계치 안에서 후보 선정 (semantic 우선), `_collect_bindings`로 노드 트리에서 추출, `_apply_bindings`로 `batch_bind_variables` / `batch_set_text_style_id` / `set_effect_style_id` 일괄 호출.

**Tech Stack:** Python 3 표준 라이브러리 (unittest, json, math). 추가 의존성 없음.

**Spec 참조:** `docs/superpowers/specs/2026-05-01-token-binding-sweep-design.md`

---

## File Structure

| 파일 | 역할 | 변경 형태 |
|---|---|---|
| `scripts/figma_mcp_client.py` | 모든 sweep 함수 + post-fix 통합 + CLI flag | 수정 (line 2382 부근에 함수 추가, `cmd_post_fix` 내 호출 추가, `cmd_build` argparse 수정) |
| `scripts/tests/__init__.py` | 패키지 마커 | 신규 (빈 파일) |
| `scripts/tests/test_token_binding_sweep.py` | unittest 테스트 (matcher 4종 + collector + index loader) | 신규 |
| `scripts/tests/fixtures/sample_token_map.json` | 테스트용 축약 TOKEN_MAP | 신규 |

테스트 실행 명령: `python3 -m unittest scripts.tests.test_token_binding_sweep -v` (프로젝트 루트에서)

---

## Task 1: Token Index Loader (`_load_token_index`)

**Files:**
- Modify: `scripts/figma_mcp_client.py` — 파일 끝(`if __name__ == "__main__"` 직전)에 추가
- Create: `scripts/tests/__init__.py`
- Create: `scripts/tests/fixtures/sample_token_map.json`
- Create: `scripts/tests/test_token_binding_sweep.py`

- [ ] **Step 1: Create test fixtures and empty package**

Create `scripts/tests/__init__.py`:

```python
```

(empty file)

Create `scripts/tests/fixtures/sample_token_map.json`:

```json
{
  "--colors-grayLightMode-900": {
    "figmaPath": "Colors/Gray (light mode)/900",
    "value": "#181d27",
    "type": "COLOR"
  },
  "--colors-text-textPrimary": {
    "figmaPath": "Colors/Text/text-primary",
    "value": "#181d27",
    "type": "COLOR"
  },
  "--colors-bg-bgBrandSolid": {
    "figmaPath": "Colors/Bg/bg-brand-solid",
    "value": "#7700ff",
    "type": "COLOR"
  },
  "--spacing-2-8px": {
    "figmaPath": "Spacing/2 (8px)",
    "value": 8,
    "type": "NUMBER"
  },
  "--spacing-3-12px": {
    "figmaPath": "Spacing/3 (12px)",
    "value": 12,
    "type": "NUMBER"
  },
  "--fontSize-2": {
    "figmaPath": "fontSize/2",
    "value": 16,
    "type": "NUMBER"
  },
  "--display2xl-semibold": {
    "figmaPath": "Display 2xl/Semibold",
    "value": {
      "fontFamily": "{Font family.font-family-display}",
      "fontWeight": "{Font weight.semibold}",
      "lineHeight": "{Line height.display-2xl}",
      "fontSize": "{fontSize.10}",
      "letterSpacing": "{letterSpacing.0}"
    },
    "type": "TYPOGRAPHY"
  }
}
```

- [ ] **Step 2: Write failing test for `_load_token_index`**

Create `scripts/tests/test_token_binding_sweep.py`:

```python
import json
import os
import sys
import unittest

# Add scripts dir to path so we can import figma_mcp_client
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import figma_mcp_client as fmc

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "fixtures", "sample_token_map.json")


def load_fixture():
    with open(FIXTURE_PATH) as f:
        return json.load(f)


class TestLoadTokenIndex(unittest.TestCase):
    def test_color_index_groups_same_value(self):
        idx = fmc._load_token_index(load_fixture())
        # Both grayLightMode-900 and text-textPrimary share #181d27
        key = (24, 29, 39, 1.0)  # rgba normalized to 0-255 ints + alpha float
        self.assertIn(key, idx["color_index"])
        names = [t[0] for t in idx["color_index"][key]]
        self.assertIn("--colors-text-textPrimary", names)
        self.assertIn("--colors-grayLightMode-900", names)

    def test_color_index_marks_semantic_first(self):
        idx = fmc._load_token_index(load_fixture())
        key = (24, 29, 39, 1.0)
        # semantic (text-*) should come before primitive (gray*)
        first_token, first_is_semantic = idx["color_index"][key][0]
        self.assertEqual(first_token, "--colors-text-textPrimary")
        self.assertTrue(first_is_semantic)

    def test_number_index_groups_value(self):
        idx = fmc._load_token_index(load_fixture())
        self.assertIn(8, idx["number_index"])
        self.assertIn(("--spacing-2-8px", False), idx["number_index"][8])

    def test_typography_list_resolves_references(self):
        idx = fmc._load_token_index(load_fixture())
        self.assertEqual(len(idx["typography_list"]), 1)
        ts = idx["typography_list"][0]
        self.assertEqual(ts["name"], "--display2xl-semibold")
        # fontSize.10 → 72 (from sample_token_map)... but our fixture only has fontSize.2.
        # When resolution fails the value stays as raw reference string — test that we keep it.
        self.assertTrue("fontSize" in ts)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd /Users/julee/imin/figma-design-agent
python3 -m unittest scripts.tests.test_token_binding_sweep -v
```

Expected: FAIL with `AttributeError: module 'figma_mcp_client' has no attribute '_load_token_index'`

- [ ] **Step 4: Implement `_load_token_index`**

Append to `scripts/figma_mcp_client.py` (just before the final `if __name__ == "__main__":` block):

```python
# ============================================================
# Semantic Token Binding Sweep (post-fix step 6)
# ============================================================

_SEMANTIC_PREFIXES = ("fg-", "bg-", "border-", "text-")
_SEMANTIC_PATH_PARTS = ("/Fg/", "/Bg/", "/Border/", "/Text/")


def _is_semantic_token(name: str, figma_path: str) -> bool:
    """Heuristic: token is semantic if name contains fg-/bg-/border-/text- after
    the type prefix, or if figmaPath has those segments."""
    lower_name = name.lower()
    for p in _SEMANTIC_PREFIXES:
        if p in lower_name:
            return True
    for p in _SEMANTIC_PATH_PARTS:
        if p in figma_path:
            return True
    return False


def _hex_to_rgba_ints(hex_str: str):
    """'#181d27' or '#181d27ff' -> (24, 29, 39, 1.0). None if not parseable."""
    if not isinstance(hex_str, str) or not hex_str.startswith("#"):
        return None
    h = hex_str[1:]
    try:
        if len(h) == 6:
            r = int(h[0:2], 16); g = int(h[2:4], 16); b = int(h[4:6], 16); a = 1.0
        elif len(h) == 8:
            r = int(h[0:2], 16); g = int(h[2:4], 16); b = int(h[4:6], 16)
            a = round(int(h[6:8], 16) / 255.0, 3)
        else:
            return None
        return (r, g, b, a)
    except ValueError:
        return None


def _resolve_typography_value(value: dict, token_map: dict) -> dict:
    """TYPOGRAPHY value uses {Font family.x} / {fontSize.N} reference syntax.
    Return a dict where references are replaced by their resolved primitive
    value if found in token_map; otherwise keep the original reference string
    so we can debug later."""
    resolved = {}
    for k, v in value.items():
        if isinstance(v, str) and v.startswith("{") and v.endswith("}"):
            ref = v[1:-1]  # 'Font family.font-family-display' or 'fontSize.10'
            # Convert reference path 'fontSize.10' -> figmaPath 'fontSize/10'
            ref_path = ref.replace(".", "/")
            found = None
            for tkn in token_map.values():
                if tkn.get("figmaPath") == ref_path:
                    found = tkn.get("value")
                    break
            resolved[k] = found if found is not None else v
        else:
            resolved[k] = v
    return resolved


def _load_token_index(token_map: dict) -> dict:
    """Build reverse indexes from TOKEN_MAP.json contents.

    Returns:
        {
          "color_index":  {(r,g,b,a): [(token_name, is_semantic)]},
          "number_index": {value: [(token_name, is_semantic)]},
          "typography_list": [{name, fontFamily, fontWeight, fontSize,
                               lineHeight, letterSpacing}],
          "shadow_list":     [{name, color, offsetX, offsetY, radius, spread}]
        }
    Each color_index / number_index list is sorted with semantic tokens first.
    """
    color_index: dict = {}
    number_index: dict = {}
    typography_list: list = []
    shadow_list: list = []

    for name, entry in token_map.items():
        ttype = entry.get("type")
        figma_path = entry.get("figmaPath", "")
        is_semantic = _is_semantic_token(name, figma_path)
        value = entry.get("value")

        if ttype == "COLOR":
            rgba = _hex_to_rgba_ints(value)
            if rgba is None:
                continue
            color_index.setdefault(rgba, []).append((name, is_semantic))
        elif ttype == "NUMBER":
            if isinstance(value, (int, float)):
                number_index.setdefault(value, []).append((name, is_semantic))
        elif ttype == "TYPOGRAPHY" and isinstance(value, dict):
            resolved = _resolve_typography_value(value, token_map)
            typography_list.append({"name": name, **resolved})
        elif ttype == "BOXSHADOW" and isinstance(value, dict):
            shadow_list.append({"name": name, **value})

    # Sort each bucket: semantic first, then alphabetical
    def _sort_bucket(bucket: list) -> list:
        return sorted(bucket, key=lambda t: (not t[1], t[0]))

    for k in list(color_index.keys()):
        color_index[k] = _sort_bucket(color_index[k])
    for k in list(number_index.keys()):
        number_index[k] = _sort_bucket(number_index[k])

    return {
        "color_index": color_index,
        "number_index": number_index,
        "typography_list": typography_list,
        "shadow_list": shadow_list,
    }
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd /Users/julee/imin/figma-design-agent
python3 -m unittest scripts.tests.test_token_binding_sweep -v
```

Expected: All 4 tests PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/julee/imin/figma-design-agent
git add scripts/figma_mcp_client.py scripts/tests/__init__.py scripts/tests/fixtures/sample_token_map.json scripts/tests/test_token_binding_sweep.py
git commit -m "$(cat <<'EOF'
feat(token-bind): add _load_token_index reverse indexer

TOKEN_MAP.json을 역인덱스 4종(color/number/typography/shadow)으로 변환. semantic alias 우선 정렬, TYPOGRAPHY reference 문법 resolve 포함.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Color Matcher (`_match_color`)

**Files:**
- Modify: `scripts/figma_mcp_client.py` (sweep 섹션 안에 함수 추가)
- Modify: `scripts/tests/test_token_binding_sweep.py`

- [ ] **Step 1: Write failing test**

Append to `scripts/tests/test_token_binding_sweep.py`:

```python
class TestMatchColor(unittest.TestCase):
    def setUp(self):
        self.idx = fmc._load_token_index(load_fixture())

    def test_exact_match_picks_semantic(self):
        # #181d27 maps to text-textPrimary AND grayLightMode-900; semantic wins
        result = fmc._match_color((24, 29, 39, 1.0), self.idx["color_index"])
        self.assertEqual(result, "--colors-text-textPrimary")

    def test_near_match_within_threshold(self):
        # Off by 5 in each channel = ΔRGB 15... outside 12 → None
        result = fmc._match_color((29, 34, 44, 1.0), self.idx["color_index"])
        self.assertIsNone(result)

    def test_near_match_inside_threshold(self):
        # Off by 3+3+3 = ΔRGB 9 → matches
        result = fmc._match_color((27, 32, 42, 1.0), self.idx["color_index"])
        self.assertEqual(result, "--colors-text-textPrimary")

    def test_returns_none_when_no_candidates(self):
        result = fmc._match_color((250, 250, 250, 1.0), self.idx["color_index"])
        self.assertIsNone(result)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m unittest scripts.tests.test_token_binding_sweep.TestMatchColor -v
```

Expected: FAIL with `AttributeError: ... '_match_color'`

- [ ] **Step 3: Implement `_match_color`**

Append in the sweep section (after `_load_token_index`):

```python
_COLOR_THRESHOLD = 12  # ΔRGB sum, RGB 0-255


def _match_color(rgba_tuple, color_index) -> str | None:
    """Return the best-matching token name for an (r,g,b,a) tuple, or None.

    Strategy:
        1. Exact (r,g,b,a) hit → first token in pre-sorted bucket (semantic first).
        2. Otherwise scan all entries with same alpha (±0.05), find lowest
           ΔRGB that is ≤ _COLOR_THRESHOLD. Tie-break by semantic-first sort.
    """
    if rgba_tuple in color_index:
        return color_index[rgba_tuple][0][0]

    r, g, b, a = rgba_tuple
    best_dist = _COLOR_THRESHOLD + 1
    best_token = None
    best_is_semantic = False
    for (cr, cg, cb, ca), bucket in color_index.items():
        if abs(ca - a) > 0.05:
            continue
        dist = abs(cr - r) + abs(cg - g) + abs(cb - b)
        if dist > _COLOR_THRESHOLD:
            continue
        cand_name, cand_semantic = bucket[0]
        # Prefer: smaller distance > semantic > alphabetical (already in bucket order)
        better = (
            dist < best_dist
            or (dist == best_dist and cand_semantic and not best_is_semantic)
        )
        if better:
            best_dist = dist
            best_token = cand_name
            best_is_semantic = cand_semantic
    return best_token
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m unittest scripts.tests.test_token_binding_sweep.TestMatchColor -v
```

Expected: All 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/figma_mcp_client.py scripts/tests/test_token_binding_sweep.py
git commit -m "$(cat <<'EOF'
feat(token-bind): add _match_color with ΔRGB ≤12 threshold

semantic alias 우선, exact hit 먼저 시도 후 scan으로 nearest 선택.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Number Matcher (`_match_number`)

**Files:**
- Modify: `scripts/figma_mcp_client.py`
- Modify: `scripts/tests/test_token_binding_sweep.py`

- [ ] **Step 1: Write failing test**

Append to test file:

```python
class TestMatchNumber(unittest.TestCase):
    def setUp(self):
        self.idx = fmc._load_token_index(load_fixture())

    def test_exact_match(self):
        self.assertEqual(fmc._match_number(8, self.idx["number_index"]), "--spacing-2-8px")

    def test_within_threshold(self):
        # 9 is within ±2 of 8 (closest: 8 over 12)
        self.assertEqual(fmc._match_number(9, self.idx["number_index"]), "--spacing-2-8px")

    def test_outside_threshold(self):
        # 5 is 3 away from 8, outside ±2
        self.assertIsNone(fmc._match_number(5, self.idx["number_index"]))

    def test_zero_returns_none(self):
        self.assertIsNone(fmc._match_number(0, self.idx["number_index"]))
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m unittest scripts.tests.test_token_binding_sweep.TestMatchNumber -v
```

Expected: FAIL `AttributeError: ... '_match_number'`

- [ ] **Step 3: Implement `_match_number`**

Append:

```python
_NUMBER_THRESHOLD = 2  # ±px


def _match_number(value, number_index) -> str | None:
    """Return best NUMBER token within ±_NUMBER_THRESHOLD of value, or None.
    value=0 is treated as 'no semantic meaning' and skipped."""
    if value == 0 or value is None:
        return None
    if value in number_index:
        return number_index[value][0][0]
    best_dist = _NUMBER_THRESHOLD + 1
    best_token = None
    best_is_semantic = False
    for cand_value, bucket in number_index.items():
        dist = abs(cand_value - value)
        if dist > _NUMBER_THRESHOLD:
            continue
        cand_name, cand_semantic = bucket[0]
        better = (
            dist < best_dist
            or (dist == best_dist and cand_semantic and not best_is_semantic)
        )
        if better:
            best_dist = dist
            best_token = cand_name
            best_is_semantic = cand_semantic
    return best_token
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m unittest scripts.tests.test_token_binding_sweep.TestMatchNumber -v
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/figma_mcp_client.py scripts/tests/test_token_binding_sweep.py
git commit -m "$(cat <<'EOF'
feat(token-bind): add _match_number with ±2px snap

zero value skip, nearest-within-threshold + semantic 우선.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Typography Matcher (`_match_textstyle`)

**Files:**
- Modify: `scripts/figma_mcp_client.py`
- Modify: `scripts/tests/test_token_binding_sweep.py`

- [ ] **Step 1: Write failing test**

Append to test file:

```python
class TestMatchTextstyle(unittest.TestCase):
    def setUp(self):
        # Build a richer fixture so fontSize.10 (=72) resolves
        self.token_map = load_fixture()
        # Add fontSize.10 = 72
        self.token_map["--fontSize-10"] = {
            "figmaPath": "fontSize/10", "value": 72, "type": "NUMBER"
        }
        # Add Font family / weight / lineHeight / letterSpacing primitives
        self.token_map["--fontFamily-fontFamilyDisplay"] = {
            "figmaPath": "Font family/font-family-display",
            "value": "Pretendard", "type": "TEXT"
        }
        self.token_map["--fontWeight-semibold"] = {
            "figmaPath": "Font weight/semibold", "value": "Semibold", "type": "TEXT"
        }
        self.token_map["--lineHeight-display2xl"] = {
            "figmaPath": "Line height/display-2xl", "value": 90, "type": "NUMBER"
        }
        self.token_map["--letterSpacing-0"] = {
            "figmaPath": "letterSpacing/0", "value": 0, "type": "NUMBER"
        }
        self.idx = fmc._load_token_index(self.token_map)

    def test_exact_typography_match(self):
        text_props = {
            "fontFamily": "Pretendard",
            "fontWeight": "Semibold",
            "fontSize": 72,
            "lineHeight": 90,
            "letterSpacing": 0,
        }
        self.assertEqual(
            fmc._match_textstyle(text_props, self.idx["typography_list"]),
            "--display2xl-semibold",
        )

    def test_near_size_within_threshold(self):
        text_props = {
            "fontFamily": "Pretendard", "fontWeight": "Semibold",
            "fontSize": 73,  # ±1 OK
            "lineHeight": 90, "letterSpacing": 0,
        }
        self.assertEqual(
            fmc._match_textstyle(text_props, self.idx["typography_list"]),
            "--display2xl-semibold",
        )

    def test_family_mismatch_rejects(self):
        text_props = {
            "fontFamily": "Roboto",  # different family
            "fontWeight": "Semibold", "fontSize": 72,
            "lineHeight": 90, "letterSpacing": 0,
        }
        self.assertIsNone(
            fmc._match_textstyle(text_props, self.idx["typography_list"])
        )

    def test_weight_mismatch_rejects(self):
        text_props = {
            "fontFamily": "Pretendard",
            "fontWeight": "Bold",  # different weight
            "fontSize": 72, "lineHeight": 90, "letterSpacing": 0,
        }
        self.assertIsNone(
            fmc._match_textstyle(text_props, self.idx["typography_list"])
        )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m unittest scripts.tests.test_token_binding_sweep.TestMatchTextstyle -v
```

Expected: FAIL `AttributeError: ... '_match_textstyle'`

- [ ] **Step 3: Implement `_match_textstyle`**

Append:

```python
_FONT_SIZE_THRESHOLD = 1     # ±px
_LINE_HEIGHT_PCT = 0.03      # ±3%
_LETTER_SPACING_PCT = 0.03   # ±3% relative to fontSize, fallback ±0.1


def _match_textstyle(text_props: dict, typography_list: list) -> str | None:
    """Find a TYPOGRAPHY token whose family/weight match exactly and whose
    size/lineHeight/letterSpacing are within tolerance. Returns the token name
    (caller maps name → text style id elsewhere)."""
    pf = text_props.get("fontFamily")
    pw = text_props.get("fontWeight")
    ps = text_props.get("fontSize")
    plh = text_props.get("lineHeight")
    pls = text_props.get("letterSpacing")
    if pf is None or pw is None or ps is None:
        return None

    best_dist = float("inf")
    best_name = None
    for ts in typography_list:
        if ts.get("fontFamily") != pf:
            continue
        if ts.get("fontWeight") != pw:
            continue
        ts_size = ts.get("fontSize")
        if not isinstance(ts_size, (int, float)):
            continue
        if abs(ts_size - ps) > _FONT_SIZE_THRESHOLD:
            continue
        ts_lh = ts.get("lineHeight")
        if isinstance(ts_lh, (int, float)) and isinstance(plh, (int, float)):
            tol = max(ts_lh * _LINE_HEIGHT_PCT, 1.0)
            if abs(ts_lh - plh) > tol:
                continue
        ts_ls = ts.get("letterSpacing")
        if isinstance(ts_ls, (int, float)) and isinstance(pls, (int, float)):
            tol = max(abs(ts_size) * _LETTER_SPACING_PCT, 0.1)
            if abs(ts_ls - pls) > tol:
                continue
        # distance: sum of normalized deltas
        dist = abs(ts_size - ps)
        if dist < best_dist:
            best_dist = dist
            best_name = ts["name"]
    return best_name
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m unittest scripts.tests.test_token_binding_sweep.TestMatchTextstyle -v
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/figma_mcp_client.py scripts/tests/test_token_binding_sweep.py
git commit -m "$(cat <<'EOF'
feat(token-bind): add _match_textstyle (family+weight exact, size ±1, lh/ls ±3%)

TYPOGRAPHY 토큰 매칭. fontFamily/fontWeight 정확 일치 필수, fontSize ±1px, lineHeight/letterSpacing ±3%.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Shadow Matcher (`_match_shadow`)

**Files:**
- Modify: `scripts/figma_mcp_client.py`
- Modify: `scripts/tests/test_token_binding_sweep.py`

- [ ] **Step 1: Write failing test**

Append to test file:

```python
class TestMatchShadow(unittest.TestCase):
    def setUp(self):
        token_map = load_fixture()
        token_map["--shadow-md"] = {
            "figmaPath": "Shadows/md",
            "value": {
                "color": "#0a0d12",
                "alpha": 0.08,
                "offsetX": 0, "offsetY": 4,
                "radius": 6, "spread": -2
            },
            "type": "BOXSHADOW"
        }
        self.idx = fmc._load_token_index(token_map)

    def test_exact_shadow_match(self):
        effect = {
            "type": "DROP_SHADOW",
            "color": {"r": 0.039, "g": 0.051, "b": 0.071, "a": 0.08},
            "offset": {"x": 0, "y": 4},
            "radius": 6, "spread": -2,
        }
        self.assertEqual(
            fmc._match_shadow(effect, self.idx["shadow_list"]),
            "--shadow-md",
        )

    def test_near_shadow_within_tolerance(self):
        effect = {
            "type": "DROP_SHADOW",
            "color": {"r": 0.039, "g": 0.051, "b": 0.071, "a": 0.08},
            "offset": {"x": 0, "y": 5},  # off by 1
            "radius": 7,                   # off by 1
            "spread": -2,
        }
        self.assertEqual(
            fmc._match_shadow(effect, self.idx["shadow_list"]),
            "--shadow-md",
        )

    def test_color_mismatch_rejects(self):
        effect = {
            "type": "DROP_SHADOW",
            "color": {"r": 1.0, "g": 0, "b": 0, "a": 0.08},  # red shadow
            "offset": {"x": 0, "y": 4},
            "radius": 6, "spread": -2,
        }
        self.assertIsNone(
            fmc._match_shadow(effect, self.idx["shadow_list"])
        )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m unittest scripts.tests.test_token_binding_sweep.TestMatchShadow -v
```

Expected: FAIL `AttributeError: ... '_match_shadow'`

- [ ] **Step 3: Implement `_match_shadow`**

Append:

```python
_SHADOW_OFFSET_TOL = 1   # ±px
_SHADOW_RADIUS_TOL = 2   # ±px
_SHADOW_SPREAD_TOL = 1   # ±px
_SHADOW_ALPHA_TOL = 0.1


def _match_shadow(effect: dict, shadow_list: list) -> str | None:
    """Match a Figma effect (DROP_SHADOW) to a BOXSHADOW token."""
    if effect.get("type") not in ("DROP_SHADOW", "INNER_SHADOW"):
        return None
    e_color = effect.get("color") or {}
    er = int(round(e_color.get("r", 0) * 255))
    eg = int(round(e_color.get("g", 0) * 255))
    eb = int(round(e_color.get("b", 0) * 255))
    ea = e_color.get("a", 1)
    e_off = effect.get("offset") or {}
    eox = e_off.get("x", 0)
    eoy = e_off.get("y", 0)
    erad = effect.get("radius", 0)
    espread = effect.get("spread", 0)

    best_dist = float("inf")
    best_name = None
    for sh in shadow_list:
        sh_color = sh.get("color")
        s_rgba = _hex_to_rgba_ints(sh_color) if isinstance(sh_color, str) else None
        if s_rgba is None:
            continue
        sr, sg, sb, _ = s_rgba
        sa = sh.get("alpha", 1)
        if abs(sr - er) + abs(sg - eg) + abs(sb - eb) > _COLOR_THRESHOLD:
            continue
        if abs(sa - ea) > _SHADOW_ALPHA_TOL:
            continue
        if abs(sh.get("offsetX", 0) - eox) > _SHADOW_OFFSET_TOL:
            continue
        if abs(sh.get("offsetY", 0) - eoy) > _SHADOW_OFFSET_TOL:
            continue
        if abs(sh.get("radius", 0) - erad) > _SHADOW_RADIUS_TOL:
            continue
        if abs(sh.get("spread", 0) - espread) > _SHADOW_SPREAD_TOL:
            continue
        dist = (
            abs(sh.get("offsetX", 0) - eox)
            + abs(sh.get("offsetY", 0) - eoy)
            + abs(sh.get("radius", 0) - erad)
            + abs(sh.get("spread", 0) - espread)
        )
        if dist < best_dist:
            best_dist = dist
            best_name = sh["name"]
    return best_name
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m unittest scripts.tests.test_token_binding_sweep.TestMatchShadow -v
```

Expected: 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/figma_mcp_client.py scripts/tests/test_token_binding_sweep.py
git commit -m "$(cat <<'EOF'
feat(token-bind): add _match_shadow (color ΔRGB ≤12, offset/radius/spread ±2)

DROP_SHADOW/INNER_SHADOW 효과를 BOXSHADOW 토큰에 매칭.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Tree Walker (`_walk_node_tree`)

**Files:**
- Modify: `scripts/figma_mcp_client.py`
- Modify: `scripts/tests/test_token_binding_sweep.py`

- [ ] **Step 1: Write failing test (uses local fake instead of MCP)**

Append:

```python
class TestWalkNodeTree(unittest.TestCase):
    def test_flatten_recursive_tree(self):
        tree = {
            "id": "1:1", "type": "FRAME",
            "children": [
                {"id": "1:2", "type": "TEXT"},
                {"id": "1:3", "type": "FRAME",
                 "children": [{"id": "1:4", "type": "TEXT"}]},
            ],
        }
        flat = fmc._flatten_node_tree(tree)
        ids = [n["id"] for n in flat]
        self.assertEqual(ids, ["1:1", "1:2", "1:3", "1:4"])

    def test_no_children_handles_gracefully(self):
        tree = {"id": "1:1", "type": "RECTANGLE"}
        flat = fmc._flatten_node_tree(tree)
        self.assertEqual([n["id"] for n in flat], ["1:1"])
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m unittest scripts.tests.test_token_binding_sweep.TestWalkNodeTree -v
```

Expected: FAIL `AttributeError: ... '_flatten_node_tree'`

- [ ] **Step 3: Implement `_flatten_node_tree`**

Append:

```python
def _flatten_node_tree(node: dict) -> list:
    """DFS flatten a recursive node-info dict into a list of node dicts.
    Each returned node retains its original keys (without 'children').
    Resilient to missing 'children' or non-list 'children'."""
    out: list = []
    stack = [node]
    while stack:
        cur = stack.pop(0)  # BFS-ish but order matches DFS-pre when reversed
        if not isinstance(cur, dict):
            continue
        copy = {k: v for k, v in cur.items() if k != "children"}
        out.append(copy)
        children = cur.get("children")
        if isinstance(children, list):
            # prepend children so siblings come right after parent
            stack = list(children) + stack
    return out
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m unittest scripts.tests.test_token_binding_sweep.TestWalkNodeTree -v
```

Expected: 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/figma_mcp_client.py scripts/tests/test_token_binding_sweep.py
git commit -m "$(cat <<'EOF'
feat(token-bind): add _flatten_node_tree DFS helper

재귀 트리를 평면 list로 풀어 collector가 단일 패스로 처리하도록.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Binding Collector (`_collect_bindings`)

**Files:**
- Modify: `scripts/figma_mcp_client.py`
- Modify: `scripts/tests/test_token_binding_sweep.py`

- [ ] **Step 1: Write failing test**

Append:

```python
class TestCollectBindings(unittest.TestCase):
    def setUp(self):
        self.idx = fmc._load_token_index(load_fixture())

    def test_collect_color_fill(self):
        nodes = [{
            "id": "1:1", "type": "FRAME",
            "fills": [{"type": "SOLID", "color": {"r": 24/255, "g": 29/255, "b": 39/255, "a": 1}}],
        }]
        q = fmc._collect_bindings(nodes, self.idx)
        self.assertEqual(len(q["color_bindings"]), 1)
        b = q["color_bindings"][0]
        self.assertEqual(b["nodeId"], "1:1")
        self.assertEqual(b["field"], "fills")
        self.assertEqual(b["index"], 0)
        self.assertEqual(b["token_name"], "--colors-text-textPrimary")

    def test_collect_padding_and_radius(self):
        nodes = [{
            "id": "1:1", "type": "FRAME",
            "paddingTop": 8, "paddingLeft": 12, "paddingBottom": 0,  # 0 skipped
            "itemSpacing": 8,
            "cornerRadius": 12,
        }]
        q = fmc._collect_bindings(nodes, self.idx)
        fields = sorted(b["field"] for b in q["number_bindings"])
        self.assertEqual(fields, ["cornerRadius", "itemSpacing", "paddingLeft", "paddingTop"])

    def test_skip_image_fill(self):
        nodes = [{
            "id": "1:1", "type": "FRAME",
            "fills": [{"type": "IMAGE", "imageHash": "abc"}],
        }]
        q = fmc._collect_bindings(nodes, self.idx)
        self.assertEqual(q["color_bindings"], [])

    def test_unmapped_color_recorded(self):
        nodes = [{
            "id": "1:1", "type": "FRAME",
            "fills": [{"type": "SOLID", "color": {"r": 0.1, "g": 0.5, "b": 0.9, "a": 1}}],
        }]
        q = fmc._collect_bindings(nodes, self.idx)
        self.assertEqual(q["color_bindings"], [])
        self.assertEqual(len(q["unmapped"]["colors"]), 1)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m unittest scripts.tests.test_token_binding_sweep.TestCollectBindings -v
```

Expected: FAIL `AttributeError: ... '_collect_bindings'`

- [ ] **Step 3: Implement `_collect_bindings`**

Append:

```python
_NUMBER_FIELDS = (
    "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
    "itemSpacing",
    "cornerRadius",
    "topLeftRadius", "topRightRadius", "bottomLeftRadius", "bottomRightRadius",
    "strokeWeight",
    "strokeTopWeight", "strokeRightWeight",
    "strokeBottomWeight", "strokeLeftWeight",
)


def _figma_color_to_rgba_ints(c: dict):
    """{r:0..1, g:0..1, b:0..1, a:0..1} -> (r,g,b,a) with ints + alpha float."""
    if not isinstance(c, dict):
        return None
    try:
        r = int(round(c.get("r", 0) * 255))
        g = int(round(c.get("g", 0) * 255))
        b = int(round(c.get("b", 0) * 255))
        a = round(c.get("a", 1.0), 3)
        return (r, g, b, a)
    except (TypeError, ValueError):
        return None


def _collect_bindings(nodes: list, indexes: dict) -> dict:
    """Walk flattened nodes and produce binding queues + unmapped report.

    Returns:
        {
          "color_bindings":     [{nodeId, field: "fills"|"strokes", index, token_name}],
          "number_bindings":    [{nodeId, field, token_name}],
          "textstyle_bindings": [{nodeId, token_name}],
          "effect_bindings":    [{nodeId, index, token_name}],
          "unmapped": {colors:[], numbers:[], typography:[], shadows:[]}
        }
    """
    out = {
        "color_bindings": [],
        "number_bindings": [],
        "textstyle_bindings": [],
        "effect_bindings": [],
        "unmapped": {"colors": [], "numbers": [], "typography": [], "shadows": []},
    }
    color_idx = indexes["color_index"]
    number_idx = indexes["number_index"]
    typo_list = indexes["typography_list"]
    shadow_list = indexes["shadow_list"]

    for n in nodes:
        nid = n.get("id")
        if not nid:
            continue

        # fills
        for i, fill in enumerate(n.get("fills") or []):
            if not isinstance(fill, dict):
                continue
            if fill.get("type") != "SOLID":
                continue
            rgba = _figma_color_to_rgba_ints(fill.get("color"))
            if rgba is None:
                continue
            tok = _match_color(rgba, color_idx)
            if tok:
                out["color_bindings"].append(
                    {"nodeId": nid, "field": "fills", "index": i, "token_name": tok}
                )
            else:
                out["unmapped"]["colors"].append(
                    {"nodeId": nid, "field": "fills", "index": i, "rgba": rgba}
                )

        # strokes
        for i, stroke in enumerate(n.get("strokes") or []):
            if not isinstance(stroke, dict):
                continue
            if stroke.get("type") != "SOLID":
                continue
            rgba = _figma_color_to_rgba_ints(stroke.get("color"))
            if rgba is None:
                continue
            tok = _match_color(rgba, color_idx)
            if tok:
                out["color_bindings"].append(
                    {"nodeId": nid, "field": "strokes", "index": i, "token_name": tok}
                )
            else:
                out["unmapped"]["colors"].append(
                    {"nodeId": nid, "field": "strokes", "index": i, "rgba": rgba}
                )

        # numbers
        for f in _NUMBER_FIELDS:
            if f not in n:
                continue
            v = n[f]
            if not isinstance(v, (int, float)) or v == 0:
                continue
            tok = _match_number(v, number_idx)
            if tok:
                out["number_bindings"].append(
                    {"nodeId": nid, "field": f, "token_name": tok}
                )
            else:
                out["unmapped"]["numbers"].append(
                    {"nodeId": nid, "field": f, "value": v}
                )

        # typography (TEXT nodes only)
        if n.get("type") == "TEXT":
            # mixed style detection: 'fontSize' missing or marked mixed
            if n.get("hasMixedStyle") or n.get("fontSize") is None:
                out["unmapped"]["typography"].append(
                    {"nodeId": nid, "reason": "mixed_or_missing"}
                )
            else:
                text_props = {
                    "fontFamily": n.get("fontFamily") or (n.get("fontName") or {}).get("family"),
                    "fontWeight": (
                        n.get("fontWeight")
                        or (n.get("fontName") or {}).get("style")
                    ),
                    "fontSize": n.get("fontSize"),
                    "lineHeight": (n.get("lineHeight") or {}).get("value")
                                  if isinstance(n.get("lineHeight"), dict)
                                  else n.get("lineHeight"),
                    "letterSpacing": (n.get("letterSpacing") or {}).get("value")
                                     if isinstance(n.get("letterSpacing"), dict)
                                     else n.get("letterSpacing"),
                }
                tok = _match_textstyle(text_props, typo_list)
                if tok:
                    out["textstyle_bindings"].append(
                        {"nodeId": nid, "token_name": tok}
                    )
                else:
                    out["unmapped"]["typography"].append(
                        {"nodeId": nid, "props": text_props}
                    )

        # effects
        for i, eff in enumerate(n.get("effects") or []):
            if not isinstance(eff, dict):
                continue
            if eff.get("type") not in ("DROP_SHADOW", "INNER_SHADOW"):
                continue
            tok = _match_shadow(eff, shadow_list)
            if tok:
                out["effect_bindings"].append(
                    {"nodeId": nid, "index": i, "token_name": tok}
                )
            else:
                out["unmapped"]["shadows"].append(
                    {"nodeId": nid, "index": i, "effect": eff}
                )

    return out
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m unittest scripts.tests.test_token_binding_sweep.TestCollectBindings -v
```

Expected: 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/figma_mcp_client.py scripts/tests/test_token_binding_sweep.py
git commit -m "$(cat <<'EOF'
feat(token-bind): add _collect_bindings node-tree extractor

fills/strokes/padding/radius/strokeWeight/typography/effects를 한 패스로 큐잉. IMAGE/GRADIENT skip, mixed style 보고.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Binding Applier (`_apply_bindings`)

**Files:**
- Modify: `scripts/figma_mcp_client.py`
- Modify: `scripts/tests/test_token_binding_sweep.py`

이 task는 실제 MCP 호출이 필요하므로 단위 테스트는 `call_tool`을 monkey-patch하여 호출 페이로드만 검증한다.

- [ ] **Step 1: Write failing test**

Append:

```python
class TestApplyBindings(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def fake_call_tool(name, args, msg_id=1):
            self.calls.append((name, args))
            return [{"text": "{\"success\": true}"}]
        self._orig = fmc.call_tool
        fmc.call_tool = fake_call_tool

    def tearDown(self):
        fmc.call_tool = self._orig

    def test_color_bindings_chunked_to_100(self):
        queues = {
            "color_bindings": [
                {"nodeId": f"1:{i}", "field": "fills", "index": 0,
                 "token_name": "--colors-text-textPrimary"}
                for i in range(150)
            ],
            "number_bindings": [], "textstyle_bindings": [],
            "effect_bindings": [],
            "unmapped": {"colors": [], "numbers": [], "typography": [], "shadows": []},
        }
        fmc._apply_bindings(queues)
        # 150 colors → 2 batch_bind_variables calls (100 + 50)
        bind_calls = [c for c in self.calls if c[0] == "batch_bind_variables"]
        self.assertEqual(len(bind_calls), 2)
        self.assertEqual(len(bind_calls[0][1]["bindings"]), 100)
        self.assertEqual(len(bind_calls[1][1]["bindings"]), 50)

    def test_textstyle_calls_batch(self):
        queues = {
            "color_bindings": [], "number_bindings": [],
            "textstyle_bindings": [
                {"nodeId": "1:1", "token_name": "--display2xl-semibold"}
            ],
            "effect_bindings": [],
            "unmapped": {"colors": [], "numbers": [], "typography": [], "shadows": []},
        }
        fmc._apply_bindings(queues)
        ts_calls = [c for c in self.calls if c[0] == "batch_set_text_style_id"]
        self.assertEqual(len(ts_calls), 1)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m unittest scripts.tests.test_token_binding_sweep.TestApplyBindings -v
```

Expected: FAIL `AttributeError: ... '_apply_bindings'`

- [ ] **Step 3: Implement `_apply_bindings`**

Append:

```python
_BIND_CHUNK = 100


def _apply_bindings(queues: dict) -> dict:
    """Issue MCP calls for collected bindings. Returns counts.

    `batch_bind_variables` payload shape (per existing tool):
        bindings: [{nodeId, property, variableName}, ...]
    Note: 'property' is the Figma node prop ('fills', 'paddingTop', etc.).
    Color bindings need to encode the fills index → property uses 'fills.0'.
    """
    counts = {"colors": 0, "numbers": 0, "textstyles": 0, "effects": 0}

    color_payloads = [
        {"nodeId": b["nodeId"],
         "property": f"{b['field']}.{b['index']}",
         "variableName": b["token_name"]}
        for b in queues["color_bindings"]
    ]
    number_payloads = [
        {"nodeId": b["nodeId"], "property": b["field"],
         "variableName": b["token_name"]}
        for b in queues["number_bindings"]
    ]
    bindings = color_payloads + number_payloads
    for i in range(0, len(bindings), _BIND_CHUNK):
        chunk = bindings[i:i + _BIND_CHUNK]
        if not chunk:
            continue
        call_tool("batch_bind_variables", {"bindings": chunk}, msg_id=10000 + i)
    counts["colors"] = len(color_payloads)
    counts["numbers"] = len(number_payloads)

    if queues["textstyle_bindings"]:
        ts_payload = [
            {"nodeId": b["nodeId"], "textStyleName": b["token_name"]}
            for b in queues["textstyle_bindings"]
        ]
        call_tool("batch_set_text_style_id", {"items": ts_payload}, msg_id=20000)
        counts["textstyles"] = len(ts_payload)

    for b in queues["effect_bindings"]:
        call_tool(
            "set_effect_style_id",
            {"nodeId": b["nodeId"], "effectStyleName": b["token_name"]},
            msg_id=30000,
        )
        counts["effects"] += 1

    return counts
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m unittest scripts.tests.test_token_binding_sweep.TestApplyBindings -v
```

Expected: 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/figma_mcp_client.py scripts/tests/test_token_binding_sweep.py
git commit -m "$(cat <<'EOF'
feat(token-bind): add _apply_bindings batch dispatcher

color+number을 batch_bind_variables 100개 청크로, typography는 batch_set_text_style_id, shadow는 set_effect_style_id 개별 호출.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Unmapped Reporter (`_report_unmapped`)

**Files:**
- Modify: `scripts/figma_mcp_client.py`
- Modify: `scripts/tests/test_token_binding_sweep.py`

- [ ] **Step 1: Write failing test**

Append:

```python
import tempfile

class TestReportUnmapped(unittest.TestCase):
    def test_writes_json_and_returns_summary(self):
        unmapped = {
            "colors": [{"nodeId": "1:1", "field": "fills", "index": 0, "rgba": (10,20,30,1.0)}],
            "numbers": [{"nodeId": "1:2", "field": "paddingTop", "value": 7}],
            "typography": [],
            "shadows": [],
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.json")
            summary = fmc._report_unmapped(unmapped, output_path=path)
            self.assertEqual(summary, "1 color, 1 number")
            self.assertTrue(os.path.exists(path))
            with open(path) as f:
                data = json.load(f)
            self.assertEqual(len(data["colors"]), 1)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m unittest scripts.tests.test_token_binding_sweep.TestReportUnmapped -v
```

Expected: FAIL `AttributeError: ... '_report_unmapped'`

- [ ] **Step 3: Implement `_report_unmapped`**

Append:

```python
def _report_unmapped(unmapped: dict, output_path: str) -> str:
    """Write detailed unmapped report to JSON, return one-line summary.

    Report format (JSON pretty-printed for human inspection):
        {colors: [...], numbers: [...], typography: [...], shadows: [...]}
    Tuples are converted to lists so json.dump works.
    """
    def _normalize(v):
        if isinstance(v, tuple):
            return list(v)
        if isinstance(v, dict):
            return {k: _normalize(x) for k, x in v.items()}
        if isinstance(v, list):
            return [_normalize(x) for x in v]
        return v

    serializable = _normalize(unmapped)
    try:
        with open(output_path, "w") as f:
            json.dump(serializable, f, indent=2, ensure_ascii=False)
    except OSError as exc:
        print(f"WARNING: could not write unmapped report → {output_path}: {exc}")

    parts = []
    counts = {
        "color":      len(unmapped.get("colors") or []),
        "number":     len(unmapped.get("numbers") or []),
        "typography": len(unmapped.get("typography") or []),
        "shadow":     len(unmapped.get("shadows") or []),
    }
    for label, n in counts.items():
        if n:
            parts.append(f"{n} {label}" + ("s" if n != 1 else ""))
    return ", ".join(parts) if parts else "0"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m unittest scripts.tests.test_token_binding_sweep.TestReportUnmapped -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/figma_mcp_client.py scripts/tests/test_token_binding_sweep.py
git commit -m "$(cat <<'EOF'
feat(token-bind): add _report_unmapped (json file + one-line summary)

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Main Entrypoint + Post-fix Integration + CLI Flag

**Files:**
- Modify: `scripts/figma_mcp_client.py` — sweep section + `cmd_post_fix` + argparse

이 task는 모든 부분을 합치고 build/post-fix에 wire하는 단계다.

- [ ] **Step 1: Add `_bind_semantic_tokens` entrypoint**

Append at end of sweep section (after `_report_unmapped`):

```python
def _bind_semantic_tokens(root_node_id: str) -> dict:
    """Post-fix step 6: walk the rendered tree and bind raw values to
    semantic tokens. Returns counts dict for logging."""
    print(f"[token-bind] starting sweep on root={root_node_id}")
    try:
        token_map = load_token_map()
        if not token_map:
            print("[token-bind] TOKEN_MAP empty → skip")
            return {"skipped": True}
        indexes = _load_token_index(token_map)
    except Exception as exc:
        print(f"[token-bind] failed to load token index: {exc} → skip")
        return {"skipped": True}

    # Pull the recursive tree via MCP
    try:
        results = call_tool("get_node_info", {"nodeId": root_node_id})
        tree = parse_content(results) or {}
    except Exception as exc:
        print(f"[token-bind] get_node_info failed: {exc} → skip")
        return {"skipped": True}

    nodes = _flatten_node_tree(tree)
    queues = _collect_bindings(nodes, indexes)
    counts = _apply_bindings(queues)
    report_path = f"/tmp/unmapped-tokens-{root_node_id.replace(':', '_')}.json"
    summary = _report_unmapped(queues["unmapped"], output_path=report_path)
    print(
        f"[token-bind] mapped colors={counts['colors']} "
        f"numbers={counts['numbers']} text={counts['textstyles']} "
        f"effects={counts['effects']} | unmapped: {summary} "
        f"(detail: {report_path})"
    )
    return counts
```

- [ ] **Step 2: Wire into `cmd_post_fix`**

Find `cmd_post_fix` definition. Look at the end of its body (after step 5 `_match_status_bar_bg_to_nav` call). Add the sweep call there, gated by a module-level flag.

First, locate the function and read context:

```bash
grep -n "def cmd_post_fix\|_match_status_bar_bg_to_nav" /Users/julee/imin/figma-design-agent/scripts/figma_mcp_client.py
```

Open the file, find the last fix call inside `cmd_post_fix`, and add right after:

```python
    # Step 6: bind raw values to semantic tokens
    if not _SKIP_TOKEN_BIND:
        try:
            _bind_semantic_tokens(root_node_id)
        except Exception as exc:
            print(f"[token-bind] sweep crashed: {exc} → continuing")
```

Also add the module-level flag near the top of the file (right after the existing config constants like `TOKEN_MAP_FILE`):

```python
_SKIP_TOKEN_BIND = False
```

- [ ] **Step 3: Add CLI flag**

Find argparse setup for `build` / `post-fix` commands. Add a flag handler. Look for the `if __name__ == "__main__":` block.

Add to argument parser:

```python
parser.add_argument(
    "--skip-token-bind",
    action="store_true",
    help="Disable post-fix step 6 (semantic token binding sweep)",
)
```

Then near the dispatch logic (after argparse):

```python
if args.skip_token_bind:
    _SKIP_TOKEN_BIND = True
```

If the existing argparse uses subparsers, add the same flag to each subparser that triggers post-fix (`build`, `post-fix`). If unsure, **read** the existing argparse block first and adapt minimally — match the style of existing flags.

- [ ] **Step 4: Smoke-test with synthetic tree**

Create `scripts/tests/test_sweep_integration.py`:

```python
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import figma_mcp_client as fmc


class TestBindSemanticTokensSmoke(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def fake_call_tool(name, args, msg_id=1):
            self.calls.append((name, args))
            if name == "get_node_info":
                # Return a minimal rendered tree
                return [{"text": '{"id": "1:1", "type": "FRAME", '
                                  '"paddingTop": 8, '
                                  '"fills": [{"type":"SOLID","color":{"r":0.094,"g":0.114,"b":0.153,"a":1}}], '
                                  '"children": []}'}]
            return [{"text": '{"success": true}'}]
        self._orig = fmc.call_tool
        fmc.call_tool = fake_call_tool

    def tearDown(self):
        fmc.call_tool = self._orig

    def test_end_to_end_pass(self):
        counts = fmc._bind_semantic_tokens("1:1")
        # Should issue at least one batch_bind_variables call
        bind_calls = [c for c in self.calls if c[0] == "batch_bind_variables"]
        self.assertTrue(len(bind_calls) >= 1, f"calls: {self.calls}")
        self.assertNotIn("skipped", counts)
```

- [ ] **Step 5: Run integration smoke test**

```bash
cd /Users/julee/imin/figma-design-agent
python3 -m unittest scripts.tests.test_sweep_integration -v
```

Expected: PASS

- [ ] **Step 6: Verify all tests still pass**

```bash
python3 -m unittest discover -s scripts/tests -v
```

Expected: all tests PASS, no failures

- [ ] **Step 7: Commit**

```bash
git add scripts/figma_mcp_client.py scripts/tests/test_sweep_integration.py
git commit -m "$(cat <<'EOF'
feat(token-bind): integrate sweep as post-fix step 6 + --skip-token-bind flag

빌드 직후 _bind_semantic_tokens 자동 실행. 토큰 인덱스 로드 → get_node_info → collect → apply → report. 실패 시 빌드는 계속 진행. CLI flag로 비활성화 가능.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: End-to-End Validation on a Real Build

**Files:** 변경 없음 — 실제 빌드 화면 위에서 수동 검증

- [ ] **Step 1: Build a small known screen**

Choose any existing blueprint (e.g. `scripts/imin_home_prd_v2.json` 또는 `scripts/blueprint_stage_tab.json`). Run:

```bash
cd /Users/julee/imin/figma-design-agent
python3 scripts/figma_mcp_client.py build scripts/imin_home_prd_v2.json
```

(혹은 가까운 다른 화면)

Expected console output (마지막 부분에 추가됨):
```
[token-bind] starting sweep on root=...
[token-bind] mapped colors=N numbers=M text=K effects=E | unmapped: ... (detail: /tmp/unmapped-tokens-X.json)
```

- [ ] **Step 2: Verify a node has bound variables**

빌드된 root nodeId를 사용해 직접 확인:

```bash
python3 scripts/figma_mcp_client.py call get_bound_variables '{"nodeId": "<some inner FRAME id>"}'
```

Expected: `fills` / `paddingTop` 등 필드가 token name에 바인딩되어 반환됨.

- [ ] **Step 3: Inspect unmapped report**

```bash
cat /tmp/unmapped-tokens-*.json | head -60
```

미매칭이 30% 이상이면 임계치 조정 필요 (별도 PR / 후속 spec).

- [ ] **Step 4: Time the sweep**

빌드 로그에서 token-bind 출력 직전과 직후의 timestamp 또는 시계 측정. 단일 화면이 1분 30초를 크게 넘으면 후속 최적화 필요 (별도 issue).

- [ ] **Step 5: Verify `--skip-token-bind` flag works**

```bash
python3 scripts/figma_mcp_client.py build scripts/imin_home_prd_v2.json --skip-token-bind
```

Expected: token-bind 출력이 없어야 함.

- [ ] **Step 6: No commit needed for validation, but record findings**

빌드 로그/스크린샷이 의미 있다면 PR description에 첨부. 코드 변경 없으면 commit 생략.

---

## Self-Review Checklist (계획 작성자용 — 실행 전 마지막 확인)

| 점검 | 결과 |
|---|---|
| Spec의 매칭 정책(컬러 ΔRGB≤12 등)이 Task 2-5 구현에 정확히 반영됨? | ✓ Task 2 (`_COLOR_THRESHOLD=12`), Task 3 (`_NUMBER_THRESHOLD=2`), Task 4 (size ±1, lh/ls ±3%), Task 5 (offset ±1, radius ±2) |
| semantic 우선 정책이 매처 4개 모두에 적용됨? | ✓ Task 1 `_sort_bucket` semantic 먼저, Task 2/3 동률 시 semantic 선택 |
| TextStyle reference 해석이 일관됨? | ✓ Task 1 `_resolve_typography_value` |
| build 자동 통합 + `--skip-token-bind`? | ✓ Task 10 |
| 미매칭 보고 (콘솔 + JSON 파일)? | ✓ Task 9 + Task 10 wire-up |
| 제외 항목 (width/height, IMAGE/GRADIENT, mixed style)? | ✓ Task 7 collector |
| 에러 시 빌드 계속? | ✓ Task 10 `try/except` 감싸기 |
| 테스트가 각 task에 포함됨? | ✓ Task 1-9 모두 unittest 동봉 |
| 노드 트리 호출 비용? | Task 6 `_flatten_node_tree`로 단일 `get_node_info` 결과 활용 |
| Type/이름 일관성? | `_match_color/number/textstyle/shadow` / `_collect_bindings` / `_apply_bindings` / `_bind_semantic_tokens` 일관 사용 |

---

## Risk / Open Items (작업 완료 후 갱신, 2026-05-01 e2e 검증 결과 반영)

### 해결됨
1. ~~`get_node_info`가 recursive 트리를 반환하는가~~ — 빌드 1회 시 root 1개 + 직계 자식 ~10개 + 손자/증손까지 반환됨을 확인. BFS fallback 불필요.
2. ~~`batch_bind_variables`의 `property` 표기법~~ — Task 8 review에서 plugin contract와 불일치 발견 → `items` + `bindings: {fields/0: figmaPath}` slash 표기로 수정 후 e2e에서 fills/strokes 13/18, numbers 81/82 매칭 확인.
3. ~~`fontWeight` 값 형식~~ — Figma는 `"SemiBold"` (대문자 B)를 반환. e2e에서 발견 후 `_match_textstyle`을 case-insensitive로 fix 적용 (commit `e28b9ce`). typography 매칭률 23% → 46%.

### 알려진 갭 — 향후 작업
4. **TextStyle 실제 적용 미확인** — sweep 콘솔이 `text=6` 카운트하지만 e2e 검증 결과 실제 Figma 노드의 `textStyleId`가 갱신되지 않은 것으로 관찰됨. 가능한 원인:
   - `batchSetTextStyleId` plugin patch가 캐시 등으로 반영 안 됨 (Close/Run 재로드 누락 가능성)
   - `figma.getLocalTextStylesAsync().name` 매칭 시 trailing space 등 미세 차이
   - plugin response의 `errors` 배열에 silent failure가 있는데 우리 클라이언트가 무시
   - **다음 단계**: `_apply_bindings`에 plugin response 로깅 추가, 또는 `setStyleId` per-node 호출 + per-call 응답 점검.
5. **Multi-layer BOXSHADOW 미지원** — `ds/TOKEN_MAP.json` 21개 BOXSHADOW 토큰 중 15개가 list-shaped (multi-layer). 현재 6개만 인덱스에 포함. Task 5 e2e에서 effects 0/1로 확인됨.
6. **DS에 brand purple `#7f56d9` / gold `#ffd700` 미등록** — 디자인 시안에 사용되는 color지만 토큰화되지 않음. 코드 결함 아니라 DS 추가 필요.
7. **`cmd_build`의 redundant double sweep** — `cmd_post_fix`가 layout 안정화 위해 2회 호출되어 sweep도 2회 실행 (~1.4초씩). 첫 호출에서 step 9 skip 옵션을 추가하면 ~0.7초 절약 가능.
8. **NUMBER 인덱스 카테고리 혼합** — `_match_number`가 spacing/fontSize/lineHeight 토큰을 카테고리 구분 없이 검색. 우연한 짝퉁 매칭 위험 (예: paddingTop=10이 Font size/text-xxs에 매칭). 화면별 패턴은 적지만 category-aware 매칭 권장.
9. **테스트 fixture 키 형식과 production 차이** — fixture는 `--colors-text-textPrimary` (CSS-var 형식), `load_token_map()`은 figmaPath-keyed (`Colors/Text/text-primary`). 둘 다 통과하지만 통합 경로 테스트 1건 추가 권장.
10. **`--skip-token-bind` 플래그 docstring 미문서화** — 기능 작동하지만 모듈 docstring에 사용법 없음.
11. **`_apply_bindings` plan 시그니처 불일치** — plan은 `(queues)`로 명시하나 실제는 `(queues, indexes)`. plan 문서 갱신 권장.
