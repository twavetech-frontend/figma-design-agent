2026-05-05 archived. These blueprint JSONs encode pre-v17 patterns the user explicitly rejected. Do NOT clone these as a build base.

Notable anti-patterns:
- `blueprint_assembled_imin_home_v12.json` — Brand Recommend Card uses brand-purple bg with "3 회차" Round element overflowing the card. v17 replaced this with a bg-secondary card + inline pill counter + 스테이지 참여하기 CTA.
- `blueprint_assembled_imin_Stage_Tab*.json` — pre-canonical stage tab patterns superseded by user-modified design (file `SsgiLsXVMkf0wv8OhRGwks` node `16941:51284`).

Canonical patterns now live in `scripts/blueprint_templates.json`.
