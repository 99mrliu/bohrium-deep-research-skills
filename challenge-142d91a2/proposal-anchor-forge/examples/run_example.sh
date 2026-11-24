#!/usr/bin/env bash
# 合成示例端到端演示（非正式案例结果）：
#   契约 init -> 锚点抽取+QC -> 台账核验(演示拦截) -> 诚实 partial 收尾
# 注：curated_fact_ledger.jsonl / curated_proposal_draft.md 在真实运行中由 Agent
#     精读锚定文本产出；本示例为演示机器管线而预制，标注为合成示例。
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL="$(dirname "$HERE")"
WORK="$HERE/work"
OUT="$HERE/expected"
rm -rf "$WORK"
mkdir -p "$WORK" "$OUT"

echo "== 步骤 0: 读契约, 写 partial result.json =="
python3 "$SKILL/scripts/result_forge.py" init "$HERE/input/case.json" "$OUT/result.json" \
  --note "synthetic example run: contract read; extraction pending"

echo "== 步骤 1: 锚点抽取 + QC =="
python3 "$SKILL/scripts/anchor_extract.py" "$HERE/input" "$WORK/anchors"
cp "$WORK/anchors/anchor_map.jsonl" "$WORK/anchors/manifest.json" "$OUT/"

echo "== 步骤 2: (合成) 使用预制台账与草稿代替 Agent 起草 =="
cp "$HERE/curated_fact_ledger.jsonl" "$OUT/fact_ledger_full.jsonl"
cp "$HERE/curated_proposal_draft.md" "$OUT/proposal_draft.md"

echo "== 步骤 3: 机器核验论断台账 (预期拦截 C007/C008, 退出码 1) =="
VERIFY_RC=0
python3 "$SKILL/scripts/verify_claims.py" "$WORK/anchors/anchor_map.jsonl" \
  "$HERE/curated_fact_ledger.jsonl" "$OUT/claim_verification.json" \
  --accepted "$OUT/fact_ledger.jsonl" || VERIFY_RC=$?
if [ "$VERIFY_RC" -ne 0 ]; then
  echo "[门控生效] 核验未全部通过 (rc=$VERIFY_RC): fail/unverifiable 论断禁止进入交付稿"
fi

echo "== 步骤 4: 收尾 —— 请求 ok, 但核验门强制降级为诚实 partial =="
python3 "$SKILL/scripts/result_forge.py" final "$HERE/input/case.json" "$OUT/result.json" \
  --status ok --verification "$OUT/claim_verification.json" \
  --set proposal_draft='"proposal_draft.md"' \
  --set fact_ledger='"fact_ledger.jsonl"' \
  --set claim_verification='"claim_verification.json"' \
  --set schedule='"见 proposal_draft.md 第 5 节阶段计划（M1–M24，受 case.json 24 个月约束）"' \
  --set risk_register='"见 proposal_draft.md 第 6 节风险登记表（触发信号 + 备选方案）"' \
  --note "synthetic example: 演示 fail/unverifiable 拦截与强制 partial"

echo "== expected/ 产物 =="
ls -1 "$OUT"
echo "== contract_audit / verification_audit =="
python3 -c "
import json
doc = json.load(open('$OUT/result.json'))
print(json.dumps({'status': doc['status'],
                  'contract_audit': doc['contract_audit'],
                  'verification_audit': doc.get('verification_audit')},
                 ensure_ascii=False, indent=2))
"
