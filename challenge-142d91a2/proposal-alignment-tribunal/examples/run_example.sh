#!/usr/bin/env bash
# 合成示例端到端演示（非正式案例结果）：
#   契约播种 -> 对齐裁定（演示三类 fail 拦截）-> 组装 result -> final 收尾（强制 partial）
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL="$(dirname "$HERE")"
WORK="$HERE/work"
OUT="$HERE/expected"
rm -rf "$WORK"
mkdir -p "$WORK" "$OUT"

# 步骤 0：读契约，播种有效 partial result.json
python3 "$SKILL/scripts/contract_result.py" init "$HERE/input/case.json" "$WORK/result.json"

# 步骤 3：对齐裁定。预制矩阵故意含三处违例（OBJ2 无 VAL、STEP4 孤儿、RSK2 缺触发信号），
# 预期退出码 1；报告照常归档。
set +e
python3 "$SKILL/scripts/alignment_check.py" "$HERE/curated/alignment_matrix.json" "$OUT/alignment_report.json"
CHECK_RC=$?
set -e
echo "alignment_check exit code: $CHECK_RC (预期 1，演示三类 fail 拦截)"

# 步骤 4：按矩阵执笔 + 组装契约字段（真实运行中由 Agent 完成，此处用 curated 制品演示）
python3 - "$WORK/result.json" "$HERE/curated" "$OUT/alignment_report.json" <<'PY'
import json
import sys

res_path, curated, report_path = sys.argv[1:4]
with open(res_path, encoding='utf-8') as f:
    res = json.load(f)
with open(curated + '/proposal_draft.md', encoding='utf-8') as f:
    res['proposal_draft'] = f.read()
with open(curated + '/alignment_matrix.json', encoding='utf-8') as f:
    matrix = json.load(f)
res['alignment_matrix'] = matrix
with open(curated + '/fact_source_map.json', encoding='utf-8') as f:
    res['fact_source_map'] = json.load(f)
res['risk_register'] = [
    {'id': r.get('id'), 'affects': r.get('affects'),
     'trigger_signal': r.get('trigger_signal'),
     'fallback': r.get('fallback'),
     'decision_point': r.get('decision_point')}
    for r in matrix.get('risks', [])]
with open(report_path, encoding='utf-8') as f:
    res['verification_report'] = json.load(f)
res['sources'] = ['input/prior_survey_2023.csv（合成前期数据）',
                  'curated/fact_source_map.json（合成证据映射）']
res['uncertainty'] = [u for u in res.get('uncertainty', [])
                      if '待填充' not in u]
res['change_records'].append(
    {'event': 'fill',
     'detail': '按 curated 矩阵执笔初稿；对齐裁定 gate_pass=false，保持 partial 待修复'})
with open(res_path, 'w', encoding='utf-8') as f:
    json.dump(res, f, ensure_ascii=False, indent=2)
PY

# 步骤 5：final 收尾。verification_report.gate_pass=false -> 强制 partial（预期退出码 1）
set +e
python3 "$SKILL/scripts/contract_result.py" final "$HERE/input/case.json" "$WORK/result.json"
FINAL_RC=$?
set -e
echo "contract_result final exit code: $FINAL_RC (预期 1，诚实 partial)"

cp "$WORK/result.json" "$OUT/result.json"
echo "示例完成：产物已写入 $OUT"
