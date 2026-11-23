# Minimal example — termbase-gated translation pipeline

> **⚠️ 合成示例声明 / Synthetic data notice**
> All files under `examples/data/` are a **合成示例，非正式案例结果** (synthetic example,
> NOT a real case result). `source_en.txt` is a fabricated mini-paper about perovskite
> solar cells written only to exercise this skill; the numbers and claims are invented.
> `pairs_good.jsonl` / `pairs_bad.jsonl` are hand-written synthetic translations —
> `pairs_bad.jsonl` contains **two deliberate terminology violations** for testing.

## Data

| file | content |
|---|---|
| `data/source_en.txt` | synthetic EN mini-paper (title + Abstract + Introduction + Figure 1 caption + Conclusion, 15 content lines). Terms used: `perovskite solar cell (PSC)`, `power conversion efficiency (PCE)`, `charge transport layer`, `open-circuit voltage` — each appears in ≥3 sections. |
| `data/pairs_good.jsonl` | 15 bilingual segments (S001–S015, sections title/abstract/body/caption/conclusion) with locked renderings used **everywhere**: PSC→钙钛矿太阳能电池, PCE→光电转换效率, charge transport layer→电荷传输层, open-circuit voltage→开路电压 |
| `data/pairs_bad.jsonl` | identical to good **except**: S014 (caption) renders PSC as 钙钛矿电池; S015 (conclusion) renders PCE as 能量转换效率 — two deliberate term-drift violations |

## Commands (run from `examples/`)

```bash
SKILL=..   # path to the skill root

# 1. extract candidate terms
python3 $SKILL/scripts/extract_terms.py --src data/source_en.txt --out /tmp/tg/termbase_draft.json

# 2. write translations (normally done by the agent reading the draft)
cat > /tmp/tg/translations.json <<'EOF'
{
  "perovskite solar cell": "钙钛矿太阳能电池",
  "power conversion efficiency": "光电转换效率",
  "charge transport layer": "电荷传输层",
  "open-circuit voltage": "开路电压"
}
EOF

# 3. lock the termbase
python3 $SKILL/scripts/lock_termbase.py --draft /tmp/tg/termbase_draft.json \
    --translations /tmp/tg/translations.json --out /tmp/tg/termbase.locked.json

# 4a. audit the consistent translation  -> EXPECT exit 0
python3 $SKILL/scripts/audit_translation.py --termbase /tmp/tg/termbase.locked.json \
    --pairs data/pairs_good.jsonl --out /tmp/tg/audit_good.json --md /tmp/tg/audit_good.md
echo "good exit: $?"     # 0

# 4b. audit the drifted translation     -> EXPECT exit 1, exactly 2 violations
python3 $SKILL/scripts/audit_translation.py --termbase /tmp/tg/termbase.locked.json \
    --pairs data/pairs_bad.jsonl --out /tmp/tg/audit_bad.json
echo "bad exit: $?"      # 1

# 5. secure a result.json first (runtime contract habit)
cat > /tmp/tg/case.json <<'EOF'
{"case_id": "synthetic-demo-000", "output_contract": {"zh_title": "", "audit_summary": ""}}
EOF
python3 $SKILL/scripts/make_result.py --case /tmp/tg/case.json \
    --out /tmp/tg/result.json --status partial --note "placeholder secured"
```

## Expected outcomes

- **Step 1** prints 4 candidate entries: `Perovskite solar cell [PSC]`,
  `Power conversion efficiency [PCE]`, `Charge Transport Layer`, `Open-Circuit Voltage`.
- **Step 4a (good)**: `violations: 0`, **exit code 0**; every coverage row ✅ across
  title/abstract/body/caption/conclusion.
- **Step 4b (bad)**: **exit code 1** with **exactly 2 violations**, both `term-drift`:
  - `S014 (caption)`: `perovskite solar cell` expected `钙钛矿太阳能电池` (found 钙钛矿电池)
  - `S015 (conclusion)`: `power conversion efficiency` expected `光电转换效率` (found 能量转换效率)
- **Step 5**: `result.json` created with `case_id`, both contract fields (empty),
  `status: partial`, and a one-item `change_record`.

Negative control (optional): delete one key from `translations.json` and re-run step 3 —
`lock_termbase.py` must **exit 1** listing the uncovered entry; adding `--allow-partial`
makes it exit 0 with `status: partial`.
