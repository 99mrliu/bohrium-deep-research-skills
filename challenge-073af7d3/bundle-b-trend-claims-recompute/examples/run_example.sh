#!/usr/bin/env bash
# run_example.sh -- 在合成语料上跑完整管道并证明审计器能抓出植入的错误主张。
# 数据全部为合成（synthetic / 合成），植入：2018 速率变点、2014 单年尖峰、2025 右删失。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS="$HERE/../scripts"
CASE_DIR="$HERE/synthetic_case"
OUT="$HERE/example_output"
WORK="$HERE/.work_example"

# 固定路径清理（仅本目录内的已知子路径）
[ -n "$OUT" ] && [ -n "$WORK" ] && rm -rf "$OUT" "$WORK"
mkdir -p "$OUT/good" "$OUT/bad" "$WORK"

echo "== 1) build_corpus =="
python3 "$SCRIPTS/build_corpus.py" --work "$WORK" --inputs "$CASE_DIR/corpus.jsonl"

echo "== 2) slice_stats =="
python3 "$SCRIPTS/slice_stats.py" --work "$WORK"

echo "== 3) changepoint =="
python3 "$SCRIPTS/changepoint.py" --work "$WORK"

echo "== 4) GOOD claims: claim_audit (expect exit 0) =="
python3 "$SCRIPTS/claim_audit.py" --work "$WORK" --claims "$CASE_DIR/claims_good.json"
cp "$WORK/canon.jsonl" "$WORK/corpus_meta.json" "$WORK/slices.json" "$WORK/slices.csv" \
   "$WORK/changepoints.json" "$WORK/claim_audit.json" "$OUT/good/"
echo "PROOF good-run: claim_audit exit 0（与植入真值一致的主张全部通过）"

echo "== 5) BAD claims: claim_audit (expect exit 1) =="
set +e
python3 "$SCRIPTS/claim_audit.py" --work "$WORK" --claims "$CASE_DIR/claims_bad.json" \
  > "$OUT/bad/claim_audit_stdout.txt" 2>&1
rc=$?
set -e
cp "$WORK/claim_audit.json" "$OUT/bad/"
if [ "$rc" -ne 1 ]; then
  echo "FAIL: bad-run exit code = $rc, expected 1" >&2
  exit 1
fi
echo "PROOF bad-run: claim_audit exit 1（矛盾主张被拒绝）"

# 断言四种植入违规全部触发
python3 - "$OUT/bad/claim_audit.json" <<'PYEOF'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    audit = json.load(f)
found = {v for verdict in audit["verdicts"] for v in verdict["violations"]}
expected = {"censored_year_as_decline", "fluctuation_as_inflection",
            "unsupported_changepoint", "direction_mismatch"}
missing = expected - found
if missing:
    print("FAIL: missing violation types: %s" % sorted(missing))
    sys.exit(1)
for verdict in audit["verdicts"]:
    print("PROOF violation: %s -> %s" % (verdict["claim_id"], verdict["violations"]))
print("PROOF violation-types: all 4 planted types fired: %s" % sorted(found))
PYEOF

# 断言 2018 变点被支持（CI 排除 1）且 2014 被列为波动
python3 - "$OUT/good/changepoints.json" <<'PYEOF'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    cp = json.load(f)
cand = {c["tau"]: c for c in cp["candidates"]}
c18 = cand.get(2018)
assert c18 and c18["supported"] and c18["ci95_lo"] > 1, "2018 changepoint not supported!"
assert cp["adopted_tau"] == 2018, "adopted_tau != 2018: %r" % cp["adopted_tau"]
fluct_years = {f["year"] for f in cp["fluctuations"]}
assert 2014 in fluct_years, "2014 not flagged as fluctuation!"
print("PROOF changepoint-2018: adopted, rate_ratio=%.3f CI=[%.3f, %.3f] ll_gain=%.3f"
      % (c18["rate_ratio"], c18["ci95_lo"], c18["ci95_hi"], c18["ll_gain"]))
print("PROOF fluctuation-2014: z=%.3f (|z|>=2 -> 单年尖峰=波动候选)"
      % next(f["z"] for f in cp["fluctuations"] if f["year"] == 2014))
PYEOF

# 断言 2025 被判右删失
python3 - "$OUT/good/slices.json" <<'PYEOF'
import json, sys
with open(sys.argv[1], encoding="utf-8") as f:
    sl = json.load(f)
assert sl["partial_year_suspect"] is True, "2025 not flagged as partial-year suspect!"
print("PROOF censoring-2025: partial_year_suspect=true, final_count=%d, threshold=%s"
      % (sl["censoring"]["final_count"], sl["censoring"]["threshold"]))
PYEOF

rm -rf "$WORK"
echo "ALL CHECKS PASSED -> artifacts in $OUT/{good,bad}"
